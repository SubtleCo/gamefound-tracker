.PHONY: fetch build deploy setup-new

fetch:
	@test -n "$(PROJECT)" || (echo "usage: make fetch PROJECT=<gamefound-url-name>" >&2; exit 1)
	python3 export_csv.py $(PROJECT)

build:
	sam build

# Deploy an update to an already-deployed project's stack.
deploy: build
	@test -n "$(PROJECT)" || (echo "usage: make deploy PROJECT=<gamefound-url-name>" >&2; exit 1)
	sam deploy --config-env $(PROJECT)

# First-time deploy for a new campaign: walks through `sam deploy --guided`
# and saves the answers as a new named environment in samconfig.toml, so
# future `make deploy PROJECT=...` / `make fetch PROJECT=...` just work.
setup-new: build
	@test -n "$(PROJECT)" || (echo "usage: make setup-new PROJECT=<gamefound-url-name>" >&2; exit 1)
	sam deploy --guided \
		--config-env $(PROJECT) \
		--stack-name $(PROJECT)-data-fetch \
		--parameter-overrides Project=$(PROJECT)
