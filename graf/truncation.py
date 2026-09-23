"""Empirical calibration for accounts at the four-hop observation boundary."""

from __future__ import annotations

import numpy as np
import pandas as pd


BUCKETS = ("1", "2-3", "4-10", ">10")


def _bucket(in_tx: pd.Series) -> pd.Series:
    return pd.Series(
        np.select(
            [in_tx.eq(1), in_tx.between(2, 3), in_tx.between(4, 10), in_tx.gt(10)],
            BUCKETS,
            default="0",
        ),
        index=in_tx.index,
    )


def calibrate(features: pd.DataFrame) -> pd.DataFrame:
    """Estimate P(observed forwarding) by incoming transaction count.

    Only non-seed accounts at depths 1–3 with incoming edges provide a
    comparable, fully observed training population. Empty buckets receive the
    population mean as a fallback and retain ``n=0`` for transparency.
    """
    sample = features.loc[
        (~features["is_seed"].astype(bool))
        & features["depth"].between(1, 3)
        & features["in_deg"].gt(0)
    ].copy()
    sample["bucket"] = _bucket(sample["in_tx"])
    sample["forwarded"] = sample["out_deg"].gt(0)
    fallback = float(sample["forwarded"].mean()) if len(sample) else 0.0

    by_bucket = sample.groupby("bucket", sort=False)["forwarded"].agg(["size", "mean"])
    return pd.DataFrame(
        {
            "bucket": BUCKETS,
            "n": [int(by_bucket.loc[b, "size"]) if b in by_bucket.index else 0 for b in BUCKETS],
            "p_forward": [
                float(by_bucket.loc[b, "mean"]) if b in by_bucket.index else fallback
                for b in BUCKETS
            ],
        }
    )


def apply(features: pd.DataFrame, calibration: pd.DataFrame) -> pd.DataFrame:
    """Flag all depth-4 accounts and attach calibrated forwarding estimates."""
    result = features.copy()
    result["truncated"] = result["depth"].eq(4)
    result["p_forward"] = 0.0
    probabilities = calibration.set_index("bucket")["p_forward"].to_dict()
    total_n = calibration["n"].sum()
    fallback = (
        float((calibration["n"] * calibration["p_forward"]).sum() / total_n)
        if total_n > 0
        else 0.0
    )
    is_boundary = result["truncated"]
    result.loc[is_boundary, "p_forward"] = (
        _bucket(result.loc[is_boundary, "in_tx"]).map(probabilities).fillna(fallback).to_numpy()
    )
    return result
