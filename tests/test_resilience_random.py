"""Independent checks of the random-removal ensemble and empirical quantiles."""
import math
import random
from statistics import fmean

import networkx as nx
import pandas as pd
import pytest

from graf.config import RANDOM_TRIALS
from graf.resilience import removal_curve


@pytest.fixture
def small_network():
    graph = nx.DiGraph()
    graph.add_nodes_from(range(1, 10))
    graph.add_edges_from([(1, 2), (2, 3), (3, 4), (1, 5), (5, 6), (7, 8)])
    features = pd.DataFrame({
        'gid': list(graph),
        'is_seed': [gid in {1, 7} for gid in graph],
        'priority_score': [1 / gid for gid in graph],
        'betweenness': [0.1 if gid in {2, 3, 5} else 0.0 for gid in graph],
        'out_deg': [graph.out_degree(gid) for gid in graph],
        'in_deg': [graph.in_degree(gid) for gid in graph],
    })
    return graph, features


def _reachable_by_networkx(graph, seeds):
    reached = set()
    for seed in seeds & set(graph):
        reached.update(nx.descendants(graph, seed))
    return reached - seeds


def _linear_quantile(values, fraction):
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    lower, upper = math.floor(index), math.ceil(index)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def _independent_random_outcomes(graph, features, counts, trials, seed):
    seeds = set(features.loc[features.is_seed, 'gid'])
    baseline = _reachable_by_networkx(graph, seeds)
    candidate_ids = sorted(set(graph) - seeds)
    rng = random.Random(seed)
    result = {count: [] for count in counts}
    for _ in range(trials):
        order = candidate_ids.copy()
        rng.shuffle(order)
        for count in counts:
            # Deliberately use actual graph removal and NetworkX descendants,
            # independently of the optimized traversal used by the pipeline.
            after = graph.copy()
            after.remove_nodes_from(order[:count])
            reach = _reachable_by_networkx(after, seeds)
            share = len(reach & baseline) / len(baseline) if baseline else 0.0
            largest = max(map(len, nx.weakly_connected_components(after)), default=0)
            result[count].append((share, largest))
    return result


def test_random_mean_and_empirical_quantiles_match_independent_removals(small_network):
    graph, features = small_network
    original = features.copy(deep=True)
    counts = (0, 1, 3)
    actual = removal_curve(graph, features, n_values=counts)
    assert RANDOM_TRIALS == 100
    expected = _independent_random_outcomes(graph, features, counts, 100, 42)
    for row in actual.loc[actual.strategy.eq('random')].itertuples():
        shares = [outcome[0] for outcome in expected[row.n_removed]]
        sizes = [outcome[1] for outcome in expected[row.n_removed]]
        assert row.n_trials == 100
        assert row.seed_reach_share == pytest.approx(fmean(shares))
        assert row.largest_wcc == pytest.approx(fmean(sizes))
        assert row.seed_reach_p05 == pytest.approx(_linear_quantile(shares, 0.05))
        assert row.seed_reach_p95 == pytest.approx(_linear_quantile(shares, 0.95))
    pd.testing.assert_frame_equal(features, original)
    assert len(graph) == 9 and graph.number_of_edges() == 6


def test_random_repeatability_and_deterministic_strategies_are_preserved(small_network):
    graph, features = small_network
    many = removal_curve(graph, features, n_values=(0, 1, 3))
    repeated = removal_curve(graph, features.iloc[::-1], n_values=(0, 1, 3))
    pd.testing.assert_frame_equal(many, repeated)
    once = removal_curve(graph, features, n_values=(0, 1, 3), random_trials=1)
    deterministic = many.loc[many.strategy.ne('random')].reset_index(drop=True)
    pd.testing.assert_frame_equal(deterministic, once.loc[once.strategy.ne('random')].reset_index(drop=True))
    assert set(many.strategy) == {'priority', 'betweenness', 'out_deg', 'in_deg', 'random', 'all_seeds'}
    assert len(many) == 5 * 3 + 1
    assert deterministic.n_trials.eq(1).all()
    assert deterministic.seed_reach_p05.equals(deterministic.seed_reach_share)
    assert deterministic.seed_reach_p95.equals(deterministic.seed_reach_share)
    assert deterministic.largest_wcc.mod(1).eq(0).all()
    expected = _independent_random_outcomes(graph, features, (0, 1, 3), 1, 42)
    for row in once.loc[once.strategy.eq('random')].itertuples():
        assert row.seed_reach_share == expected[row.n_removed][0][0]
        assert row.largest_wcc == expected[row.n_removed][0][1]


def test_random_handles_exhausted_candidates_and_no_seed_reach(small_network):
    graph, features = small_network
    curve = removal_curve(graph, features, n_values=(50,), random_trials=7)
    random_row = curve.loc[curve.strategy.eq('random')].iloc[0]
    assert random_row.n_removed == int((~features.is_seed).sum())
    assert random_row.seed_reach_share == random_row.seed_reach_p05 == random_row.seed_reach_p95 == 0
    no_seeds = removal_curve(graph, features.assign(is_seed=False), n_values=(0, 2), random_trials=3)
    assert no_seeds[['seed_reach_share', 'seed_reach_p05', 'seed_reach_p95']].eq(0).all().all()
    with pytest.raises(ValueError, match='positive integer'):
        removal_curve(graph, features, random_trials=0)
