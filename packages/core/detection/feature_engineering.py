"""On-chain feature extraction for Stellar Lense wash-trading scoring.

Computes, for one account over a `Trade`-shaped DataFrame (as produced by
`ingestion.historical_loader.load_historical_trades`):

- Benford's Law features per rolling window (chi-square, MAD, max Z-score,
  per-stratum summaries, KS/Kuiper tests, a majority-vote flag);
- trade-pattern features (counterparty concentration, round-trip frequency,
  self-matching, order cancellations);
- volume/timing features (volume per counterparty, intra-minute clustering,
  off-hours ratio, volume spikes);
- wallet features (shared funding source, degree centrality, account age);
- cross-pair Benford coordination features (when trades for several pairs
  are supplied).

Order-book events and account metadata are optional; features that need
them are `0.0` when they are absent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config.settings import settings
from detection.benford_engine import (
    AdaptiveBenfordWindow,
    compute_benford_ks_kuiper,
    compute_benford_metrics,
    stratified_benford_analysis,
)

try:
    import numba
    _HAS_NUMBA = True
except ImportError:
    _HAS_NUMBA = False


if _HAS_NUMBA:

    @numba.njit(cache=True)
    def _round_trip_count_jit(gave_ids: "np.ndarray", got_ids: "np.ndarray", max_trades: int) -> int:
        n = len(gave_ids)
        round_trips = 0
        for i in range(n):
            for j in range(i + 1, min(i + 1 + max_trades, n)):
                if gave_ids[j] == got_ids[i] and got_ids[j] == gave_ids[i]:
                    round_trips += 1
                    break
        return round_trips


def _round_trip_count_python(legs: list, max_trades: int) -> int:
    """Pure-Python reference implementation of `_round_trip_count_jit`.

    Takes `legs` as a list of `(gave, got)` pairs directly (any hashable/
    comparable type -- `round_trip_trade_frequency` passes integer-coded ids
    when using the JIT path and asset-symbol strings here), unlike the JIT
    kernel which requires two pre-split numeric arrays for Numba compilation.
    """
    n = len(legs)
    round_trips = 0
    for i in range(n):
        gave_i, got_i = legs[i]
        for j in range(i + 1, min(i + 1 + max_trades, n)):
            gave_j, got_j = legs[j]
            if gave_j == got_i and got_j == gave_i:
                round_trips += 1
                break
    return round_trips


ROLLING_WINDOWS = {
    "1h": pd.Timedelta(hours=1),
    "4h": pd.Timedelta(hours=4),
    "24h": pd.Timedelta(hours=24),
    "7d": pd.Timedelta(days=7),
    "30d": pd.Timedelta(days=30),
}

# Hours (UTC) treated as "off hours" for off_hours_activity_ratio.
DEFAULT_OFF_HOURS = frozenset(range(0, 6))

BENFORD_FEATURE_NAMES = [
    f"benford_{metric}_{window}"
    for window in ROLLING_WINDOWS
    for metric in ("chi_square", "mad", "max_zscore")
]

# Boolean flags indicating that the corresponding Benford window was
# adaptively expanded or merged due to insufficient sample count.
BENFORD_WINDOW_EXPANDED_FEATURE_NAMES = [
    f"benford_window_expanded_{window}" for window in ROLLING_WINDOWS
]

# Per-stratum Benford summary features (3 features x 5 windows = 15 new)
BENFORD_STRATUM_FEATURE_NAMES = [
    f"max_stratum_chi2_{window}" for window in ROLLING_WINDOWS
] + [
    f"max_stratum_MAD_{window}" for window in ROLLING_WINDOWS
] + [
    f"n_flagged_strata_{window}" for window in ROLLING_WINDOWS
]

# KS and Kuiper test features (4 per window x 5 windows = 20 new)
BENFORD_KS_KUIPER_FEATURE_NAMES = [
    f"ks_stat_{window}" for window in ROLLING_WINDOWS
] + [
    f"ks_pval_{window}" for window in ROLLING_WINDOWS
] + [
    f"kuiper_stat_{window}" for window in ROLLING_WINDOWS
] + [
    f"kuiper_pval_{window}" for window in ROLLING_WINDOWS
]

# Majority-vote combined Benford flag (1 per window x 5 windows = 5 new)
BENFORD_COMBINED_FLAG_FEATURE_NAMES = [
    f"benford_combined_flag_{window}" for window in ROLLING_WINDOWS
]

TRADE_PATTERN_FEATURE_NAMES = [
    "counterparty_concentration_ratio",
    "round_trip_trade_frequency",
    "self_matching_rate",
    "order_cancellation_rate",
]

VOLUME_TIMING_FEATURE_NAMES = [
    "volume_to_unique_counterparty_ratio",
    "intra_minute_clustering_coefficient",
    "off_hours_activity_ratio",
    "volume_spike_frequency",
]


WALLET_FEATURE_NAMES = [
    "funding_source_similarity_score",
    "network_centrality",
    "account_age_days",
]

MULTIVARIATE_BENFORD_FEATURE_NAMES = [
    "benford_copula_pval",
    "cross_pair_sync_ratio",
    "digit_entropy_delta",
]

FEATURE_NAMES = (
    BENFORD_FEATURE_NAMES
    + TRADE_PATTERN_FEATURE_NAMES
    + VOLUME_TIMING_FEATURE_NAMES
    + WALLET_FEATURE_NAMES
    + MULTIVARIATE_BENFORD_FEATURE_NAMES
    + BENFORD_WINDOW_EXPANDED_FEATURE_NAMES
    + BENFORD_STRATUM_FEATURE_NAMES
    + BENFORD_KS_KUIPER_FEATURE_NAMES
    + BENFORD_COMBINED_FLAG_FEATURE_NAMES
)


def _window_slice(trades: pd.DataFrame, as_of: pd.Timestamp, window: pd.Timedelta) -> pd.DataFrame:
    start = as_of - window
    mask = (trades["ledger_close_time"] > start) & (trades["ledger_close_time"] <= as_of)
    return trades.loc[mask]


def _account_trades(trades: pd.DataFrame, account: str) -> pd.DataFrame:
    return trades[(trades["base_account"] == account) | (trades["counter_account"] == account)]


def _counterparties(account_trades: pd.DataFrame, account: str) -> pd.Series:
    return account_trades.apply(
        lambda r: r["counter_account"] if r["base_account"] == account else r["base_account"],
        axis=1,
    )


def _asset_symbol(asset: dict) -> str:
    code = asset["code"]
    issuer = asset.get("issuer")
    return code if issuer is None else f"{code}:{issuer}"


def benford_features(
    trades: pd.DataFrame,
    as_of: pd.Timestamp,
    adaptive_window: AdaptiveBenfordWindow | None = None,
) -> dict:
    """Chi-square, MAD, and max Z-score for `base_amount` across each rolling window.

    Also computes per-stratum Benford summary features (max chi-square, max MAD,
    and flagged strata count) for each window via ``stratified_benford_analysis``.

    When ``adaptive_window`` is provided the window is expanded (or merged) as
    needed to reach the configured minimum sample count, and a boolean
    ``benford_window_expanded_{label}`` flag is set for each window that was
    widened beyond the nominal target.
    """
    features = {}
    for label, window in ROLLING_WINDOWS.items():
        if adaptive_window is not None:
            result = adaptive_window.fit(trades, label, as_of, ROLLING_WINDOWS)
            amounts = result.trades
            features[f"benford_window_expanded_{label}"] = float(result.expanded or result.merged)
            subset = _window_slice(trades, as_of, window)
        else:
            subset = _window_slice(trades, as_of, window)
            amounts = subset["base_amount"].tolist()
            features[f"benford_window_expanded_{label}"] = 0.0
        metrics = compute_benford_metrics(amounts)
        features[f"benford_chi_square_{label}"] = metrics["chi_square"]
        features[f"benford_mad_{label}"] = metrics["mad"]
        features[f"benford_max_zscore_{label}"] = max(metrics["z_scores"].values(), default=0.0)

        summary = stratified_benford_analysis(subset)
        features[f"max_stratum_chi2_{label}"] = summary.max_stratum_chi2
        features[f"max_stratum_MAD_{label}"] = summary.max_stratum_MAD
        features[f"n_flagged_strata_{label}"] = float(summary.n_flagged_strata)

        ks_kuiper = compute_benford_ks_kuiper(amounts)
        features[f"ks_stat_{label}"] = ks_kuiper["ks_stat"] if not _is_nan(ks_kuiper["ks_stat"]) else 0.0
        features[f"ks_pval_{label}"] = ks_kuiper["ks_pval"] if not _is_nan(ks_kuiper["ks_pval"]) else 1.0
        features[f"kuiper_stat_{label}"] = ks_kuiper["kuiper_stat"] if not _is_nan(ks_kuiper["kuiper_stat"]) else 0.0
        features[f"kuiper_pval_{label}"] = ks_kuiper["kuiper_pval"] if not _is_nan(ks_kuiper["kuiper_pval"]) else 1.0

        chi2_flag = metrics["chi_square"] > 15.507
        ks_flag = ks_kuiper.get("ks_flag", False)
        kuiper_flag = ks_kuiper.get("kuiper_flag", False)
        n_flags = sum([chi2_flag, ks_flag, kuiper_flag])
        features[f"benford_combined_flag_{label}"] = 1.0 if n_flags >= 2 else 0.0
    return features


def _is_nan(value: float) -> bool:
    import math
    try:
        return math.isnan(value)
    except (TypeError, ValueError):
        return False


def counterparty_concentration_ratio(trades: pd.DataFrame, account: str) -> float:
    """Fraction of `account`'s volume traded against its single largest counterparty."""
    account_trades = _account_trades(trades, account)
    if account_trades.empty:
        return 0.0

    counterparties = _counterparties(account_trades, account)
    volumes = account_trades["base_amount"].groupby(counterparties).sum()
    total = volumes.sum()
    return float(volumes.max() / total) if total > 0 else 0.0


