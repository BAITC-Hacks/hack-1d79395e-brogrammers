"""Baseline graph metrics; A1 extends this module."""

import numpy as np


def compute_features(edges, nodes, graph):
    """Keep every node, including seed clients without observed edges."""
    frame = nodes[["gid", "depth", "is_seed"]].copy()
    for column, values in (
        ("in_deg", dict(graph.in_degree())),
        ("out_deg", dict(graph.out_degree())),
        ("in_tx", dict(graph.in_degree(weight="n_tx"))),
        ("out_tx", dict(graph.out_degree(weight="n_tx"))),
        ("in_kzt", dict(graph.in_degree(weight="sum_kzt"))),
        ("out_kzt", dict(graph.out_degree(weight="sum_kzt"))),
    ):
        frame[column] = frame["gid"].map(values).fillna(0)
    for column in ("in_deg", "out_deg", "in_tx", "out_tx"):
        frame[column] = frame[column].astype("int64")
    frame["pass_through"] = np.where(
        frame["in_kzt"] > 0,
        frame["out_kzt"] / frame["in_kzt"].replace(0, np.nan),
        np.nan,
    )
    return frame
