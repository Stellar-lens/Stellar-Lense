# Configuration Layering

## Overview

`config.py` reads flat settings directly from environment variables with
inline defaults — simple, but it makes two common questions hard to
answer: "what's actually different between local and CI?" and "why is this
setting the value it currently has?"

`config/layering.py` adds `LayeredConfig`, a small, additive capability
that resolves configuration from an explicit, ordered stack of layers and
records which layer supplied each key's final value.

Precedence (lowest to highest):

1. `defaults` — hardcoded fallback values passed by the caller
2. `config/environments/base.yaml` — checked-in shared defaults
3. `config/environments/{environment}.yaml` — environment-specific overlay
   (`local.yaml`, `ci.yaml`; add `staging.yaml`/`production.yaml` as needed)
4. `LEDGERLENS_*` environment variables
5. `overrides` — explicit runtime overrides (tests, CLI flags)

This module does not replace `config.Config` — it's for new subsystems (or
incremental migration) that want layered, diagnosable configuration without
redesigning the existing env-var-only settings class.

## Contract

- Missing YAML overlay files are tolerated (returns an empty layer) — an
  environment without its own overlay simply inherits `base.yaml`.
- A YAML file whose top level isn't a mapping raises `ConfigurationError`
  (`CFG-001`, from [[error_taxonomy]]) naming the offending path.
- Environment variables are coerced to match the *type* of the value
  already resolved for that key (bool/int/float/comma-list), so
  `LEDGERLENS_DB_POOL_SIZE=20` becomes `int(20)`, not the string `"20"`.
- `require(*keys)` batches every missing/empty required key into a single
  `ConfigurationError` (`CFG-002`) with a `missing_keys` list in `context`,
  instead of failing one key at a time across repeated CI runs.
- `.source(key)` and `.explain()` expose provenance for diagnostics.
- `detect_environment()` picks `LEDGERLENS_ENV` if set, else `"ci"` when
  `CI`/`GITHUB_ACTIONS` are present (matching the same signal
  `tests/conftest.py` already uses to select the Hypothesis profile), else
  `"local"`.

## Usage

```python
from config.layering import LayeredConfig, detect_environment

cfg = LayeredConfig(
    defaults={"log_level": "INFO", "db_pool_size": 5},
    environment=detect_environment(),
)
cfg.require("risk_score_db_url")
print(cfg.explain())
```

```
$ python -c "from config.layering import LayeredConfig, detect_environment; \
  print(LayeredConfig({'log_level': 'INFO'}, environment=detect_environment()).explain())"
LayeredConfig(environment='local'):
  db_max_overflow = 10  [base_file]
  db_pool_size = 5  [base_file]
  log_level = 'DEBUG'  [env_file]
  ...
```

## Validation

```
pytest tests/test_config_layering.py -v
```

Covers: default/base/env-file/env-var/override precedence in isolation and
combined, type coercion (int/bool/list) for env var overrides, unknown env
var keys, `require()` batching all missing keys, invalid YAML top-level
detection, `.explain()` output, `detect_environment()` precedence, and
tolerance of a missing environment overlay file.

## Design tradeoffs / follow-ups

- Config keys are flat strings (matching the flat style of the existing
  `Config` class), not nested. A follow-up could add dotted-key nesting
  (`db.pool_size`) if a subsystem needs it.
- No schema/type declarations beyond "coerce to match the default's type" —
  a follow-up could add per-key validators (e.g. a range check) alongside
  `require()`.
- `config/environments/{base,local,ci}.yaml` are illustrative starter
  overlays covering a handful of representative settings; expand them as
  subsystems adopt `LayeredConfig`.
