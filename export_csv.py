#!/usr/bin/env python3
"""Pull the aggregate history for a Gamefound project from S3 and write CSVs.

Usage: python3 export_csv.py <project>

<project> is the Gamefound urlName (also the stack's Project parameter).
The S3 bucket is looked up from the "<project>-data-fetch" stack's
BucketName output, so nothing here needs to be edited per-project. Data
comes from the single "<project>/history.json" aggregate the Lambda
maintains on every run (the same file a static site fetches publicly).
"""

import csv
import json
import sys
from datetime import datetime

import boto3

RAW_FIELDS = ["datetime", "backerCount", "commentCount", "fundsGathered"]
CHART_FIELDS = ["date", "time", "hourly_funds", "cumulative_funds_today"]


def stack_name(project):
    return f"{project}-data-fetch"


def bucket_for(project):
    cfn = boto3.client("cloudformation")
    stack = cfn.describe_stacks(StackName=stack_name(project))["Stacks"][0]
    for output in stack.get("Outputs", []):
        if output["OutputKey"] == "BucketName":
            return output["OutputValue"]
    raise RuntimeError(f"stack {stack_name(project)!r} has no BucketName output")


def fetch_rows(bucket, project):
    s3 = boto3.client("s3")
    body = s3.get_object(Bucket=bucket, Key=f"{project}/history.json")["Body"].read()
    rows = json.loads(body)
    for r in rows:
        r["datetime"] = datetime.fromisoformat(r["datetime"])
    rows.sort(key=lambda r: r["datetime"])
    return rows


def write_raw(rows, out_path):
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RAW_FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow({**r, "datetime": r["datetime"].isoformat()})
    print(f"wrote {len(rows)} rows to {out_path}")


def write_json(rows, out_path):
    data = [{**r, "datetime": r["datetime"].isoformat()} for r in rows]
    with open(out_path, "w") as f:
        json.dump(data, f)
    print(f"wrote {len(rows)} rows to {out_path}")


def write_chart(rows, out_path):
    chart_rows = []
    prev_funds = None
    prev_date = None
    daily_cumulative = 0.0

    for r in rows:
        dt = r["datetime"]
        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%H:%M")
        hourly = round(r["fundsGathered"] - prev_funds, 2) if prev_funds is not None else 0.0

        if date_str != prev_date:
            daily_cumulative = hourly
        else:
            daily_cumulative = round(daily_cumulative + hourly, 2)

        chart_rows.append({
            "date": date_str,
            "time": time_str,
            "hourly_funds": hourly,
            "cumulative_funds_today": daily_cumulative,
        })
        prev_funds = r["fundsGathered"]
        prev_date = date_str

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CHART_FIELDS)
        writer.writeheader()
        writer.writerows(chart_rows)
    print(f"wrote {len(chart_rows)} rows to {out_path}")


def main():
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <project>", file=sys.stderr)
        sys.exit(1)
    project = sys.argv[1]

    bucket = bucket_for(project)
    rows = fetch_rows(bucket, project)
    write_raw(rows, f"{project}.csv")
    write_chart(rows, f"{project}_chart.csv")
    write_json(rows, f"{project}.json")


if __name__ == "__main__":
    main()
