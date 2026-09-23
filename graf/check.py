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
ADDITIONAL_EXPORTS = {
    "seeds_review.csv": ["gid", "role", "role_label", "evidence"],
    "paths.csv": [
        "target_gid", "path_rank", "seed_gid", "hops", "path_gids",
        "path_days", "path_amounts", "bottleneck_kzt",
    ],
    "resilience.csv": [
        "strategy", "n_removed", "seed_reach_share", "largest_wcc"
    ],
    "ablation_links.csv": ["level", "n_nonseed_nodes", "share"],
    "tracked_by_depth.csv": ["depth", "tracked_kept_kzt"],
    "truncation_calibration.csv": ["bucket", "n", "p_forward"],
    "data_requests.csv": ["gid", "request", "reason", "priority_score"],
}
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


def _bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False)
    return series.astype("string").str.lower().isin(["true", "1", "yes"])


def _audit_table(roles: pd.DataFrame, top: pd.DataFrame) -> pd.DataFrame:
    by_gid = roles.set_index("gid")
    rows = []
    for scope, size in (("top10", 10), ("top30", 30)):
        selected = by_gid.reindex(top.sort_values("rank")["gid"].head(size))
        checks = {
            "is_seed": _bool(selected["is_seed"]),
            "payer": selected["role"].eq("payer"),
            "excluded": _bool(selected["excluded"]),
            "aggregator_like": _bool(selected["aggregator_like"]),
            "visibility != full": selected["visibility"].ne("full"),
            "seed_exp_chrono == 0 (non-seed)": (
                ~_bool(selected["is_seed"])
                & selected["seed_exp_chrono"].eq(0)
            ),
        }
        for name, mask in checks.items():
            count = int(mask.sum())
            rows.append({
                "scope": scope, "check": name,
                "count": count, "ok": count == 0,
            })
    return pd.DataFrame(rows, columns=["scope", "check", "count", "ok"])


def check_outputs(out_dir: Path) -> None:
    """Raise ValueError for a broken export and print a concise success line."""
    out_dir = Path(out_dir)
    roles = pd.read_csv(out_dir / "nodes_roles.csv", dtype={"gid": "int64"})
    clusters = pd.read_csv(out_dir / "clusters.csv")
    top = pd.read_csv(out_dir / "top_nodes.csv", dtype={"gid": "int64"})
    _columns(roles, REQUIRED_NODES, OPTIONAL_NODES, "nodes_roles.csv")
    _columns(clusters, REQUIRED_CLUSTERS, OPTIONAL_CLUSTERS, "clusters.csv")
    _columns(top, REQUIRED_TOP, OPTIONAL_TOP, "top_nodes.csv")

    for filename, columns in ADDITIONAL_EXPORTS.items():
        frame = pd.read_csv(out_dir / filename)
        missing = set(columns) - set(frame.columns)
        if missing:
            raise ValueError(f"{filename}: отсутствуют колонки {sorted(missing)}")

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
    excluded_gids = set(roles.loc[_bool(roles["excluded"]), "gid"])
    top_excluded = top["gid"].isin(excluded_gids)

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
    audit = _audit_table(roles, top)
    audit.to_csv(out_dir / "audit.csv", index=False)
    print(audit.to_string(index=False))
    top10 = top.sort_values("rank").head(10)
    if top10["role"].eq("payer").any() or top10["gid"].isin(excluded_gids).any():
        raise ValueError("в топ-10 обнаружен payer или excluded")
    if top["role"].eq("payer").any() or top_excluded.any():
        raise ValueError("top_nodes.csv не должен содержать payer или excluded")
    print(f"CHECK OK: {len(roles)} узлов, {len(clusters)} кластеров, {len(top)} в топе")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", default="out")
    check_outputs(Path(parser.parse_args().out))
