"""Focused A4 checks for ranking, final cluster metadata, and audit flags."""

import json

import networkx as nx
import pandas as pd
import pytest

from graf.check import _audit_table
from graf.outputs import write_outputs
from graf.priority import score_priority


def test_priority_uses_components_and_counter_signal_multipliers():
    features = pd.DataFrame(
        {
            "gid": [1, 2, 3],
            "role": ["coordinator", "consolidator", "payer"],
            "role_label": ["кандидат в организаторы", "признаки сбора", "разовый плательщик"],
            "is_seed": [True, False, False],
            "seed_above_bottom": [True, False, False],
            "excluded": [False, False, True],
            "visibility": ["in_unseen_seed", "full", "external_funding"],
            "counter_signals": ["seed: входящие не видны", "", "внешний источник"],
            "in_deg": [1, 5, 0],
            "out_deg": [2, 1, 1],
            "in_kzt": [0, 200_000, 0],
            "out_kzt": [1_000, 100_000, 10_000],
            "tracked_in": [0, 100_000, 0],
            "seed_exp_chrono": [0, 2, 0],
            "fast_out_share": [0.0, 0.2, 0.0],
            "max_sync_payers": [0, 3, 0],
        }
    )
    result = score_priority(features, {1: 0.9, 2: 0.5, 3: 0.9}).set_index("gid")
    assert result.loc[1, "prio_role"] == pytest.approx(1.0)
    assert result.loc[2, "prio_temporal"] == pytest.approx(1.0)
    assert result.loc[3, "prio_brokerage"] == pytest.approx(0.0)
    assert result.loc[1, "prio_multiplier"] == pytest.approx(0.6 * 0.8)
    assert result.loc[2, "prio_multiplier"] == pytest.approx(1.0)
    assert result.loc[3, "prio_multiplier"] == pytest.approx(0.0)
    assert result.loc[3, "priority_score"] == 0.0
    assert result.loc[2, "rank"] == 1
    assert "Контр: seed" in result.loc[1, "why"]
    why = result.loc[2, "why"]
    assert "деньги курьеров" in why
    assert "атрибутировано 100,000 ₸" in why
    assert "seed с маршрутом 2" in why
    assert "связи вход/выход 5/1" in why
    assert "потеря seed-достижимости при удалении 50.00%" in why
    assert "50.0% входящих не атрибутировано seed" in why
    assert "не доказывает происхождение" in why

    # Reachable endpoints still lose themselves when removed. A disabled score
    # component must not be described as a measured zero connectivity loss.
    terminal = features.iloc[[1]].assign(
        out_deg=0, role="terminal", role_label="конечный получатель"
    )
    endpoint = score_priority(terminal, {2: 0.1}).iloc[0]
    assert endpoint.prio_brokerage == 0
    assert "компонент связности не учитывается" in endpoint.why
    assert "потеря seed-достижимости при удалении 0.00%" not in endpoint.why


def test_outputs_keep_final_cluster_hypothesis_and_write_requests(tmp_path):
    features = pd.DataFrame(
        {
            "gid": [1, 2, 3],
            "depth": [0, 1, 4],
            "is_seed": [True, False, False],
            "in_deg": [0, 1, 1],
            "out_deg": [1, 1, 0],
            "in_kzt": [0.0, 20_000.0, 10_000.0],
            "out_kzt": [20_000.0, 10_000.0, 0.0],
            "pass_through": [float("nan"), 0.5, 0.0],
            "role": ["distributor", "consolidator", "terminal"],
            "role_score": [0.8, 0.7, 0.6],
            "role_label": ["признаки распределения", "признаки сбора", "конечный получатель"],
            "priority_score": [0.8, 0.7, 0.6],
            "rank": [1, 2, 3],
            "cluster_id": [0, 0, 0],
            "evidence": ["исходящих 1", "входящих 1", "входящих 1"],
            "seed_above_bottom": [True, False, False],
            "excluded": [False, False, False],
            "near_threshold_share": [0.0, 0.6, 0.0],
            "p_forward": [0.0, 0.0, 0.7],
        }
    )
    edges = pd.DataFrame(
        {"src": [1, 2], "dst": [2, 3], "sum_kzt": [20_000.0, 10_000.0], "n_tx": [1, 1]}
    )
    graph = nx.DiGraph()
    graph.add_weighted_edges_from([(1, 2, 20_000.0), (2, 3, 10_000.0)])
    summary = pd.DataFrame(
        {
            "cluster_id": [0],
            "fingerprints": ["fan_in;chain"],
            "hypothesis": ["Признаки цепочки из 3 узлов"],
        }
    )
    write_outputs(features, edges, graph, tmp_path, summary)
    clusters = pd.read_csv(tmp_path / "clusters.csv")
    assert clusters.loc[0, "fingerprints"] == "fan_in;chain"
    assert clusters.loc[0, "hypothesis"] == "Признаки цепочки из 3 узлов"
    review = pd.read_csv(tmp_path / "seeds_review.csv")
    assert review["gid"].tolist() == [1]
    requests = pd.read_csv(tmp_path / "data_requests.csv")
    assert len(requests) == 6
    assert (requests["request"] == "запросить выписку исходящих").sum() == 1
    payload = json.loads((tmp_path / "graph.json").read_text(encoding="utf-8"))
    assert all(isinstance(node["id"], str) for node in payload["nodes"])


def test_audit_counts_risks_in_both_top_windows():
    roles = pd.DataFrame(
        {
            "gid": [1, 2, 3],
            "role": ["coordinator", "payer", "terminal"],
            "is_seed": [True, False, False],
            "excluded": [False, False, True],
            "aggregator_like": [False, True, False],
            "visibility": ["in_unseen_seed", "full", "out_unseen"],
            "seed_exp_chrono": [0, 0, 1],
        }
    )
    top = pd.DataFrame({"rank": [1, 2, 3], "gid": [1, 2, 3]})
    audit = _audit_table(roles, top).set_index(["scope", "check"])
    assert audit.loc[("top10", "payer"), "count"] == 1
    assert audit.loc[("top10", "excluded"), "count"] == 1
    assert audit.loc[("top30", "seed_exp_chrono == 0 (non-seed)"), "count"] == 1
    assert not audit.loc[("top10", "payer"), "ok"]
