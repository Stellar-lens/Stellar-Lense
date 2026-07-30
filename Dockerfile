# ─── Builder stage ─────────────────────────────────────────────────────────
# Installs all build-time dependencies and compiles wheels.  Build tools
# (gcc, make, etc.) never reach the final image.
#
# Build targets:
#   docker build --target runtime .          ← default (base deps only)
#   docker build --target runtime-chain .    ← + EVM/chain deps (web3, k8s)
#   docker build --target runtime-ml .       ← + ML deps (mlflow, torch)
#   docker build --target dev .              ← all extras (local dev / CI)
FROM python:3.12-slim AS builder

# Pinned OS packages — update these in sync with security advisories
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy only manifest + lockfiles first so that the pip install layer is cached
# when source code changes but dependencies do not.
COPY pyproject.toml requirements/base.txt ./
COPY requirements/ requirements/

# Upgrade pip/wheel to a known-good version, then install from the committed
# lockfile.  --require-hashes is not used here because the base.txt files in
# this repo use >= constraints (to be solved by the developer's pip-compile run);
# for fully hermetic container builds, run `make lock` first and commit the
# hash-annotated output from pip-compile --generate-hashes.
RUN pip install --upgrade pip==24.0 wheel==0.43.0 && \
    pip install --no-cache-dir --prefix=/install -r requirements/base.txt

# ─── Builder-chain stage ────────────────────────────────────────────────────
FROM builder AS builder-chain

RUN pip install --no-cache-dir --prefix=/install -r requirements/chain.txt

# ─── Builder-ml stage ───────────────────────────────────────────────────────
FROM builder AS builder-ml

RUN pip install --no-cache-dir --prefix=/install -r requirements/ml.txt

# ─── Builder-dev stage ──────────────────────────────────────────────────────
FROM builder AS builder-dev

RUN pip install --no-cache-dir --prefix=/install -r requirements/dev.txt

# ─── Common runtime base ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime-base

ARG BUILD_VERSION="0.0.0"

LABEL org.opencontainers.image.title="ledgerlens-core"
LABEL org.opencontainers.image.description="Benford's Law + ensemble ML wash-trading detection engine"
LABEL org.opencontainers.image.version="${BUILD_VERSION}"
LABEL org.opencontainers.image.source="https://github.com/Ledger-Lenz/Ledgerlens-core"

RUN groupadd --gid 1000 ledgerlens && \
    useradd --uid 1000 --gid ledgerlens --shell /bin/bash --create-home ledgerlens

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/usr/local/bin:${PATH}"

COPY --chown=ledgerlens:ledgerlens . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

USER ledgerlens

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ─── Default runtime (base deps) ─────────────────────────────────────────────
FROM runtime-base AS runtime

COPY --from=builder /install /usr/local

# ─── Runtime with chain extras (EVM / kubernetes) ────────────────────────────
FROM runtime-base AS runtime-chain

COPY --from=builder-chain /install /usr/local

# ─── Runtime with ML extras (mlflow / torch) ─────────────────────────────────
FROM runtime-base AS runtime-ml

COPY --from=builder-ml /install /usr/local

# ─── Dev image (all extras + test/lint tools) ────────────────────────────────
FROM runtime-base AS dev

COPY --from=builder-dev /install /usr/local
