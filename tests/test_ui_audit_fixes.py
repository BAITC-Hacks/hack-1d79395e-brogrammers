"""B-004 regression scenarios adapted to the integrated A interface.

Preserves the behavior checked in B's 13500e9 without fixing a particular
Plotly symbol, border color, or location of the shared role-criteria helper.
"""
import json
import math
import re
from itertools import combinations
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from graf.evidence_xlsx import evidence_frames, role_criteria
from ui.data import load_bundle, chronology_filter
from ui.graphs import directed_graph, ego_html, layer_figure
from ui.navigation import selected_gid

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("gap,column", [(2, "seed_exp_fast"), (31, "seed_exp_chrono")])
def test_saved_money_layer_without_transactions(gap, column):
    nodes = load_bundle(ROOT / "out").nodes
    counts, explanation = chronology_filter(nodes, None, gap, ready=True)
    assert counts == nodes.set_index("gid")[column].to_dict()
    assert any(counts.values()) and "Готовая колонка" in explanation
    with pytest.raises(ValueError, match="transactions.parquet"):
        chronology_filter(nodes, None, 7, ready=True)


def _at(value, index):
    """Read scalar and per-point Plotly styling through the same assertion."""
    return value[index] if isinstance(value, (list, tuple)) else value


def map_points(figure):
    return {
        row[0]: {
            "opacity": _at(trace.marker.opacity, i),
            "fill": _at(trace.marker.color, i),
            "symbol": _at(trace.marker.symbol, i),
            "border": _at(trace.marker.line.color, i),
            "width": _at(trace.marker.line.width, i),
        }
        for trace in figure.data if trace.customdata is not None
        for i, row in enumerate(trace.customdata)
    }


def test_map_visibility_and_hidden_selection():
    bundle = load_bundle(ROOT / "out")
    gid = str(bundle.tables["top_nodes"].iloc[0].gid)
    nodes = bundle.nodes.loc[~bundle.nodes.gid.astype(str).eq(gid)]
    figure, _ = layer_figure(nodes, bundle.graph["edges"], bundle.graph, gid)
    assert all(point["opacity"] == 1 for point in map_points(figure).values())

    visible = bundle.nodes.copy()
    original, _ = layer_figure(visible, [], bundle.graph)
    visible["visibility"] = "full"
    complete, _ = layer_figure(visible, [], bundle.graph)
    before, after = map_points(original), map_points(complete)
    changed = {gid for gid in before if before[gid] != after[gid]}
    assert changed == set(bundle.nodes.loc[bundle.nodes.visibility.ne("full"), "gid"].astype(str))


def test_map_new_selection_highlights_neighbors_and_rejects_hidden_gid():
    bundle = load_bundle(ROOT / "out")
    edge = bundle.graph["edges"][0]
    event = {"selection": {"points": [{"customdata": [edge["src"]]}]}}
    selected = selected_gid(event, bundle.nodes.gid)
    assert selected == edge["src"]
    figure, _ = layer_figure(bundle.nodes, bundle.graph["edges"], bundle.graph, selected)
    expected = {selected}
    for item in bundle.graph["edges"]:
        if selected in (item["src"], item["dst"]):
            expected.update((item["src"], item["dst"]))
    assert {gid for gid, point in map_points(figure).items() if point["opacity"] == 1} == expected
    assert selected_gid(event, [edge["dst"]]) is None
    assert selected_gid({"selection": {"points": [{}]}}, bundle.nodes.gid) is None


def test_top_ego_has_separated_circles_and_visible_incomplete_borders():
    bundle = load_bundle(ROOT / "out")
    gid = str(bundle.tables["top_nodes"].iloc[0].gid)
    graph = directed_graph(bundle.nodes, bundle.graph["edges"])
    html, shown, total = ego_html(graph, gid)
    nodes = json.loads(re.search(r"nodes = new vis.DataSet\((\[.*?\])\);", html).group(1))
    assert shown == total and len(nodes) > 1
    collisions = [
        (left["id"], right["id"]) for left, right in combinations(nodes, 2)
        if math.hypot(left["x"] - right["x"], left["y"] - right["y"]) < left["size"] + right["size"]
    ]
    assert not collisions
    for node in nodes:
        data = graph.nodes[node["id"]]
        assert node["id"] in node["title"]
        if data["visibility"] != "full":
            assert node["shapeProperties"]["borderDashes"]
            assert node["borderWidth"] >= 2
            assert node["color"]["border"] != node["color"]["background"]
        if data["is_seed"]:
            assert node["borderWidth"] >= 4


def test_full_workbook_contains_all_requests_and_node_book_only_its_requests():
    bundle = load_bundle(ROOT / "out")
    requests = bundle.tables["data_requests"]
    frames = evidence_frames(ROOT / "data", ROOT / "out")
    actual = frames["Границы данных"].query("тип == 'запрос'")
    assert list(zip(actual.gid, actual.описание)) == list(zip(requests.gid.astype(str), requests.request))
    gid = str(requests.loc[~requests.gid.isin(bundle.tables["top_nodes"].gid), "gid"].iloc[0])
    per_node = evidence_frames(ROOT / "data", ROOT / "out", gid)["Границы данных"].query("тип == 'запрос'")
    assert set(per_node.gid) == {gid}
    assert len(per_node) == requests.gid.eq(int(gid)).sum()


def test_criteria_have_actual_thresholds_and_selection_order(monkeypatch):
    from graf import config

    monkeypatch.setattr(config, "PAYER_MAX_KZT", 123456)
    rules = role_criteria().set_index("роль")
    payer = rules.loc["payer", "ворота"]
    assert "123456" in payer
    for term in ["out_deg", "out_tx", "получатель", "transit"]:
        assert term in payer
    assert "не пройдены" in payer.lower()
    coordinator = rules.loc["coordinator", "ворота"]
    assert "from_key" in coordinator and "или" in coordinator.lower()
    terminal = rules.loc["terminal", "ворота"].replace(" ", "")
    assert "depth≤3" in terminal and "1−p_forward≥" in terminal
    assert "coordinator → payer" in rules.loc["Порядок выбора", "ворота"]


def test_map_card_action_survives_plotly_rerender(monkeypatch):
    monkeypatch.setenv("GRAF_OUT", str(ROOT / "out"))
    monkeypatch.setenv("GRAF_DATA", str(ROOT / "data"))
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_MODEL", "")
    app = AppTest.from_file(ROOT / "app.py", default_timeout=30).run()
    gid = str(load_bundle(ROOT / "out").tables["top_nodes"].iloc[0].gid)
    app.session_state["pending_gid"] = gid
    app.run()
    app.radio(key="page").set_value("Карта по коленам").run()
    app.run()  # Plotly can clear the event after mounting the updated figure.
    assert not app.exception
    next(button for button in app.button if button.label == f"Открыть узел {gid}").click().run()
    assert not app.exception
    assert app.radio(key="page").value == "Узел"
    assert app.session_state["gid"] == gid

