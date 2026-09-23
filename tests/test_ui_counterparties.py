"""Counterparty table selection opens only exact known IDs in either direction."""
from types import SimpleNamespace

import pandas as pd
from streamlit.testing.v1 import AppTest

from ui.card import render_counterparties
from ui.formatting import COLUMN_LABELS


class _Panel:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class _Streamlit:
    def __init__(self):
        self.session_state = {}
        self.tables = {}
        self.captions = []
        self.headings = []
    def columns(self, n):
        return [_Panel() for _ in range(n)]
    def markdown(self, text):
        self.headings.append(text)
    def caption(self, text):
        self.captions.append(text)
    def dataframe(self, frame, **kwargs):
        self.tables[kwargs['key']] = (frame, kwargs)


def _sample():
    anchor = 100000000000000017
    incoming, other_incoming, outgoing = anchor + 2, anchor + 4, anchor + 6
    unknown = 999999999999999999
    bundle = SimpleNamespace(nodes=pd.DataFrame({'gid': [anchor, incoming, other_incoming, outgoing]}))
    tx = pd.DataFrame({
        'src': [incoming, other_incoming, anchor, anchor],
        'dst': [anchor, anchor, outgoing, unknown],
        'sum_kzt': [20000.0, 10000.0, 40000.0, 50000.0],
        'date': pd.to_datetime(['2026-07-01', '2026-07-02', '2026-07-03', '2026-07-04']),
    })
    return anchor, incoming, outgoing, unknown, bundle, tx


def test_each_direction_callback_keeps_exact_id_and_its_own_rows():
    anchor, incoming, outgoing, unknown, bundle, tx = _sample()
    st = _Streamlit()
    opened = []
    render_counterparties(st, {'gid': anchor}, bundle, tx, on_open_node=opened.append)
    incoming_key, outgoing_key = f'peer_{anchor}_in', f'peer_{anchor}_out'
    assert set(st.tables) == {incoming_key, outgoing_key}
    assert any('Кто переводил на этот счёт' in heading for heading in st.headings)
    assert any('Кому переводил этот счёт' in heading for heading in st.headings)
    incoming_frame, incoming_options = st.tables[incoming_key]
    outgoing_frame, outgoing_options = st.tables[outgoing_key]
    assert incoming_frame[COLUMN_LABELS['src']].iloc[0] == str(incoming)
    assert outgoing_frame[COLUMN_LABELS['dst']].tolist() == [str(unknown), str(outgoing)]
    st.session_state[incoming_key] = {'selection': {'rows': [0]}}
    incoming_options['on_select']()
    assert opened == [str(incoming)]
    st.session_state[outgoing_key] = {'selection': {'rows': [1]}}
    outgoing_options['on_select']()
    assert opened == [str(incoming), str(outgoing)]
    assert all(isinstance(gid, str) and len(gid) == 18 for gid in opened)
    assert incoming_options['selection_mode'] == outgoing_options['selection_mode'] == 'single-row'


def test_unknown_or_invalid_selection_never_opens_node():
    anchor, _, _, _, bundle, tx = _sample()
    st = _Streamlit()
    opened = []
    render_counterparties(st, {'gid': anchor}, bundle, tx, on_open_node=opened.append)
    key = f'peer_{anchor}_out'
    callback = st.tables[key][1]['on_select']
    for rows in [[], [0], [-1], [5], [True], ['1']]:
        st.session_state[key] = {'selection': {'rows': rows}}
        callback()
    assert opened == []


def test_tables_remain_read_only_without_callback_and_missing_tx_is_explicit():
    anchor, _, _, _, bundle, tx = _sample()
    st = _Streamlit()
    render_counterparties(st, {'gid': anchor}, bundle, tx)
    assert all('on_select' not in options for _, options in st.tables.values())
    missing = _Streamlit()
    render_counterparties(missing, {'gid': anchor}, bundle, None)
    assert not missing.tables
    assert any('Транзакции не загружены' in caption for caption in missing.captions)


def test_counterparties_can_be_placed_before_graph_without_duplicate_tables():
    script = """
import streamlit as st
from ui.data import load_bundle, load_raw
from ui.card import render_summary, render_counterparties, render_card
bundle = load_bundle('out')
row = bundle.nodes.sort_values('rank').iloc[0].to_dict()
_, _, tx = load_raw('data')
render_summary(st, row, bundle)
render_counterparties(st, row, bundle, tx, on_open_node=lambda gid: st.session_state.update(opened=gid))
st.markdown('GRAPH_PLACEHOLDER')
render_card(st, row, bundle, tx, summary=False, show_counterparties=False)
"""
    app = AppTest.from_string(script, default_timeout=30).run()
    assert not app.exception
    headings = [item.value for item in app.markdown]
    incoming = next(text for text in headings if 'Кто переводил на этот счёт' in text)
    outgoing = next(text for text in headings if 'Кому переводил этот счёт' in text)
    assert headings.count(incoming) == headings.count(outgoing) == 1
    assert headings.index(incoming) < headings.index('GRAPH_PLACEHOLDER')
    assert headings.index(outgoing) < headings.index('GRAPH_PLACEHOLDER')
    assert any(metric.label == 'Источников с маршрутом к узлу' for metric in app.metric)
    peer_tables = [table for table in app.dataframe if {COLUMN_LABELS['src'], COLUMN_LABELS['dst']} & set(table.value.columns)]
    assert len(peer_tables) == 2
