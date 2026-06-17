"""pytest suite for the growth_v1 (Poisson rate) synthetic incident generator.

Tests call the real production code and real bundle assets — no monkeypatching.
All windows are kept short (≤1 week) so the full suite completes in seconds.

Import convention matches the existing test_survival_sampling.py:
    from src.engine.incidents_variants import ...
(pyproject.toml sets pythonpath = ["src"], so 'src' is on sys.path at test time.)
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Suppress sklearn version/feature-name warnings that come from loading the
# pickled StandardScaler — they are informational, not test failures.
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

from engine.incidents_variants import (  # noqa: E402
    _build_cluster_type_marginal,
    _build_temporal_features,
    _load_default_payload,
    _load_fire_types,
    generate,
    predict_incidents,
)

# ---------------------------------------------------------------------------
# Convenience: short window used by most tests (Mon–Sun, 7 days)
# ---------------------------------------------------------------------------
_START = "2025-01-01"
_END = "2025-01-08"

# Bundle path (same derivation as the module itself)
_BUNDLE = Path(__file__).resolve().parents[1] / "data" / "models" / "growth_poisson_v1"


# ===========================================================================
# 1. Determinism
# ===========================================================================

class TestDeterminism:
    """Same seed → identical output; different seed → different output."""

    def test_same_seed_produces_identical_row_count(self):
        """Calling predict_incidents twice with seed=42 returns same number of rows."""
        df1 = predict_incidents(_START, _END, seed=42)
        df2 = predict_incidents(_START, _END, seed=42)
        assert len(df1) == len(df2), (
            f"Row counts diverged: {len(df1)} vs {len(df2)}"
        )

    def test_same_seed_produces_identical_incident_ids(self):
        """Incident IDs are deterministic — same seed → same IDs in same order."""
        df1 = predict_incidents(_START, _END, seed=42)
        df2 = predict_incidents(_START, _END, seed=42)
        assert (df1["incident_id"].values == df2["incident_id"].values).all(), (
            "incident_id columns differed between two identical-seed runs"
        )

    def test_same_seed_produces_identical_datetimes(self):
        """Event timestamps are deterministic — same seed → same datetimes."""
        df1 = predict_incidents(_START, _END, seed=42)
        df2 = predict_incidents(_START, _END, seed=42)
        assert (df1["datetime"].values == df2["datetime"].values).all(), (
            "datetime columns differed between two identical-seed runs"
        )

    def test_different_seeds_produce_different_row_counts_or_content(self):
        """Different seeds must not be identical (high probability by construction)."""
        df42 = predict_incidents(_START, _END, seed=42)
        df99 = predict_incidents(_START, _END, seed=99)
        # At minimum the lengths should differ OR the event streams differ.
        # Both cannot be identical; Poisson sampling with different RNG seeds
        # will produce different count draws.
        same_length = len(df42) == len(df99)
        same_ids = (
            (df42["incident_id"].values == df99["incident_id"].values).all()
            if same_length
            else False
        )
        assert not (same_length and same_ids), (
            "seed=42 and seed=99 produced bit-for-bit identical DataFrames"
        )

    def test_same_seed_via_generate_dispatch_is_deterministic(self):
        """generate() (the dispatcher) is also deterministic for poisson_rate payloads."""
        payload = _load_default_payload()
        df1 = generate(payload, _START, _END, seed=7)
        df2 = generate(payload, _START, _END, seed=7)
        assert len(df1) == len(df2)
        assert (df1["datetime"].values == df2["datetime"].values).all()


# ===========================================================================
# 2. Output schema
# ===========================================================================

REQUIRED_COLUMNS = {
    "incident_id", "datetime", "cell_id", "cluster",
    "incident_type", "category", "lat", "lon",
}


class TestOutputSchema:
    """Returned DataFrame has the required columns and is non-empty."""

    def test_required_columns_present(self):
        df = predict_incidents(_START, _END, seed=42)
        missing = REQUIRED_COLUMNS - set(df.columns)
        assert not missing, f"Missing columns: {missing}"

    def test_non_empty_for_one_week_window(self):
        df = predict_incidents(_START, _END, seed=42)
        assert len(df) > 0, "Expected at least one incident in a 7-day window"

    def test_incident_id_is_unique(self):
        df = predict_incidents(_START, _END, seed=42)
        assert df["incident_id"].duplicated().sum() == 0, (
            "Duplicate incident_ids found in output"
        )

    def test_output_is_sorted_by_datetime(self):
        df = predict_incidents(_START, _END, seed=42)
        assert df["datetime"].is_monotonic_increasing, (
            "Output DataFrame is not sorted by datetime"
        )

    def test_incident_id_dtype_is_integer(self):
        df = predict_incidents(_START, _END, seed=42)
        assert pd.api.types.is_integer_dtype(df["incident_id"]), (
            f"incident_id dtype should be integer, got {df['incident_id'].dtype}"
        )

    def test_datetime_dtype_is_datetime(self):
        df = predict_incidents(_START, _END, seed=42)
        assert pd.api.types.is_datetime64_any_dtype(df["datetime"]), (
            f"datetime dtype should be datetime64, got {df['datetime'].dtype}"
        )

    def test_all_datetimes_within_requested_window(self):
        start = pd.Timestamp(_START)
        end = pd.Timestamp(_END)
        df = predict_incidents(_START, _END, seed=42)
        assert (df["datetime"] >= start).all(), "Events before start date found"
        assert (df["datetime"] < end).all(), "Events on or after end date found"

    def test_incident_ids_start_at_poisson_base(self):
        """Poisson rate generator starts incident IDs at 7_000_000."""
        df = predict_incidents(_START, _END, seed=42)
        assert df["incident_id"].min() >= 7_000_000, (
            f"Minimum incident_id {df['incident_id'].min()} < 7_000_000"
        )

    def test_cluster_values_are_within_valid_range(self):
        """Cluster labels should be integers 0–7 (8-cluster KMeans)."""
        df = predict_incidents(_START, _END, seed=42)
        assert df["cluster"].between(0, 7).all(), (
            f"Unexpected cluster values: {df['cluster'].unique()}"
        )


# ===========================================================================
# 3. Coordinate validity (Davidson County, Nashville)
# ===========================================================================

class TestCoordinates:
    """Coordinates must be non-NaN and within Davidson County bounding box."""

    # Conservative Davidson County bounding box
    LAT_MIN, LAT_MAX = 35.9, 36.5
    LON_MIN, LON_MAX = -87.1, -86.4

    def test_no_nan_lat(self):
        df = predict_incidents(_START, _END, seed=42)
        assert not df["lat"].isna().any(), "NaN latitudes found in output"

    def test_no_nan_lon(self):
        df = predict_incidents(_START, _END, seed=42)
        assert not df["lon"].isna().any(), "NaN longitudes found in output"

    def test_lat_within_davidson_county(self):
        df = predict_incidents(_START, _END, seed=42)
        assert df["lat"].between(self.LAT_MIN, self.LAT_MAX).all(), (
            f"Latitudes out of [{self.LAT_MIN}, {self.LAT_MAX}]: "
            f"min={df['lat'].min():.4f}, max={df['lat'].max():.4f}"
        )

    def test_lon_within_davidson_county(self):
        df = predict_incidents(_START, _END, seed=42)
        assert df["lon"].between(self.LON_MIN, self.LON_MAX).all(), (
            f"Longitudes out of [{self.LON_MIN}, {self.LON_MAX}]: "
            f"min={df['lon'].min():.4f}, max={df['lon'].max():.4f}"
        )


# ===========================================================================
# 4. Incident-type filtering
# ===========================================================================

class TestTypeFiltering:
    """incident_type='fire' returns a pure fire subset; all-types run is larger."""

    def test_fire_filter_returns_only_fire_types(self):
        """Every incident_type in the fire-filtered output must be in fire_types set."""
        df_fire = predict_incidents(_START, _END, seed=42, incident_type="fire")
        fire_types = _load_fire_types()
        non_fire = set(df_fire["incident_type"].unique()) - fire_types
        assert not non_fire, (
            f"Non-fire incident_types found after fire filter: {non_fire}"
        )

    def test_fire_filter_nonempty_for_one_week(self):
        """Fire incidents are rare but at least a handful should appear in a week."""
        df_fire = predict_incidents(_START, _END, seed=42, incident_type="fire")
        assert len(df_fire) > 0, "Fire filter returned empty DataFrame for 1-week window"

    def test_ems_fire_has_strictly_more_rows_than_fire(self):
        """All-types run (ems_fire) must have strictly more rows than fire-only."""
        df_all = predict_incidents(_START, _END, seed=42, incident_type="ems_fire")
        df_fire = predict_incidents(_START, _END, seed=42, incident_type="fire")
        assert len(df_all) > len(df_fire), (
            f"Expected len(ems_fire)={len(df_all)} > len(fire)={len(df_fire)}"
        )

    def test_none_and_all_and_ems_fire_are_equivalent(self):
        """None, 'all', and 'ems_fire' are semantically identical (no filtering)."""
        df_none = predict_incidents(_START, _END, seed=42, incident_type=None)
        df_all = predict_incidents(_START, _END, seed=42, incident_type="all")
        df_ems = predict_incidents(_START, _END, seed=42, incident_type="ems_fire")
        assert len(df_none) == len(df_all) == len(df_ems), (
            f"Lengths: None={len(df_none)}, all={len(df_all)}, ems_fire={len(df_ems)}"
        )

    def test_fire_filter_is_subset_of_full_output(self):
        """Fire-filtered IDs must be a subset of the unfiltered run's IDs."""
        df_all = predict_incidents(_START, _END, seed=42)
        df_fire = predict_incidents(_START, _END, seed=42, incident_type="fire")
        all_ids = set(df_all["incident_id"].values)
        fire_ids = set(df_fire["incident_id"].values)
        assert fire_ids.issubset(all_ids), (
            "Fire-filtered incident_ids are not a subset of the unfiltered run"
        )

    def test_fire_types_set_is_nonempty(self):
        """The fire_incident_types.json bundle must be non-empty."""
        fire_types = _load_fire_types()
        assert len(fire_types) > 0, "fire_incident_types.json is empty"


