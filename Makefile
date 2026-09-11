.PHONY: lint-all test-all lint-js lint-py lint-rust test-js test-py test-rust

lint-all: lint-js lint-py lint-rust

test-all: test-js test-py test-rust

lint-js:
	pnpm -r --if-present run lint

lint-py:
	# uvx, not `uv run`: ruff is a standalone tool with no project deps of its
	# own. `uv run ruff` from the workspace root (no root [project]) needs a
	# --package, and packages/core's own "dev" extra (the one declaring ruff)
	# also pulls in atheris (fuzz), which fails to build on Python 3.12 - see
	# atheris#pybind11-precall-issue. uvx installs just ruff, isolated from
	# all of that.
	uvx ruff check .

lint-rust:
	cd contracts/soroban && cargo fmt --all -- --check && cargo clippy --workspace --all-targets --all-features -- -D warnings

test-js:
	pnpm -r --if-present run test

test-py:
	# Scoped per uv workspace member ([tool.uv.workspace] in /pyproject.toml:
	# packages/core, apps/api) rather than a bare `uv run pytest`, which at
	# the workspace root collects every tests/ dir it can find on disk -
	# including data/pipelines (not a workspace member; standalone venv,
	# out of scope here - see data/pipelines/README.md) and nested SDK
	# packages under packages/core/packages/ - producing import collisions
	# and ModuleNotFoundErrors unrelated to actual test failures.
	uv run --package stellar-lense-core --extra test pytest packages/core/tests
	uv run --package stellar-lense-api --extra test pytest apps/api/tests

test-rust:
	cd contracts/soroban && cargo test --workspace
