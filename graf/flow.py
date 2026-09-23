"""Chronological seed reach, conservative attributed flow, and candidate paths."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from graf.config import CHRONO_GAPS, FAST_DAYS, PATH_GAP_DAYS, TOP_N


PATH_COLUMNS = [
    "target_gid", "path_rank", "seed_gid", "hops", "path_gids",
    "path_days", "path_amounts", "bottleneck_kzt",
]


def _day_numbers(tx: pd.DataFrame) -> np.ndarray:
    return pd.to_datetime(tx["date"]).to_numpy(dtype="datetime64[D]").astype("int64")


def _chrono_index(tx: pd.DataFrame) -> tuple[dict[int, list[tuple[int, int]]], list[int]]:
    days = _day_numbers(tx)
    unique_days = sorted(set(map(int, days)))
    day_bits = {day: 1 << index for index, day in enumerate(unique_days)}
    outgoing: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for src, dst, day in zip(tx["src"], tx["dst"], days):
        outgoing[int(src)].append((int(dst), int(day)))
    return outgoing, unique_days


def chrono_reach(
    tx: pd.DataFrame, seeds: set[int], gap_days: int, max_hops: int = 4
) -> dict[int, int]:
    """Count seeds with a date-compatible route of at most ``max_hops``.

    All arrival dates are retained per seed, node, and hop. The first edge
    from the originating seed is valid on any date. Later edges require an
    arrival on or before their date and at most ``gap_days`` earlier. Routes
    cannot return to their own seed. Same-day chains are permitted because
    the source contains dates but no times.
    """
    if gap_days < 0 or max_hops < 0:
        raise ValueError("gap_days and max_hops must be nonnegative")
    if tx.empty or not seeds or max_hops == 0:
        return {}

    outgoing, unique_days = _chrono_index(tx)
    bit_by_day = {day: 1 << index for index, day in enumerate(unique_days)}
    window_by_day = {
        day: sum(
            bit_by_day[prior]
            for prior in unique_days
            if day - gap_days <= prior <= day
        )
        for day in unique_days
    }
    counts: dict[int, int] = defaultdict(int)
    for seed in map(int, seeds):
        frontier: dict[int, int] = {seed: 0}
        reached: set[int] = set()
        for hop in range(1, max_hops + 1):
            next_frontier: dict[int, int] = defaultdict(int)
            for src, arrival_bits in frontier.items():
                for dst, day in outgoing.get(src, ()):
                    if dst == seed:
                        continue
                    if hop > 1 and not (arrival_bits & window_by_day[day]):
                        continue
                    next_frontier[dst] |= bit_by_day[day]
                    reached.add(dst)
            if not next_frontier:
                break
            frontier = next_frontier
        for gid in reached:
            counts[gid] += 1
    return dict(counts)


def topo_reach(
    graph: nx.DiGraph, seeds: set[int], max_hops: int = 4
) -> dict[int, int]:
    """Count seed origins with an ordinary directed path of at most four hops."""
    counts: dict[int, int] = defaultdict(int)
    for seed in map(int, seeds):
        if seed not in graph:
            continue
        for gid, hops in nx.single_source_shortest_path_length(
            graph, seed, cutoff=max_hops
        ).items():
            if hops > 0:
                counts[int(gid)] += 1
    return dict(counts)


def _depth_mapping(depth: Mapping[int, int] | pd.DataFrame | pd.Series) -> dict[int, int]:
    if isinstance(depth, pd.DataFrame):
        return dict(zip(depth["gid"].astype(int), depth["depth"].astype(int)))
    return {int(gid): int(value) for gid, value in depth.items()}


def flow_ledger(
    tx: pd.DataFrame,
    seeds: set[int],
    depth: Mapping[int, int] | pd.DataFrame | pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return node and edge tables of conservatively attributed seed money.

    Transactions are ordered by date, then sender depth. A non-seed account
    forwards no more attributed money than its current balance. Seed outgoing
    transactions inject their full amount regardless of seed incoming balance.
    """
    seed_set = set(map(int, seeds))
    depths = _depth_mapping(depth)
    ordered = tx[["src", "dst", "date", "sum_kzt"]].copy()
    ordered["date"] = pd.to_datetime(ordered["date"]).dt.normalize()
    ordered["src_depth"] = ordered["src"].map(depths).fillna(99).astype(int)
    ordered = ordered.sort_values(
        ["date", "src_depth", "src", "dst"], kind="stable"
    )

    balance: dict[int, float] = defaultdict(float)
    tracked_in: dict[int, float] = defaultdict(float)
    tracked_out: dict[int, float] = defaultdict(float)
    tracked_edge: dict[tuple[int, int], float] = defaultdict(float)
    for row in ordered.itertuples(index=False):
        src, dst = int(row.src), int(row.dst)
        amount = float(row.sum_kzt)
        if amount < 0:
            raise ValueError("transaction amounts must be nonnegative")
        attributed = amount if src in seed_set else min(amount, balance[src])
        if src not in seed_set:
            balance[src] = max(0.0, balance[src] - attributed)
        if dst not in seed_set:
            balance[dst] += attributed
        tracked_out[src] += attributed
        tracked_in[dst] += attributed
        tracked_edge[(src, dst)] += attributed

    all_gids = sorted(
        set(depths) | seed_set | set(map(int, tx["src"])) | set(map(int, tx["dst"]))
    )
    in_kzt = tx.groupby("dst")["sum_kzt"].sum().to_dict()
    out_kzt = tx.groupby("src")["sum_kzt"].sum().to_dict()
    node_rows = []
    for gid in all_gids:
        incoming = float(tracked_in[gid])
        outgoing = float(tracked_out[gid])
        total_in = float(in_kzt.get(gid, 0.0))
        total_out = float(out_kzt.get(gid, 0.0))
        node_rows.append(
            {
                "gid": gid,
                "tracked_in": incoming,
                "tracked_out": outgoing,
                "tracked_share_in": incoming / total_in if total_in > 0 else 0.0,
                "tracked_out_share": outgoing / total_out if total_out > 0 else 0.0,
                "tracked_kept": 0.0 if gid in seed_set else float(balance[gid]),
            }
        )
    node_table = pd.DataFrame(
        node_rows,
        columns=[
            "gid", "tracked_in", "tracked_out", "tracked_share_in",
            "tracked_out_share", "tracked_kept",
        ],
    )
    edge_table = pd.DataFrame(
        [
            {"src": src, "dst": dst, "tracked_kzt": amount}
            for (src, dst), amount in sorted(tracked_edge.items())
        ],
        columns=["src", "dst", "tracked_kzt"],
    )
    return node_table, edge_table


