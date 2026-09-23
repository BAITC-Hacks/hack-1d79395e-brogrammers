"""Louvain communities within each weak component of the directed graph."""

from __future__ import annotations

import networkx as nx
import pandas as pd

from graf.config import RANDOM_SEED


ROLE_COUNTS = (
    "coordinator", "consolidator", "distributor",
    "transit", "terminal", "payer",
)
CLUSTER_COLUMNS = (
    "cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids",
    "hypothesis", "fingerprints", "n_coordinator", "n_consolidator",
    "n_distributor", "n_transit", "n_terminal", "n_payer",
    "tracked_kzt_internal",
)


def undirected_amount_projection(graph: nx.DiGraph) -> nx.Graph:
    """Project directed transfers, summing amounts in both directions."""
    projected = nx.Graph()
    projected.add_nodes_from(graph.nodes)
    for src, dst, attrs in graph.edges(data=True):
        amount = float(attrs.get("sum_kzt", 0.0))
        if projected.has_edge(src, dst):
            projected[src][dst]["sum_kzt"] += amount
        else:
            projected.add_edge(src, dst, sum_kzt=amount)
    return projected


def louvain_clusters(
    graph: nx.DiGraph, *, seed: int = RANDOM_SEED
) -> dict[int, int]:
    """Assign every gid to one community; IDs follow descending size."""
    undirected = undirected_amount_projection(graph)
    communities: list[set[int]] = []
    for component in nx.weakly_connected_components(graph):
        if len(component) == 1:
            communities.append(set(component))
            continue
        subgraph = undirected.subgraph(component)
        communities.extend(
            set(group)
            for group in nx.community.louvain_communities(
                subgraph, weight="sum_kzt", seed=seed
            )
        )
    communities.sort(key=lambda group: (-len(group), min(group)))
    return {
        int(gid): cluster_id
        for cluster_id, group in enumerate(communities)
        for gid in group
    }


def summarize_clusters(
    features: pd.DataFrame, edges: pd.DataFrame
) -> pd.DataFrame:
    """Compute contract columns from the current community assignments."""
    gid_to_cluster = features.set_index("gid")["cluster_id"]
    internal = edges[["src", "dst", "sum_kzt"]].copy()
    internal["cluster_id"] = internal["src"].map(gid_to_cluster)
    internal = internal.loc[
        internal["cluster_id"].eq(internal["dst"].map(gid_to_cluster))
    ].copy()
    amounts = internal.groupby("cluster_id")["sum_kzt"].sum().to_dict()
    if "tracked_kzt" in edges:
        internal["tracked_kzt"] = edges.loc[internal.index, "tracked_kzt"].fillna(0.0)
        tracked = internal.groupby("cluster_id")["tracked_kzt"].sum().to_dict()
    else:
        tracked = {}

    rows = []
    for cluster_id, members in features.groupby("cluster_id", sort=True):
        ordering = (
            ["priority_score", "gid"] if "priority_score" in members else ["gid"]
        )
        ascending = [False, True] if len(ordering) == 2 else [True]
        top = members.sort_values(ordering, ascending=ascending, kind="stable").head(5)
        n_seed = int(members["is_seed"].sum())
        amount = float(amounts.get(cluster_id, 0.0))
        row = {
            "cluster_id": int(cluster_id),
            "n_nodes": int(len(members)),
            "n_seed": n_seed,
            "sum_kzt_internal": amount,
            "top_gids": ";".join(top["gid"].astype(str)),
            "hypothesis": (
                f"Признаки связанной группы: {len(members)} узлов, {n_seed} seed, "
                f"внутренний оборот {amount:,.0f} ₸."
            ),
            "fingerprints": "",
            "tracked_kzt_internal": float(tracked.get(cluster_id, 0.0)),
        }
        for role in ROLE_COUNTS:
            row[f"n_{role}"] = (
                int(members["role"].eq(role).sum()) if "role" in members else 0
            )
        rows.append(row)
    return pd.DataFrame(rows, columns=CLUSTER_COLUMNS)


def run(context: dict) -> None:
    """Attach community IDs to features and their summary to context."""
    features = context["features"].copy()
    graph = context["graph"]
    missing = set(map(int, features["gid"])) - set(map(int, graph.nodes))
    if missing:
        raise ValueError(f"{len(missing)} feature gids are absent from graph")
    mapping = louvain_clusters(graph)
    features["cluster_id"] = features["gid"].map(mapping).astype("int64")
    context["features"] = features
    context["clusters"] = summarize_clusters(features, context["edges"])
