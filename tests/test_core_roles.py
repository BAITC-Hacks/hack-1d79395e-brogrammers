"""Gate order, evidence, flags and 17-digit account IDs for A3."""

from pathlib import Path

import networkx as nx
import pandas as pd
import pytest

from graf.roles import ROLE_LABELS, assign_roles, run


BIG_GID = 100_000_000_000_000_017


def _row(gid: int, **changes) -> dict:
    row = {
        "gid": gid, "depth": 2, "is_seed": False,
        "in_deg": 0, "out_deg": 0, "in_tx": 0, "out_tx": 0,
        "in_kzt": 0.0, "out_kzt": 0.0, "pass_through": float("nan"),
        "in_hhi": 0.0, "out_hhi": 0.0,
        "fast_out_share": 0.0, "max_sync_payers": 0,
        "payer_one_off_share": 0.0, "active_in_days": 0,
        "p_forward": 0.0, "truncated": False,
        "tracked_share_in": 0.0, "tracked_out_share": 0.0,
        "seed_exp_chrono": 0,
    }
    row.update(changes)
    return row


def _case():
    # Structural metrics are supplied by features.py in production. The small
    # graph here exercises only key neighbours, payer destinations and HHI text.
    rows = [
        _row(1, depth=0, is_seed=True, in_deg=5, out_deg=10,
             in_kzt=100_000, out_kzt=300_000, pass_through=3.0),
        _row(2, in_deg=10, out_deg=1, in_kzt=1_000_000, out_kzt=50_000,
             in_hhi=0.1, max_sync_payers=5, tracked_share_in=1),
        _row(3, in_deg=1, out_deg=30, in_kzt=200_000, out_kzt=150_000,
             out_hhi=0.1, fast_out_share=0.8),
        _row(4, in_deg=2, out_deg=2, in_kzt=100_000, out_kzt=100_000,
             pass_through=1.0, fast_out_share=1.0, seed_exp_chrono=1),
        _row(5, in_deg=1, out_deg=0, in_kzt=100_000,
             tracked_share_in=0.8, seed_exp_chrono=1),
        _row(6, out_deg=1, out_tx=1, out_kzt=50_000),
        _row(7, depth=4, in_deg=1, p_forward=0.2, truncated=True),
        _row(8, depth=4, in_deg=1, p_forward=0.7, truncated=True),
        _row(9, in_deg=1, out_deg=1, in_kzt=20_000,
             out_kzt=460_000, pass_through=23,
             tracked_out_share=0, seed_exp_chrono=1),
        _row(BIG_GID, in_deg=10, in_kzt=1_000_000,
             payer_one_off_share=0.9, in_hhi=0.1, active_in_days=15),
        # Numeric seed pass-through must not trigger transit or terminal.
        _row(11, depth=0, is_seed=True, in_deg=1, out_deg=1,
             in_kzt=1_000_000, out_kzt=1_000_000, pass_through=1.0),
        # Key links alone trigger coordinator: K, D and T each count as key.
        _row(12, in_deg=3, out_deg=3, in_kzt=100_000, out_kzt=40_000),
        _row(13, in_deg=5, out_deg=1, in_kzt=100_000, out_kzt=100_000,
             pass_through=1.0, in_hhi=0.6, fast_out_share=1.0,
             seed_exp_chrono=1),
        _row(14, in_deg=2, out_deg=1, in_kzt=1_000_000, out_kzt=20_000,
             pass_through=0.02, tracked_share_in=0.01),
        _row(15, in_deg=5, out_deg=1, in_kzt=100_000, out_kzt=80_000,
             pass_through=0.8, max_sync_payers=1,
             fast_out_share=0.6, seed_exp_chrono=1),
        _row(16, depth=0, is_seed=True, in_deg=1, out_deg=1,
             in_kzt=1_000_000, out_kzt=20_000, pass_through=0.02),
    ]
    graph = nx.DiGraph()
    graph.add_nodes_from(row["gid"] for row in rows)
    graph.add_edge(6, 2, sum_kzt=50_000)
    for key_gid in (2, 3, 4):
        graph.add_edge(key_gid, 12, sum_kzt=10_000)
        graph.add_edge(12, key_gid, sum_kzt=10_000)
    graph.add_edge(1, 11, sum_kzt=10_000)
    graph.add_edge(13, 14, sum_kzt=500_000)
    return pd.DataFrame(rows), graph