def _path_sort_key(row: dict) -> tuple:
    return (
        -row["bottleneck_kzt"], row["hops"], row["seed_gid"],
        row["path_gids"], row["path_days"], row["path_amounts"],
    )


def money_paths(
    tx: pd.DataFrame,
    seeds: set[int],
    targets: Iterable[int],
    gap_days: int = PATH_GAP_DAYS,
    max_hops: int = 4,
    k: int = 3,
) -> pd.DataFrame:
    """Find up to ``k`` strongest date-compatible simple paths per target.

    These are candidate transaction routes ranked by their smallest transfer,
    then by fewer hops. They are not amounts attributed by ``flow_ledger``.
    """
    if gap_days < 0 or max_hops < 0 or k < 0:
        raise ValueError("gap_days, max_hops, and k must be nonnegative")
    targets = set(map(int, targets))
    if tx.empty or not seeds or not targets or max_hops == 0 or k == 0:
        return pd.DataFrame(columns=PATH_COLUMNS)

    dates = pd.to_datetime(tx["date"])
    day_numbers = dates.to_numpy(dtype="datetime64[D]").astype("int64")
    days_of_month = dates.dt.day.to_numpy(dtype=int)
    adjacency: dict[int, list[tuple[int, int, int, float]]] = defaultdict(list)
    graph = nx.DiGraph()
    for src, dst, day_number, day_of_month, amount in zip(
        tx["src"], tx["dst"], day_numbers, days_of_month, tx["sum_kzt"]
    ):
        src, dst = int(src), int(dst)
        adjacency[src].append((dst, int(day_number), int(day_of_month), float(amount)))
        graph.add_edge(src, dst)
    for rows in adjacency.values():
        rows.sort(key=lambda edge: (edge[1], edge[0], -edge[3]))

    # A topology-only lower bound prunes branches that cannot hit any target
    # within the remaining hops. Date checks still determine actual paths.
    reverse = graph.reverse(copy=False)
    distance: dict[int, int] = {}
    for target in targets:
        if target not in reverse:
            continue
        for gid, hops in nx.single_source_shortest_path_length(
            reverse, target, cutoff=max_hops
        ).items():
            distance[gid] = min(distance.get(gid, max_hops + 1), hops)

    best: dict[int, list[dict]] = defaultdict(list)

    def remember(target: int, seed: int, gids: tuple[int, ...], path_days: tuple[int, ...],
                 amounts: tuple[float, ...], bottleneck: float) -> None:
        candidate = {
            "target_gid": target,
            "seed_gid": seed,
            "hops": len(path_days),
            "path_gids": ">".join(map(str, gids)),
            "path_days": ">".join(map(str, path_days)),
            "path_amounts": ">".join(format(value, ".12g") for value in amounts),
            "bottleneck_kzt": bottleneck,
        }
        signature = (candidate["seed_gid"], candidate["path_gids"], candidate["path_days"])
        current = best[target]
        for index, prior in enumerate(current):
            if (prior["seed_gid"], prior["path_gids"], prior["path_days"]) == signature:
                if bottleneck <= prior["bottleneck_kzt"]:
                    return
                current.pop(index)
                break
        current.append(candidate)
        current.sort(key=_path_sort_key)
        del current[k:]

    for seed in map(int, seeds):
        if seed not in adjacency:
            continue
        stack = [(seed, None, (seed,), (), (), float("inf"))]
        while stack:
            src, last_day, gids, path_days, amounts, bottleneck = stack.pop()
            if len(path_days) >= max_hops:
                continue
            if distance.get(src, max_hops + 1) > max_hops - len(path_days):
                continue
            for dst, day_number, day_of_month, amount in reversed(adjacency.get(src, ())):
                if dst in gids:
                    continue
                if last_day is not None and not (0 <= day_number - last_day <= gap_days):
                    continue
                next_gids = (*gids, dst)
                next_days = (*path_days, day_of_month)
                next_amounts = (*amounts, amount)
                next_bottleneck = min(bottleneck, amount)
                if dst in targets:
                    remember(dst, seed, next_gids, next_days, next_amounts, next_bottleneck)
                if len(next_days) < max_hops:
                    stack.append((
                        dst, day_number, next_gids, next_days,
                        next_amounts, next_bottleneck,
                    ))

    rows = []
    for target in sorted(best):
        for rank, candidate in enumerate(sorted(best[target], key=_path_sort_key), 1):
            rows.append({"path_rank": rank, **candidate})
    return pd.DataFrame(rows, columns=PATH_COLUMNS)


