# Alert Dispatcher, WebSocket Server, and Streaming Pipeline Entrypoint — Real-Time Pipeline Phase 2

**Label:** `advanced` | `streaming` | `infrastructure` | `alerting`
**Difficulty:** Advanced
**Area:** new `streaming/alert_dispatcher.py`, new `streaming/ws_server.py`, new `streaming/pipeline.py`, new `scripts/stream.py`

> **Depends on:** Issue #012 (Streaming Feature Buffer and Scorer — Phase 1) must be merged first. This issue builds on `FeatureBuffer` and `StreamingScorer` delivered in Phase 1. Do not start this issue until #012 is merged.

---

## Summary

Phase 1 (Issue #012) delivered `FeatureBuffer` and `StreamingScorer` — the stateful core of the real-time detection pipeline. This issue completes the pipeline by adding:

1. **`AlertDispatcher`** — threshold check, deduplication, and outbound delivery (stdout / webhook / WebSocket).
2. **`ws_server.py`** — a minimal `asyncio` WebSocket server that the `AlertDispatcher` pushes scores to.
3. **`StreamingPipeline`** — the top-level orchestrator that starts one SSE thread per watched pair and wires everything together.
4. **`scripts/stream.py`** — the CLI entrypoint: `python -m scripts.stream`.

When Phase 2 is merged, `python -m scripts.stream` will score wallets in real time as trades land on the Stellar ledger and push alerts within one Stellar ledger close (~5 seconds) of a wallet crossing the risk threshold.

---

## Detailed Description

### Full pipeline recap (Phases 1 + 2 combined)

```
Horizon SSE Stream (per pair)          ← horizon_streamer.py (existing)
        │
        ▼
  FeatureBuffer    ←── Phase 1 (merged)
        │
        ▼
  StreamingScorer  ←── Phase 1 (merged)
        │ RiskScore dict
        ▼
  AlertDispatcher  ←── THIS ISSUE
        │
        ├── stdout (local dev)
        ├── HTTP webhook POST        ←── THIS ISSUE
        └── WebSocket push  ──────────→  ws_server.py  ←── THIS ISSUE
                                           (asyncio, 127.0.0.1 only)

StreamingPipeline  ←── THIS ISSUE: orchestrator
scripts/stream.py  ←── THIS ISSUE: CLI entrypoint
```

### `streaming/alert_dispatcher.py` — `AlertDispatcher`

```python
class AlertDispatcher:
    def __init__(
        self,
        channel: str = "stdout",           # "stdout" | "webhook" | "websocket"
        webhook_url: str | None = None,
        ws_client=None,                    # injected WebSocket client handle
        alert_cooldown_seconds: int = 3600,
        threshold: int | None = None,      # defaults to config.RISK_SCORE_FLAG_THRESHOLD
    ): ...

    def dispatch(self, wallet: str, risk_score: dict, pair_id: str) -> None:
        """Deliver alert if score >= threshold and wallet not in cooldown."""
```

**Deduplication:** maintain `{wallet: expiry_timestamp}` dict, protected by a `threading.Lock`. A wallet is in cooldown if `time.time() < expiry_timestamp`. On alert dispatch, set `expiry = time.time() + alert_cooldown_seconds`.

**Stdout channel:** print a structured single-line alert:
```
[ALERT] wallet=GABC... pair=USDC:.../XLM:native score=83 benford=True ml=True confidence=76
```

**Webhook channel:** HTTP POST to `ALERT_WEBHOOK_URL` (from env or constructor). Reject `http://` URLs at startup with `ValueError`. Use `requests` (already in `requirements.txt` transitively via `stellar_sdk`). Timeout: 5 seconds. On HTTP error, log WARNING and continue — do not crash the pipeline.

**WebSocket channel:** call `ws_client.send(json.dumps(alert_payload))` where `alert_payload` is the `RiskScore` dict plus `wallet` and `pair_id`. The `ws_client` is injected at construction time so it can be mocked in tests.

### `streaming/ws_server.py` — WebSocket server

A minimal `asyncio` WebSocket server using the `websockets` library (add to `requirements.txt`):

```python
async def run_ws_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    """Serve connected clients; broadcast alerts pushed via send_alert()."""

async def send_alert(payload: dict) -> None:
    """Broadcast payload to all connected WebSocket clients."""
```

- `WS_BIND_HOST` env var overrides `host` (default `127.0.0.1`). Reject `0.0.0.0` in production unless `WS_ALLOW_EXTERNAL=1` is explicitly set.
- `WS_PORT` env var overrides `port`.
- The server runs in its own daemon `asyncio` event loop thread — it does not block the SSE threads.
- Keep a `set` of connected client websockets; remove on disconnect.

### `streaming/pipeline.py` — `StreamingPipeline`

```python
class StreamingPipeline:
    def __init__(
        self,
        buffer: FeatureBuffer,
        scorer: StreamingScorer,
        dispatcher: AlertDispatcher,
    ): ...

    def run(self) -> None:
        """Start one thread per watched pair; block until KeyboardInterrupt."""

    def _stream_pair(self, base_asset, counter_asset) -> None:
        """Thread target: stream trades from Horizon and update buffer + score."""
```

- One daemon `threading.Thread` per pair, running `stream_trades` from `horizon_streamer.py`.
- On each incoming `Trade`, call `buffer.update(trade)`, then score both `base_account` and `counter_account` via `scorer.score_wallet`, then call `dispatcher.dispatch` for any non-None score.
- Handle `KeyboardInterrupt` in `run()` by joining all threads with a 5-second timeout then exiting cleanly.

### `scripts/stream.py` — CLI entrypoint

```bash
python -m scripts.stream \
  [--alert-channel stdout|webhook|websocket] \
  [--cooldown-seconds 3600] \
  [--min-trades 20] \
  [--no-ws]            # disable WebSocket server even if channel=websocket
```

Startup sequence:
1. Validate config (call `config.validate(require_onchain=False)`).
2. Load `RiskScorer` from `MODEL_DIR` (exit 1 if no models).
3. Start WebSocket server thread (unless `--no-ws`).
4. Instantiate `FeatureBuffer`, `StreamingScorer`, `AlertDispatcher`, `StreamingPipeline`.
5. Log startup banner with pair count, alert channel, and WebSocket address (if active).
6. Call `pipeline.run()`.

### New env vars (add to `.env.example` and `config.py`)

| Variable | Default | Purpose |
|---|---|---|
| `ALERT_CHANNEL` | `stdout` | Alert delivery channel |
| `ALERT_WEBHOOK_URL` | — | Required when `ALERT_CHANNEL=webhook` |
| `ALERT_COOLDOWN_SECONDS` | `3600` | Alert dedup window |
| `WS_PORT` | `8765` | WebSocket server port |
| `WS_BIND_HOST` | `127.0.0.1` | WebSocket bind address |
| `WS_ALLOW_EXTERNAL` | — | Set to `1` to allow non-loopback bind |

### Package dependency

Add `websockets>=12.0` to `requirements.txt`.

---

## Requirements

### Functional
- Latency from ledger close to alert delivery (stdout or webhook) must be < 10 seconds on a typical connection.
- Alert dedup must prevent repeat alerts for the same wallet within `alert_cooldown_seconds`.
- Graceful shutdown on `SIGINT`/`SIGTERM`: all threads join within 5 seconds; in-flight scores are flushed before exit.
- `StreamingPipeline` must reconnect automatically on Horizon SSE disconnection (delegated to `stream_trades` in `horizon_streamer.py` — verify integration).

### Thread safety
- `AlertDispatcher`'s cooldown dict must be protected by a `threading.Lock`.
- The WebSocket client set in `ws_server.py` must be managed inside the `asyncio` event loop only — no cross-thread mutation.

### Security
- `ALERT_WEBHOOK_URL` must not appear in any log output.
- Webhook channel must reject `http://` URLs at startup with a clear `ValueError`.
- WebSocket server must bind to `127.0.0.1` by default; require explicit opt-in for external binding.

### Documentation
- New `docs/streaming_architecture.md` with a full pipeline diagram and explanation of every component (covers both Phase 1 and Phase 2).
- Update `README.md` to document `scripts/stream.py` and all new env vars.
- Update `scripts/README.md` with `stream.py` usage examples.

---

## Tests Required (mandatory — all must pass)

Add `tests/test_alert_dispatcher.py` and `tests/test_streaming_pipeline.py`:

**`tests/test_alert_dispatcher.py`:**

1. **`test_dispatch_stdout_above_threshold`** — score=83, threshold=70; assert formatted alert is printed to stdout (capture with `capsys`).
2. **`test_dispatch_suppressed_below_threshold`** — score=50, threshold=70; assert nothing is printed.
3. **`test_dedup_within_cooldown`** — dispatch twice within cooldown; assert outbound channel called exactly once (mock the channel).
4. **`test_dedup_allows_after_cooldown_expires`** — mock `time.time` to advance past cooldown expiry; assert second dispatch fires.
5. **`test_webhook_rejects_http_url`** — pass `webhook_url="http://example.com"`; assert `ValueError` on construction.
6. **`test_webhook_posts_correct_payload`** — mock `requests.post`; assert it is called with JSON containing `wallet`, `score`, `benford_flag`, `ml_flag`, `pair_id`.
7. **`test_websocket_channel_calls_send`** — inject a mock `ws_client` with a `send` method; assert `send` is called with valid JSON on dispatch above threshold.

**`tests/test_streaming_pipeline.py`:**

8. **`test_pipeline_scores_both_accounts_per_trade`** — mock `stream_trades` to yield one trade between wallets A and B; assert `dispatcher.dispatch` is called for both A and B (after min-trades warmup is bypassed by mocking `StreamingScorer`).
9. **`test_pipeline_reconnects_on_stream_failure`** — mock `stream_trades` to raise `ConnectionError` once then yield normally; assert pipeline does not crash and continues scoring.
10. **`test_pipeline_graceful_shutdown`** — call `pipeline.run()` in a thread; send `SIGINT`; assert all threads join within 5 seconds.

Run with: `pytest tests/test_alert_dispatcher.py tests/test_streaming_pipeline.py -v`

All ten tests must pass. `make lint` and `make test` must pass with no new failures.

---

## How to Apply for This Issue

**Specialty area:** Python streaming systems / `asyncio` / real-time alerting infrastructure. Familiarity with `asyncio`, `websockets`, `threading`, HTTP webhooks, and graceful shutdown patterns in Python is required. You do **not** need Stellar or ML expertise for this issue — it is purely infrastructure.

When commenting to claim this issue, please include:
- Your experience building real-time alerting or event delivery systems in Python.
- Whether you have worked with `asyncio` alongside `threading` (mixed sync/async Python).
- Whether you have read the Phase 1 issue (#012) and the `streaming/feature_buffer.py` / `streaming/streaming_scorer.py` code it introduces.
- Any prior work on WebSocket servers, webhook delivery systems, or streaming pipelines.

Completing this issue makes LedgerLens a live detection system — the first open-source real-time wash-trade monitor for the Stellar DEX.
