"""Responses tool loop runs entirely offline with a fake client."""
import json
from types import SimpleNamespace as NS
import pytest
from tools.ui_fixtures import ensure_stub
from graf.assistant import GraphTools, TOOLS, SYSTEM, ask_graph, validate


@pytest.fixture
def graph():
    return GraphTools('out_stub')


def test_strict_schemas_and_validation(graph):
    for t in TOOLS:
        assert t['strict'] and 'function' not in t
        p = t['parameters']
        assert p['additionalProperties'] is False
        assert set(p['required']) == set(p['properties'])
    gid = str(graph.nodes.iloc[0].gid)
    assert graph.dispatch('node_card', {'gid':int(gid)})['gids'] == []
    assert 'error' in graph.dispatch('neighbors', {'gid':gid,'direction':'out','limit':51})
    assert 'error' in graph.dispatch('common_receivers', {'gids':[gid],'hops':3})
    assert 'error' in graph.dispatch('__dict__', {})
    assert graph.dispatch('node_card', {'gid':gid})['meta']['stub']


def test_neighbors_trails_and_top(graph):
    src, dst = next(iter(graph.graph.edges))
    outgoing = graph.neighbors(src, 'out', 50)
    incoming = graph.neighbors(dst, 'in', 50)
    assert all(e['src'] == src for e in outgoing['edges'])
    assert all(e['dst'] == dst for e in incoming['edges'])
    assert all(isinstance(e['src'], str) and isinstance(e['dst'], str) for e in outgoing['edges'])
    assert dst in graph.common_receivers([src], 1)['gids'] or graph.common_receivers([src],1)['truncated']
    top = graph.top_nodes(None,None,3)
    assert len(top['nodes']) == 3
    gid = top['gids'][0]
    paths = graph.money_trail(gid)
    assert all(r['target_gid'] == gid for r in paths['paths'])
    cid = int(graph.nodes.loc[graph.nodes.gid.eq(int(gid)), 'cluster_id'].iloc[0])
    assert graph.cluster_info(cid)['cluster']['cluster_id'] == cid


class FakeResponses:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.calls = []
    def create(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.outputs)


def call(name, arguments, call_id='c1'):
    return NS(type='function_call', name=name, arguments=arguments, call_id=call_id)


def response(id, output=(), text=''):
    return NS(id=id, output=list(output), output_text=text)