def ablation_table(
    graph: nx.DiGraph,
    tx: pd.DataFrame,
    seeds: set[int],
    nodes: pd.DataFrame,
    *,
    topo: Mapping[int, int] | None = None,
    chrono_any: Mapping[int, int] | None = None,
    chrono_fast: Mapping[int, int] | None = None,
) -> pd.DataFrame:
    """Count non-seed accounts reachable under four increasingly strict rules."""
    nonseed = set(map(int, nodes.loc[~nodes["is_seed"], "gid"]))
    counts = {
        "topology": topo if topo is not None else topo_reach(graph, seeds),
        "chrono_any": chrono_any if chrono_any is not None else chrono_reach(
            tx, seeds, CHRONO_GAPS["any"]
        ),
        "chrono_7d": chrono_reach(tx, seeds, CHRONO_GAPS["7d"]),
        "chrono_2d": chrono_fast if chrono_fast is not None else chrono_reach(
            tx, seeds, CHRONO_GAPS["2d"]
        ),
    }
    rows = []
    for level, exposures in counts.items():
        n = sum(exposures.get(gid, 0) > 0 for gid in nonseed)
        rows.append({
            "level": level, "n_nonseed_nodes": n,
            "share": n / len(nonseed) if nonseed else 0.0,
        })
    return pd.DataFrame(rows, columns=["level", "n_nonseed_nodes", "share"])


