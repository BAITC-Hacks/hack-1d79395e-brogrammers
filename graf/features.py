"""Structural features for every account in the supplied node table."""

from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd


def _hhi_by_account(edges: pd.DataFrame, account: str) -> pd.Series:
    """Sum squared amount shares across distinct counterparties."""
    if edges.empty:
        return pd.Series(dtype=float)

    # Group pairs here even if a caller passes unaggregated edges. HHI must
    # measure counterparty concentration, not concentration across rows.
    pairs = edges.groupby(["src", "dst"], sort=False)["sum_kzt"].sum().reset_index()
    totals = pairs.groupby(account, sort=False)["sum_kzt"].transform("sum")
    shares = pairs["sum_kzt"].div(totals.where(totals.ne(0)))
    return shares.pow(2).groupby(pairs[account], sort=False).sum()


def compute_features(
    edges: pd.DataFrame, nodes: pd.DataFrame, graph: nx.DiGraph
) -> pd.DataFrame:
    """Calculate directed, unweighted graph features for all listed gids.

    The node table is authoritative: nodes omitted by the edge list, including
    isolated seed accounts, remain in the result. A seed's pass-through ratio
    is calculated when possible, but role assignment must not use it because
    the extract does not show all incoming transfers to seeds.
    """
    if not nodes["gid"].is_unique:
        raise ValueError("nodes.gid must be unique")

    all_gids = set(nodes["gid"].tolist())
    unknown = set(graph.nodes) - all_gids
    if unknown:
        raise ValueError("graph contains gids absent from nodes")

    full_graph = graph.copy()
    full_graph.add_nodes_from(nodes["gid"].tolist())

    result = nodes[["gid", "depth", "is_seed"]].copy()
    for name, values, dtype in (
        ("in_deg", dict(full_graph.in_degree()), int),
        ("out_deg", dict(full_graph.out_degree()), int),
        ("in_tx", dict(full_graph.in_degree(weight="n_tx")), int),
        ("out_tx", dict(full_graph.out_degree(weight="n_tx")), int),
        ("in_kzt", dict(full_graph.in_degree(weight="sum_kzt")), float),
        ("out_kzt", dict(full_graph.out_degree(weight="sum_kzt")), float),
    ):
        result[name] = result["gid"].map(values).fillna(0).astype(dtype)

    result["in_hhi"] = result["gid"].map(_hhi_by_account(edges, "dst")).fillna(0.0)
    result["out_hhi"] = result["gid"].map(_hhi_by_account(edges, "src")).fillna(0.0)

    result["pass_through"] = np.divide(
        result["out_kzt"].to_numpy(dtype=float),
        result["in_kzt"].to_numpy(dtype=float),
        out=np.full(len(result), np.nan, dtype=float),
        where=result["in_kzt"].to_numpy(dtype=float) > 0,
    )

    # Direction matters for brokerage; amounts do not weight this metric.
    betweenness = nx.betweenness_centrality(full_graph, normalized=True, weight=None)
    result["betweenness"] = result["gid"].map(betweenness).fillna(0.0)
    return result
