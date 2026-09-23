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
