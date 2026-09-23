"""Interpretable motifs and cautious hypotheses for each cluster."""

from __future__ import annotations

from collections import defaultdict

import networkx as nx
import pandas as pd

from graf.clusters import ROLE_COUNTS


FINGERPRINT_ORDER = (
    "fan_in", "fan_out", "chain", "scatter_gather", "cycle", "fragmentation",
)


def chronological_transit_chain(
    transactions: pd.DataFrame, transit_gids: set[int]
) -> tuple[int, int, int] | None:
    """Find three distinct transit accounts linked by nondecreasing dates."""
    if len(transit_gids) < 3 or transactions.empty:
        return None
    candidate = transactions.loc[
        transactions["src"].isin(transit_gids)
        & transactions["dst"].isin(transit_gids),
        ["src", "dst", "date"],
    ].copy()
    if candidate.empty:
        return None
    candidate["date"] = pd.to_datetime(candidate["date"])
    incoming: dict[int, list[tuple[int, pd.Timestamp]]] = defaultdict(list)
    outgoing: dict[int, list[tuple[int, pd.Timestamp]]] = defaultdict(list)
    for row in candidate.itertuples(index=False):
        src, dst = int(row.src), int(row.dst)
        incoming[dst].append((src, row.date))
        outgoing[src].append((dst, row.date))
    for middle in sorted(transit_gids):
        for source, first_day in incoming.get(middle, ()):
            for target, second_day in outgoing.get(middle, ()):
                if source != target and first_day <= second_day:
                    return source, middle, target
    return None


def _scatter_gather(
    graph: nx.DiGraph, distributors: set[int], consolidators: set[int]
) -> tuple[int, int, int] | None:
    """Return a distributor/consolidator pair with ≥3 shared intermediates."""
    for source in sorted(distributors):
        sent_to = set(graph.successors(source)) - {source}
        for target in sorted(consolidators):
            if source == target:
                continue
            mids = (sent_to & set(graph.predecessors(target))) - {source, target}
            if len(mids) >= 3:
                return source, target, len(mids)
    return None


def describe_cluster(
    cluster_id: int,
    members: pd.DataFrame,
    graph: nx.DiGraph,
    transactions: pd.DataFrame,
    internal_kzt: float,
) -> tuple[str, str]:
    """Return semicolon separated motif names and a numerical hypothesis."""
    gids = set(map(int, members["gid"]))
    subgraph = graph.subgraph(gids)
    roles = members.set_index("gid")["role"].to_dict()
    consolidators = {int(gid) for gid, role in roles.items() if role == "consolidator"}
    distributors = {int(gid) for gid, role in roles.items() if role == "distributor"}
    transit = {int(gid) for gid, role in roles.items() if role == "transit"}
    found: dict[str, str] = {}

    for gid in sorted(consolidators):
        n = subgraph.in_degree(gid)
        if n >= 3:
            found["fan_in"] = f"сбор у {gid} от {n} плательщиков внутри кластера"
            break
    for gid in sorted(distributors):
        n = subgraph.out_degree(gid)
        if n >= 10:
            found["fan_out"] = f"рассылка от {gid} к {n} получателям внутри кластера"
            break

    chain = chronological_transit_chain(transactions, transit)
    if chain is not None:
        found["chain"] = f"хронологическая цепь транзита {chain[0]}→{chain[1]}→{chain[2]}"

    scatter = _scatter_gather(subgraph, distributors, consolidators)
    if scatter is not None:
        source, target, n = scatter
        found["scatter_gather"] = (
            f"путь {source}→{n} промежуточных→{target}"
        )

    if subgraph.number_of_edges() >= 2:
        cycle = next(nx.simple_cycles(subgraph, length_bound=6), None)
        if cycle:
            found["cycle"] = (
                f"возвратный контур из {len(cycle)} узлов (например, {cycle[0]})"
            )

    near_threshold = int(
        members.get(
            "near_threshold_share", pd.Series(0.0, index=members.index)
        ).fillna(0.0).ge(0.5).sum()
    )
    if near_threshold >= 2:
        found["fragmentation"] = (
            f"у {near_threshold} узлов ≥50% исходящих переводов близки к порогу"
        )

    names = [name for name in FINGERPRINT_ORDER if name in found]
    count = len(members)
    n_seed = int(members["is_seed"].sum())
    evidence = "; ".join(found[name] for name in names)
    hypothesis = (
        f"Признаки структуры кластера {cluster_id}: {count} узлов, {n_seed} seed, "
        f"внутренний оборот {internal_kzt:,.0f} ₸"
        + (f"; {evidence}." if evidence else "; выраженных схем по заданным правилам нет.")
    )
    return ";".join(names), hypothesis


def run(context: dict) -> None:
    """Enrich the cluster summary after roles and Louvain assignment."""
    features = context["features"]
    clusters = context["clusters"].copy()
    graph = context["graph"]
    tx = context.get("tx", pd.DataFrame(columns=["src", "dst", "date"]))
    gid_to_cluster = features.set_index("gid")["cluster_id"]
    inside = tx.loc[
        tx["src"].map(gid_to_cluster).eq(tx["dst"].map(gid_to_cluster))
    ].copy()
    inside["cluster_id"] = inside["src"].map(gid_to_cluster)
    tx_by_cluster = {int(cid): group for cid, group in inside.groupby("cluster_id")}

    for index, row in clusters.iterrows():
        cid = int(row["cluster_id"])
        members = features.loc[features["cluster_id"].eq(cid)]
        names, hypothesis = describe_cluster(
            cid, members, graph, tx_by_cluster.get(cid, tx.iloc[0:0]),
            float(row["sum_kzt_internal"]),
        )
        clusters.at[index, "fingerprints"] = names
        clusters.at[index, "hypothesis"] = hypothesis
        for role in ROLE_COUNTS:
            clusters.at[index, f"n_{role}"] = int(members["role"].eq(role).sum())
    context["clusters"] = clusters
