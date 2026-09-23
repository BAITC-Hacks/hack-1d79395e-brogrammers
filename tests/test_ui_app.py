"""B1: navigation, missing data and exact identifiers at presentation boundaries."""
import json
import re
from pathlib import Path

import pandas as pd
import pytest
from tools.ui_fixtures import ensure_stub
from streamlit.testing.v1 import AppTest

from ui.data import load_bundle, display_frame, json_records, fingerprint, load_raw
from ui.graphs import directed_graph, ego_html, bounded_nodes
from ui.card import counterparties

APP = Path(__file__).resolve().parents[1] / "app.py"

@pytest.fixture
def app(monkeypatch):
    if not Path("out_stub/nodes_roles.csv").exists():
        pytest.skip("Сначала создайте out_stub командой tools/make_stub_outputs.py")
    monkeypatch.setenv("GRAF_OUT", "out_stub")
    monkeypatch.setenv("GRAF_DATA", "data")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return AppTest.from_file(APP, default_timeout=30).run()


def test_top_and_node(app):
    assert not app.exception
    assert app.metric[0].value == "2,248"
    gid = str(load_bundle("out_stub").tables["top_nodes"].iloc[0].gid)
    app.session_state["pending_gid"] = gid
    app.run()
    assert not app.exception
    assert app.radio(key="page").value == "Узел"
    assert app.session_state["gid"] == gid
    assert any(gid in c.value for c in app.caption)
    assert len(app.code) == 3
    assert all(isinstance(x, str) and len(x) == 18 for x in app.dataframe[1].value.src)


def test_search_exact_and_missing(app):
    app.text_input(key="search").set_value("does-not-exist").run()
    assert not app.exception
    assert any("не найден" in info.value for info in app.info)
    gid = str(load_bundle("out_stub").nodes.iloc[2].gid)
    app.text_input(key="search").set_value(gid).run()
    open_button = next(b for b in app.button if b.label == "Открыть узел")
    open_button.click().run()
    assert not app.exception
    assert app.session_state["gid"] == gid
    assert app.radio(key="page").value == "Узел"


def test_isolated_seed_is_viewable(app):
    nodes = load_bundle("out_stub").nodes
    gid = str(nodes.loc[nodes.is_seed & (nodes.in_deg+nodes.out_deg).eq(0)].iloc[0].gid)
    app.session_state["pending_gid"] = gid
    app.run()
    assert not app.exception
    assert any("Показано 1 из 1" in c.value for c in app.caption)


def test_no_data_clear_message(tmp_path, monkeypatch):
    monkeypatch.setenv("GRAF_OUT", str(tmp_path / "missing"))
    app = AppTest.from_file(APP, default_timeout=20).run()
    assert not app.exception
    assert any("nodes_roles.csv" in info.value for info in app.info)


def test_money_fallback_and_empty_roles(app):
    next(r for r in app.radio if r.label == "Слой анализа").set_value("Деньги курьеров").run()
    assert not app.exception
    assert any("Узлов в следе" in info.value for info in app.info)
    app.multiselect[0].set_value([]).run()
    assert not app.exception
    assert app.metric[3].value == "0"


def test_exact_id_roundtrip(tmp_path):
    ids = [10**17+1, 10**17+2]
    frame = pd.DataFrame({"gid": ids, "src": ids[::-1], "sum_kzt": [1.0, 2.0]})
    shown = display_frame(frame)
    assert shown.gid.tolist() == list(map(str, ids))
    assert json_records(frame)[0]["gid"] == str(ids[0])
    assert json_records(frame)[1]["src"] == str(ids[0])
    from ui.data import read_csv
    file = tmp_path / "ids.csv"
    frame.to_csv(file, index=False)
    assert read_csv(file).gid.tolist() == ids


def test_graph_direction_precision_and_offline_resources():
    bundle = load_bundle("out_stub")
    graph = directed_graph(bundle.nodes, bundle.graph["edges"])
    gid = str(bundle.nodes.iloc[0].gid)
    html, shown, total = ego_html(graph, gid, 2, cap=30)
    assert shown <= 30 and shown <= total
    assert gid in html
    assert not re.search(r'<(?:script|link)[^>]*(?:src|href)=["\'](?:https?:)?//', html)
    nodes_json = re.search(r'nodes = new vis.DataSet\((\[.*?\])\);', html).group(1)
    edges_json = re.search(r'edges = new vis.DataSet\((\[.*?\])\);', html).group(1)
    node_ids = {n["id"] for n in json.loads(nodes_json)}
    assert all(isinstance(n, str) and len(n) == 18 for n in node_ids)
    assert gid in node_ids
    for edge in json.loads(edges_json):
        assert edge["from"] in node_ids and edge["to"] in node_ids
        assert graph.has_edge(edge["from"], edge["to"])
        assert edge["arrows"] == "to"


def test_counterparties_sum_and_dates():
    _, _, tx = load_raw("data")
    gid = int(tx.dst.iloc[0])
    actual = counterparties(tx, gid, "in")
    expected = tx.loc[tx.dst.eq(gid)].groupby("src").sum_kzt.sum()
    for row in actual.itertuples():
        assert row.sum_kzt == expected.loc[row.src]
        assert row.first_date <= row.last_date


def test_cache_fingerprint_changes(tmp_path):
    path = tmp_path / "nodes_roles.csv"
    path.write_text("old")
    old = fingerprint(tmp_path)
    path.write_text("new longer output")
    assert old != fingerprint(tmp_path)


@pytest.mark.parametrize('page', ['Карта по коленам', 'Кластеры', 'Устойчивость', 'Доказательства', 'Ассистент'])
def test_remaining_pages_without_api_key(app, page):
    app.radio(key='page').set_value(page).run()
    assert not app.exception
    assert any('не установление вины' in c.value for c in app.caption)
