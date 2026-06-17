"""Mechanism tests for the survival forecaster inter-arrival sampling.

The synthetic incident generator (predict_incidents_with_types_and_coordinates)
steps a cell forward by the time-between-incidents the survival model returns.
It must SAMPLE that inter-arrival from the exponential distribution (a proper
Poisson process), not use the deterministic mean E[T]. Using the mean made
low-rate (outskirt) cells whose mean inter-arrival exceeds the window emit
exactly zero incidents every run, leaving the outskirts deterministically empty.

These tests use a tiny in-memory model (no data loads, no patching) to assert:
  1. predict() returns the deterministic mean E[T] = exp(w . x).
  2. sample() returns stochastic exponential draws whose mean is that same E[T].
"""
import numpy as np
import pandas as pd

from src.engine.models.survival_forecaster import SurvivalRegressionForecaster

FEATURES = ["f0", "f1"]
# w . x = 0.5*1 + (-0.2)*2 = 0.1  ->  E[T] = exp(0.1)
W = [[0.5, -0.2]]
EXPECTED_ET = np.exp(0.1)


def _model():
    m = SurvivalRegressionForecaster()
    m.model_params = {0: W}
    return m


def _row():
    return pd.DataFrame([{"cluster_label": 0, "f0": 1.0, "f1": 2.0}])


def test_predict_returns_deterministic_mean():
    m = _model()
    r1 = m.predict(_row(), {"features": FEATURES})["predicted_time_bet"].iloc[0]
    r2 = m.predict(_row(), {"features": FEATURES})["predicted_time_bet"].iloc[0]
    assert r1 == r2  # deterministic
    assert abs(r1 - EXPECTED_ET) < 1e-9


def test_sample_is_stochastic_with_correct_mean():
    m = _model()
    np.random.seed(0)
    draws = [
        m.sample(_row(), {"features": FEATURES})["predicted_time_bet"].iloc[0]
        for _ in range(20000)
    ]
    # Stochastic: not all draws identical (this is the fix vs. the mean).
    assert np.std(draws) > 0
    # Exponential mean equals E[T] = exp(w . x).
    assert abs(np.mean(draws) - EXPECTED_ET) / EXPECTED_ET < 0.05


def test_sample_can_fire_within_window_where_mean_cannot():
    """A cell whose mean inter-arrival exceeds the window.

    predict()/mean: next event is always > window  -> 0 incidents, every run.
    sample(): a fraction of draws fall inside the window -> cell can fire.
    """
    m = SurvivalRegressionForecaster()
    # log E[T] = 0  -> E[T] = 1.0 (hour). Window below the mean.
    m.model_params = {0: [[0.0, 0.0]]}
    row = pd.DataFrame([{"cluster_label": 0, "f0": 0.0, "f1": 0.0}])
    window = 0.5  # hours, < E[T]=1.0

    mean_T = m.predict(row.copy(), {"features": FEATURES})["predicted_time_bet"].iloc[0]
    assert mean_T > window  # mean never fits the window -> deterministic zero

    np.random.seed(1)
    draws = [
        m.sample(row.copy(), {"features": FEATURES})["predicted_time_bet"].iloc[0]
        for _ in range(2000)
    ]
    within = sum(d <= window for d in draws)
    # ~1 - exp(-0.5) ~= 39% of draws fall inside the window.
    assert within > 0
    assert 0.30 < within / len(draws) < 0.48