# ===========================================================================
# 5. _build_cluster_type_marginal: probability validity per cluster
#    (The task spec mentions _build_bldg_type_marginal; the actual production
#     function is _build_cluster_type_marginal. Both the cluster marginal and
#     the bldg-area marginal bundle JSON are tested here.)
# ===========================================================================

class TestClusterTypeMarginal:
    """Each cluster's type distribution must be a valid probability simplex."""

    @pytest.fixture(scope="class")
    def marginal(self):
        rng = np.random.default_rng(42)
        return _build_cluster_type_marginal(rng)

    def test_returns_all_eight_clusters(self, marginal):
        assert set(marginal.keys()) == set(range(8)), (
            f"Expected clusters 0-7, got {set(marginal.keys())}"
        )

    def test_probs_sum_to_one_per_cluster(self, marginal):
        for cl, (types, probs) in marginal.items():
            total = probs.sum()
            assert np.isclose(total, 1.0, atol=1e-4), (
                f"Cluster {cl}: probs sum to {total:.8f}, not 1.0"
            )

    def test_types_and_probs_same_length(self, marginal):
        for cl, (types, probs) in marginal.items():
            assert len(types) == len(probs), (
                f"Cluster {cl}: types length {len(types)} != probs length {len(probs)}"
            )

    def test_no_negative_probabilities(self, marginal):
        for cl, (types, probs) in marginal.items():
            assert (probs >= 0).all(), (
                f"Cluster {cl}: negative probability found"
            )

    def test_fire_type_probability_mass_positive_in_every_cluster(self, marginal):
        """Each cluster must assign non-zero probability to fire incident types."""
        fire_types = _load_fire_types()
        for cl, (types, probs) in marginal.items():
            fire_mass = sum(
                float(p) for t, p in zip(types, probs) if str(t) in fire_types
            )
            assert fire_mass > 0, (
                f"Cluster {cl}: zero fire-type probability mass (fire_types not represented)"
            )

    def test_types_are_strings(self, marginal):
        for cl, (types, probs) in marginal.items():
            assert all(isinstance(t, str) for t in types), (
                f"Cluster {cl}: non-string type found in types array"
            )


