"""Load the parquet inputs and build the directed transaction graph."""

from __future__ import annotations

from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd


def load(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return aggregated edges, all nodes, and dated transactions."""
    data_dir = Path(data_dir)
    required = ("edges.parquet", "nodes.parquet", "transactions.parquet")
    missing = [name for name in required if not (data_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"Missing input parquet file(s) in {data_dir}: {', '.join(missing)}"
        )

    edges = pd.read_parquet(data_dir / "edges.parquet")
    nodes = pd.read_parquet(data_dir / "nodes.parquet")
    tx = pd.read_parquet(data_dir / "transactions.parquet")
    tx["date"] = pd.to_datetime(tx["date"])
    return edges, nodes, tx


def sanity_check(
    edges: pd.DataFrame, nodes: pd.DataFrame, tx: pd.DataFrame
) -> set[int]:
    """Check the edge aggregates and report nodes absent from all edges."""
    print("=" * 64)
    print("ПРОВЕРКА ДАННЫХ")
    print("=" * 64)
    print(f"  узлов в nodes.parquet : {len(nodes):>6}")
    print(f"  рёбер                 : {len(edges):>6}")
    print(f"  транзакций            : {len(tx):>6}")
    print(f"  seed-клиентов         : {int(nodes.is_seed.sum()):>6}")
    print(f"  оборот, KZT           : {edges.sum_kzt.sum():>14,.0f}")
    if not tx.empty:
        print(f"  период                : {tx.date.min().date()} — {tx.date.max().date()}")

    aggregate = (
        tx.groupby(["src", "dst"], as_index=False)
        .agg(sum_kzt_tx=("sum_kzt", "sum"), n_tx_tx=("sum_kzt", "size"))
    )
    joined = edges.merge(
        aggregate, on=["src", "dst"], how="outer", indicator=True,
        validate="one_to_one",
    )
    if not joined["_merge"].eq("both").all():
        raise ValueError("edges.parquet и transactions.parquet расходятся по парам src, dst")
    if not np.isclose(
        joined["sum_kzt"].to_numpy(),
        joined["sum_kzt_tx"].to_numpy(),
        rtol=1e-9,
        atol=1e-6,
    ).all():
        raise ValueError("sum_kzt рёбер не равна сумме отдельных транзакций")
    if not joined["n_tx"].eq(joined["n_tx_tx"]).all():
        raise ValueError("n_tx рёбер не равна числу отдельных транзакций")
    print("  edges == transactions : OK (пары, суммы, количество)")

    edge_gids = set(map(int, edges["src"])) | set(map(int, edges["dst"]))
    orphans = set(map(int, nodes["gid"])) - edge_gids
    seed_gids = set(map(int, nodes.loc[nodes["is_seed"], "gid"]))
    print(
        f"\n  ВНИМАНИЕ: {len(orphans)} узлов нет ни в одном ребре "
        f"(из них seed: {len(orphans & seed_gids)})"
    )
    print("  Они всё равно должны попасть в nodes_roles.csv")
    print("=" * 64, "\n")
    return orphans


def build_graph(
    edges: pd.DataFrame, nodes: pd.DataFrame | None = None
) -> nx.DiGraph:
    """Build a directed graph with KZT, transaction count, and depth per edge.

    Passing ``nodes`` retains isolated clients in the graph. The one-argument
    call from the starter remains supported.
    """
    graph = nx.DiGraph()
    if nodes is not None:
        for node in nodes.itertuples(index=False):
            graph.add_node(
                int(node.gid), depth=int(node.depth), is_seed=bool(node.is_seed)
            )
    for edge in edges.itertuples(index=False):
        graph.add_edge(
            int(edge.src),
            int(edge.dst),
            sum_kzt=float(edge.sum_kzt),
            n_tx=int(edge.n_tx),
            depth=int(edge.depth),
        )
    return graph
