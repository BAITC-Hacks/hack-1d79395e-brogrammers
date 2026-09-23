"""Contract exports for the A1 pipeline and later analytic stages."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from graf.config import (
    CONF_LEVELS,
    CONS_MIN_IN_DEG,
    DIST_MIN_OUT_DEG,
    RANDOM_SEED,
    TOP_N,
    TRANSIT_PT,
)


ROLE_LABELS = {
    "coordinator": "кандидат в организаторы",
    "consolidator": "признаки точки консолидации",
    "distributor": "признаки веерного распределения",
    "transit": "признаки транзитного счёта",
    "terminal": "конечный получатель в пределах выгрузки",
    "peripheral": "периферия, признаков роли не выявлено",
    "payer": "разовый плательщик (возможный покупатель/потерпевший)",
}

REQUIRED_NODES = (
    "gid", "role", "role_score", "cluster_id", "priority_score", "evidence"
)
OPTIONAL_NODES = (
    "rank", "role_label", "role_alt", "ambiguous", "confidence_level",
    "visibility", "excluded", "aggregator_like", "seed_above_bottom",
    "is_seed", "truncated", "depth", "in_deg", "out_deg", "in_tx",
    "out_tx", "in_kzt", "out_kzt", "pass_through", "in_hhi",
    "out_hhi", "betweenness", "from_key", "to_key", "fast_out_share",
    "max_sync_payers", "near_threshold_share", "p_forward", "tracked_in",
    "tracked_out", "tracked_share_in", "tracked_out_share", "tracked_kept",
    "seed_exp_topo", "seed_exp_chrono", "seed_exp_fast", "signals",
    "counter_signals", "prio_role", "prio_money", "prio_brokerage",
    "prio_volume", "prio_temporal", "prio_multiplier",
)


def _preliminary_role(row) -> str:
    if row.in_deg >= CONS_MIN_IN_DEG:
        return "consolidator"
    if row.out_deg >= DIST_MIN_OUT_DEG:
        return "distributor"
    if (
        not row.is_seed
        and row.in_deg > 0
        and row.out_deg > 0
        and TRANSIT_PT[0] <= row.pass_through <= TRANSIT_PT[1]
    ):
        return "transit"
    if row.depth <= 3 and row.in_deg > 0 and row.out_deg == 0:
        return "terminal"
    return "peripheral"


def _cluster_ids(graph: nx.DiGraph) -> dict[int, int]:
    components = sorted(
        nx.weakly_connected_components(graph),
        key=lambda members: (-len(members), min(members)),
    )
    return {
        int(gid): cluster_id
        for cluster_id, members in enumerate(components)
        for gid in members
    }


def _ensure_columns(roles: pd.DataFrame) -> pd.DataFrame:
    """Keep computed later-stage values; fill only fields not available in A1."""
    defaults = {
        "role_alt": "", "ambiguous": False, "excluded": False,
        "aggregator_like": False, "seed_above_bottom": False,
        "truncated": False, "in_deg": 0, "out_deg": 0, "in_tx": 0,
        "out_tx": 0, "in_kzt": 0.0, "out_kzt": 0.0,
        "pass_through": np.nan, "in_hhi": 0.0, "out_hhi": 0.0,
        "betweenness": 0.0, "from_key": 0, "to_key": 0,
        "fast_out_share": 0.0, "max_sync_payers": 0,
        "near_threshold_share": 0.0, "p_forward": 0.0,
        "tracked_in": 0.0, "tracked_out": 0.0,
        "tracked_share_in": 0.0, "tracked_out_share": 0.0,
        "tracked_kept": 0.0, "seed_exp_topo": 0,
        "seed_exp_chrono": 0, "seed_exp_fast": 0,
        "signals": "", "counter_signals": "", "prio_role": 0.0,
        "prio_money": 0.0, "prio_brokerage": 0.0,
        "prio_volume": 0.0, "prio_temporal": 0.0,
        "prio_multiplier": 1.0,
    }
    for column, default in defaults.items():
        if column not in roles:
            roles[column] = default
    if "role_label" not in roles:
        roles["role_label"] = roles["role"].map(ROLE_LABELS)
    if "confidence_level" not in roles:
        low, high = CONF_LEVELS
        roles["confidence_level"] = np.select(
            [roles["role_score"].ge(high), roles["role_score"].ge(low)],
            ["высокая", "средняя"], default="низкая",
        )
    if "visibility" not in roles:
        roles["visibility"] = np.select(
            [roles["depth"].eq(4), roles["is_seed"].astype(bool)],
            ["out_unseen", "in_unseen_seed"], default="full",
        )
    return roles


def _prepare_roles(features: pd.DataFrame, graph: nx.DiGraph) -> pd.DataFrame:
    roles = features.copy()
    if "cluster_id" not in roles:
        roles["cluster_id"] = roles["gid"].map(_cluster_ids(graph))
    if roles["cluster_id"].isna().any():
        raise ValueError("some gids are absent from graph clusters")
    roles["cluster_id"] = roles["cluster_id"].astype("int64")
    if "role" not in roles:
        roles["role"] = [_preliminary_role(row) for row in roles.itertuples(index=False)]
    if "role_score" not in roles:
        roles["role_score"] = 0.5
    if "priority_score" not in roles:
        roles["priority_score"] = (
            roles["in_deg"] + roles["out_deg"]
        ).rank(method="average", pct=True)
    roles = _ensure_columns(roles)
    if "evidence" not in roles:
        roles["evidence"] = [
            f"{row.role_label}: входящих {row.in_deg}, исходящих {row.out_deg}, "
            f"получено {row.in_kzt:,.0f} ₸ (предварительно)"
            for row in roles.itertuples(index=False)
        ]
    if "rank" not in roles:
        order = roles.sort_values(
            ["priority_score", "gid"], ascending=[False, True], kind="stable"
        ).index
        roles.loc[order, "rank"] = range(1, len(roles) + 1)
    roles["rank"] = roles["rank"].astype(int)
    return roles.sort_values("gid", kind="stable")


def _clusters_table(
    roles: pd.DataFrame,
    edges: pd.DataFrame,
    cluster_summary: pd.DataFrame | None = None,
) -> pd.DataFrame:
    gid_to_cluster = roles.set_index("gid")["cluster_id"]
    edge_clusters = edges[["src", "dst", "sum_kzt"]].copy()
    edge_clusters["src_cluster"] = edge_clusters["src"].map(gid_to_cluster)
    edge_clusters["dst_cluster"] = edge_clusters["dst"].map(gid_to_cluster)
    internal = edge_clusters.loc[
        edge_clusters["src_cluster"].eq(edge_clusters["dst_cluster"])
    ]
    sum_internal = internal.groupby("src_cluster")["sum_kzt"].sum().to_dict()
    if "tracked_kzt" in edges:
        edge_clusters["tracked_kzt"] = edges["tracked_kzt"]
        tracked_internal = edge_clusters.loc[
            edge_clusters["src_cluster"].eq(edge_clusters["dst_cluster"])
        ].groupby("src_cluster")["tracked_kzt"].sum().to_dict()
    else:
        tracked_internal = {}

    rows = []
    for cluster_id, members in roles.groupby("cluster_id", sort=True):
        ordered = members.sort_values("rank", kind="stable")
        n_seed = int(members["is_seed"].sum())
        amount = float(sum_internal.get(cluster_id, 0.0))
        row = {
            "cluster_id": int(cluster_id),
            "n_nodes": int(len(members)),
            "n_seed": n_seed,
            "sum_kzt_internal": amount,
            "top_gids": ";".join(str(int(gid)) for gid in ordered["gid"].head(5)),
            "hypothesis": (
                f"Признаки связного фрагмента: {len(members)} узлов, "
                f"{n_seed} seed, внутренний оборот {amount:,.0f} ₸; нужна проверка."
            ),
            "fingerprints": "",
            "tracked_kzt_internal": float(tracked_internal.get(cluster_id, 0.0)),
        }
        for role in (
            "coordinator", "consolidator", "distributor", "transit", "terminal", "payer"
        ):
            row[f"n_{role}"] = int(members["role"].eq(role).sum())
        rows.append(row)
    columns = [
        "cluster_id", "n_nodes", "n_seed", "sum_kzt_internal",
        "top_gids", "hypothesis", "fingerprints", "n_coordinator",
        "n_consolidator", "n_distributor", "n_transit", "n_terminal",
        "n_payer", "tracked_kzt_internal",
    ]
    table = pd.DataFrame(rows, columns=columns)
    if cluster_summary is not None:
        summary = cluster_summary.set_index("cluster_id")
        if not summary.index.is_unique:
            raise ValueError("cluster_summary must contain unique cluster_id values")
        if set(summary.index) != set(table["cluster_id"]):
            raise ValueError("cluster_summary cluster IDs differ from nodes_roles")
        table = table.set_index("cluster_id")
        for column in summary.columns:
            # The cluster stage runs before priority. Recompute these gids from
            # the final rank rather than importing their provisional order.
            if column == "top_gids":
                continue
            replacement = summary[column].reindex(table.index)
            if column in table:
                table[column] = replacement.combine_first(table[column])
            else:
                table[column] = replacement
        table = table.reset_index()
    return table


def _day(value):
    return int(value) if pd.notna(value) else None

def _number(value, default: float = 0.0) -> float:
    return float(value) if pd.notna(value) else default


def _write_graph_json(
    roles: pd.DataFrame, edges: pd.DataFrame, graph: nx.DiGraph, out_dir: Path
) -> None:
    positions = nx.spring_layout(graph, seed=RANDOM_SEED)
    node_rows = []
    for row in roles.itertuples(index=False):
        x, y = positions[int(row.gid)]
        node_rows.append(
            {
                "id": str(int(row.gid)), "role": str(row.role),
                "role_label": str(row.role_label), "cluster_id": int(row.cluster_id),
                "priority_score": _number(row.priority_score), "rank": int(row.rank),
                "depth": int(row.depth), "is_seed": bool(row.is_seed),
                "visibility": str(row.visibility), "tracked_in": _number(row.tracked_in),
                "seed_exp_chrono": int(row.seed_exp_chrono),
                "x": float(x), "y": float(y),
            }
        )
    edge_rows = []
    for edge in edges.itertuples(index=False):
        edge_rows.append(
            {
                "src": str(int(edge.src)), "dst": str(int(edge.dst)),
                "sum_kzt": float(edge.sum_kzt), "n_tx": int(edge.n_tx),
                "tracked_kzt": _number(getattr(edge, "tracked_kzt", 0.0)),
                "first_day": _day(getattr(edge, "first_day", None)),
                "last_day": _day(getattr(edge, "last_day", None)),
            }
        )
    payload = {
        "meta": {
            "n_nodes": len(node_rows), "n_edges": len(edge_rows),
            "layout": "spring_layout", "seed": RANDOM_SEED,
        },
        "nodes": node_rows,
        "edges": edge_rows,
    }
    (out_dir / "graph.json").write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )


def _data_requests(roles: pd.DataFrame, top: pd.DataFrame) -> pd.DataFrame:
    requests = []

    def add(row, request: str, reason: str) -> None:
        requests.append({
            "gid": int(row.gid), "request": request, "reason": reason,
            "priority_score": float(row.priority_score),
        })

    for row in roles.loc[roles["is_seed"].astype(bool)].itertuples(index=False):
        add(
            row, "запросить входящие переводы",
            "seed: входящие за пределами исходящей выгрузки не видны",
        )
    boundary = roles.loc[
        roles["depth"].eq(4) & roles["p_forward"].ge(0.5)
        & roles["rank"].le(200)
    ]
    for row in boundary.itertuples(index=False):
        add(
            row, "запросить выписку исходящих",
            f"4-е колено обрывает исходящие; p_forward={row.p_forward:.0%}",
        )
    near = roles.loc[roles["near_threshold_share"].ge(0.5)]
    for row in near.itertuples(index=False):
        add(
            row, "запросить переводы < 5 000 ₸",
            f"{row.near_threshold_share:.0%} исходящих в интервале 5–7 тыс. ₸",
        )
    for row in top.itertuples(index=False):
        add(
            row, "запросить время транзакций для точного FlowTrace",
            f"ранг {row.rank}: в выгрузке есть даты, но нет времени",
        )
    columns = ["gid", "request", "reason", "priority_score"]
    return pd.DataFrame(requests, columns=columns).sort_values(
        ["priority_score", "gid", "request"],
        ascending=[False, True, True], kind="stable",
    )


def write_outputs(
    features: pd.DataFrame,
    edges: pd.DataFrame,
    graph: nx.DiGraph,
    out_dir: Path,
    cluster_summary: pd.DataFrame | None = None,
) -> dict[str, int]:
    """Write contract exports, preserving computed A2–A4 values."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    roles = _prepare_roles(features, graph)
    columns = list(REQUIRED_NODES) + list(OPTIONAL_NODES)
    columns += [column for column in roles if column not in columns]
    roles[columns].to_csv(out_dir / "nodes_roles.csv", index=False)

    clusters = _clusters_table(roles, edges, cluster_summary)
    clusters.to_csv(out_dir / "clusters.csv", index=False)

    eligible = roles.loc[~roles["role"].eq("payer") & ~roles["excluded"].astype(bool)]
    top = eligible.sort_values("rank", kind="stable").head(TOP_N).copy()
    if "why" not in top:
        top["why"] = top["evidence"]
    top[
        ["rank", "gid", "role", "priority_score", "why", "role_label",
         "confidence_level", "visibility", "is_seed"]
    ].to_csv(out_dir / "top_nodes.csv", index=False)

    seeds_review = roles.loc[
        roles["is_seed"].astype(bool) & roles["seed_above_bottom"].astype(bool),
        ["gid", "role", "role_label", "evidence"],
    ]
    seeds_review.to_csv(out_dir / "seeds_review.csv", index=False)
    data_requests = _data_requests(roles, top)
    data_requests.to_csv(out_dir / "data_requests.csv", index=False)

    _write_graph_json(roles, edges, graph, out_dir)
    return {
        "nodes_roles": len(roles), "clusters": len(clusters),
        "top_nodes": len(top), "graph_nodes": len(roles),
        "graph_edges": len(edges), "seeds_review": len(seeds_review),
        "data_requests": len(data_requests),
    }
