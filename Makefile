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
	#
	# Pinned per-project, not floating: neither packages/core nor apps/api
	# pins a `select` list in [tool.ruff.lint], so both rely on ruff's
	# *default* rule set - and that default has grown enormously between
	# versions (0.4.10 -> 0.16.7 added ~800 newly-enabled rules: isort,
	# flake8-bugbear, pyupgrade, refurb, ruff-specific...). packages/core's
	# own original CI (packages/core/.github/workflows/ci.yml) pinned
	# `ruff==0.4.10` for exactly this reason; its per-file-ignores above were
	# curated against that version. An unpinned `uvx ruff` here silently
	# reran the whole codebase against ~800 rules nobody has ever triaged,
	# surfacing ~1250 findings that are new-rule noise, not regressions.
	# apps/api has no ruff config of its own but shares the same code
	# heritage and the same failure mode (verified: pinning collapses its
	# 42 latest-ruff findings, all in the same rule families, down to the
	# 1 real one) - pinned to match packages/core rather than left floating.
	#
	# data/pipelines is excluded here for the same reason test-py excludes
	# it above: standalone project, not a workspace member, own Makefile/CI
	# - see data/pipelines/README.md. Unlike the version-drift findings
	# above, its lint debt (159 findings even at its own lockfile-pinned
	# ruff==0.16.1, including genuine bugs like an undefined `logger` in
	# detection/forensic_report.py) is real and pre-existing; fixing it is
	# out of scope for this monorepo-consolidation pass.
	cd packages/core && uvx ruff@0.4.10 check .
	cd apps/api && uvx ruff@0.4.10 check .

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
	#
	# _TYPER_FORCE_DISABLE_TERMINAL=1 and COLUMNS are pinned: some CLI tests
	# assert on Typer/Rich --help output containing specific option names
	# as a plain substring. Typer's rich_utils.py computes a module-level
	# FORCE_TERMINAL constant once at import time as True if ANY of
	# GITHUB_ACTIONS, FORCE_COLOR, or PY_COLORS is set -- and GitHub
	# Actions sets GITHUB_ACTIONS=true unconditionally on every run, so
	# clearing FORCE_COLOR alone (tried first; still failed in CI) can
	# never disable it there. With FORCE_TERMINAL true, Typer's Console
	# emits ANSI styling for --help even though CliRunner's captured
	# stream isn't a real terminal, and its highlighter wraps an option's
	# leading "--" in its own SGR span separately from the rest (e.g.
	# "--start" becomes two escape-delimited fragments), breaking a plain
	# `"--start" in result.output` check even though exit_code stays 0.
	# _TYPER_FORCE_DISABLE_TERMINAL is the escape hatch typer itself
	# provides: it forces FORCE_TERMINAL back to False regardless of
	# GITHUB_ACTIONS/FORCE_COLOR/PY_COLORS. Confirmed locally by setting
	# GITHUB_ACTIONS=true (reproducing the exact CI condition) both with
	# and without this variable.
	_TYPER_FORCE_DISABLE_TERMINAL=1 COLUMNS=200 uv run --package stellar-lense-core --extra test pytest packages/core/tests
	_TYPER_FORCE_DISABLE_TERMINAL=1 COLUMNS=200 uv run --package stellar-lense-api --extra test pytest apps/api/tests

test-rust:
	cd contracts/soroban && cargo test --workspace
