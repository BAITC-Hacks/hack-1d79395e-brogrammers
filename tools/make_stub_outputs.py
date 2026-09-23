"""B0: reproducible UI fixtures, never an analytical result or A's out/."""
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import networkx as nx
import numpy as np
import pandas as pd

from ui.data import load_raw, OPTIONAL, json_records
from ui.theme import LABELS


def sample_paths(target, incoming, seeds):
    """Up to three distinct real date-ordered paths, without invented edges."""
    found, signatures = [], set()

    def visit(current, reverse_ids, reverse_days, reverse_amounts):
        if len(found) >= 3:
            return
        if current in seeds and reverse_amounts:
            path = (list(reversed(reverse_ids)), list(reversed(reverse_days)), list(reversed(reverse_amounts)))
            signature = tuple(path[0]), tuple(path[1]), tuple(path[2])
            if signature not in signatures:
                signatures.add(signature)
                found.append(path)
            return
        if len(reverse_amounts) == 4 or current not in incoming:
            return
        for r in incoming[current].itertuples():
            day = int(r.date.day)
            if int(r.src) in reverse_ids or (reverse_days and not 0 <= reverse_days[-1]-day <= 7):
                continue
            visit(int(r.src), reverse_ids+[int(r.src)], reverse_days+[day], reverse_amounts+[float(r.sum_kzt)])
            if len(found) >= 3:
                break
    visit(target, [target], [], [])
    return found


