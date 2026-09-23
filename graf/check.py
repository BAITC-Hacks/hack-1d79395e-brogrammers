"""Mechanical checks of the three mandatory CSV exports."""

from pathlib import Path
import re

import pandas as pd


REQUIRED_NODES = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]
REQUIRED_CLUSTERS = [
    "cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"
]
REQUIRED_TOP = ["rank", "gid", "role", "priority_score", "why"]
VALID_ROLES = {
    "consolidator", "transit", "distributor", "terminal",
    "coordinator", "peripheral", "payer",
}


def check_outputs(out_dir: Path) -> None:
    out_dir = Path(out_dir)
    roles = pd.read_csv(out_dir / "nodes_roles.csv", dtype={"gid": "int64"})
    clusters = pd.read_csv(out_dir / "clusters.csv")
    top = pd.read_csv(out_dir / "top_nodes.csv", dtype={"gid": "int64"})
    for name, frame, required in (
        ("nodes_roles.csv", roles, REQUIRED_NODES),
        ("clusters.csv", clusters, REQUIRED_CLUSTERS),
        ("top_nodes.csv", top, REQUIRED_TOP),
    ):
        missing = set(required) - set(frame.columns)
        if missing:
            raise ValueError(f"{name}: отсутствуют колонки {sorted(missing)}")
        if frame[required].isna().any().any():
            raise ValueError(f"{name}: пустые обязательные значения")
    if len(roles) != 2248 or roles["gid"].nunique() != 2248:
        raise ValueError("nodes_roles.csv должен содержать ровно 2248 разных gid")
    if len(top) < 20:
        raise ValueError("top_nodes.csv должен содержать не менее 20 узлов")
    if not set(roles["role"]).issubset(VALID_ROLES):
        raise ValueError("nodes_roles.csv содержит неизвестную роль")
    evidence = roles["evidence"].astype(str)
    if (evidence.str.len() > 200).any() or not evidence.str.contains(r"\d", regex=True).all():
        raise ValueError("evidence должен содержать числа и не превышать 200 символов")
    if not set(roles["cluster_id"]).issubset(set(clusters["cluster_id"])):
        raise ValueError("cluster_id отсутствует в clusters.csv")
    print(f"CHECK OK: {len(roles)} узлов, {len(clusters)} кластеров, {len(top)} в топе")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", default="out")
    check_outputs(Path(parser.parse_args().out))
