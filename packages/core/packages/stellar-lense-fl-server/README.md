# Stellar Lense Federated Learning Server

This is the standalone federated learning coordinator for Stellar Lense.
It was extracted from `stellar-lense-core` to enable independent deployment.

## Installation

```bash
pip install -e .
```

## Running the Server

```bash
python -m stellar_lense_fl_server
```

Configuration is handled via environment variables. See `config.py` for supported settings.
