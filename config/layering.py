"""Environment-specific configuration layering with hard-fail enforcement.

Loads YAML configs from config/environments/ and layers them:
base.yaml → {local,production,staging}.yaml

Fails startup if production/staging config is missing in non-local mode.
"""

import os
from pathlib import Path

import yaml

ENVIRONMENTS_DIR = Path(__file__).parent / "environments"
DEFAULT_ENVIRONMENT = "local"


def _get_environment() -> str:
    """Get the active environment from LEDGERLENS_ENV or default to local."""
    return os.getenv("LEDGERLENS_ENV", DEFAULT_ENVIRONMENT).lower()


def _load_yaml_file(path: Path) -> dict:
    """Load YAML file, return empty dict if missing."""
    if not path.exists():
        return {}
    with open(path) as f:
        content = yaml.safe_load(f)
    return content or {}


def _merge_configs(base: dict, overlay: dict) -> dict:
    """Deep merge overlay into base config."""
    result = base.copy()
    for key, value in overlay.items():
        if isinstance(value, dict) and key in result:
            result[key] = _merge_configs(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict:
    """Load layered configuration with hard-fail for missing prod/staging configs.

    Returns:
        Merged configuration dictionary

    Raises:
        RuntimeError: If production/staging config file is missing
    """
    env = _get_environment()

    if env not in ("local", "production", "staging"):
        raise ValueError(
            f"Invalid LEDGERLENS_ENV={env!r}. "
            "Must be 'local', 'production', or 'staging'."
        )

    base_path = ENVIRONMENTS_DIR / "base.yaml"
    env_path = ENVIRONMENTS_DIR / f"{env}.yaml"

    if not base_path.exists():
        raise RuntimeError(f"Missing base config: {base_path}")

    if env != "local" and not env_path.exists():
        raise RuntimeError(
            f"LEDGERLENS_ENV={env} requires {env_path} to exist. "
            "Fail-closed: refusing to run in {env} mode without explicit config. "
            "Create {env_path} or set LEDGERLENS_ENV=local."
        )

    base_config = _load_yaml_file(base_path)
    env_config = _load_yaml_file(env_path)

    config = _merge_configs(base_config, env_config)

    if env != "local":
        _validate_production_config(config, env)

    return config


def _validate_production_config(config: dict, env: str) -> None:
    """Validate that production/staging has required hardened settings.

    Args:
        config: Loaded configuration
        env: Environment name (production or staging)

    Raises:
        RuntimeError: If required production settings are missing
    """
    required_fields = [
        ("database.url", "Database URL must be set in production"),
        ("database.require_tls", "TLS must be required in production"),
        ("logging.format", "Logging format must be JSON in production"),
        ("security.enable_query_audit", "Query auditing must be enabled"),
    ]

    for path, message in required_fields:
        parts = path.split(".")
        value = config
        for part in parts:
            value = value.get(part, {}) if isinstance(value, dict) else {}
        if not value:
            raise RuntimeError(f"{env} config error: {message}")