def round_trip_trade_frequency(trades: pd.DataFrame, account: str, max_trades: int = 5) -> float:
    """Fraction of `account`'s trades that are reversed within the next `max_trades` trades.

    A trade is considered "reversed" if a later trade sends back the asset
    `account` just received in exchange for the asset it just gave up
    (regardless of amount) — a hallmark of circular wash-trading routes.

    Direction comes from Horizon's `base_is_seller`: the base party gives
    up the base asset when it is the seller, and the counter party gives up
    the base asset when it isn't. This matters on the SDEX, where a wash
    trader commonly stays on the same (base) side of every match while
    alternately buying and selling. When `base_is_seller` is absent (older
    callers, hand-built frames) the base side is assumed to give up the
    base asset.

    Uses a Numba-JIT two-pointer-free O(n * max_trades) scan when available
    and enabled (`FEATURE_ENGINE_JIT_ENABLED`), falling back to the pure
    Python reference implementation otherwise -- see `_round_trip_count_jit`
    / `_round_trip_count_python`.
    """
    account_trades = _account_trades(trades, account).sort_values("ledger_close_time").reset_index(drop=True)
    n = len(account_trades)
    if n < 2:
        return 0.0

    has_side = "base_is_seller" in account_trades.columns
    legs = []
    for _, row in account_trades.iterrows():
        account_is_base = row["base_account"] == account
        base_is_seller = bool(row["base_is_seller"]) if has_side and pd.notna(row["base_is_seller"]) else True
        base, counter = _asset_symbol(row["base_asset"]), _asset_symbol(row["counter_asset"])
        if account_is_base == base_is_seller:
            legs.append((base, counter))
        else:
            legs.append((counter, base))

    if _HAS_NUMBA and settings.feature_engine_jit_enabled:
        symbol_to_id: dict[str, int] = {}
        gave_ids = np.empty(n, dtype=np.int64)
        got_ids = np.empty(n, dtype=np.int64)
        for i, (gave, got) in enumerate(legs):
            gave_ids[i] = symbol_to_id.setdefault(gave, len(symbol_to_id))
            got_ids[i] = symbol_to_id.setdefault(got, len(symbol_to_id))
        round_trips = _round_trip_count_jit(gave_ids, got_ids, max_trades)
    else:
        round_trips = _round_trip_count_python(legs, max_trades)

    return round_trips / n


