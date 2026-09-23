"""Fallback uses published chronology when raw transactions are unavailable."""
import pandas as pd
import pytest

from ui.data import chronology_filter


@pytest.mark.parametrize('gap,column', [(2, 'seed_exp_fast'), (31, 'seed_exp_chrono')])
def test_ready_flow_without_transactions_uses_published_column(gap, column):
    nodes = pd.DataFrame({'gid': [100000000000000001, 100000000000000002],
                          'is_seed': [True, False], 'seed_exp_fast': [0, 2],
                          'seed_exp_chrono': [1, 3]})
    reach, message = chronology_filter(nodes, None, gap, ready=True)
    assert reach == nodes.set_index('gid')[column].to_dict()
    assert 'Готовая колонка выгрузки' in message


def test_missing_transactions_does_not_invent_other_gap_reach():
    nodes = pd.DataFrame({'gid': [100000000000000001], 'is_seed': [False],
                          'seed_exp_fast': [1], 'seed_exp_chrono': [2]})
    with pytest.raises(ValueError, match='Δ=2 и Δ=31'):
        chronology_filter(nodes, None, 7, ready=True)
