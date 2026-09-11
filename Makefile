.PHONY: lint-all test-all lint-js lint-py lint-rust test-js test-py test-rust

lint-all: lint-js lint-py lint-rust

test-all: test-js test-py test-rust

lint-js:
	pnpm -r --if-present run lint

lint-py:
	uv run ruff check .

lint-rust:
	cd contracts/soroban && cargo fmt --all -- --check && cargo clippy --workspace --all-targets --all-features -- -D warnings

test-js:
	pnpm -r --if-present run test

test-py:
	uv run pytest

test-rust:
	cd contracts/soroban && cargo test --workspace
