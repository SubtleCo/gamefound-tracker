# gamefound-tracker

Tracks [Gamefound](https://gamefound.com) crowdfunding campaigns over time:
a Lambda snapshots a campaign's public API into S3 every 5 minutes, and a
[live dashboard](docs/index.html) (published via GitHub Pages) charts
funding, backers, and comments as they come in. The dashboard's compare
view can also overlay any campaign - including ones we never tracked
ourselves, backfilled from third-party data - normalized by percent of
campaign elapsed, with checkboxes to pick which ones to show.

The stack is generic - one CloudFormation template, parameterized by
`Project` (the Gamefound `urlName`, e.g. `tend-expansions` for
`gamefound.com/projects/tend-expansions`). Each campaign you track gets
its own independent stack, deployed from this same template.

## How it works

- **`AlteraFetchFunction`** (Lambda, `lambda/handler.py`) - runs every 5
  minutes via an EventBridge schedule, hits
  `https://gamefound.com/api/public/projects/getCrowdfundingProject?urlName=<Project>`,
  and writes two things to S3:
  - the raw JSON response, archived at `<Project>/<yyyy>/<mm>/<dd>/<hh>-<mm>.json`
  - `<Project>/history.json`, an aggregate array of every snapshot
    (`{datetime, backerCount, commentCount, fundsGathered}`), read-modified-written
    on every run
- **`AlteraDataBucket`** (S3) - stores both. `DeletionPolicy: Retain`, so
  deleting the stack never deletes the data. Only `<Project>/history.json`
  is publicly readable (via a bucket policy scoped to that exact key, plus
  a CORS rule allowing `GET`) - that's what the dashboard fetches directly
  from the browser. The raw per-snapshot archive stays private.
- **`docs/index.html`** - the dashboard, served by GitHub Pages from this
  repo's `/docs` folder. For a **live** project it fetches the public
  `history.json` URL directly and re-polls it every 60 seconds. For an
  **archived** project (a campaign that's over and will never update
  again) it instead reads a static JSON file bundled into `docs/data/`,
  committed once and never touched again - no need to keep AWS
  infrastructure running for data that can't change.
- **`export_csv.py`** - run locally, pulls a project's `history.json` and
  writes `<project>.csv` / `<project>_chart.csv` for ad hoc analysis
  outside the dashboard.

> The logical resource names (`AlteraFetchFunction`, `AlteraDataBucket`)
> are legacy - kept as-is so updating an existing stack never replaces
> its bucket. They're internal CloudFormation IDs only; they don't affect
> what a new project's stack does or is named.

## Prerequisites

- AWS credentials configured locally - `aws configure` or an SSO login,
  whatever you already use with `sam`/`aws`.
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- Python 3 with `boto3` installed
- [GitHub CLI](https://cli.github.com/) (`gh`), already authenticated, if
  you're setting up Pages for the first time

## Tracking a new campaign

```
make setup-new PROJECT=<gamefound-url-name>
```

This builds the Lambda and runs `sam deploy --guided`, prompting you
through a one-time deploy that creates a brand-new stack named
`<project>-data-fetch` and saves your answers as a named environment in
`samconfig.toml` (gitignored - it's per-machine deploy state, not
checked in).

`<gamefound-url-name>` is the slug from the campaign's URL - for
`gamefound.com/projects/foo`, that's `foo`.

Once deployed, snapshots start on their own every 5 minutes. To put it
on the dashboard while it's still running, add an entry to the
`PROJECTS` array in `docs/index.html`:

```js
{ id: '<project>', label: '<Display Name>', status: 'live', url: '<PublicHistoryUrl output>' }
```

`PublicHistoryUrl` is a stack output - `aws cloudformation describe-stacks
--stack-name <project>-data-fetch --query "Stacks[0].Outputs"` prints it,
or watch it scroll by in the `sam deploy` output.

## When a campaign ends

Don't leave the stack (and its 5-minute schedule) running forever for
numbers that will never change again. Instead, freeze it once:

```
make fetch PROJECT=<project>          # writes <project>.json locally
cp <project>.json docs/data/<project>.json
```

Then flip its `docs/index.html` entry to `status: 'archived'` and point
`url` at `data/<project>.json`. The stack itself can stay running or be
torn down separately - the dashboard no longer depends on it either way.

## Adding a campaign we never tracked ourselves

Every campaign in `PROJECTS` besides Altera and Tend Expansions was
never run through our own Lambda - their data comes entirely from
[tabletopanalytics.com](https://www.tabletopanalytics.com), which embeds
daily funds/backers/comments series right in each project's page (a
`jquery.flot` chart, data inlined as a JS array - no API, just fetch the
page and regex it out). Backers/comments there are daily *deltas*, not
running totals, so they need summing into cumulative counts before they
match our schema.

Two honest limits on this data: it's **daily** resolution (vs. our own
hourly/5-minute data), and there's **no independent way to validate
it** the way Altera's backfill was cross-checked against our own real
snapshots - it's trust-the-third-party-site for anything we didn't
track ourselves. Sanity-check monotonicity (funds/backers should only
occasionally dip, from failed pledges - a big or frequent drop means
something's wrong) and cross-reference the final totals against the
project's own summary stats before trusting a new one.

Each entry in `PROJECTS` needs: `campaignStart`/`campaignEnd` (here,
just the first/last data point's own timestamp - there's no Gamefound
API to pull an authoritative campaign date from for a Kickstarter
project), a `platformUrl` (wherever the campaign actually ran), and a
`color` (a plain hex value works for these - `colorVar` is reserved for
the two hand-tuned, theme-aware colors on Altera/Tend Expansions).

## Day to day

```
make deploy PROJECT=<name>   # push a code/template change to an existing stack
make fetch  PROJECT=<name>   # pull history.json -> <name>.csv, <name>_chart.csv
```

## Publishing the dashboard

The dashboard lives at `docs/index.html` with no build step - GitHub
Pages serves it as-is. One-time setup for a new repo:

```
gh repo create <you>/gamefound-tracker --public --source=. --push
gh api -X POST repos/<you>/gamefound-tracker/pages -f source[branch]=main -f source[path]=/docs
```

After that, any commit to `main` that touches `docs/` republishes
automatically - no further steps.

## What AWS you need for a new campaign

Nothing to provision by hand - `make setup-new` creates everything
through the same CloudFormation stack shape, in your existing AWS
account:

- 1 S3 bucket (snapshot archive + public `history.json`, retained on stack delete)
- 1 Lambda function
- 1 EventBridge (CloudWatch Events) rule, 5-minute schedule
- 1 IAM execution role for the Lambda (S3 get/put on its own bucket + CloudWatch Logs)
- 1 CloudWatch Logs log group
- 1 S3 bucket policy + CORS rule, making exactly one object
  (`<Project>/history.json`) public so the dashboard can fetch it from
  the browser - everything else in the bucket stays private

No new IAM users or API keys - just the AWS credentials you already use
for `sam`/`aws` locally, with permission to create CloudFormation
stacks, S3 buckets/policies, Lambda functions, IAM roles, EventBridge
rules, and log groups.
