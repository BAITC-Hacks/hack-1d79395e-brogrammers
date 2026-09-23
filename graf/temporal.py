"""Date-granularity transaction features.

Same-day incoming and outgoing transfers count as temporally compatible.
The extract contains dates only, so their order within a day is unknown.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from graf.config import FAST_DAYS, NEAR_THRESHOLD


def add_temporal(
    features: pd.DataFrame, tx: pd.DataFrame, edges: pd.DataFrame
) -> pd.DataFrame:
    """Add timing and threshold metrics without dropping isolated accounts.

    ``near_threshold_share`` is the fraction of *transactions* in the closed
    NEAR_THRESHOLD amount interval. ``fast_out_share`` instead weights by
    outgoing amount, as required by the team plan.
    """
    result = features.copy()
    for col in ("fast_out_share", "near_threshold_share", "payer_one_off_share"):
        result[col] = 0.0
    for col in ("max_sync_payers", "active_in_days"):
        result[col] = 0

    if not edges.empty:
        pair_tx = edges.groupby(["src", "dst"], sort=False)["n_tx"].sum().reset_index()
        one_off = pair_tx.assign(one_off=pair_tx["n_tx"].eq(1))
        one_off_share = one_off.groupby("dst")["one_off"].mean()
        result["payer_one_off_share"] = (
            result["gid"].map(one_off_share).fillna(0.0).astype(float)
        )

    if tx.empty:
        return result

    dated = tx[["src", "dst", "date", "sum_kzt"]].copy()
    dated["date"] = pd.to_datetime(dated["date"]).dt.normalize()
    dated["day_number"] = dated["date"].to_numpy(dtype="datetime64[D]").astype("int64")

    active = dated.groupby("dst")["date"].nunique()
    sync = dated.groupby(["dst", "date"])["src"].nunique().groupby(level=0).max()
    result["active_in_days"] = result["gid"].map(active).fillna(0).astype(int)
    result["max_sync_payers"] = result["gid"].map(sync).fillna(0).astype(int)

    low, high = NEAR_THRESHOLD
    near_counts = dated["sum_kzt"].between(low, high, inclusive="both")
    near_share = near_counts.groupby(dated["src"]).mean()
    result["near_threshold_share"] = result["gid"].map(near_share).fillna(0.0)

    incoming_days = {
        gid: np.sort(group["day_number"].unique())
        for gid, group in dated.groupby("dst", sort=False)
    }
    fast_share: dict[int, float] = {}
    for gid, outgoing in dated.groupby("src", sort=False):
        dates = incoming_days.get(gid)
        if dates is None or len(dates) == 0:
            continue
        out_days = outgoing["day_number"].to_numpy(dtype="int64")
        last_in_idx = np.searchsorted(dates, out_days, side="right") - 1
        valid = last_in_idx >= 0
        lag = np.full(len(out_days), FAST_DAYS + 1, dtype="int64")
        lag[valid] = out_days[valid] - dates[last_in_idx[valid]]
        qualifying = valid & (lag >= 0) & (lag <= FAST_DAYS)
        amounts = outgoing["sum_kzt"].to_numpy(dtype=float)
        total = amounts.sum()
        fast_share[gid] = float(amounts[qualifying].sum() / total) if total > 0 else 0.0
    result["fast_out_share"] = result["gid"].map(fast_share).fillna(0.0)
    return result