def self_matching_rate(trades: pd.DataFrame) -> float:
    """Fraction of trades where the base and counter accounts are identical."""
    if trades.empty:
        return 0.0
    return float((trades["base_account"] == trades["counter_account"]).mean())


def order_cancellation_rate(events: pd.DataFrame, account: str) -> float:
    """Fraction of `account`'s order-book events (see `OrderBookEvent`) that are cancellations."""
    if events.empty:
        return 0.0
    account_events = events[events["account"] == account]
    if account_events.empty:
        return 0.0
    return float((account_events["event_type"] == "cancelled").mean())


def volume_to_unique_counterparty_ratio(trades: pd.DataFrame, account: str) -> float:
    """Total volume for `account` divided by the number of distinct counterparties."""
    account_trades = _account_trades(trades, account)
    if account_trades.empty:
        return 0.0
    counterparties = _counterparties(account_trades, account)
    unique_counterparties = counterparties.nunique()
    total_volume = account_trades["base_amount"].sum()
    if not unique_counterparties:
        return 0.0
    # Clamp to 0.0: negative base_amount from erroneous ingestion produces a
    # negative ratio which is nonsensical for a volume metric.
    return max(0.0, float(total_volume / unique_counterparties))


def intra_minute_clustering_coefficient(trades: pd.DataFrame) -> float:
    """Fraction of trades that share the same calendar minute as another trade."""
    if trades.empty:
        return 0.0
    minute_buckets = trades["ledger_close_time"].dt.floor("min")
    counts = minute_buckets.value_counts()
    clustered = counts[counts > 1].sum()
    return float(clustered / len(trades))


