"""
Mechanism tests for the legacy exponential survival incident model.

Coverage map
------------
UNIT (synthetic in-memory models, no data files):
  test_calculate_incident_rate_per_row_formula          — rate == exp(-(w·x)) for each row
  test_calculate_incident_rate_total_is_sum             — total_incident_rate == sum of per-row rates
  test_predict_is_reciprocal_of_incident_rate           — predicted_time_bet == 1 / incident_rate
  test_get_likelihood_returns_finite_scalar             — log-lik is a finite float on a small synthetic df
  test_get_likelihood_better_for_near_weights           — objective is higher for weights near the DGP
  test_get_likelihood_clips_log_t_zero                  — time_bet=0 (log=-inf) does not raise, returns finite
  test_get_likelihood_clips_large_time_bet              — time_bet=1e300 does not raise, returns finite
  test_fit_single_feature_positive_weight_sign          — learned weight has correct sign (positive DGP)
  test_fit_single_feature_negative_weight_sign          — learned weight has correct sign (negative DGP)
  test_fit_two_clusters_populates_both_keys             — both cluster keys present after fit
  test_predict_unknown_cluster_returns_nan              — predict NaN for cluster not in model_params
  test_calculate_incident_rate_unknown_cluster_nan_zero — rate NaN, total=0 for unknown cluster
  test_get_regression_expr_contains_cluster_labels      — string contains each cluster label
  test_get_regression_expr_contains_coefficients        — string contains the numeric coefficients
  test_get_regression_expr_empty_model                  — empty model_params returns empty string
REAL-DATA (loads bundle once via get_prediction_components):
  test_generate_random_coordinates_within_cell_bounds   — (lat, lon) lies inside the cell polygon's bounding box
  test_random_incident_selector_known_cluster           — returns (str, str) for a real cluster key
  test_random_incident_selector_unknown_cluster_nones   — returns (None, None) for an unknown key
INTEGRATION (real loaders, 3-day window):
  test_integration_different_seeds_give_different_counts — two seeds produce different total counts
  test_integration_fixed_seed_is_reproducible            — same seed produces identical count twice
"""

import numpy as np
import pandas as pd
import pytest