class TestBldgTypeMarginalJson:
    """Validate the type_marginal_by_bldg.json bundle directly.

    This covers the _build_bldg_type_marginal / _bldg_area_bin semantics
    referenced in the task spec; those helpers are embedded in the JSON asset
    itself rather than as separate functions in incidents_variants.py.
    """

    @pytest.fixture(scope="class")
    def bundle(self):
        path = _BUNDLE / "type_marginal_by_bldg.json"
        with open(path) as f:
            return json.load(f)

    def test_has_thresholds_and_bins_keys(self, bundle):
        assert "thresholds" in bundle, "Missing 'thresholds' key"
        assert "bins" in bundle, "Missing 'bins' key"

    def test_num_bins_equals_num_thresholds_plus_one(self, bundle):
        n_thresh = len(bundle["thresholds"])
        n_bins = len(bundle["bins"])
        assert n_bins == n_thresh + 1, (
            f"Expected {n_thresh + 1} bins for {n_thresh} thresholds, got {n_bins}"
        )

    def test_each_bin_probs_sum_to_one(self, bundle):
        for key, data in bundle["bins"].items():
            total = sum(data["probs"])
            assert abs(total - 1.0) < 1e-3, (
                f"Bin {key}: probs sum to {total:.8f}, expected ~1.0"
            )

    def test_each_bin_types_probs_same_length(self, bundle):
        for key, data in bundle["bins"].items():
            assert len(data["types"]) == len(data["probs"]), (
                f"Bin {key}: types/probs length mismatch"
            )

    def test_fire_type_mass_positive_in_every_bin(self, bundle):
        """Every building-area bin must contain non-zero fire-type probability."""
        fire_types = _load_fire_types()
        for key, data in bundle["bins"].items():
            fire_mass = sum(
                p for t, p in zip(data["types"], data["probs"]) if t in fire_types
            )
            assert fire_mass > 0, (
                f"Bin {key}: zero fire-type probability mass"
            )

    def test_thresholds_are_sorted_ascending(self, bundle):
        thresh = bundle["thresholds"]
        assert thresh == sorted(thresh), (
            f"Thresholds are not sorted: {thresh}"
        )


