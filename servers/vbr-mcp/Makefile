.PHONY: q quality quality-check typecheck install i lock test env-example check-env-example docker-build

lock:
	- uv lock

upgrade:
	- uv lock --upgrade

install:
	- uv sync --all-groups

quality:
	uv run ruff format .
	uv run ruff check . --fix
	$(MAKE) typecheck

# Non-mutating counterpart of `quality`, for CI: `quality` rewrites files, which a
# CI job must never do - it would report success on code that was never committed.
quality-check:
	uv run ruff format --check .
	uv run ruff check .

typecheck:
	uv run --group test ty check .

env-example:
	uv run python scripts/update_env_example.py --settings-dir src/vbr_mcp --env-example-path .env.example

check-env-example:
	uv run python scripts/update_env_example.py --settings-dir src/vbr_mcp --env-example-path .env.example --check

test:
	uv run --group test pytest . --cov --junitxml=tests_results.xml

docker-build:
	docker build -f docker/Dockerfile -t vbr-mcp .

# Aliases
i: install
q: quality