from src.engine.models.survival_forecaster import SurvivalRegressionForecaster
from src.engine.incidents import (
    generate_random_coordinates_in_cell,
    get_prediction_components,
    predict_incidents_with_types_and_coordinates,
    random_incident_selector,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_FEATURES_2 = ["f0", "f1"]
_W_2 = [[0.5, -0.2]]  # w·x = 0.5*f0 - 0.2*f1


def _model_2f():
    """Minimal forecaster with two features, one cluster (label 0)."""
    m = SurvivalRegressionForecaster()
    m.model_params = {0: _W_2}
    return m


def _rows_3():
    """Three distinct rows so per-row assertions are unambiguous."""
    return pd.DataFrame([
        {"cluster_label": 0, "f0": 1.0, "f1": 2.0},
        {"cluster_label": 0, "f0": 0.0, "f1": 0.5},
        {"cluster_label": 0, "f0": 2.0, "f1": 1.0},
    ])


def _expected_rates(rows: pd.DataFrame) -> np.ndarray:
    """rate_i = exp(-(w·x_i))  with w = _W_2."""
    w = np.array(_W_2[0])
    x = rows[_FEATURES_2].values
    return np.exp(-x.dot(w))


# ---------------------------------------------------------------------------
# Session-scoped fixture: load prediction components once for all real-data
# and integration tests.  Avoids re-reading disk 5+ times.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def pred_components():
    return get_prediction_components("fire")


# ===========================================================================
# 1. calculate_incident_rate — per-row formula
# ===========================================================================

def test_calculate_incident_rate_per_row_formula():
    """Each row's incident_rate column equals exp(-(w·x))."""
    m = _model_2f()
    rows = _rows_3()
    result_df, _ = m.calculate_incident_rate(rows.copy(), {"features": _FEATURES_2})
    expected = _expected_rates(rows)
    assert np.allclose(result_df["incident_rate"].values, expected, rtol=1e-9)


def test_calculate_incident_rate_total_is_sum():
    """total_incident_rate == sum of all per-row rates."""
    m = _model_2f()
    rows = _rows_3()
    result_df, total = m.calculate_incident_rate(rows.copy(), {"features": _FEATURES_2})
    assert np.isclose(total, result_df["incident_rate"].sum(), rtol=1e-9)


# ===========================================================================
# 2. predict vs rate reciprocal
# ===========================================================================

def test_predict_is_reciprocal_of_incident_rate():
    """predicted_time_bet == 1 / incident_rate for every row."""
    m = _model_2f()
    rows = _rows_3()
    pred_df = m.predict(rows.copy(), {"features": _FEATURES_2})
    rate_df, _ = m.calculate_incident_rate(rows.copy(), {"features": _FEATURES_2})
    assert np.allclose(
        pred_df["predicted_time_bet"].values,
        1.0 / rate_df["incident_rate"].values,
        rtol=1e-9,
    )


# ===========================================================================
# 3. _get_likelihood — scalar, finiteness, and ordering
# ===========================================================================

def _synthetic_df(seed: int = 7, n: int = 50):
    rng = np.random.default_rng(seed)
    f0 = rng.normal(1.0, 0.3, n)
    f1 = rng.normal(2.0, 0.3, n)
    # DGP: log(scale) = 0.5*f0 - 0.2*f1
    true_scale = np.exp(0.5 * f0 - 0.2 * f1)
    times = rng.exponential(true_scale)
    return pd.DataFrame({"f0": f0, "f1": f1, "time_bet": times})


def test_get_likelihood_returns_finite_scalar():
    """_get_likelihood returns a single finite float."""
    m = _model_2f()
    df = _synthetic_df()
    w = np.array(_W_2, dtype=float)
    ll = m._get_likelihood(df, w, _FEATURES_2)
    assert np.isscalar(ll) or ll.ndim == 0
    assert np.isfinite(float(ll))


def test_get_likelihood_better_for_near_weights():
    """Weights close to the DGP (0.5, -0.2) score higher than far-off weights."""
    m = SurvivalRegressionForecaster()
    df = _synthetic_df(seed=7, n=200)
    w_good = np.array([[0.5, -0.2]], dtype=float)
    w_bad = np.array([[5.0, -5.0]], dtype=float)
    ll_good = m._get_likelihood(df, w_good.copy(), _FEATURES_2)
    ll_bad = m._get_likelihood(df, w_bad.copy(), _FEATURES_2)
    assert ll_good > ll_bad


def test_get_likelihood_clips_log_t_zero():
    """time_bet=0 causes log(0)=-inf; the clip must absorb this and return finite."""
    m = SurvivalRegressionForecaster()
    df = pd.DataFrame({"f0": [1.0], "f1": [2.0], "time_bet": [0.0]})
    w = np.array([[0.5, -0.2]], dtype=float)
    ll = m._get_likelihood(df, w, _FEATURES_2)
    assert np.isfinite(float(ll))


def test_get_likelihood_clips_large_time_bet():
    """time_bet=1e300 (log ~690) is clipped at +500 and must still return finite."""
    m = SurvivalRegressionForecaster()
    df = pd.DataFrame({"f0": [1.0], "f1": [2.0], "time_bet": [1e300]})
    w = np.array([[0.5, -0.2]], dtype=float)
    ll = m._get_likelihood(df, w, _FEATURES_2)
    assert np.isfinite(float(ll))


# ===========================================================================
# 4. fit — sign recovery and cluster population
# ===========================================================================

def test_fit_single_feature_positive_weight_sign():
    """
    With DGP log(scale) = +0.8 * x and n=200 iid observations,
    the learned weight must be positive (correct sign) and within 0.3 of truth.
    """
    rng = np.random.default_rng(42)
    n = 200
    true_w = 0.8
    x = np.ones(n)
    times = rng.exponential(np.exp(true_w * x))
    df = pd.DataFrame({"x0": x, "time_bet": times, "cluster_label": 0})
    m = SurvivalRegressionForecaster()
    m.fit(df, {"features": ["x0"]})
    learned = m.model_params[0][0][0]
    assert learned > 0, f"Expected positive weight, got {learned}"
    assert abs(learned - true_w) < 0.3, f"Weight {learned} too far from truth {true_w}"


def test_fit_single_feature_negative_weight_sign():
    """
    With DGP log(scale) = -0.5 * x, the learned weight must be negative.
    """
    rng = np.random.default_rng(99)
    n = 200
    true_w = -0.5
    x = np.ones(n)
    times = rng.exponential(np.exp(true_w * x))
    df = pd.DataFrame({"x0": x, "time_bet": times, "cluster_label": 0})
    m = SurvivalRegressionForecaster()
    m.fit(df, {"features": ["x0"]})
    learned = m.model_params[0][0][0]
    assert learned < 0, f"Expected negative weight, got {learned}"
    assert abs(learned - true_w) < 0.3, f"Weight {learned} too far from truth {true_w}"


def test_fit_two_clusters_populates_both_keys():
    """fit() on data with two cluster labels must produce entries for both."""
    rng = np.random.default_rng(11)
    n = 100
    dfA = pd.DataFrame({
        "x0": np.ones(n),
        "time_bet": rng.exponential(np.exp(0.6 * np.ones(n))),
        "cluster_label": 0,
    })
    dfB = pd.DataFrame({
        "x0": np.ones(n),
        "time_bet": rng.exponential(np.exp(-0.4 * np.ones(n))),
        "cluster_label": 1,
    })
    df = pd.concat([dfA, dfB], ignore_index=True)
    m = SurvivalRegressionForecaster()
    m.fit(df, {"features": ["x0"]})
    assert 0 in m.model_params
    assert 1 in m.model_params


# ===========================================================================
# 5. Unknown cluster edge cases
# ===========================================================================

def test_predict_unknown_cluster_returns_nan():
    """predict() fills NaN when a row's cluster_label is absent from model_params."""
    m = _model_2f()
    row = pd.DataFrame([{"cluster_label": 999, "f0": 1.0, "f1": 2.0}])
    result = m.predict(row, {"features": _FEATURES_2})
    assert np.isnan(result["predicted_time_bet"].iloc[0])


def test_calculate_incident_rate_unknown_cluster_nan_zero():
    """
    calculate_incident_rate() places NaN in the rate column and
    contributes 0 to total_incident_rate for an unknown cluster.
    """
    m = _model_2f()
    row = pd.DataFrame([{"cluster_label": 999, "f0": 1.0, "f1": 2.0}])
    result_df, total = m.calculate_incident_rate(row, {"features": _FEATURES_2})
    assert np.isnan(result_df["incident_rate"].iloc[0])
    assert total == 0.0


# ===========================================================================
# 6. get_regression_expr
# ===========================================================================

def test_get_regression_expr_contains_cluster_labels():
    """Expression string must mention every cluster key."""
    m = SurvivalRegressionForecaster()
    m.model_params = {0: [[0.5, -0.2]], 3: [[1.1, 0.3, -0.7]]}
    expr = m.get_regression_expr()
    assert "0" in expr
    assert "3" in expr


def test_get_regression_expr_contains_coefficients():
    """Expression string must contain the literal coefficient values."""
    m = SurvivalRegressionForecaster()
    m.model_params = {0: [[0.5, -0.2]]}
    expr = m.get_regression_expr()
    assert "0.5" in expr
    assert "-0.2" in expr


def test_get_regression_expr_empty_model():
    """An un-fit model (no clusters) returns an empty string."""
    m = SurvivalRegressionForecaster()
    assert m.get_regression_expr() == ""


# ===========================================================================
# 7. generate_random_coordinates_in_cell  (real bundle grid)
# ===========================================================================

def test_generate_random_coordinates_within_cell_bounds(pred_components):
    """
    Returned (lat, lon) must lie within the bounding box of the chosen cell.
    Checked across 10 independent draws to guard against lucky centroid fallback.
    """
    grid = pred_components["grid_geometry"]
    # Use a mid-index cell to avoid edge cells that are sometimes degenerate
    cell_id = grid["cell_id"].iloc[50]
    cell_geom = grid[grid["cell_id"] == cell_id]["geometry"].iloc[0]
    minx, miny, maxx, maxy = cell_geom.bounds

    rng_state = np.random.get_state()
    try:
        np.random.seed(17)
        for _ in range(10):
            lat, lon = generate_random_coordinates_in_cell(cell_id, grid)
            assert miny <= lat <= maxy, f"lat {lat} outside [{miny}, {maxy}]"
            assert minx <= lon <= maxx, f"lon {lon} outside [{minx}, {maxx}]"
    finally:
        np.random.set_state(rng_state)


# ===========================================================================
# 8. random_incident_selector  (real bundle incident_probabilities)
# ===========================================================================

def test_random_incident_selector_known_cluster(pred_components):
    """
    For a cluster present in the real probability dict,
    random_incident_selector returns a (str, str) pair — not None.
    """
    prob_dict = pred_components["incident_probabilities"]
    cluster = list(prob_dict.keys())[0]

    rng_state = np.random.get_state()
    try:
        np.random.seed(5)
        cat, itype = random_incident_selector(cluster, prob_dict)
    finally:
        np.random.set_state(rng_state)

    assert cat is not None, "category should not be None for a known cluster"
    assert itype is not None, "incident_type should not be None for a known cluster"
    assert isinstance(cat, str)
    assert isinstance(itype, str)


def test_random_incident_selector_unknown_cluster_nones(pred_components):
    """
    For a cluster NOT in the probability dict, the function must return (None, None)
    rather than raising an exception (documented graceful fallback behaviour).
    """
    prob_dict = pred_components["incident_probabilities"]
    cat, itype = random_incident_selector(99999, prob_dict)
    assert cat is None
    assert itype is None


# ===========================================================================
# 9. Integration — predict_incidents_with_types_and_coordinates  (3-day window)
# ===========================================================================

_START = "2024-01-01"
_END = "2024-01-04"  # 3 days; fast enough (~3 s on this hardware)


def test_integration_different_seeds_give_different_counts():
    """
    Two distinct numpy seeds must produce different total incident counts,
    proving the loop samples exponential draws rather than using a deterministic mean.
    """
    np.random.seed(42)
    count_a = len(predict_incidents_with_types_and_coordinates(_START, _END))
    np.random.seed(99)
    count_b = len(predict_incidents_with_types_and_coordinates(_START, _END))
    assert count_a != count_b, (
        f"Both seeds yielded {count_a} incidents — sampling appears deterministic."
    )


def test_integration_fixed_seed_is_reproducible():
    """
    The same numpy seed must yield an identical incident count on two consecutive runs,
    confirming that no hidden global state escapes between calls.
    """
    np.random.seed(42)
    count_first = len(predict_incidents_with_types_and_coordinates(_START, _END))
    np.random.seed(42)
    count_second = len(predict_incidents_with_types_and_coordinates(_START, _END))
    assert count_first == count_second, (
        f"Same seed gave {count_first} then {count_second} — run is not reproducible."
    )
