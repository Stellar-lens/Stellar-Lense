"""Forensic report structures for risk scoring and causal attribution."""

from __future__ import annotations

import csv
import io
import os
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import pandas as pd

from detection.causal_attribution import CounterfactualAttributor
from detection.model_inference import RiskScorer
from detection.shap_explainer import ShapExplainer

# CSV column order for flat export (one row per SHAP feature).
CSV_COLUMNS = [
    "wallet",
    "asset_pair",
    "risk_score",
    "feature",
    "shap_value",
    "shap_contribution",
]


@dataclass(slots=True)
class CausalAttribution:
    minimal_exonerating_trades: list[str]
    counterfactual_score: int
    root_cause_wallet: str | None
    causal_chain: list[dict]
    interventional_score_if_no_wash: int


@dataclass(slots=True)
class PropagationContributor:
    """A single wallet that contributed to the target wallet's propagated score."""

    source_wallet: str
    base_score: float
    ppr_weight: float
    contribution: float
    fraction: float  # share of total propagated score from this source


@dataclass(slots=True)
class PropagationPath:
    """Propagation attribution section of a :class:`ForensicReport`."""

    propagated_risk: float
    contributors: list[PropagationContributor] = field(default_factory=list)


@dataclass(slots=True)
class ForensicReport:
    wallet: str
    asset_pair: str
    risk_score: dict
    shap_explanations: list[dict] = field(default_factory=list)
    causal_attribution: CausalAttribution | None = None
    propagation_path: PropagationPath | None = None

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a fully serialisable nested dict representation.

        The propagation_path section is included when present so the caller
        can write it verbatim to a JSON file for compliance ingestion.
        """
        d: dict = {
            "wallet": self.wallet,
            "asset_pair": self.asset_pair,
            "risk_score": dict(self.risk_score),
            "shap_explanations": list(self.shap_explanations),
        }

        if self.causal_attribution is not None:
            ca = self.causal_attribution
            d["causal_attribution"] = {
                "minimal_exonerating_trades": list(ca.minimal_exonerating_trades),
                "counterfactual_score": ca.counterfactual_score,
                "root_cause_wallet": ca.root_cause_wallet,
                "causal_chain": list(ca.causal_chain),
                "interventional_score_if_no_wash": ca.interventional_score_if_no_wash,
            }
        else:
            d["causal_attribution"] = None

        if self.propagation_path is not None:
            pp = self.propagation_path
            d["propagation_path"] = {
                "propagated_risk": pp.propagated_risk,
                "contributors": [
                    {
                        "source_wallet": c.source_wallet,
                        "base_score": c.base_score,
                        "ppr_weight": c.ppr_weight,
                        "contribution": c.contribution,
                        "fraction": c.fraction,
                    }
                    for c in pp.contributors
                ],
            }
        else:
            d["propagation_path"] = None

        return d

    def to_csv_rows(self) -> list[dict]:
        """Return a flat list of dicts — one row per SHAP feature.

        Columns: wallet, asset_pair, risk_score, feature, shap_value,
        shap_contribution.

        If there are no SHAP explanations a single summary row is still
        emitted with empty feature/shap columns so the wallet is always
        represented in the exported file.
        """
        score_value = (
            self.risk_score.get("score", "") if isinstance(self.risk_score, dict) else self.risk_score
        )

        base: dict = {
            "wallet": self.wallet,
            "asset_pair": self.asset_pair,
            "risk_score": score_value,
        }

        if not self.shap_explanations:
            return [{**base, "feature": "", "shap_value": "", "shap_contribution": ""}]

        rows: list[dict] = []
        for exp in self.shap_explanations:
            rows.append(
                {
                    **base,
                    "feature": exp.get("feature", ""),
                    "shap_value": exp.get("value", ""),
                    "shap_contribution": exp.get("contribution", ""),
                }
            )
        return rows


class ForensicReportGenerator:
    """Build a structured report for a scored wallet."""

    def __init__(self, scorer: RiskScorer | None = None, explainer: ShapExplainer | None = None):
        self._scorer = scorer or RiskScorer()
        self._explainer = explainer or ShapExplainer()

    def generate(
        self,
        wallet: str,
        asset_pair: str,
        feature_row: pd.Series,
        wallet_trades: pd.DataFrame,
        activity=None,
        orderbook_events: pd.DataFrame | None = None,
        funding_graph: nx.DiGraph | None = None,
        all_pairs_df: pd.DataFrame | None = None,
        causal: bool = False,
        top_n: int = 5,
        # Propagation inputs — both required for propagation_path to be populated
        base_scores: dict[str, float] | None = None,
        co_trade_graph: nx.Graph | None = None,
        propagation_alpha: float = 0.15,
    ) -> ForensicReport:
        risk_score = self._scorer.score(feature_row)
        shap_explanations = []
        try:
            shap_explanations = self._explainer.explain_ensemble(
                feature_row, self._scorer.models, top_n=top_n
            )
        except Exception:  # noqa: BLE001
            shap_explanations = []

        causal_attribution = None
        if causal:
            attributor = CounterfactualAttributor(self._scorer)
            minimal_set = (
                attributor.minimal_exonerating_set(
                    wallet,
                    wallet_trades,
                    activity=activity,
                    orderbook_events=orderbook_events,
                    funding_graph=funding_graph,
                    all_pairs_df=all_pairs_df,
                )
                or []
            )
            counterfactual = attributor.counterfactual_score(
                wallet,
                wallet_trades,
                minimal_set,
                activity=activity,
                orderbook_events=orderbook_events,
                funding_graph=funding_graph,
                all_pairs_df=all_pairs_df,
            )
            scm = attributor.build_scm(
                wallet,
                wallet_trades,
                activities=[activity] if activity is not None else None,
                orderbook_events=orderbook_events,
                funding_graph=funding_graph,
                all_pairs_df=all_pairs_df,
            )
            intervention_score = counterfactual["counterfactual_score"]
            intervention_key = next(
                (name for name in feature_row.index if name == "benford_chi_square_24h"),
                next(
                    (name for name in feature_row.index if name.startswith("benford_chi_square_")),
                    None,
                ),
            )
            if intervention_key is not None:
                intervention_result = attributor.interventional_score(
                    wallet, scm, {intervention_key: 0.0}
                )
                intervention_score = intervention_result["score"]

            causal_attribution = CausalAttribution(
                minimal_exonerating_trades=minimal_set,
                counterfactual_score=counterfactual["counterfactual_score"],
                root_cause_wallet=attributor.root_cause_wallet(
                    wallet,
                    wallet_trades,
                    funding_graph,
                    activity=activity,
                    orderbook_events=orderbook_events,
                    all_pairs_df=all_pairs_df,
                ),
                causal_chain=attributor.causal_chain(wallet, funding_graph),
                interventional_score_if_no_wash=intervention_score,
            )

        # ------------------------------------------------------------------
        # Propagation path — only computed when base_scores and a graph are
        # supplied, and only when the wallet has a non-zero propagated score.
        # ------------------------------------------------------------------
        propagation_path: PropagationPath | None = None
        if base_scores is not None and funding_graph is not None:
            from detection.risk_propagation import (
                propagate_risk_scores,
                propagation_attribution,
            )

            propagated_scores = propagate_risk_scores(
                base_scores,
                funding_graph,
                co_trade_graph=co_trade_graph,
                alpha=propagation_alpha,
            )
            wallet_propagated = propagated_scores.get(wallet, 0.0)

            if wallet_propagated > 0.0:
                raw_contributors = propagation_attribution(
                    wallet,
                    base_scores,
                    funding_graph,
                    co_trade_graph=co_trade_graph,
                    alpha=propagation_alpha,
                    top_n=top_n,
                )
                propagation_path = PropagationPath(
                    propagated_risk=round(wallet_propagated, 4),
                    contributors=[
                        PropagationContributor(
                            source_wallet=c["source_wallet"],
                            base_score=c["base_score"],
                            ppr_weight=c["ppr_weight"],
                            contribution=c["contribution"],
                            fraction=c["fraction"],
                        )
                        for c in raw_contributors
                    ],
                )

        return ForensicReport(
            wallet=wallet,
            asset_pair=asset_pair,
            risk_score=risk_score,
            shap_explanations=shap_explanations,
            causal_attribution=causal_attribution,
            propagation_path=propagation_path,
        )


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def write_report_secure(path: str, content: str) -> None:
    """Write *content* to *path* with restrictive permissions (0o600).

    Parent directories are created automatically.  The file is opened with
    ``os.O_CREAT | os.O_WRONLY | os.O_TRUNC`` so the mode is set atomically
    on creation rather than via a subsequent chmod.
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(dest), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
    except Exception:
        # Ensure fd is not leaked when os.fdopen raises
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def write_csv_report(path: str, report: ForensicReport) -> None:
    """Write *report* as a flat CSV to *path* with restrictive permissions.

    Columns: wallet, asset_pair, risk_score, feature, shap_value,
    shap_contribution.  One row is emitted per SHAP feature; wallets with
    no SHAP explanations get a single row with empty feature/shap fields.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(report.to_csv_rows())
    write_report_secure(path, buf.getvalue())
