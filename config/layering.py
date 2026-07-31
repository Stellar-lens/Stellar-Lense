"""Advanced configuration layering for local and CI environments.

`config.py` reads flat settings directly from environment variables with
inline defaults, which works well for a single deployment target but makes
it hard to answer two recurring questions:

- "What's actually different between how this runs locally vs. in CI?"
- "Why is this setting the value it is right now?"

`LayeredConfig` resolves settings from an explicit, ordered stack of layers
and remembers which layer supplied each key's final value, so both
questions have a one-line answer (`.explain()`) instead of requiring a
diff of `.env` files or a grep through CI YAML.

Precedence (lowest to highest):
    1. `defaults`                          — hardcoded fallback values
    2. `<config_dir>/base.yaml`            — checked-in shared defaults
    3. `<config_dir>/{environment}.yaml`   — environment-specific overlay
       (e.g. local.yaml, ci.yaml, staging.yaml, production.yaml)
    4. environment variables               — `{env_prefix}{KEY}`
    5. `overrides`                         — explicit runtime overrides
       (tests, CLI flags)

This module is additive: it does not replace `config.py` or `Config`. It's
intended for new subsystems (or incremental migration) that want layered,
diagnosable configuration without redesigning the existing env-var-only
`Config` class.

Usage:
    from config.layering import LayeredConfig, detect_environment

    cfg = LayeredConfig(
        defaults={"log_level": "INFO", "db_pool_size": 5},
        environment=detect_environment(),
    )
    cfg.require("risk_score_db_url")
    print(cfg.explain())
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from utils.errors import ConfigurationError


class ConfigSource(str, Enum):
    DEFAULT = "default"
    BASE_FILE = "base_file"
    ENV_FILE = "env_file"
    ENV_VAR = "env_var"
    OVERRIDE = "override"


def detect_environment(env_var: str = "LEDGERLENS_ENV") -> str:
    """Infer the running environment name.

    Precedence: an explicit `{env_var}` wins; otherwise standard CI
    indicators (`CI`, `GITHUB_ACTIONS`) select `"ci"`; otherwise `"local"`.
    """
    explicit = os.getenv(env_var)
    if explicit:
        return explicit
    if os.getenv("CI") or os.getenv("GITHUB_ACTIONS"):
        return "ci"
    return "local"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ConfigurationError(
            "001",
            f"config file must contain a top-level mapping, got {type(data).__name__}",
            context={"path": str(path)},
            remediation="Ensure the YAML file's top level is `key: value` pairs, not a list or scalar.",
        )
    return data


def _coerce_like(reference: Any, raw: str) -> Any:
    """Coerce an environment-variable string into the type of `reference`."""
    if isinstance(reference, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(reference, int):
        return int(raw)
    if isinstance(reference, float):
        return float(raw)
    if isinstance(reference, list):
        return [v.strip() for v in raw.split(",") if v.strip()]
    return raw


class LayeredConfig:
    """Resolves configuration from layered sources with precedence and provenance."""

    def __init__(
        self,
        defaults: dict[str, Any],
        *,
        environment: str,
        config_dir: str | os.PathLike = "config/environments",
        env_prefix: str = "LEDGERLENS_",
        overrides: dict[str, Any] | None = None,
    ):
        self.environment = environment
        self.config_dir = Path(config_dir)
        self.env_prefix = env_prefix
        self._values: dict[str, Any] = {}
        self._sources: dict[str, ConfigSource] = {}

        self._apply_layer(defaults, ConfigSource.DEFAULT)
        self._apply_layer(_load_yaml(self.config_dir / "base.yaml"), ConfigSource.BASE_FILE)
        self._apply_layer(
            _load_yaml(self.config_dir / f"{environment}.yaml"), ConfigSource.ENV_FILE
        )
        self._apply_env_vars()
        if overrides:
            self._apply_layer(overrides, ConfigSource.OVERRIDE)

    def _apply_layer(self, layer: dict[str, Any], source: ConfigSource) -> None:
        for key, value in layer.items():
            self._values[key] = value
            self._sources[key] = source

    def _apply_env_vars(self) -> None:
        for env_key, raw_value in os.environ.items():
            if not env_key.startswith(self.env_prefix):
                continue
            config_key = env_key[len(self.env_prefix) :].lower()
            if config_key in self._values:
                reference = self._values[config_key]
                self._values[config_key] = _coerce_like(reference, raw_value)
            else:
                # Unknown keys are still accepted as raw strings — a follow-up
                # schema layer could reject unrecognised keys if that's desired.
                self._values[config_key] = raw_value
            self._sources[config_key] = ConfigSource.ENV_VAR

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self._values[key]

    def __contains__(self, key: str) -> bool:
        return key in self._values

    def source(self, key: str) -> ConfigSource | None:
        return self._sources.get(key)

    def as_dict(self) -> dict[str, Any]:
        return dict(self._values)

    def require(self, *keys: str) -> None:
        """Raise ConfigurationError listing every missing/empty required key at once.

        Batches all missing keys into a single error instead of failing on
        the first one — a misconfigured CI job is usually missing several
        related keys at once, and fixing them one failed run at a time is
        slow.
        """
        missing = [k for k in keys if self._values.get(k) in (None, "")]
        if missing:
            raise ConfigurationError(
                "002",
                f"missing required configuration keys for environment={self.environment!r}: "
                f"{', '.join(missing)}",
                context={"environment": self.environment, "missing_keys": missing},
                remediation=(
                    f"Set these via {self.env_prefix}<KEY> environment variables, or add "
                    f"them to {self.config_dir}/{self.environment}.yaml"
                ),
            )

    def explain(self) -> str:
        """Diagnostic dump of every resolved key, its value, and which layer set it."""
        lines = [f"LayeredConfig(environment={self.environment!r}):"]
        for key in sorted(self._values):
            lines.append(f"  {key} = {self._values[key]!r}  [{self._sources[key].value}]")
        return "\n".join(lines)
