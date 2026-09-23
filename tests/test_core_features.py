"""Small, deterministic cases for structural, temporal, and boundary features."""

from datetime import date

import networkx as nx
import pandas as pd
import pytest

from graf.features import compute_features
from graf.temporal import add_temporal
from graf.truncation import apply, calibrate


def _small_graph():
    nodes = pd.DataFrame(
        {
            "gid": [1, 2, 3, 4, 5],
            "depth": [0, 1, 1, 2, 0],
            "is_seed": [True, False, False, False, True],
        }
    )
    edges = pd.DataFrame(
        {
            "src": [1, 3, 2],
            "dst": [2, 2, 4],
            "sum_kzt": [30_000.0, 70_000.0, 46_000.0],
            "n_tx": [1, 1, 2],
        }
    )
    graph = nx.DiGraph()
    for edge in edges.itertuples(index=False):
        graph.add_edge(
            edge.src, edge.dst, sum_kzt=edge.sum_kzt, n_tx=edge.n_tx
        )
    return nodes, edges, graph


def test_structural_features_keep_isolated_seed_and_use_counterparty_hhi():
    nodes, edges, graph = _small_graph()
    result = compute_features(edges, nodes, graph).set_index("gid")

    assert len(result) == 5
    assert result.loc[5, "is_seed"]
    assert result.loc[5, ["in_deg", "out_deg", "in_tx", "out_tx"]].eq(0).all()
    assert pd.isna(result.loc[5, "pass_through"])
    assert result.loc[2, "in_deg"] == 2
    assert result.loc[2, "in_tx"] == 2
    assert result.loc[2, "out_tx"] == 2
    assert result.loc[2, "in_kzt"] == 100_000
    assert result.loc[2, "pass_through"] == pytest.approx(0.46)
    assert result.loc[2, "in_hhi"] == pytest.approx(0.3**2 + 0.7**2)
    assert result.loc[2, "out_hhi"] == pytest.approx(1.0)
    assert result.loc[2, "betweenness"] > 0
    assert result.loc[5, "betweenness"] == 0


def test_temporal_features_use_dates_and_distinct_same_day_payers():
    nodes, edges, graph = _small_graph()
    features = compute_features(edges, nodes, graph)
    tx = pd.DataFrame(
        {
            "src": [1, 3, 2, 2],
            "dst": [2, 2, 4, 4],
            "date": [date(2026, 7, 1), date(2026, 7, 1), date(2026, 7, 3), date(2026, 7, 4)],
            "sum_kzt": [30_000.0, 70_000.0, 6_000.0, 40_000.0],
        }
    )
    result = add_temporal(features, tx, edges).set_index("gid")

    assert result.loc[2, "active_in_days"] == 1
    assert result.loc[2, "max_sync_payers"] == 2
    assert result.loc[2, "payer_one_off_share"] == pytest.approx(1.0)
    assert result.loc[4, "payer_one_off_share"] == pytest.approx(0.0)
    assert result.loc[2, "near_threshold_share"] == pytest.approx(0.5)
    assert result.loc[2, "fast_out_share"] == pytest.approx(6_000 / 46_000)
    assert result.loc[5, "fast_out_share"] == 0.0


def test_truncation_calibrates_only_nonseed_observed_depths():
    features = pd.DataFrame(
        {
            "gid": [1, 2, 3, 4, 5, 6, 7],
            "depth": [1, 2, 3, 2, 1, 4, 1],
            "is_seed": [False, False, False, False, False, False, True],
            "in_deg": [1] * 7,
            "out_deg": [1, 0, 1, 0, 1, 0, 1],
            "in_tx": [1, 1, 2, 4, 11, 1, 1],
        }
    )
    calibration = calibrate(features).set_index("bucket")
    assert calibration.loc["1", "n"] == 2
    assert calibration.loc["1", "p_forward"] == pytest.approx(0.5)
    assert calibration.loc["2-3", "p_forward"] == pytest.approx(1.0)
    assert calibration.loc["4-10", "p_forward"] == pytest.approx(0.0)
    assert calibration.loc[">10", "p_forward"] == pytest.approx(1.0)

    result = apply(features, calibration.reset_index()).set_index("gid")
    assert result.loc[6, "truncated"]
    assert result.loc[6, "p_forward"] == pytest.approx(0.5)
    assert not result.loc[1, "truncated"]
    assert result.loc[1, "p_forward"] == 0.0
