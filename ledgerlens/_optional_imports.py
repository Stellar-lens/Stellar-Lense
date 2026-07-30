"""ledgerlens._optional_imports
================================
Lazy-import helpers for optional heavy dependencies.

Each helper raises ``ImportError`` with a precise ``pip install`` command when
the dependency is absent, so contributors and users get an *actionable* message
instead of a generic ModuleNotFoundError.

Usage pattern (module-level guard)::

    from ledgerlens._optional_imports import require_torch, HAS_TORCH
    if not HAS_TORCH:
        raise ImportError(require_torch("detection/temporal_model.py"))

Usage pattern (function-level guard)::

    def train_gnn(...):
        torch = require_torch("detection/gnn_model.py")   # returns the module
        ...

For try/except patterns already in the codebase (e.g. gnn_ring_detector.py),
the ``HAS_*`` sentinels exported from this module can be used to short-circuit
at the module level without re-importing.
"""

from __future__ import annotations

import importlib
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Availability sentinels
# ---------------------------------------------------------------------------

def _available(module: str) -> bool:
    """Return True when *module* can be imported without side-effects."""
    return importlib.util.find_spec(module) is not None  # type: ignore[attr-defined]


HAS_TORCH: bool = _available("torch")
HAS_TORCH_GEOMETRIC: bool = _available("torch_geometric")
HAS_WEB3: bool = _available("web3")
HAS_MLFLOW: bool = _available("mlflow")
HAS_DOWHY: bool = _available("dowhy")
HAS_ATHERIS: bool = _available("atheris")
HAS_KUBERNETES: bool = _available("kubernetes")
HAS_STRAWBERRY: bool = _available("strawberry")
HAS_DP_ACCOUNTING: bool = _available("dp_accounting")

# ---------------------------------------------------------------------------
# Actionable install messages
# ---------------------------------------------------------------------------

_EXTRAS: dict[str, str] = {
    "torch":           "ml",
    "torch_geometric": "ml",
    "web3":            "chain",
    "mlflow":          "ml",
    "dowhy":           "causal",
    "atheris":         "fuzz",
    "kubernetes":      "chain",
    "strawberry":      "graphql",
    "dp_accounting":   "federated",
}

_PYPI_NAMES: dict[str, str] = {
    "torch_geometric": "torch-geometric",
    "dp_accounting":   "dp-accounting",
}


def _install_hint(package: str, caller: str = "") -> str:
    extra = _EXTRAS.get(package, package)
    pypi = _PYPI_NAMES.get(package, package.replace("_", "-"))
    location = f" (imported by {caller})" if caller else ""
    return (
        f"Optional dependency '{pypi}' is not installed{location}.\n"
        f"  Install the '{extra}' extra:  pip install 'ledgerlens-core[{extra}]'\n"
        f"  Or install directly:          pip install {pypi}"
    )


# ---------------------------------------------------------------------------
# Require helpers — return the module or raise ImportError
# ---------------------------------------------------------------------------

def require_torch(caller: str = "") -> Any:
    """Return the ``torch`` module, raising ImportError with install hint if absent."""
    if not HAS_TORCH:
        raise ImportError(_install_hint("torch", caller))
    import torch  # noqa: PLC0415
    return torch


def require_torch_geometric(caller: str = "") -> Any:
    """Return ``torch_geometric``, raising ImportError with install hint if absent."""
    if not HAS_TORCH_GEOMETRIC:
        raise ImportError(_install_hint("torch_geometric", caller))
    import torch_geometric  # noqa: PLC0415
    return torch_geometric


def require_web3(caller: str = "") -> Any:
    """Return the ``web3`` module, raising ImportError with install hint if absent."""
    if not HAS_WEB3:
        raise ImportError(_install_hint("web3", caller))
    import web3  # noqa: PLC0415
    return web3


def require_mlflow(caller: str = "") -> Any:
    """Return the ``mlflow`` module, raising ImportError with install hint if absent."""
    if not HAS_MLFLOW:
        raise ImportError(_install_hint("mlflow", caller))
    import mlflow  # noqa: PLC0415
    return mlflow


def require_dowhy(caller: str = "") -> Any:
    """Return the ``dowhy`` module, raising ImportError with install hint if absent."""
    if not HAS_DOWHY:
        raise ImportError(_install_hint("dowhy", caller))
    import dowhy  # noqa: PLC0415
    return dowhy


def require_kubernetes(caller: str = "") -> Any:
    """Return the ``kubernetes`` module, raising ImportError with install hint if absent."""
    if not HAS_KUBERNETES:
        raise ImportError(_install_hint("kubernetes", caller))
    import kubernetes  # noqa: PLC0415
    return kubernetes


def require_strawberry(caller: str = "") -> Any:
    """Return the ``strawberry`` module, raising ImportError with install hint if absent."""
    if not HAS_STRAWBERRY:
        raise ImportError(_install_hint("strawberry", caller))
    import strawberry  # noqa: PLC0415
    return strawberry


def require_dp_accounting(caller: str = "") -> Any:
    """Return the ``dp_accounting`` module, raising ImportError with install hint if absent."""
    if not HAS_DP_ACCOUNTING:
        raise ImportError(_install_hint("dp_accounting", caller))
    import dp_accounting  # noqa: PLC0415
    return dp_accounting
