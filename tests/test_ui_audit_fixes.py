"""Regressions for A-004: analyst-visible failures on real release data."""
import json
import math
import re
from itertools import combinations

import pandas as pd
import pytest

from ui.data import load_bundle, chronology_filter
from ui.graphs import directed_graph, ego_html, layer_figure, selected_map_gid
from graf.evidence_xlsx import evidence_frames


@pytest.mark.parametrize("gap,column", [(2, "seed_exp_fast"), (31, "seed_exp_chrono")])
def test_saved_money_layer_without_transactions(gap, column):
    nodes = load_bundle("out").nodes
    counts, explanation = chronology_filter(nodes, None, gap, ready=True)
    assert counts == nodes.set_index("gid")[column].to_dict()
    assert any(counts.values()) and "Готовая колонка" in explanation
    with pytest.raises(ValueError, match="transactions.parquet"):
        chronology_filter(nodes, None, 7, ready=True)


def map_points(figure):
    return {row[0]: (trace.marker.opacity[i], trace.marker.symbol[i], trace.marker.line.color[i])
            for trace in figure.data if trace.customdata is not None
            for i, row in enumerate(trace.customdata)}


def test_map_visibility_and_hidden_selection():
    bundle = load_bundle("out")
    gid = str(bundle.tables["top_nodes"].iloc[0].gid)
    nodes = bundle.nodes.loc[~bundle.nodes.gid.astype(str).eq(gid)]
    figure, _ = layer_figure(nodes, bundle.graph["edges"], bundle.graph, gid)
    assert all(p[0] == 1 for p in map_points(figure).values())
    visible = bundle.nodes.copy()
    original, _ = layer_figure(visible, [], bundle.graph)
    visible["visibility"] = "full"
    complete, _ = layer_figure(visible, [], bundle.graph)
    before, after = map_points(original), map_points(complete)
    changed = {g for g in before if before[g] != after[g]}
    assert changed == set(bundle.nodes.loc[bundle.nodes.visibility.ne("full"), "gid"].astype(str))


def test_map_new_selection_highlights_neighbors_and_rejects_hidden_gid():
    b = load_bundle("out")
    edge = b.graph["edges"][0]
    event = {"selection": {"points": [{"customdata": [edge["src"]]}]}}
    selected = selected_map_gid(event, b.nodes.gid)
    assert selected == edge["src"]
    fig, _ = layer_figure(b.nodes, b.graph["edges"], b.graph, selected)
    expected = {selected}
    for e in b.graph["edges"]:
        if selected in (e["src"], e["dst"]):
            expected.update((e["src"], e["dst"]))
    assert {g for g, p in map_points(fig).items() if p[0] == 1} == expected
    assert selected_map_gid(event, [edge["dst"]]) is None
    assert selected_map_gid({"selection": {"points": [{}]}}, b.nodes.gid) is None


def test_top_ego_has_separated_circles_and_visible_incomplete_borders():
    b = load_bundle("out")
    gid = str(b.tables["top_nodes"].iloc[0].gid)
    graph = directed_graph(b.nodes, b.graph["edges"])
    html, shown, total = ego_html(graph, gid)
    nodes = json.loads(re.search(r"nodes = new vis.DataSet\((\[.*?\])\);", html).group(1))
    assert shown == total and len(nodes) > 1
    collisions = [(a["id"], b["id"]) for a, b in combinations(nodes, 2)
                  if math.hypot(a["x"]-b["x"], a["y"]-b["y"]) < a["size"]+b["size"]]
    assert not collisions
    for node in nodes:
        data = graph.nodes[node["id"]]
        if data["visibility"] != "full":
            assert node["shapeProperties"]["borderDashes"]
            assert node["borderWidth"] >= 3
            assert node["color"]["border"] != node["color"]["background"]
        if data["is_seed"]:
            assert node["color"]["border"] == "#000000"


def test_full_workbook_contains_all_requests_and_node_book_only_its_requests():
    b = load_bundle("out")
    requests = b.tables["data_requests"]
    frames = evidence_frames("data", "out")
    actual = frames["Границы данных"].query("тип == 'запрос'")
    assert list(zip(actual.gid, actual.описание)) == list(zip(requests.gid.astype(str), requests.request))
    # A seed outside the top list still has an actionable request in the full book.
    gid = str(requests.loc[~requests.gid.isin(b.tables["top_nodes"].gid), "gid"].iloc[0])
    per_node = evidence_frames("data", "out", gid)["Границы данных"].query("тип == 'запрос'")
    assert set(per_node.gid) == {gid}
    assert len(per_node) == requests.gid.eq(int(gid)).sum()


def test_criteria_have_actual_thresholds_and_selection_order(monkeypatch):
    from graf import config
    from ui.criteria import role_criteria, ROLE_ORDER
    monkeypatch.setattr(config, "PAYER_MAX_KZT", 123456)
    rules = {r["роль"]: r for r in role_criteria()}
    assert "123456" in rules["payer"]["ворота"]
    for term in ["out_deg", "out_tx", "получатель", "transit НЕ"]:
        assert term in rules["payer"]["ворота"]
    assert "from_key" in rules["coordinator"]["ворота"] and "ИЛИ" in rules["coordinator"]["ворота"]
    assert "depth ≤ 3" in rules["terminal"]["ворота"] and "1 − p_forward ≥" in rules["terminal"]["ворота"]
    assert "coordinator → payer" in ROLE_ORDER
