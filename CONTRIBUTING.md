# Contributing to ledgerlens-data

Thanks for your interest in contributing to LedgerLens! This repo holds the
data ingestion and fraud-detection layer — see the README's
[Organization Map](README.md#organization-map) for how it fits with the
other LedgerLens repos.

## Development setup

```bash
git clone https://github.com/<org>/ledgerlens-data.git
cd ledgerlens-data
python -m venv .venv && source .venv/bin/activate
make install
cp .env.example .env  # then edit as needed
```

## Running checks locally

```bash
make lint     # ruff + black --check
make format   # ruff --fix + black
make test     # pytest
```

Optionally install the pre-commit hooks so checks run automatically:

```bash
pip install pre-commit
pre-commit install
```

## Pull requests

- Keep PRs focused on a single logical change.
- Add or update tests for any behavior change.
- Run `make lint` and `make test` before opening a PR — CI runs the same
  checks on Python 3.11 and 3.12.
- If you change a shared contract (`RiskScore` shape, asset pair ID format,
  feature schema — see the README's "Shared Contracts" section), call that
  out in the PR description so consuming repos (`ledgerlens-core`,
  `ledgerlens-api`, `ledgerlens-contract`, `ledgerlens-dashboard`) can be
  updated.

## Code style

- Formatting/linting is enforced by `ruff` and `black` (see
  `pyproject.toml`). Line length is 100.
- Favor small, composable functions following the existing module layout:
  `ingestion/` for data acquisition, `detection/` for scoring logic,
  `tests/` mirrors both.
- New feature columns added to `detection/feature_engineering.py` must be
  documented in the README's feature tables and accounted for in
  `detection/model_training.py::FEATURE_COLUMNS_EXCLUDE` handling.

## Reporting issues

Use the issue templates in `.github/ISSUE_TEMPLATE/`. Include the asset
pair, wallet, and time window if reporting a detection accuracy issue —
that's usually enough to reproduce a Benford/feature calculation locally.
