"""Score the labelled evaluation set and write REPORT.md.

Runs offline on the committed data/ files (see build_dataset.py for how
they were made and what the labels mean):

    uv run --package stellar-lense-core python packages/core/evaluation/evaluate.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api_free_scoring import ALERT_THRESHOLD, score_labelled  # noqa: E402

HERE = Path(__file__).parent
THRESHOLDS = (30, 40, ALERT_THRESHOLD, 60, 70)


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """95% Wilson score interval for a proportion; None when n == 0."""
    if n == 0:
        return None
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def auc(scores: list[float], labels: list[int]) -> float | None:
    """Probability a random positive outscores a random negative (ties = 1/2)."""
    pos = [s for s, y in zip(scores, labels) if y == 1]
    neg = [s for s, y in zip(scores, labels) if y == 0]
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def fmt(x: float | None, ci: tuple[float, float] | None = None) -> str:
    if x is None:
        return "n/a"
    out = f"{x:.2f}"
    if ci is not None:
        out += f" [{ci[0]:.2f}, {ci[1]:.2f}]"
    return out


def metrics(df: pd.DataFrame, threshold: int) -> dict:
    predicted = df["score"] >= threshold
    actual = df["label"] == 1
    tp = int((predicted & actual).sum())
    fp = int((predicted & ~actual).sum())
    fn = int((~predicted & actual).sum())
    tn = int((~predicted & ~actual).sum())
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    return {
        "threshold": threshold,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": precision,
        "precision_ci": wilson(tp, tp + fp),
        "recall": recall,
        "recall_ci": wilson(tp, tp + fn),
    }


def main() -> int:
    labelled = pd.read_csv(HERE / "data" / "labelled_wallets.csv", dtype={"label": str})
    trades = pd.read_csv(HERE / "data" / "trades.csv.gz")
    source = (HERE / "data" / "SOURCE.txt").read_text().strip()

    scored = score_labelled(labelled, trades)
    known = scored[scored["label"].isin(["0", "1"])].copy()
    known["label"] = known["label"].astype(int)
    n_pos, n_neg = int(known["label"].sum()), int((known["label"] == 0).sum())
    n_unknown = len(scored) - len(known)
    rows = [metrics(known, t) for t in THRESHOLDS]
    area = auc(known["score"].tolist(), known["label"].tolist())
    mean_pos = known.loc[known["label"] == 1, "score"].mean() if n_pos else None
    mean_neg = known.loc[known["label"] == 0, "score"].mean() if n_neg else None
    alert = next(r for r in rows if r["threshold"] == ALERT_THRESHOLD)

    table = "\n".join(
        f"| {r['threshold']} | {r['tp']} | {r['fp']} | {r['fn']} | {r['tn']} "
        f"| {fmt(r['precision'], r['precision_ci'])} | {fmt(r['recall'], r['recall_ci'])} |"
        for r in rows
    )
    reasons = scored["label_reason"].value_counts().to_dict()
    # With a handful of positives, AUC is just where those few wallets happen
    # to rank among the negatives; say so instead of presenting it as a result.
    auc_caveat = (
        f" With only {n_pos} positive{'s' if n_pos != 1 else ''}, this is just "
        f"where {'that wallet ranks' if n_pos == 1 else 'those wallets rank'} "
        "among the negatives, not a measure of ranking quality."
        if n_pos < 10
        else ""
    )
    if n_pos < 10 or n_neg < 10:
        bottom_line = (
            f"**This evaluation is not yet meaningful.** Only {n_pos} positive and "
            f"{n_neg} negative wallets could be labelled from public data, so precision "
            "and recall below are reported for completeness but say essentially nothing "
            "about the scorer (look at the interval widths). Most sampled wallets are "
            "long-running bots whose account creation predates public Horizon's retained "
            "history and whose payment histories are too long to scan. The finding is "
            "that this labelling approach doesn't yield enough cases; a better source of "
            "ground truth is needed, not a better threshold."
        )
    else:
        bottom_line = (
            f"{n_pos} positive and {n_neg} negative proxy-labelled wallets. "
            f"AUC {fmt(area)}; at the alert threshold precision "
            f"{fmt(alert['precision'], alert['precision_ci'])}, recall "
            f"{fmt(alert['recall'], alert['recall_ci'])}. See the caveats below."
        )

    report = f"""# Scorer evaluation

Generated by `packages/core/evaluation/evaluate.py`. Re-run it to reproduce
these numbers exactly from the committed data.

## Bottom line

{bottom_line}

## Read this first

* **The labels are proxies, not confirmed wash trading.** A wallet is
  labelled positive when it and its largest counterparty share an account
  creator, one created the other, or they paid each other directly
  (Horizon history). See `build_dataset.py` for the exact rule. An exchange funding many unrelated
  users can create false positives; a wash trader using unrelated funding
  sources is labelled negative.
* **The sample is small** ({len(known)} labelled wallets, {n_pos} positive),
  so the 95% intervals below are wide. Treat the point estimates as rough.
* **The sample is not random.** Every wallet scoring 40 or more was
  included, plus a random sample of the rest, so precision/recall here do
  not describe the whole population of SDEX wallets.
* The scorer evaluated is the fixed heuristic (`detection/scoring.py`),
  which uses none of the funding information the labels are built from.

## Data

{source}

| | Wallets |
|---|---|
| Labelled positive (funding or payment link) | {n_pos} |
| Labelled negative (no link, check complete) | {n_neg} |
| Unknown, excluded (no link found but the check was incomplete) | {n_unknown} |

Label reasons: {", ".join(f"{k}: {v}" for k, v in reasons.items())}.

## Results

Ranking quality (AUC, positive vs negative): {fmt(area)}
(0.5 = no better than chance).{auc_caveat} Mean score: positives {fmt(mean_pos)},
negatives {fmt(mean_neg)}.

Precision and recall when flagging wallets at or above each score
threshold (95% Wilson intervals). The API's alert threshold is
{ALERT_THRESHOLD}.

| Threshold | TP | FP | FN | TN | Precision | Recall |
|---|---|---|---|---|---|---|
{table}

At the alert threshold, the scorer flagged {alert['tp'] + alert['fp']} of
{len(known)} labelled wallets, with precision {fmt(alert['precision'], alert['precision_ci'])}
and recall {fmt(alert['recall'], alert['recall_ci'])} against the proxy labels.

## What this does and doesn't show

It shows how often the heuristic's high scores coincide with an
independent on-chain signal of common control, on one day of data from the
tracked pairs. It does not show that flagged wallets are wash trading, or
that unflagged wallets aren't. Better ground truth (cases confirmed by
issuers, exchanges or investigators) is needed before quoting any of these
numbers as detection accuracy.
"""
    (HERE / "REPORT.md").write_text(report)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