def off_hours_activity_ratio(trades: pd.DataFrame, off_hours: frozenset[int] = DEFAULT_OFF_HOURS) -> float:
    """Fraction of trades occurring during `off_hours` (UTC hour-of-day, default 00:00-05:59)."""
    if trades.empty:
        return 0.0
    hours = trades["ledger_close_time"].dt.hour
    return float(hours.isin(off_hours).mean())


def volume_spike_frequency(
    trades: pd.DataFrame,
    as_of: pd.Timestamp,
    bucket: str = "1h",
    baseline_window: pd.Timedelta = ROLLING_WINDOWS["24h"],
    spike_threshold: float = 2.0,
) -> float:
    """Fraction of `bucket`-sized time buckets within `baseline_window` whose volume
    exceeds the mean bucket volume by more than `spike_threshold` standard deviations.
    """
    subset = _window_slice(trades, as_of, baseline_window)
    if subset.empty:
        return 0.0

    bucketed = subset.set_index("ledger_close_time")["base_amount"].resample(bucket).sum()
    if len(bucketed) < 2 or bucketed.std() == 0:
        return 0.0

    threshold = bucketed.mean() + spike_threshold * bucketed.std()
    return float((bucketed > threshold).mean())


def funding_source_similarity_score(trades: pd.DataFrame, account: str, account_metadata: dict[str, dict]) -> float:
    """Fraction of `account`'s counterparties funded by the same source account as `account`.

    `account_metadata` maps account -> `{"funding_source": str | None, "created_at": datetime | None}`,
    as returned by `ingestion.account_loader.load_account_metadata`.
    """
    funding_source = account_metadata.get(account, {}).get("funding_source")
    if funding_source is None:
        return 0.0

    account_trades = _account_trades(trades, account)
    if account_trades.empty:
        return 0.0

    counterparties = _counterparties(account_trades, account)
    matches = counterparties.map(lambda cp: account_metadata.get(cp, {}).get("funding_source") == funding_source)
    return float(matches.mean())


