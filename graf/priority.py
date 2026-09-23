"""Explainable ranking from roles, attributed money, brokerage, and timing."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from graf import resilience
from graf.config import MULT, PRIORITY_WEIGHTS, ROLE_WEIGHT, SYNC_MIN_PAYERS, TOP_N
from graf.flow import money_paths


def _values(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column in frame:
        return pd.to_numeric(frame[column], errors="coerce").fillna(default)
    return pd.Series(default, index=frame.index, dtype=float)


def _percentile(values: pd.Series) -> pd.Series:
    """Pandas average-rank percentile, including ties, in the 0–1 interval."""
    return values.rank(method="average", pct=True).fillna(0.0)


def _first_counter(value: object) -> str:
    if pd.isna(value) or not str(value).strip():
        return "только даты и 4 колена"
    return str(value).split(" | ", 1)[0].strip()


def score_priority(
    features: pd.DataFrame, brokerage: Mapping[int, float]
) -> pd.DataFrame:
    """Attach each formula component, multipliers, rank, and explanation."""
    result = features.copy()
    result["prio_role"] = result["role"].map(ROLE_WEIGHT).fillna(0.0).astype(float)
    result["prio_money"] = 0.5 * _percentile(_values(result, "tracked_in")) + (
        0.5 * _percentile(_values(result, "seed_exp_chrono"))
    )
    result["prio_brokerage"] = (
        result["gid"].map(brokerage).fillna(0.0).astype(float).clip(0.0, 1.0)
    )
    eligible_broker = _values(result, "in_deg").gt(0) & _values(result, "out_deg").gt(0)
    result.loc[~eligible_broker, "prio_brokerage"] = 0.0
    volume = np.log1p(_values(result, "in_kzt") + _values(result, "out_kzt"))
    result["prio_volume"] = _percentile(volume)
    sync = _values(result, "max_sync_payers").ge(SYNC_MIN_PAYERS).astype(float)
    result["prio_temporal"] = np.maximum(_values(result, "fast_out_share"), sync).clip(0.0, 1.0)

    is_seed = result["is_seed"].astype(bool)
    is_payer = result["role"].eq("payer")
    excluded = result.get("excluded", pd.Series(False, index=result.index)).astype(bool)
    seed_above_bottom = result.get(
        "seed_above_bottom", pd.Series(False, index=result.index)
    ).astype(bool)
    external = result.get("visibility", pd.Series("full", index=result.index)).eq(
        "external_funding"
    )
    no_chrono = ~is_seed & _values(result, "seed_exp_chrono").eq(0)
    multiplier = np.ones(len(result), dtype=float)
    for flag, key in (
        (no_chrono, "no_chrono"),
        (external, "external_funding"),
        (is_seed, "seed"),
        (seed_above_bottom, "seed_above_bottom"),
        (is_payer, "payer"),
        (excluded, "excluded"),
    ):
        multiplier *= np.where(flag.to_numpy(), MULT[key], 1.0)
    result["prio_multiplier"] = multiplier
    weighted = sum(
        PRIORITY_WEIGHTS[name] * result[f"prio_{name}"]
        for name in ("role", "money", "brokerage", "volume", "temporal")
    )
    result["priority_score"] = (weighted * multiplier).clip(0.0, 1.0)

    labels = {
        "role": "роль", "money": "деньги курьеров", "brokerage": "связность",
        "volume": "оборот", "temporal": "время",
    }
    why = []
    for row in result.itertuples(index=False):
        components = [
            (PRIORITY_WEIGHTS[name] * getattr(row, f"prio_{name}"), labels[name])
            for name in labels
        ]
        components.sort(key=lambda pair: (-pair[0], pair[1]))
        major = ", ".join(f"{label} {value:.2f}" for value, label in components[:3])
        counter = _first_counter(getattr(row, "counter_signals", ""))
        role_label = getattr(row, "role_label", str(row.role))
        why.append(
            f"{role_label}: {major}; множитель {row.prio_multiplier:.2f}. "
            f"Контр: {counter}."
        )
    result["why"] = why

    order = result.sort_values(
        ["priority_score", "gid"], ascending=[False, True], kind="stable"
    ).index
    result.loc[order, "rank"] = range(1, len(result) + 1)
    result["rank"] = result["rank"].astype(int)
    return result


def run(context: dict) -> None:
    """Compute A4 priority, then refresh paths for the final eligible top 30."""
    features = context["features"]
    seeds = set(map(int, features.loc[features["is_seed"], "gid"]))
    candidates = set(map(
        int,
        features.loc[
            features["in_deg"].gt(0) & features["out_deg"].gt(0), "gid"
        ],
    ))
    brokerage = resilience.single_node_loss(
        context["graph"], seeds, candidates=candidates
    )
    result = score_priority(features, brokerage)
    context["features"] = result

    eligible = result.loc[
        ~result["role"].eq("payer") & ~result["excluded"].astype(bool)
    ].sort_values("rank", kind="stable")
    targets = eligible["gid"].head(TOP_N)
    out_dir = Path(context["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    money_paths(context["tx"], seeds, targets).to_csv(
        out_dir / "paths.csv", index=False
    )