def test_multi_round_grounding_and_invalid_reference(graph, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    gid = str(graph.nodes.iloc[0].gid)
    fake = FakeResponses([
        response('r1',[call('node_card',json.dumps({'gid':gid}))]),
        response('r2',[call('neighbors',json.dumps({'gid':gid,'direction':'out','limit':2}),'c2')]),
        response('r3',text=f'{gid} — гипотеза; 999999999999999999'),
    ])
    result = ask_graph('Проверь узел','out_stub', client=NS(responses=fake),model='mock')
    assert result['calls'] == 2 and gid in result['gids']
    assert 'непроверенная ссылка' in result['text'] and 'ЗАГЛУШКА' in result['text']
    assert fake.calls[0]['tool_choice'] == 'required'
    assert fake.calls[1]['previous_response_id'] == 'r1'
    assert fake.calls[2]['previous_response_id'] == 'r2'
    assert all(c['instructions'] == SYSTEM for c in fake.calls)
    assert fake.calls[1]['input'][0]['call_id'] == 'c1'
    assert json.loads(fake.calls[1]['input'][0]['output'])['node']['gid'] == gid


def test_malformed_call_and_no_grounding():
    fake=FakeResponses([response('r1',[call('node_card','not-json')]),response('r2',text='Выдуманный вывод')])
    result=ask_graph('Проверь','out_stub',client=NS(responses=fake),model='mock')
    assert 'Недостаточно проверенных' in result['text']
    assert 'Неверный JSON' in json.loads(fake.calls[1]['input'][0]['output'])['error']


def test_loop_budget(graph):
    gid=str(graph.nodes.iloc[0].gid)
    fake=FakeResponses([response('r1',[call('node_card',json.dumps({'gid':gid}))])])
    result=ask_graph('Проверь','out_stub',client=NS(responses=fake),model='mock',max_rounds=1)
    assert 'лимит шагов' in result['text']
    assert validate(gid,[gid]) == gid


def test_cluster_hypothesis_references_are_grounded_only_for_members(graph):
    cid = int(graph.nodes.groupby('cluster_id').size().idxmax())
    members = graph.nodes.loc[graph.nodes.cluster_id.eq(cid), 'gid'].astype(str).tolist()
    assert len(members) > 5
    outside = str(graph.nodes.loc[~graph.nodes.cluster_id.eq(cid), 'gid'].iloc[0])
    referenced = members[5]
    unknown = '999999999999999999'
    table = graph.bundle.tables['clusters']
    table.loc[table.cluster_id.eq(cid), 'top_gids'] = ';'.join(members[:5])
    table.loc[table.cluster_id.eq(cid), 'hypothesis'] = f'Признаки сбора у {referenced}; непроверенные {outside} и {unknown}'
    result = graph.cluster_info(cid)
    assert referenced in result['gids']
    assert outside not in result['gids'] and unknown not in result['gids']
    checked = validate(result['cluster']['hypothesis'], result['gids'])
    assert f'непроверенная ссылка ({referenced})' not in checked
    assert f'непроверенная ссылка ({outside})' in checked
    assert f'непроверенная ссылка ({unknown})' in checked


def test_real_cluster_motif_reference_survives_mock_response():
    import re
    graph = GraphTools('out')
    for row in graph.bundle.tables['clusters'].itertuples():
        motif_ids = set(re.findall(r'(?<!\d)\d{18}(?!\d)', row.hypothesis))
        extra = motif_ids - set(row.top_gids.split(';'))
        if extra:
            cid = int(row.cluster_id)
            gid = sorted(extra)[0]
            break
    else:
        pytest.fail('Expected a real motif participant outside cluster top-five')
    assert gid in graph.cluster_info(cid)['gids']
    unknown = '999999999999999999'
    fake = FakeResponses([
        response('r1', [call('cluster_info', json.dumps({'cluster_id': cid}))]),
        response('r2', text=f'Гипотеза по {gid}; {unknown}'),
    ])
    result = ask_graph('Объясни кластер', 'out', client=NS(responses=fake), model='mock')
    assert gid in result['gids']
    assert f'непроверенная ссылка ({gid})' not in result['text']
    assert f'непроверенная ссылка ({unknown})' in result['text']


def test_all_real_cluster_hypotheses_ground_members_outside_top_five():
    """B-004's full-cluster audit also rejects a newly injected unknown gid."""
    import re

    graph = GraphTools('out')
    clusters = graph.bundle.tables['clusters']
    assert not clusters.empty
    examined = set()
    for row in clusters.itertuples():
        cid = int(row.cluster_id)
        result = graph.cluster_info(cid)
        mentioned = set(re.findall(r'(?<!\d)\d{18}(?!\d)', str(row.hypothesis)))
        members = set(graph.nodes.loc[graph.nodes.cluster_id.eq(cid), 'gid'].astype(str))
        assert mentioned <= members
        assert mentioned <= set(result['gids'])
        assert 'непроверенная ссылка' not in validate(str(row.hypothesis), result['gids'])
        examined.add(cid)
    assert examined == set(clusters.cluster_id)

    cid = int(clusters.iloc[0].cluster_id)
    unknown = '999999999999999999'
    clusters.loc[clusters.cluster_id.eq(cid), 'hypothesis'] += f' {unknown}'
    result = graph.cluster_info(cid)
    assert unknown not in result['gids']
    assert f'непроверенная ссылка ({unknown})' in validate(result['cluster']['hypothesis'], result['gids'])
