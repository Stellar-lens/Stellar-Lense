.PHONY: lint-all test-all lint-js lint-py lint-rust test-js test-py test-rust

lint-all: lint-js lint-py lint-rust

test-all: test-js test-py test-rust

lint-js:
	pnpm -r --if-present run lint

lint-py:
	# uvx, not `uv run`: ruff is a standalone tool with no project deps of its
	# own, and `uv run ruff` from the workspace root (no root [project])
	# would need a --package. uvx installs just ruff, isolated.
	#
	# Pinned, not floating: neither packages/core nor apps/api pins a
	# `select` list in [tool.ruff.lint], so both rely on ruff's *default*
	# rule set - and that default grows between versions (0.4.10 -> 0.16.7
	# added ~800 newly-enabled rules). An unpinned `uvx ruff` would silently
	# rerun the code against rules nobody has triaged. Bump deliberately,
	# together with any fixes the new version asks for.
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
	# including nested packages that aren't workspace members - producing import collisions
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