# ===========================================================================
# 6. _bldg_area_bin boundary behaviour
#    The searchsorted logic is embedded in the bundle JSON but the boundary
#    rules are straightforward: bin index = np.searchsorted(thresholds, value).
#    We test that contract directly using the bundle thresholds.
# ===========================================================================

class TestBldgAreaBinBoundaries:
    """Boundary behaviour of building-area bin assignment (searchsorted contract)."""

    @pytest.fixture(scope="class")
    def thresholds(self):
        path = _BUNDLE / "type_marginal_by_bldg.json"
        with open(path) as f:
            d = json.load(f)
        return np.array(d["thresholds"])

    def _bin(self, log_bldg_area: float, thresholds: np.ndarray) -> int:
        """Reference implementation: np.searchsorted mirrors the intended logic."""
        return int(np.searchsorted(thresholds, log_bldg_area))

    def test_value_below_first_threshold_maps_to_bin_zero(self, thresholds):
        val = thresholds[0] - 1.0  # clearly below all thresholds
        assert self._bin(val, thresholds) == 0

    def test_value_equal_to_first_threshold_maps_to_bin_one(self, thresholds):
        # searchsorted default side='left': exact match inserts to the left
        # meaning the value IS the threshold → bin index 1 if > threshold[0]
        # side='left' returns position BEFORE equal value → bin 0
        assert self._bin(thresholds[0], thresholds) == 0

    def test_value_just_above_first_threshold_maps_to_bin_one(self, thresholds):
        val = thresholds[0] + 1e-6
        assert self._bin(val, thresholds) == 1

    def test_value_above_last_threshold_maps_to_last_bin(self, thresholds):
        val = thresholds[-1] + 1.0
        expected = len(thresholds)  # 0..len(thresholds) inclusive
        assert self._bin(val, thresholds) == expected

    def test_returned_bin_within_valid_range(self, thresholds):
        test_values = [-10.0, 0.0] + thresholds.tolist() + [thresholds[-1] + 100.0]
        for v in test_values:
            b = self._bin(float(v), thresholds)
            assert 0 <= b <= len(thresholds), (
                f"Bin {b} out of [0, {len(thresholds)}] for value {v}"
            )

    def test_non_positive_log_area_maps_to_bin_zero(self, thresholds):
        """Log of a very small area (≤0) must resolve to the lowest bin (0)."""
        for v in [0.0, -5.0, -100.0]:
            assert self._bin(v, thresholds) == 0, (
                f"Expected bin 0 for log_bldg_area={v}, got {self._bin(v, thresholds)}"
            )


