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
