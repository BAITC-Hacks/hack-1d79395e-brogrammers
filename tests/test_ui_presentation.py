"""Presentation keeps precision, translates values and explains the actual score."""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from graf.config import PRIORITY_WEIGHTS
from ui.card import priority_components
from ui.formatting import COLUMN_LABELS, display_table, money, percent, boolean


def test_display_table_preserves_exact_ids_source_and_numeric_sorting():
    gid = 100000000000000017
    source = pd.DataFrame({
        'gid': pd.Series([gid, pd.NA], dtype='Int64'),
        'src': pd.Series([gid + 2, gid], dtype='Int64'),
        'sum_kzt': [1234567.0, 5000.0], 'tracked_share_in': [0.125, 1.0],
        'excluded': [False, True], 'visibility': ['out_unseen', 'full'],
        'strategy': ['priority', 'random'], 'priority_score': [0.75, 0.25],
        'rank': [1, 2], 'first_date': pd.to_datetime(['2026-07-01', '2026-07-03']),
    })
    original = source.copy(deep=True)
    table = display_table(source)
    assert table['gid'].tolist() == [str(gid), '—']
    assert table[COLUMN_LABELS['src']].tolist() == [str(gid + 2), str(gid)]
    assert table[COLUMN_LABELS['sum_kzt']].tolist() == ['1 234 567 ₸', '5 000 ₸']
    assert table[COLUMN_LABELS['tracked_share_in']].tolist() == ['12.5%', '100.0%']
    assert table[COLUMN_LABELS['excluded']].tolist() == ['Нет', 'Да']
    assert table[COLUMN_LABELS['visibility']].iloc[0] == 'Исходящие не видны: 4-е колено'
    assert table[COLUMN_LABELS['strategy']].iloc[0] == 'По приоритету проверки'
    assert table[COLUMN_LABELS['first_date']].iloc[0] == '01.07.2026'
    assert table[COLUMN_LABELS['priority_score']].tolist() == [0.75, 0.25]
    assert table[COLUMN_LABELS['rank']].tolist() == [1, 2]
    pd.testing.assert_frame_equal(source, original)
    legacy_keys = display_table(source, rename=False)
    assert legacy_keys.columns.tolist() == source.columns.tolist()
    assert legacy_keys.gid.iloc[0] == str(gid)


def test_formatters_handle_missing_values_and_false_strings():
    assert money(None) == money(float('nan')) == '—'
    assert percent(pd.NA) == '—'
    assert boolean('False') == 'Нет'
    assert boolean(False) == 'Нет'
    assert boolean('True') == 'Да'
    assert boolean(pd.NA) == '—'


def test_priority_chart_uses_weighted_components_not_raw_features():
    raw = {'role': 0.8, 'money': 0.6, 'brokerage': 0.2, 'volume': 0.3, 'temporal': 1.0}
    row = {f'prio_{name}': value for name, value in raw.items()}
    row['prio_multiplier'] = 0.48
    frame = priority_components(row)
    expected = [raw[name] * weight for name, weight in PRIORITY_WEIGHTS.items()]
    assert frame['Вклад'].tolist() == pytest.approx(expected)
    assert frame['Вклад'].sum() == pytest.approx(0.59)
    assert frame['Вклад'].sum() * row['prio_multiplier'] == pytest.approx(0.2832)
    assert frame['Компонент'].str.contains('Роль|деньги|связность|оборот|Временные').all()


def test_summary_and_details_render_once_without_transactions():
    script = """
import streamlit as st
from ui.data import load_bundle
from ui.card import render_summary, render_card
bundle = load_bundle('out')
row = bundle.nodes.sort_values('rank').iloc[0].to_dict()
render_summary(st, row, bundle)
render_card(st, row, bundle, None, summary=False)
"""
    app = AppTest.from_string(script, default_timeout=30).run()
    assert not app.exception
    assert len(app.metric) == 3
    assert app.metric[1].label == 'Атрибутировано входящих'
    assert '₸' in app.metric[1].value
    assert any('не вероятность виновности' in caption.value for caption in app.caption)
    assert any('транзакции не загружены' in caption.value.lower() for caption in app.caption)
    assert any('приоритет' in expander.label.lower() for expander in app.expander)
    assert any('роль' in info.value.lower() or 'кандидат' in info.value.lower() for info in app.info)
    assert len(app.code) >= 1


def test_summary_has_factual_reason_and_next_request_before_graph():
    script = """
import streamlit as st
from ui.data import load_bundle
from ui.card import render_summary
bundle = load_bundle('out')
row = bundle.nodes.sort_values('rank').iloc[0].to_dict()
render_summary(st, row, bundle)
st.markdown('GRAPH_PLACEHOLDER')
"""
    app = AppTest.from_string(script, default_timeout=30).run()
    assert not app.exception
    texts = [element.value for element in app.markdown]
    reason = next(text for text in texts if text.startswith('**Почему этот приоритет:**'))
    request = next(text for text in texts if text.startswith('**Следующий шаг:**'))
    assert '₸' in reason and 'seed' in reason
    assert len(reason) < 250
    assert 'запросить' in request
    assert texts.index(reason) < texts.index('GRAPH_PLACEHOLDER')
    assert texts.index(request) < texts.index('GRAPH_PLACEHOLDER')
    assert app.info[0].value not in reason


def test_summary_distinguishes_no_special_requests_from_missing_request_table():
    script = """
import streamlit as st
from ui.data import load_bundle
from ui.card import render_summary
bundle = load_bundle('out')
requests = bundle.tables['data_requests']
row = bundle.nodes.loc[~bundle.nodes.gid.isin(requests.gid)].iloc[0].to_dict()
render_summary(st, row, bundle)
"""
    app = AppTest.from_string(script, default_timeout=30).run()
    assert not app.exception
    assert any('Специальных запросов по заданным правилам нет' in item.value for item in app.markdown)
    assert not any('План запросов не передан' in item.value for item in app.markdown)
