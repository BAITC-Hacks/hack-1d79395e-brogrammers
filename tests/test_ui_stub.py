"""B0 integration checks on the real organiser data, never runs A's pipeline."""
import json
from pathlib import Path

import pandas as pd
import pytest

from ui.data import load_bundle, load_raw, REQUIRED, OPTIONAL
from ui.theme import LABELS

OUT = Path("out_stub")


@pytest.fixture(scope="module")
def bundle():
    if not (OUT / "run_meta.json").exists():
        pytest.skip("Сначала python tools/make_stub_outputs.py --data data --out out_stub")
    return load_bundle(OUT)


def test_complete_contract(bundle):
    assert not bundle.missing
    assert bundle.is_stub
    n = bundle.nodes
    assert len(n) == 2248
    assert n.gid.nunique() == 2248
    assert list(n.columns[:6]) == REQUIRED["nodes_roles"]
    expected = "rank role_label role_alt ambiguous confidence_level visibility excluded aggregator_like seed_above_bottom is_seed truncated depth in_deg out_deg in_tx out_tx in_kzt out_kzt pass_through in_hhi out_hhi betweenness from_key to_key fast_out_share max_sync_payers near_threshold_share p_forward tracked_in tracked_out tracked_share_in tracked_out_share tracked_kept seed_exp_topo seed_exp_chrono seed_exp_fast signals counter_signals prio_role prio_money prio_brokerage prio_volume prio_temporal prio_multiplier".split()
    assert set(expected) <= set(n.columns)
    for name, cols in {**REQUIRED, **OPTIONAL}.items():
        assert set(cols) <= set(bundle.tables[name].columns)
    assert n[REQUIRED["nodes_roles"]].notna().all().all()
    assert n.role.isin(LABELS).all()
    assert n.evidence.str.len().between(1, 200).all()
    assert n.evidence.str.contains(r"\d").all()
    assert len(bundle.tables["clusters"]) == 20
    assert bundle.tables["clusters"].n_nodes.sum() == len(n)
    top = bundle.tables["top_nodes"]
    assert len(top) == 30
    assert not top.role.eq("payer").any()
    assert top.priority_score.is_monotonic_decreasing
    assert top["rank"].tolist() == list(range(1,31))
    assert n.priority_score.between(0,1).all() and n.role_score.between(0,1).all()


def test_source_metrics_and_precision(bundle):
    edges, nodes, tx = load_raw("data")
    actual = bundle.nodes.set_index("gid")
    assert set(actual.index) == set(nodes.gid)
    assert actual.is_seed.sum() == 81
    assert ((actual.in_deg+actual.out_deg).eq(0) & actual.is_seed).sum() == 19
    for side, column in [("src", "out_kzt"), ("dst", "in_kzt")]:
        expected = edges.groupby(side).sum_kzt.sum().reindex(actual.index, fill_value=0)
        assert (actual[column]-expected).abs().max() < .001
    graph = json.loads((OUT / "graph.json").read_text())
    assert len(graph["nodes"]) == len(nodes)
    assert len(graph["edges"]) == len(edges)
    assert {r["id"] for r in graph["nodes"]} == set(nodes.gid.astype(str))
    for row in graph["nodes"]:
        assert isinstance(row["id"], str) and len(row["id"]) == 18
        assert isinstance(row["x"], (float, int)) and isinstance(row["y"], (float, int))
    for row in graph["edges"]:
        assert isinstance(row["src"], str) and isinstance(row["dst"], str)
        assert len(row["src"]) == len(row["dst"]) == 18


def test_three_real_paths_per_top_node(bundle):
    _, nodes, tx = load_raw("data")
    seeds = set(nodes.loc[nodes.is_seed, "gid"].astype(int))
    transfers = {(int(r.src), int(r.dst), r.date.day, float(r.sum_kzt)) for r in tx.itertuples()}
    paths = bundle.tables["paths"]
    assert set(paths.target_gid) == set(bundle.tables["top_nodes"].gid)
    assert paths.groupby("target_gid").size().eq(3).all()
    for r in paths.itertuples():
        ids = list(map(int, r.path_gids.split(">")))
        days = list(map(int, r.path_days.split(">")))
        amounts = list(map(float, r.path_amounts.split(">")))
        assert ids[0] == r.seed_gid and ids[0] in seeds
        assert ids[-1] == r.target_gid
        assert len(ids) == len(days) == r.hops+1
        assert len(amounts) == r.hops and r.hops <= 4
        assert all(0 <= b-a <= 7 for a,b in zip(days, days[1:]))
        assert all((src,dst,day,amount) in transfers for src,dst,day,amount in zip(ids,ids[1:],days[1:],amounts))
        assert min(amounts) == r.bottleneck_kzt


def test_refuses_real_output(tmp_path):
    from tools.make_stub_outputs import make_stubs
    with pytest.raises(ValueError, match="out/"):
        make_stubs("data", tmp_path / "out")
