"""B2: directed map, exact IDs and staged activation of A's chronology API."""
from pathlib import Path
import pandas as pd
import pytest
from tools.ui_fixtures import ensure_stub
from ui.data import load_bundle, chronology_filter, choose_output, flow_ready
from ui.graphs import layer_figure


def test_map_preserves_ids_and_limits_edges():
    bundle = load_bundle('out_stub')
    figure, total = layer_figure(bundle.nodes, bundle.graph['edges'], bundle.graph)
    points = [r for trace in figure.data if trace.customdata is not None for r in trace.customdata]
    assert {r[0] for r in points} == set(bundle.nodes.gid.astype(str))
    assert all(isinstance(r[0], str) and len(r[0]) == 18 for r in points)
    assert total == len(bundle.graph['edges'])
    assert sum(len(t.x)//3 for t in figure.data if t.mode == 'lines') == 400
    assert sum(bool(a.showarrow) for a in figure.layout.annotations) == 100
    assert len(figure.layout.shapes) == 1
    assert 'Обрыв обхода' in figure.layout.annotations[-1].text


def test_network_positions_and_selection():
    bundle = load_bundle('out_stub')
    nodes = bundle.nodes.head(4).copy()
    selected = str(nodes.iloc[0].gid)
    figure, _ = layer_figure(nodes, [], bundle.graph, selected, True)
    saved = {n['id']: n for n in bundle.graph['nodes']}
    for trace in figure.data:
        if trace.customdata is None:
            continue
        for row, x, y, opacity in zip(trace.customdata, trace.x, trace.y, trace.marker.opacity):
            assert (x, y) == (saved[row[0]]['x'], saved[row[0]]['y'])
            assert opacity == (1 if row[0] == selected else .2)
    assert not figure.layout.shapes


def test_ready_gate_and_default_output(tmp_path, monkeypatch):
    (tmp_path/'docs').mkdir()
    (tmp_path/'out').mkdir()
    (tmp_path/'out/nodes_roles.csv').touch()
    status = tmp_path/'docs/STATUS_A.md'
    assert choose_output(tmp_path).endswith('out_stub')
    status.write_text('| A1 | готово | abc |\ngraf.flow.chrono_reach готов', encoding='utf-8')
    assert Path(choose_output(tmp_path)).name == 'out'
    assert flow_ready(status)
    import graf.flow
    calls = []
    monkeypatch.setattr(graf.flow, 'chrono_reach', lambda tx,seeds,gap_days,max_hops: calls.append(gap_days) or {10**17: 1})
    nodes = pd.DataFrame({'gid':[10**17], 'is_seed':[True], 'seed_exp_fast':[2], 'seed_exp_chrono':[3]})
    assert chronology_filter(nodes, None, 2)[0] == {10**17:2}
    assert not calls
    assert chronology_filter(nodes, pd.DataFrame(), 7, ready=True)[0] == {10**17:1}
    assert calls == [7]
    with pytest.raises(ValueError):
        chronology_filter(nodes, None, 7)


def test_status_accepts_documented_function_signature(tmp_path):
    status=tmp_path/'STATUS_A.md'
    status.write_text('`graf.flow.chrono_reach(tx, seeds, gap_days, max_hops=4)` готов с A2', encoding='utf-8')
    assert flow_ready(status)
    status.write_text('graf.flow.chrono_reach не готов', encoding='utf-8')
    assert not flow_ready(status)


def test_incomplete_optional_file_is_reported(tmp_path):
    import shutil
    shutil.copytree('out_stub',tmp_path/'out_stub')
    pd.DataFrame({'strategy':['priority']}).to_csv(tmp_path/'out_stub/resilience.csv',index=False)
    bundle=load_bundle(tmp_path/'out_stub')
    assert bundle.tables['resilience'].empty
    assert any('resilience.csv: нет колонок' in s for s in bundle.missing)


def _marker_rows(figure):
    return {
        row[0]: {
            "opacity": opacity, "border_color": border_color,
            "border_width": border_width, "visibility": row[4],
        }
        for trace in figure.data if trace.customdata is not None
        for row, opacity, border_color, border_width in zip(
            trace.customdata, trace.marker.opacity,
            trace.marker.line.color, trace.marker.line.width,
        )
    }


def test_map_visibility_changes_outline_and_hover_without_dimming_selection():
    bundle = load_bundle('out')
    nodes = bundle.nodes.head(3).copy()
    nodes['visibility'] = 'full'
    nodes['is_seed'] = False
    nodes['rank'] = 100
    before, _ = layer_figure(nodes, [], bundle.graph)
    selected = str(nodes.iloc[0].gid)
    nodes.loc[nodes.index[0], 'visibility'] = 'out_unseen'
    after, _ = layer_figure(nodes, [], bundle.graph)
    full, incomplete = _marker_rows(before)[selected], _marker_rows(after)[selected]
    assert full['border_color'] != incomplete['border_color']
    assert incomplete['border_color'].startswith('rgba(')
    assert incomplete['border_width'] > full['border_width']
    assert incomplete['visibility'] == 'Неполная наблюдаемость'
    assert full['opacity'] == incomplete['opacity'] == 1


def test_hidden_selection_preserves_normal_map_after_filtering():
    bundle = load_bundle('out')
    selected = str(bundle.tables['top_nodes'].sort_values('rank').iloc[0].gid)
    filtered = bundle.nodes.loc[bundle.nodes.gid.astype(str).ne(selected)]
    ordinary, _ = layer_figure(filtered, bundle.graph['edges'], bundle.graph)
    hidden, _ = layer_figure(filtered, bundle.graph['edges'], bundle.graph, selected)
    assert hidden.to_json() == ordinary.to_json()
    assert set(row['opacity'] for row in _marker_rows(hidden).values()) == {1}


def _ego_payload(html):
    import json
    import re
    return json.loads(re.search(r'nodes = new vis.DataSet\((\[.*?\])\);', html).group(1))


def test_top_node_ego_circles_do_not_overlap_and_arrows_keep_direction():
    import json
    import math
    import re
    from ui.graphs import directed_graph, ego_html
    bundle = load_bundle('out')
    graph = directed_graph(bundle.nodes, bundle.graph['edges'])
    selected = str(bundle.tables['top_nodes'].sort_values('rank').iloc[0].gid)
    html, shown, total = ego_html(graph, selected, 1)
    nodes = _ego_payload(html)
    assert shown == total == len(nodes)
    assert all(isinstance(node['id'], str) and len(node['id']) == 18 for node in nodes)
    for i, node in enumerate(nodes):
        for other in nodes[i + 1:]:
            distance = math.hypot(node['x'] - other['x'], node['y'] - other['y'])
            assert distance >= node['size'] + other['size'], (node['id'], other['id'])
    edges = json.loads(re.search(r'edges = new vis.DataSet\((\[.*?\])\);', html).group(1))
    assert all(edge['arrows'] == 'to' and graph.has_edge(edge['from'], edge['to']) for edge in edges)


def test_ego_incomplete_visibility_has_contrasting_dashed_border():
    from ui.graphs import directed_graph, ego_html
    bundle = load_bundle('out')
    nodes = bundle.nodes.head(3).copy()
    nodes['is_seed'] = [False, False, True]
    nodes['visibility'] = ['full', 'out_unseen', 'in_unseen_seed']
    graph = directed_graph(nodes, [])
    html, shown, _ = ego_html(graph)
    payload = {row['id']: row for row in _ego_payload(html)}
    full, incomplete, seed = [payload[str(gid)] for gid in nodes.gid]
    assert shown == 3
    assert not full['shapeProperties']['borderDashes']
    assert incomplete['shapeProperties']['borderDashes']
    assert incomplete['color']['border'] != incomplete['color']['background']
    assert incomplete['borderWidth'] >= 2
    assert seed['shapeProperties']['borderDashes']
    assert seed['borderWidth'] == 4 and seed['color']['border'] == '#111827'


def test_map_seed_retains_dark_border_and_marks_missing_visibility_in_fill():
    bundle = load_bundle('out')
    nodes = bundle.nodes.head(2).copy()
    nodes['is_seed'] = [True, False]
    nodes['visibility'] = ['in_unseen_seed', 'full']
    nodes['rank'] = [100, 1]
    figure, _ = layer_figure(nodes, [], bundle.graph)
    seed_id = str(nodes.iloc[0].gid)
    seed = _marker_rows(figure)[seed_id]
    assert seed['border_color'] == '#111827' and seed['border_width'] == 4
    assert seed['visibility'] == 'Неполная наблюдаемость'
    top = _marker_rows(figure)[str(nodes.iloc[1].gid)]
    assert top['border_width'] == 3
    for trace in figure.data:
        if trace.customdata is None:
            continue
        for row, fill in zip(trace.customdata, trace.marker.color):
            if row[0] == seed_id:
                assert fill.startswith('rgba(') and fill.endswith(',0.55)')


def test_ego_short_labels_keep_exact_unique_ids_and_full_hover():
    from ui.graphs import directed_graph, ego_html
    bundle = load_bundle('out')
    graph = directed_graph(bundle.nodes, bundle.graph['edges'])
    selected = str(bundle.tables['top_nodes'].sort_values('rank').iloc[0].gid)
    html, _, _ = ego_html(graph, selected)
    payload = _ego_payload(html)
    assert len({node['label'] for node in payload}) == len(payload)
    for node in payload:
        assert isinstance(node['id'], str) and len(node['id']) == 18
        assert node['id'] in node['title']
        if node['id'] == selected:
            assert node['label'] == selected
        else:
            assert node['label'].startswith('…')
            assert node['id'].endswith(node['label'][1:])
            assert len(node['label']) < len(node['id'])


def test_ego_labels_expand_suffix_when_short_suffixes_collide():
    from ui.graphs import _node_labels
    ids = ['100000001123456789', '200000001123456789']
    labels = _node_labels(ids, None)
    assert len(set(labels.values())) == len(ids)
    assert labels[ids[0]] == ids[0] and labels[ids[1]] == ids[1]
