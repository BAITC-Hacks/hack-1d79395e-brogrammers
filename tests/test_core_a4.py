"""Focused integration cases for A4 grouping, motifs, and robustness."""

from datetime import date

import networkx as nx
import pandas as pd
import pytest

from graf.clusters import louvain_clusters, summarize_clusters, undirected_amount_projection
from graf.fingerprints import describe_cluster
from graf.resilience import removal_curve, seed_reach, single_node_loss


def test_louvain_stays_inside_weak_components_and_keeps_isolates():
    graph = nx.DiGraph()
    graph.add_nodes_from(range(1, 8))
    graph.add_edge(1, 2, sum_kzt=10)
    graph.add_edge(2, 1, sum_kzt=20)
    graph.add_edge(2, 3, sum_kzt=30)
    graph.add_edge(3, 4, sum_kzt=40)
    graph.add_edge(5, 6, sum_kzt=50)
    assert undirected_amount_projection(graph)[1][2]["sum_kzt"] == 30

    mapping = louvain_clusters(graph)
    assert set(mapping) == set(graph)
    assert len(set(mapping.values())) >= 3
    component_by_node = {
        gid: index
        for index, component in enumerate(nx.weakly_connected_components(graph))
        for gid in component
    }
    for cluster_id in set(mapping.values()):
        assert len({
            component_by_node[gid] for gid, value in mapping.items()
            if value == cluster_id
        }) == 1
    assert mapping[7] != mapping[5]

    features = pd.DataFrame({
        "gid": list(range(1, 8)),
        "cluster_id": [mapping[gid] for gid in range(1, 8)],
        "is_seed": [True, False, False, False, False, False, False],
        "role": ["peripheral"] * 7,
        "priority_score": [0.5] * 7,
    })
    edges = pd.DataFrame(
        [(src, dst, attrs["sum_kzt"]) for src, dst, attrs in graph.edges(data=True)],
        columns=["src", "dst", "sum_kzt"],
    )
    summary = summarize_clusters(features, edges)
    assert summary.n_nodes.sum() == 7
    assert summary.n_seed.sum() == 1
    assert summary.sum_kzt_internal.sum() <= edges.sum_kzt.sum()
    assert all(summary.hypothesis.str.startswith("Признаки"))


def test_fingerprints_require_observed_structure_and_chronology():
    graph = nx.DiGraph()
    gids = [10, 20] + list(range(31, 41))
    graph.add_nodes_from(gids)
    for mid in (31, 32, 33):
        graph.add_edge(20, mid)
        graph.add_edge(mid, 10)
    for recipient in range(34, 41):
        graph.add_edge(20, recipient)
    graph.add_edge(10, 20)
    graph.add_edge(31, 32)
    graph.add_edge(32, 33)
    roles = ["consolidator", "distributor"] + ["transit"] * 3 + ["peripheral"] * 7
    features = pd.DataFrame({
        "gid": gids,
        "role": roles,
        "is_seed": [False] * len(gids),
        "near_threshold_share": [0.0, 0.0, 0.6, 0.7] + [0.0] * 8,
    })
    tx = pd.DataFrame({
        "src": [31, 32],
        "dst": [32, 33],
        "date": [date(2026, 7, 1), date(2026, 7, 2)],
    })
    names, hypothesis = describe_cluster(0, features, graph, tx, 123_000.0)
    assert set(names.split(";")) == {
        "fan_in", "fan_out", "chain", "scatter_gather", "cycle",
        "fragmentation",
    }
    assert "20" in hypothesis and "10" in hypothesis
    assert "12 узлов" in hypothesis and "123,000" in hypothesis


def test_brokerage_excludes_the_removed_node_and_curve_is_repeatable():
    graph = nx.DiGraph()
    graph.add_nodes_from(range(1, 7))
    graph.add_edges_from([(1, 2), (2, 3), (3, 4), (1, 5), (3, 6)])
    assert seed_reach(graph, {1}) == {2, 3, 4, 5, 6}
    losses = single_node_loss(graph, {1}, {2, 3, 5})
    assert losses[2] == pytest.approx(3 / 5)
    assert losses[3] == pytest.approx(2 / 5)
    assert losses[5] == 0.0

    features = pd.DataFrame({
        "gid": list(range(1, 7)),
        "is_seed": [True, False, False, False, False, False],
        "priority_score": [0.0, 1.0, 0.9, 0.2, 0.1, 0.3],
        "betweenness": [0.0, 0.8, 0.7, 0.0, 0.0, 0.0],
        "out_deg": [2, 1, 2, 0, 0, 0],
        "in_deg": [0, 1, 1, 1, 1, 1],
    })
    curve = removal_curve(graph, features, n_values=(0, 1, 2))
    assert curve.equals(removal_curve(graph, features, n_values=(0, 1, 2)))
    one = curve.loc[curve.strategy.eq("priority") & curve.n_removed.eq(1)].iloc[0]
    assert one.seed_reach_share == pytest.approx(1 / 5)
    assert curve.loc[curve.strategy.eq("all_seeds"), "largest_wcc"].iloc[0] == 4
