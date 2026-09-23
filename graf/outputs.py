"""Three valid baseline CSVs. A1 adds the full team contract."""

from pathlib import Path

import networkx as nx
import pandas as pd

from graf.config import TOP_N, TRANSIT_PT


ROLE_LABELS = {
    "consolidator": "признаки точки консолидации",
    "transit": "признаки транзитного счёта",
    "distributor": "признаки веерного распределения",
    "terminal": "конечный получатель в пределах выгрузки",
    "peripheral": "периферия, признаков роли не выявлено",
}


def _baseline_role(row) -> str:
    if row.in_deg >= 5:
        return "consolidator"
    if row.out_deg >= 10:
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


def write_outputs(features, edges, graph, out_dir: Path) -> dict[str, int]:
    """Write preliminary but nonempty role, cluster, and priority outputs."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    components = sorted(
        nx.weakly_connected_components(graph),
        key=lambda members: (-len(members), min(members)),
    )
    cluster_by_gid = {
        int(gid): cluster_id
        for cluster_id, members in enumerate(components)
        for gid in members
    }
    roles = features.copy()
    roles["cluster_id"] = roles["gid"].map(cluster_by_gid).astype("int64")
    roles["role"] = [_baseline_role(row) for row in roles.itertuples(index=False)]
    roles["role_score"] = 0.5
    roles["role_label"] = roles["role"].map(ROLE_LABELS)
    roles["priority_score"] = (
        roles["in_deg"] + roles["out_deg"]
    ).rank(method="average", pct=True)
    roles["evidence"] = [
        f"{row.role_label}: входящих {row.in_deg}, исходящих {row.out_deg}, "
        f"получено {row.in_kzt:,.0f} ₸ (предварительно)"
        for row in roles.itertuples(index=False)
    ]
    roles = roles.sort_values(
        ["priority_score", "gid"], ascending=[False, True], kind="stable"
    )
    roles["rank"] = range(1, len(roles) + 1)
    roles = roles.sort_values("gid", kind="stable")

    required = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]
    roles[required + [column for column in roles if column not in required]].to_csv(
        out_dir / "nodes_roles.csv", index=False
    )

    edges = edges.copy()
    edges["cluster_id"] = edges["src"].map(cluster_by_gid)
    internal_sums = edges.groupby("cluster_id")["sum_kzt"].sum().to_dict()
    clusters = []
    for cluster_id, members in enumerate(components):
        rows = roles.loc[roles["cluster_id"] == cluster_id].sort_values("rank")
        n_seed = int(rows["is_seed"].sum())
        clusters.append(
            {
                "cluster_id": cluster_id,
                "n_nodes": len(members),
                "n_seed": n_seed,
                "sum_kzt_internal": float(internal_sums.get(cluster_id, 0.0)),
                "top_gids": ";".join(str(int(gid)) for gid in rows["gid"].head(5)),
                "hypothesis": f"Связный фрагмент: {len(members)} узлов, {n_seed} seed; назначение требует проверки.",
            }
        )
    pd.DataFrame(clusters).to_csv(out_dir / "clusters.csv", index=False)

    top = roles.nsmallest(TOP_N, "rank")
    top = top[["rank", "gid", "role", "priority_score", "evidence"]].rename(
        columns={"evidence": "why"}
    )
    top.to_csv(out_dir / "top_nodes.csv", index=False)
    return {"nodes_roles": len(roles), "clusters": len(clusters), "top_nodes": len(top)}