def test_gate_order_all_roles_key_union_and_seed_pass_through(tmp_path: Path):
    features, graph = _case()
    result = assign_roles(
        features, graph, tmp_path / "missing_excluded.csv"
    ).set_index("gid")
    assert set(result["role"]).issubset(ROLE_LABELS)
    assert result.loc[1, "role"] == "coordinator"
    assert result.loc[2, "role"] == "consolidator"
    assert result.loc[3, "role"] == "distributor"
    assert result.loc[4, "role"] == "transit"
    assert result.loc[5, "role"] == "terminal"
    assert result.loc[6, "role"] == "payer"
    assert result.loc[7, "role"] == "terminal"  # estimated E′ at depth 4
    assert result.loc[8, "role"] == "peripheral"
    assert result.loc[8, "role_score"] == pytest.approx(0.3)
    assert result.loc[12, "role"] == "coordinator"
    assert result.loc[12, "from_key"] == 3
    assert result.loc[12, "to_key"] == 3
    assert result.loc[13, "role"] == "transit"  # T score beats K score
    assert result.loc[11, "role"] == "peripheral"
    assert "пропуск" not in result.loc[11, "signals"]
    assert result.loc[16, "role"] == "peripheral"
    assert result.loc[15, "role_alt"] == "consolidator"
    assert result.loc[15, "ambiguous"]
    assert result.loc[1, "seed_above_bottom"]
    assert not result.loc[11, "seed_above_bottom"]


def test_scores_flags_counters_and_evidence_contract(tmp_path: Path):
    features, graph = _case()
    excluded_path = tmp_path / "excluded_accounts.csv"
    excluded_path.write_text(
        f"gid,account_type,reason\n{BIG_GID},technical,АБС\n", encoding="utf-8"
    )
    result = assign_roles(features, graph, excluded_path).set_index("gid")
    assert result.loc[2, "role_score"] == pytest.approx(
        0.4 * 10 / 15 + 0.2 * 0.9 + 0.2 + 0.2
    )
    assert result.loc[4, "role_score"] == pytest.approx(1.0)
    assert result.loc[7, "role_score"] == pytest.approx(0.8)
    assert result.loc[9, "visibility"] == "external_funding"
    assert "23.0 раза" in result.loc[9, "counter_signals"]
    assert result.loc[7, "visibility"] == "out_unseen"
    assert result.loc[1, "visibility"] == "in_unseen_seed"
    assert result.loc[BIG_GID, "excluded"]
    assert result.loc[BIG_GID, "aggregator_like"]
    assert "technical" in result.loc[BIG_GID, "counter_signals"]
    assert "АБС" in result.loc[BIG_GID, "counter_signals"]
    assert "лишь 1%" in result.loc[14, "counter_signals"]
    assert "крупнейший плательщик" in result.loc[13, "counter_signals"]
    assert result.loc[6, "confidence_level"] == "высокая"
    assert result.loc[8, "confidence_level"] == "низкая"
    assert result["evidence"].str.len().between(1, 200).all()
    assert result["evidence"].str.contains(r"\d", regex=True).all()
    assert result["role_label"].map(lambda label: label in ROLE_LABELS.values()).all()
    assert result.loc[1, "role_label"] == "кандидат в организаторы"


def test_run_replaces_features_and_preserves_existing_columns(tmp_path: Path):
    features, graph = _case()
    features["marker"] = 42
    context = {
        "features": features, "graph": graph,
        "excluded_path": tmp_path / "missing_excluded.csv",
    }
    run(context)
    assert len(context["features"]) == len(features)
    assert context["features"]["marker"].eq(42).all()
    assert context["features"]["gid"].tolist() == features["gid"].tolist()


def test_boundary_terminal_explains_estimate_before_other_counters(tmp_path: Path):
    features, graph = _case()
    features.loc[features.gid.eq(7), "in_hhi"] = 1.0
    result = assign_roles(features, graph, tmp_path / "missing.csv").set_index("gid")
    evidence = result.loc[7, "evidence"]
    assert result.loc[7, "role"] == "terminal"
    assert result.loc[7, "role_score"] == pytest.approx(0.8)
    assert "оценка 1−p_forward=80%" in evidence
    assert "по калибровке" in evidence
    assert "исходящие не видны" in evidence
    assert "Контр: обрыв 4-го колена" in evidence
    assert len(evidence) <= 200


def test_coordinator_evidence_names_the_gate_that_actually_passed(tmp_path: Path):
    features, graph = _case()
    result = assign_roles(features, graph, tmp_path / "missing.csv").set_index("gid")
    assert "ключевых соседей 3→3 (порог 3/3)" in result.loc[12, "evidence"]
    assert "связей вход/выход 3/3" in result.loc[12, "evidence"]
    assert "связей вход/выход 5/10 (порог 5/10)" in result.loc[1, "evidence"]