def network_centrality(trades: pd.DataFrame, account: str) -> float:
    """Degree centrality of `account` within the trading graph induced by `trades`.

    Defined as `account`'s unique counterparties divided by `(total accounts - 1)`.
    Pool trades have no counterparty wallet (`counter_account` is `None`) and
    are excluded from the account universe rather than counted as a node.
    """
    all_accounts = pd.unique(trades[["base_account", "counter_account"]].values.ravel())
    all_accounts = all_accounts[pd.notna(all_accounts)]
    if len(all_accounts) <= 1:
        return 0.0

    account_trades = _account_trades(trades, account)
    if account_trades.empty:
        return 0.0

    unique_counterparties = _counterparties(account_trades, account).nunique()
    return float(unique_counterparties / (len(all_accounts) - 1))


def account_age_days(account: str, as_of: pd.Timestamp, account_metadata: dict[str, dict]) -> float:
    """Age of `account` in days as of `as_of`, or `0.0` if its creation time is unknown."""
    created_at = account_metadata.get(account, {}).get("created_at")
    if created_at is None:
        return 0.0
    return float((as_of - pd.Timestamp(created_at)).total_seconds() / 86400)



def multivariate_benford_features(account: str, trades_by_pair: dict[str, pd.DataFrame] | None) -> dict:
    """Cross-pair Benford coordination features for `account`.

    `trades_by_pair` maps asset-pair label -> trades DataFrame (each row must
    carry an `asset_pair` column; see
    `detection.benford_engine.multivariate_benford_score`). Omitting it (or
    passing fewer than 2 pairs) yields the i.i.d.-Benford defaults.
    """
    zero = {name: (1.0 if name == "benford_copula_pval" else 0.0) for name in MULTIVARIATE_BENFORD_FEATURE_NAMES}
    if not trades_by_pair or len(trades_by_pair) < 2:
        return zero

    from detection.benford_engine import multivariate_benford_score

    wallet_pairs = [(account, pair) for pair in trades_by_pair]
    combined = pd.concat(trades_by_pair.values(), ignore_index=True)
    result = multivariate_benford_score(combined, wallet_pairs)
    return {
        "benford_copula_pval": result["copula_pval"],
        "cross_pair_sync_ratio": result["sync_ratio"],
        "digit_entropy_delta": result["digit_entropy_delta"],
    }



def build_feature_vector(
    trades: pd.DataFrame,
    account: str,
    as_of: pd.Timestamp,
    order_book_events: pd.DataFrame | None = None,
    account_metadata: dict[str, dict] | None = None,
    trades_by_pair: dict[str, pd.DataFrame] | None = None,
    adaptive_benford_window: AdaptiveBenfordWindow | None = None,
) -> dict:
    """Assemble the feature vector for `account` as of `as_of`.

    `trades` should already be filtered to the relevant asset pair / time
    range covering the largest rolling window. Returns a dict keyed by every
    name in `FEATURE_NAMES`.
    """
    order_book_events = (
        order_book_events
        if order_book_events is not None
        else pd.DataFrame(columns=["account", "event_type"])
    )
    account_metadata = account_metadata or {}

    features = benford_features(trades, as_of, adaptive_window=adaptive_benford_window)
    features.update(
        {
            "counterparty_concentration_ratio": counterparty_concentration_ratio(trades, account),
            "round_trip_trade_frequency": round_trip_trade_frequency(trades, account),
            "self_matching_rate": self_matching_rate(trades),
            "order_cancellation_rate": order_cancellation_rate(order_book_events, account),
            "volume_to_unique_counterparty_ratio": volume_to_unique_counterparty_ratio(trades, account),
            "intra_minute_clustering_coefficient": intra_minute_clustering_coefficient(trades),
            "off_hours_activity_ratio": off_hours_activity_ratio(trades),
            "volume_spike_frequency": volume_spike_frequency(trades, as_of),
            "funding_source_similarity_score": funding_source_similarity_score(trades, account, account_metadata),
            "network_centrality": network_centrality(trades, account),
            "account_age_days": account_age_days(account, as_of, account_metadata),
        }
    )
    features.update(multivariate_benford_features(account, trades_by_pair))
    for name in FEATURE_NAMES:
        features.setdefault(name, 0.0)
    return features
