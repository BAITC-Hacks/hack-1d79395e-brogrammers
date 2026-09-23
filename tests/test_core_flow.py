"""Synthetic chronology, conservation, and path-contract checks for A2."""

from datetime import date

import networkx as nx
import pandas as pd
import pytest

from graf.flow import (
    ablation_table,
    chrono_reach,
    flow_ledger,
    money_paths,
    topo_reach,
)


def _tx(rows):
    return pd.DataFrame(rows, columns=["src", "dst", "date", "sum_kzt"])


def test_chrono_reach_keeps_arrival_dates_and_handles_same_day_order():
    tx = _tx(
        [
            # Deliberately put the second edge of a same-day chain first.
            (2, 3, date(2026, 7, 1), 8_000),
            (1, 2, date(2026, 7, 1), 10_000),
            (1, 2, date(2026, 7, 5), 10_000),
            (2, 4, date(2026, 7, 7), 8_000),
            (2, 5, date(2026, 7, 8), 8_000),
            (2, 1, date(2026, 7, 6), 8_000),
            (3, 6, date(2026, 7, 1), 8_000),
            (6, 8, date(2026, 7, 1), 8_000),
            (8, 9, date(2026, 7, 1), 8_000),
        ]
    )
    reach = chrono_reach(tx, {1}, gap_days=2)
    assert {2, 3, 4, 6, 8}.issubset(reach)
    assert 1 not in reach  # no route may return to its originating seed
    assert 5 not in reach  # July 8 is 3 days after the latest arrival at 2
    assert 9 not in reach  # five hops from seed 1

    graph = nx.DiGraph()
    graph.add_edges_from(tx[["src", "dst"]].itertuples(index=False, name=None))
    assert set(chrono_reach(tx, {1}, gap_days=31)).issubset(topo_reach(graph, {1}))


def test_chrono_reach_counts_origins_and_rejects_backwards_dates():
    tx = _tx(
        [
            (2, 4, date(2026, 7, 1), 5_000),
            (1, 2, date(2026, 7, 2), 5_000),
            (7, 2, date(2026, 7, 2), 5_000),
            (2, 3, date(2026, 7, 4), 5_000),
            (2, 5, date(2026, 7, 5), 5_000),
        ]
    )
    reach = chrono_reach(tx, {1, 7}, gap_days=2)
    assert reach[2] == 2
    assert reach[3] == 2  # gap of exactly two days is allowed
    assert 4 not in reach  # transfer before either seed arrived at 2
    assert 5 not in reach  # gap of three days is not allowed


def test_flow_ledger_orders_same_day_by_depth_and_caps_nonseed_outflow():
    tx = _tx(
        [
            (2, 3, date(2026, 7, 1), 80_000),
            (1, 2, date(2026, 7, 1), 100_000),
            (2, 3, date(2026, 7, 2), 50_000),
            (3, 4, date(2026, 7, 2), 110_000),
        ]
    )
    node, edge = flow_ledger(tx, {1}, {1: 0, 2: 1, 3: 2, 4: 3, 5: 0})
    node = node.set_index("gid")
    edge = edge.set_index(["src", "dst"])
    assert node.loc[1, "tracked_out"] == pytest.approx(100_000)
    assert node.loc[2, "tracked_in"] == pytest.approx(100_000)
    assert node.loc[2, "tracked_out"] == pytest.approx(100_000)
    assert node.loc[3, "tracked_out"] == pytest.approx(100_000)
    assert node.loc[4, "tracked_kept"] == pytest.approx(100_000)
    assert edge.loc[(2, 3), "tracked_kzt"] == pytest.approx(100_000)
    assert node.loc[5, "tracked_out_share"] == 0
    nonseed = node.drop(index=1)
    assert (nonseed["tracked_out"] <= nonseed["tracked_in"] + 1e-6).all()
    assert (nonseed["tracked_kept"] >= 0).all()


def test_money_paths_ranks_bottleneck_then_hops_and_uses_day_tokens():
    tx = _tx(
        [
            (1, 2, date(2026, 7, 1), 100_000),
            (2, 4, date(2026, 7, 2), 20_000),
            (1, 3, date(2026, 7, 1), 60_000),
            (3, 4, date(2026, 7, 2), 60_000),
            (1, 4, date(2026, 7, 3), 40_000),
            (4, 1, date(2026, 7, 4), 10_000),
        ]
    )
    paths = money_paths(tx, {1}, [4, 1, 99], gap_days=2, k=3)
    assert paths["target_gid"].tolist() == [4, 4, 4]
    assert paths["path_rank"].tolist() == [1, 2, 3]
    assert paths["bottleneck_kzt"].tolist() == [60_000, 40_000, 20_000]
    assert paths.iloc[0]["path_gids"] == "1>3>4"
    assert paths.iloc[0]["path_days"] == "1>2"
    for row in paths.itertuples(index=False):
        assert len(row.path_gids.split(">")) == row.hops + 1
        assert len(row.path_days.split(">")) == row.hops
        assert len(row.path_amounts.split(">")) == row.hops


def test_ablation_uses_one_nonseed_denominator():
    tx = _tx(
        [
            (1, 2, date(2026, 7, 1), 5_000),
            (2, 3, date(2026, 7, 3), 5_000),
            (3, 4, date(2026, 7, 10), 5_000),
        ]
    )
    nodes = pd.DataFrame(
        {"gid": [1, 2, 3, 4, 5], "is_seed": [True, False, False, False, False]}
    )
    graph = nx.DiGraph()
    graph.add_edges_from(tx[["src", "dst"]].itertuples(index=False, name=None))
    table = ablation_table(graph, tx, {1}, nodes).set_index("level")
    assert table.loc["topology", "n_nonseed_nodes"] == 3
    assert table.loc["chrono_2d", "n_nonseed_nodes"] == 2
    assert table.loc["chrono_2d", "share"] == pytest.approx(0.5)
