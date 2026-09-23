"""Mechanical checks for the A1 CSV and graph export contract."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


REQUIRED_NODES = [
    "gid", "role", "role_score", "cluster_id", "priority_score", "evidence"
]
OPTIONAL_NODES = [
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
]
REQUIRED_CLUSTERS = [
    "cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"
]
OPTIONAL_CLUSTERS = [
    "fingerprints", "n_coordinator", "n_consolidator", "n_distributor",
    "n_transit", "n_terminal", "n_payer", "tracked_kzt_internal",
]
REQUIRED_TOP = ["rank", "gid", "role", "priority_score", "why"]
OPTIONAL_TOP = ["role_label", "confidence_level", "visibility", "is_seed"]
VALID_ROLES = {
    "consolidator", "transit", "distributor", "terminal",
    "coordinator", "peripheral", "payer",
}


def _columns(frame: pd.DataFrame, required: list[str], optional: list[str], name: str) -> None:
    if list(frame.columns[:len(required)]) != required:
        raise ValueError(f"{name}: обязательные колонки должны идти первыми в порядке {required}")
    missing = (set(required) | set(optional)) - set(frame.columns)
    if missing:
        raise ValueError(f"{name}: отсутствуют колонки {sorted(missing)}")
    if frame[required].isna().any().any():
        raise ValueError(f"{name}: пустые обязательные значения")


def check_outputs(out_dir: Path) -> None:
    """Raise ValueError for a broken export and print a concise success line."""
    out_dir = Path(out_dir)
    roles = pd.read_csv(out_dir / "nodes_roles.csv", dtype={"gid": "int64"})
    clusters = pd.read_csv(out_dir / "clusters.csv")
    top = pd.read_csv(out_dir / "top_nodes.csv", dtype={"gid": "int64"})
    _columns(roles, REQUIRED_NODES, OPTIONAL_NODES, "nodes_roles.csv")
    _columns(clusters, REQUIRED_CLUSTERS, OPTIONAL_CLUSTERS, "clusters.csv")
    _columns(top, REQUIRED_TOP, OPTIONAL_TOP, "top_nodes.csv")

    if len(roles) != 2248 or roles["gid"].nunique() != 2248:
        raise ValueError("nodes_roles.csv должен содержать ровно 2248 разных gid")
    if not 20 <= len(top) <= 30 or top["gid"].nunique() != len(top):
        raise ValueError("top_nodes.csv должен содержать 20–30 разных gid")
    if not roles["role"].isin(VALID_ROLES).all():
        raise ValueError("nodes_roles.csv содержит неизвестную роль")
    if not top["role"].isin(VALID_ROLES).all():
        raise ValueError("top_nodes.csv содержит неизвестную роль")
    if not roles["role_score"].between(0, 1).all():
        raise ValueError("role_score должен быть от 0 до 1")
    if not roles["priority_score"].between(0, 1).all():
        raise ValueError("priority_score должен быть от 0 до 1")
    evidence = roles["evidence"].astype(str)
    if (evidence.str.len() > 200).any() or not evidence.str.contains(r"\d", regex=True).all():
        raise ValueError("evidence должен содержать числа и не превышать 200 символов")
    if not roles["cluster_id"].isin(clusters["cluster_id"]).all():
        raise ValueError("cluster_id отсутствует в clusters.csv")
    if clusters["cluster_id"].duplicated().any() or clusters["n_nodes"].sum() != len(roles):
        raise ValueError("clusters.csv: размеры кластеров не покрывают все узлы")
    if not top["gid"].isin(roles["gid"]).all():
        raise ValueError("top_nodes.csv содержит gid вне nodes_roles.csv")
    if top["role"].eq("payer").any():
        raise ValueError("top_nodes.csv не должен содержать payer")
    if top["gid"].isin(roles.loc[roles["excluded"], "gid"]).any():
        raise ValueError("top_nodes.csv не должен содержать excluded")

    payload = json.loads((out_dir / "graph.json").read_text(encoding="utf-8"))
    if len(payload["nodes"]) != len(roles):
        raise ValueError("graph.json: число узлов не совпадает с nodes_roles.csv")
    if any(not isinstance(node["id"], str) for node in payload["nodes"]):
        raise ValueError("graph.json: node.id должен быть строкой")
    if any(
        not isinstance(edge["src"], str) or not isinstance(edge["dst"], str)
        for edge in payload["edges"]
    ):
        raise ValueError("graph.json: edge.src и edge.dst должны быть строками")
    print(f"CHECK OK: {len(roles)} узлов, {len(clusters)} кластеров, {len(top)} в топе")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", default="out")
    check_outputs(Path(parser.parse_args().out))