def run(context: dict) -> None:
    """Calculate A2 measures and add them to pipeline tables and exports."""
    features = context["features"].copy()
    tx = context["tx"]
    graph = context["graph"]
    seeds = set(map(int, features.loc[features["is_seed"], "gid"]))

    topo = topo_reach(graph, seeds)
    chrono_any = chrono_reach(tx, seeds, CHRONO_GAPS["any"])
    chrono_fast = chrono_reach(tx, seeds, FAST_DAYS)
    for column, values in (
        ("seed_exp_topo", topo),
        ("seed_exp_chrono", chrono_any),
        ("seed_exp_fast", chrono_fast),
    ):
        features[column] = features["gid"].map(values).fillna(0).astype(int)

    node_ledger, edge_ledger = flow_ledger(
        tx, seeds, features[["gid", "depth"]]
    )
    ledger_columns = [column for column in node_ledger if column != "gid"]
    features = features.drop(columns=ledger_columns, errors="ignore").merge(
        node_ledger, on="gid", how="left", validate="one_to_one"
    )
    features[ledger_columns] = features[ledger_columns].fillna(0.0)
    edges = context["edges"].drop(
        columns=["tracked_kzt", "first_day", "last_day"], errors="ignore"
    ).merge(edge_ledger, on=["src", "dst"], how="left", validate="one_to_one")
    edges["tracked_kzt"] = edges["tracked_kzt"].fillna(0.0)
    dated = tx[["src", "dst", "date"]].copy()
    dated["date"] = pd.to_datetime(dated["date"]).dt.day
    span = dated.groupby(["src", "dst"], as_index=False).agg(
        first_day=("date", "min"), last_day=("date", "max")
    )
    edges = edges.merge(span, on=["src", "dst"], how="left", validate="one_to_one")
    nx.set_edge_attributes(
        graph,
        {(int(row.src), int(row.dst)): float(row.tracked_kzt)
         for row in edges.itertuples(index=False)},
        "tracked_kzt",
    )

    out_dir = Path(context["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    by_depth = features.groupby("depth")["tracked_kept"].sum().reindex(
        range(5), fill_value=0.0
    )
    pd.DataFrame({
        "depth": by_depth.index.astype(int),
        "tracked_kept_kzt": by_depth.to_numpy(dtype=float),
    }).to_csv(out_dir / "tracked_by_depth.csv", index=False)

    ablation_table(
        graph, tx, seeds, context["nodes"],
        topo=topo, chrono_any=chrono_any, chrono_fast=chrono_fast,
    ).to_csv(out_dir / "ablation_links.csv", index=False)

    provisional = features.assign(
        _degree=features["in_deg"] + features["out_deg"]
    ).sort_values(["_degree", "gid"], ascending=[False, True], kind="stable")
    targets = provisional["gid"].head(TOP_N)
    money_paths(tx, seeds, targets).to_csv(out_dir / "paths.csv", index=False)

    context["features"] = features
    context["edges"] = edges
