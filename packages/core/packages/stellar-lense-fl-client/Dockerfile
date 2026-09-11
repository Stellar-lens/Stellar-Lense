FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml .
COPY src ./src

RUN pip install --no-cache-dir build && \
    python -m build --wheel

FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir stellar-lense-fl-client==0.1.0 || true

COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl

ENV FL_SERVER_URL=https://fl.stellar-lense.io
ENV FL_API_KEY=""
ENV FL_DATA_DIR=/data
ENV FL_OPERATOR_ID=""
ENV FL_ROUNDS=1

LABEL org.opencontainers.image.title="stellar-lense-fl-client"
LABEL org.opencontainers.image.description="Stellar Lense federated learning client for exchange-side participation"
LABEL org.opencontainers.image.source="https://github.com/Stellar-lens/Stellar-Lense"

CMD ["python", "-m", "stellar_lense_fl_client"]