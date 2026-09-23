"""Observed seed reach and structural node-removal scenarios."""

from __future__ import annotations

from collections import deque
from pathlib import Path
import random

import networkx as nx
import pandas as pd

from graf.config import RANDOM_SEED


CURVE_COLUMNS = (
    "strategy", "n_removed", "seed_reach_share", "largest_wcc",
)
REMOVAL_COUNTS = (0, 5, 10, 20, 23, 50)


def _seed_set(graph: nx.DiGraph, seeds: set[int] | None) -> set[int]:
    if seeds is None:
        return {
            int(gid) for gid, attrs in graph.nodes(data=True)
            if attrs.get("is_seed", False)
        }
    return set(map(int, seeds))


def seed_reach(
    graph: nx.DiGraph,
    seeds: set[int] | None = None,
    removed: set[int] | None = None,
) -> set[int]:
    """Non-seed gids reachable from any remaining seed along directed edges."""
    seed_gids = _seed_set(graph, seeds)
    removed_gids = set(map(int, removed or ()))
    frontier = deque(
        gid for gid in seed_gids if gid in graph and gid not in removed_gids
    )
    seen = set(frontier)
    while frontier:
        src = frontier.popleft()
        for dst in graph.successors(src):
            if dst not in removed_gids and dst not in seen:
                seen.add(dst)
                frontier.append(dst)
    return seen - seed_gids


def single_node_loss(
    graph: nx.DiGraph,
    seeds: set[int] | None = None,
    candidates: set[int] | None = None,
) -> dict[int, float]:
    """Share of original reachable non-seeds lost *beyond* the removed node.

    Excluding the removed node itself makes the score measure brokerage rather
    than merely whether that account was reachable.
    """
    seed_gids = _seed_set(graph, seeds)
    baseline = seed_reach(graph, seed_gids)
    if candidates is None:
        candidates = {
            int(gid) for gid in graph
            if graph.in_degree(gid) > 0 and graph.out_degree(gid) > 0
        }
    if not baseline:
        return {int(gid): 0.0 for gid in candidates}
    losses = {}
    denominator = len(baseline)
    for gid in sorted(map(int, candidates)):
        if gid not in graph:
            losses[gid] = 0.0
            continue
        after = seed_reach(graph, seed_gids, {gid})
        losses[gid] = len((baseline - after) - {gid}) / denominator
    return losses


def _largest_wcc(graph: nx.DiGraph, removed: set[int]) -> int:
    remaining = graph.subgraph(set(graph.nodes) - removed)
    return max((len(group) for group in nx.weakly_connected_components(remaining)), default=0)


def removal_curve(
    graph: nx.DiGraph,
    features: pd.DataFrame,
    *,
    n_values: tuple[int, ...] = REMOVAL_COUNTS,
    random_seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """Compare seed reach after removing top non-seed nodes by each strategy."""
    seeds = set(map(int, features.loc[features["is_seed"], "gid"]))
    baseline = seed_reach(graph, seeds)
    denominator = len(baseline)
    candidates = features.loc[~features["is_seed"]].copy()
    rankings = {}
    for strategy in ("priority", "betweenness", "out_deg", "in_deg"):
        column = "priority_score" if strategy == "priority" else strategy
        rankings[strategy] = candidates.sort_values(
            [column, "gid"], ascending=[False, True], kind="stable"
        )["gid"].astype(int).tolist()
    rankings["random"] = candidates["gid"].astype(int).sort_values().tolist()
    random.Random(random_seed).shuffle(rankings["random"])

    rows = []
    for strategy, ordered in rankings.items():
        for count in n_values:
            removed = set(ordered[: max(0, count)])
            reached = seed_reach(graph, seeds, removed)
            rows.append({
                "strategy": strategy,
                "n_removed": len(removed),
                "seed_reach_share": (
                    len(reached & baseline) / denominator if denominator else 0.0
                ),
                "largest_wcc": _largest_wcc(graph, removed),
            })
    rows.append({
        "strategy": "all_seeds",
        "n_removed": len(seeds),
        "seed_reach_share": 0.0,
        "largest_wcc": _largest_wcc(graph, seeds),
    })
    return pd.DataFrame(rows, columns=CURVE_COLUMNS)


def run(context: dict) -> None:
    """Write out/resilience.csv after priority ranks have been assigned."""
    curve = removal_curve(context["graph"], context["features"])
    context["resilience"] = curve
    out_dir = Path(context["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    curve.to_csv(out_dir / "resilience.csv", index=False)