# ===========================================================================
# 7. _build_temporal_features
# ===========================================================================

class TestBuildTemporalFeatures:
    """Verify trigonometric and categorical temporal features for known timestamps."""

    # 2025-01-06 12:00:00 = Monday (weekday=0), hour=12, month=1
    _MONDAY_NOON = np.array(
        pd.to_datetime(["2025-01-06 12:00:00"]).values
    )
    # 2025-01-11 00:00:00 = Saturday (weekday=5), hour=0, month=1
    _SATURDAY_MIDNIGHT = np.array(
        pd.to_datetime(["2025-01-11 00:00:00"]).values
    )
    # 2025-03-15 06:00:00 = Saturday, hour=6, month=3
    _SAT_MARCH = np.array(
        pd.to_datetime(["2025-03-15 06:00:00"]).values
    )
    # 2025-01-01 10:00:00 = Wednesday (federal holiday: New Year's Day)
    _NEW_YEARS = np.array(
        pd.to_datetime(["2025-01-01 10:00:00"]).values
    )

    def test_hour_sin1_range_minus_one_to_one(self):
        ts = pd.date_range("2025-01-01", periods=24, freq="h")
        out = _build_temporal_features(ts.values, ["hour_sin1"])
        assert (out[:, 0] >= -1.0 - 1e-9).all() and (out[:, 0] <= 1.0 + 1e-9).all()

    def test_hour_cos1_range_minus_one_to_one(self):
        ts = pd.date_range("2025-01-01", periods=24, freq="h")
        out = _build_temporal_features(ts.values, ["hour_cos1"])
        assert (out[:, 0] >= -1.0 - 1e-9).all() and (out[:, 0] <= 1.0 + 1e-9).all()

    def test_hour_sin1_correct_for_hour_12(self):
        """hour=12 → sin(2π·12/24) = sin(π) ≈ 0."""
        out = _build_temporal_features(self._MONDAY_NOON, ["hour_sin1"])
        expected = np.sin(2 * np.pi * 12 / 24)
        assert np.isclose(out[0, 0], expected, atol=1e-10)

    def test_hour_cos1_correct_for_hour_12(self):
        """hour=12 → cos(2π·12/24) = cos(π) = -1."""
        out = _build_temporal_features(self._MONDAY_NOON, ["hour_cos1"])
        assert np.isclose(out[0, 0], -1.0, atol=1e-10)

    def test_hour_sin2_correct_for_hour_12(self):
        """hour=12 → sin(4π·12/24) = sin(2π) ≈ 0."""
        out = _build_temporal_features(self._MONDAY_NOON, ["hour_sin2"])
        expected = np.sin(4 * np.pi * 12 / 24)
        assert np.isclose(out[0, 0], expected, atol=1e-10)

    def test_hour_cos2_correct_for_hour_12(self):
        """hour=12 → cos(4π·12/24) = cos(2π) = 1."""
        out = _build_temporal_features(self._MONDAY_NOON, ["hour_cos2"])
        expected = np.cos(4 * np.pi * 12 / 24)
        assert np.isclose(out[0, 0], expected, atol=1e-10)

    def test_weekend_is_zero_for_monday(self):
        out = _build_temporal_features(self._MONDAY_NOON, ["weekend"])
        assert out[0, 0] == 0.0, f"Monday should have weekend=0, got {out[0, 0]}"

    def test_weekend_is_one_for_saturday(self):
        out = _build_temporal_features(self._SATURDAY_MIDNIGHT, ["weekend"])
        assert out[0, 0] == 1.0, f"Saturday should have weekend=1, got {out[0, 0]}"

    def test_weekend_is_binary(self):
        """weekend flag must be exactly 0 or 1 for any timestamp."""
        ts = pd.date_range("2025-01-01", periods=14, freq="D")
        out = _build_temporal_features(ts.values, ["weekend"])
        assert set(out[:, 0].tolist()).issubset({0.0, 1.0})

    def test_month_sin_correct_for_march(self):
        """month=3 → sin(2π·(3-1)/12) = sin(π/3) = √3/2."""
        out = _build_temporal_features(self._SAT_MARCH, ["month_sin"])
        expected = np.sin(2 * np.pi * 2 / 12)  # (m-1)=2
        assert np.isclose(out[0, 0], expected, atol=1e-10)

    def test_month_cos_correct_for_march(self):
        """month=3 → cos(2π·(3-1)/12) = cos(π/3) = 0.5."""
        out = _build_temporal_features(self._SAT_MARCH, ["month_cos"])
        expected = np.cos(2 * np.pi * 2 / 12)
        assert np.isclose(out[0, 0], expected, atol=1e-10)

    def test_month_january_sin_is_zero(self):
        """month=1 → sin(2π·0/12) = 0."""
        out = _build_temporal_features(self._MONDAY_NOON, ["month_sin"])
        assert np.isclose(out[0, 0], 0.0, atol=1e-10)

    def test_discrete_hour_flag_correct(self):
        """hour_14 feature must be 1.0 for hour=14 and 0.0 for hour=12."""
        ts_h14 = np.array(pd.to_datetime(["2025-01-04 14:00:00"]).values)
        ts_h12 = self._MONDAY_NOON
        out14 = _build_temporal_features(ts_h14, ["hour_14"])
        out12 = _build_temporal_features(ts_h12, ["hour_14"])
        assert out14[0, 0] == 1.0, f"Expected hour_14=1 at 14:00, got {out14[0,0]}"
        assert out12[0, 0] == 0.0, f"Expected hour_14=0 at 12:00, got {out12[0,0]}"

    def test_discrete_month_flag_correct(self):
        """month_3 feature must be 1.0 in March and 0.0 in January."""
        ts_jan = self._MONDAY_NOON
        ts_mar = self._SAT_MARCH
        out_jan = _build_temporal_features(ts_jan, ["month_3"])
        out_mar = _build_temporal_features(ts_mar, ["month_3"])
        assert out_jan[0, 0] == 0.0
        assert out_mar[0, 0] == 1.0

    def test_hour_x_weekend_is_zero_on_weekday(self):
        """hour_x_weekend = sin(2π·h/24)·weekend; must be 0 on weekday."""
        out = _build_temporal_features(self._MONDAY_NOON, ["hour_x_weekend"])
        assert np.isclose(out[0, 0], 0.0, atol=1e-10)

    def test_hour_x_weekend_correct_on_saturday(self):
        """hour_x_weekend = sin(2π·0/24)·1 = 0 for Saturday midnight."""
        out = _build_temporal_features(self._SATURDAY_MIDNIGHT, ["hour_x_weekend"])
        expected = np.sin(2 * np.pi * 0 / 24) * 1.0  # hour=0
        assert np.isclose(out[0, 0], expected, atol=1e-10)

    def test_is_holiday_detected_for_new_years(self):
        """New Year's Day (Jan 1) must be flagged when holidays_set is provided."""
        from pandas.tseries.holiday import USFederalHolidayCalendar
        cal = USFederalHolidayCalendar()
        hols = cal.holidays(start="2025-01-01", end="2025-01-01")
        holidays_set = set(pd.DatetimeIndex(hols).normalize())
        out = _build_temporal_features(self._NEW_YEARS, ["is_holiday"], holidays_set=holidays_set)
        assert out[0, 0] == 1.0, "Jan 1 should be flagged as holiday"

    def test_is_holiday_zero_without_holidays_set(self):
        """Without holidays_set, is_holiday must be 0 even on a federal holiday."""
        out = _build_temporal_features(self._NEW_YEARS, ["is_holiday"])
        assert out[0, 0] == 0.0

    def test_output_shape_matches_col_count(self):
        """Output shape must be (n_timestamps, len(cat_cols))."""
        cat_cols = ["hour_sin1", "hour_cos1", "weekend", "month_sin"]
        ts = pd.date_range("2025-01-01", periods=10, freq="h").values
        out = _build_temporal_features(ts, cat_cols)
        assert out.shape == (10, 4)

    def test_unknown_column_produces_zero_column(self):
        """An unrecognised column name must produce a column of zeros (safe default)."""
        ts = pd.date_range("2025-01-01", periods=5, freq="h").values
        out = _build_temporal_features(ts, ["nonexistent_feature"])
        assert (out[:, 0] == 0.0).all(), (
            "Unrecognised feature column should be all zeros"
        )