def make_stubs(data_dir, out_dir="out_stub"):
    started = perf_counter()
    root = Path(out_dir)
    if root.resolve().name == "out":
        raise ValueError("Заглушку запрещено писать в out/. Используйте out_stub/.")
    root.mkdir(parents=True, exist_ok=True)
    edges, raw_nodes, tx = load_raw(data_dir)
    rng = np.random.default_rng(42)
    nodes = raw_nodes.sort_values("gid").reset_index(drop=True).copy()
    graph = nx.DiGraph()
    graph.add_nodes_from(nodes.gid.astype(int))
    for r in edges.itertuples(index=False):
        graph.add_edge(int(r.src), int(r.dst), sum_kzt=float(r.sum_kzt), n_tx=int(r.n_tx))
    for name, vals in {
        "in_deg": dict(graph.in_degree()), "out_deg": dict(graph.out_degree()),
        "in_kzt": dict(graph.in_degree(weight="sum_kzt")),
        "out_kzt": dict(graph.out_degree(weight="sum_kzt")),
        "in_tx": dict(graph.in_degree(weight="n_tx")),
        "out_tx": dict(graph.out_degree(weight="n_tx")),
    }.items():
        nodes[name] = nodes.gid.map(vals)
    nodes["pass_through"] = nodes.out_kzt / nodes.in_kzt.replace(0, np.nan)
    nodes["role"] = rng.choice(list(LABELS), len(nodes))
    nodes["truncated"] = nodes.depth.eq(4) & nodes.out_deg.eq(0)
    nodes.loc[nodes.truncated | (nodes.in_deg + nodes.out_deg).eq(0), "role"] = "peripheral"
    nodes["role_label"] = nodes.role.map(LABELS)
    nodes["role_score"] = rng.uniform(.3, .95, len(nodes)).round(4)
    nodes["priority_score"] = rng.uniform(0, 1, len(nodes)).round(6)
    nodes.loc[nodes.role.eq("payer"), "priority_score"] *= .1
    nodes["cluster_id"] = np.arange(len(nodes)) % min(20, len(nodes))
    nodes["role_alt"] = "peripheral"
    nodes["ambiguous"] = rng.random(len(nodes)) < .1
    nodes["confidence_level"] = pd.cut(nodes.role_score, [-1, .5, .75, 1], labels=["низкая", "средняя", "высокая"]).astype(str)
    nodes["visibility"] = np.select([nodes.truncated, nodes.is_seed], ["out_unseen", "in_unseen_seed"], default="full")
    nodes["excluded"] = False
    nodes["aggregator_like"] = False
    nodes["seed_above_bottom"] = nodes.is_seed & nodes.role.isin(["coordinator", "consolidator"])
    for c in ["in_hhi", "out_hhi", "betweenness", "fast_out_share", "near_threshold_share", "p_forward"]:
        nodes[c] = rng.uniform(0, 1, len(nodes)).round(4)
    for c in ["from_key", "to_key", "max_sync_payers", "seed_exp_topo"]:
        nodes[c] = rng.integers(0, 6, len(nodes))
    nodes["seed_exp_chrono"] = np.minimum(nodes.seed_exp_topo, rng.integers(0, 5, len(nodes)))
    nodes["seed_exp_fast"] = np.minimum(nodes.seed_exp_chrono, rng.integers(0, 3, len(nodes)))
    nodes["tracked_share_in"] = rng.uniform(0, 1, len(nodes))
    nodes["tracked_in"] = nodes.in_kzt * nodes.tracked_share_in
    nodes["tracked_out"] = np.minimum(nodes.tracked_in, nodes.out_kzt) * .5
    nodes["tracked_out_share"] = (nodes.tracked_out / nodes.out_kzt.replace(0, np.nan)).fillna(0)
    nodes["tracked_kept"] = nodes.tracked_in - nodes.tracked_out
    for c, w in [("role", .3), ("money", .3), ("brokerage", .2), ("volume", .1), ("temporal", .1)]:
        nodes[f"prio_{c}"] = rng.uniform(0, w, len(nodes))
    nodes["prio_multiplier"] = 1.0
    nodes["signals"] = "ЗАГЛУШКА: сигналы не вычислены | Метрики степеней и сумм — из исходных рёбер"
    nodes["counter_signals"] = "ЗАГЛУШКА: роль и денежный след случайны, не использовать для проверки"
    nodes["evidence"] = [f"ЗАГЛУШКА: {r.in_deg} плательщиков, {r.out_deg} получателей; роль случайна (seed=42)." for r in nodes.itertuples()]
    incoming = {int(dst): g.sort_values(["date", "src", "sum_kzt"]) for dst, g in tx.groupby("dst")}
    seeds = set(nodes.loc[nodes.is_seed, "gid"].astype(int))
    examples = {}
    # Mock ranking deliberately exercises three real paths per card, without
    # claiming these random scores are an analytical prioritisation.
    for target in nodes.loc[~nodes.role.eq("payer")].sort_values(["priority_score", "gid"], ascending=[False, True]).gid.astype(int):
        candidate = sample_paths(target, incoming, seeds)
        if len(candidate) == 3:
            examples[target] = candidate
        if len(examples) == 30:
            break
    nodes["priority_score"] *= .5
    for gid, score in zip(examples, np.linspace(.99, .75, len(examples))):
        nodes.loc[nodes.gid.eq(gid), "priority_score"] = score
    nodes = nodes.sort_values(["priority_score", "gid"], ascending=[False, True]).reset_index(drop=True)
    nodes["rank"] = np.arange(1, len(nodes) + 1)
    required = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]
    nodes = nodes[required + [c for c in nodes if c not in required]]
    tables = {name: pd.DataFrame(columns=cols) for name, cols in OPTIONAL.items()}
    tables["nodes_roles"] = nodes
    top = nodes.loc[~nodes.role.eq("payer") & ~nodes.excluded].head(30).copy()
    top["rank"] = np.arange(1, len(top) + 1)
    top["why"] = top.evidence
    tables["top_nodes"] = top[["rank", "gid", "role", "priority_score", "why", "role_label", "confidence_level", "visibility", "is_seed"]]
    tables["seeds_review"] = nodes.loc[nodes.seed_above_bottom, ["gid", "role", "role_label", "evidence"]]
    cluster_rows = []
    for cid, group in nodes.groupby("cluster_id", sort=True):
        ids = set(group.gid)
        internal = edges[edges.src.isin(ids) & edges.dst.isin(ids)]
        row = dict(cluster_id=int(cid), n_nodes=len(group), n_seed=int(group.is_seed.sum()),
                   sum_kzt_internal=float(internal.sum_kzt.sum()),
                   top_gids=";".join(group.head(5).gid.astype(str)),
                   hypothesis="ЗАГЛУШКА: случайное разбиение, аналитической гипотезы нет",
                   fingerprints="fan_in;cycle", tracked_kzt_internal=0.0)
        row.update({f"n_{role}": int(group.role.eq(role).sum()) for role in LABELS if role != "peripheral"})
        cluster_rows.append(row)
    tables["clusters"] = pd.DataFrame(cluster_rows)
    # Real directed, date-ordered paths; role/tracked scores remain mock data.
    paths = []
    for target in top.gid.astype(int):
        found = examples.get(target) or sample_paths(target, incoming, seeds)
        for rank, (ids, days, amounts) in enumerate(found, 1):
            paths.append(dict(target_gid=target, path_rank=rank, seed_gid=ids[0], hops=len(amounts),
                              path_gids=">".join(map(str, ids)), path_days=">".join(map(str, [days[0]]+days)),
                              path_amounts=">".join(map(str, amounts)), bottleneck_kzt=min(amounts)))
    tables["paths"] = pd.DataFrame(paths, columns=OPTIONAL["paths"])
    resilience = [dict(strategy=s, n_removed=n, seed_reach_share=max(0, 1-n*k), largest_wcc=max(0,len(nodes)-n*3))
                  for s, k in [("priority", .02), ("betweenness", .018), ("out_deg", .015), ("in_deg", .012), ("random", .006)]
                  for n in [0, 1, 5, 10, 20, 30]]
    resilience.append(dict(strategy="all_seeds", n_removed=len(seeds), seed_reach_share=0, largest_wcc=max(0, len(nodes)-len(seeds))))
    tables["resilience"] = pd.DataFrame(resilience)
    nonseed = nodes.loc[~nodes.is_seed]
    tables["ablation_links"] = pd.DataFrame([
        dict(level=l, n_nonseed_nodes=int(nonseed[c].gt(0).sum()), share=float(nonseed[c].gt(0).mean()))
        for l, c in [("topology", "seed_exp_topo"), ("chrono_any", "seed_exp_chrono"), ("chrono_7d", "seed_exp_chrono"), ("chrono_2d", "seed_exp_fast")]])
    tables["tracked_by_depth"] = nodes.groupby("depth", as_index=False).tracked_kept.sum().rename(columns={"tracked_kept": "tracked_kept_kzt"})
    tables["truncation_calibration"] = pd.DataFrame([dict(bucket="stub", n=int(nodes.truncated.sum()), p_forward=.5)])
    tables["data_requests"] = top[["gid", "priority_score"]].assign(request="ЗАГЛУШКА: запросить полную выписку", reason="Входящие вне выборки неизвестны")[["gid", "request", "reason", "priority_score"]]
    tables["audit"] = pd.DataFrame([dict(scope=s, check="ЗАГЛУШКА: аудит не выполнен", count=n, ok=False) for s, n in [("top10", 10), ("top30", 30)]])
    for name, frame in tables.items():
        frame.to_csv(root / f"{name}.csv", index=False)
    pos = nx.spring_layout(graph, seed=42, iterations=30)
    graph_nodes = []
    for r in json_records(nodes[["gid", "role", "role_label", "cluster_id", "priority_score", "rank", "depth", "is_seed", "visibility", "tracked_in", "seed_exp_chrono"]]):
        gid = r.pop("gid")
        graph_nodes.append(dict(id=gid, **r, x=float(pos[int(gid)][0]), y=float(pos[int(gid)][1])))
    dates = tx.groupby(["src", "dst"]).date.agg(["min", "max"])
    graph_edges = [dict(src=str(r.src), dst=str(r.dst), sum_kzt=float(r.sum_kzt), n_tx=int(r.n_tx), tracked_kzt=0.0,
                        first_day=int(dates.loc[(r.src,r.dst), "min"].day), last_day=int(dates.loc[(r.src,r.dst), "max"].day))
                   for r in edges.itertuples(index=False)]
    meta = dict(stub=True, random_seed=42, n_nodes=len(nodes), n_edges=len(edges), n_tx=len(tx), total_sec=round(perf_counter()-started, 3),
                stage_seconds={"stub": round(perf_counter()-started, 3)}, parameters={"random_seed": 42, "n_clusters": 20, "path_gap_days": 7},
                note="ЗАГЛУШКА Б: роли/скоры/след/устойчивость не являются результатами анализа")
    (root / "graph.json").write_text(json.dumps(dict(meta=meta, nodes=graph_nodes, edges=graph_edges), ensure_ascii=False), encoding="utf-8")
    (root / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"ЗАГЛУШКА: {len(nodes)} узлов, {len(top)} строк топа → {root}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data", help="Папка data/ или ZIP организаторов")
    parser.add_argument("--out", default="out_stub")
    args = parser.parse_args()
    make_stubs(args.data, args.out)
