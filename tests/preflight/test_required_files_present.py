"""Preflight: every file the backend/simulator reads at startup or at first
request must exist on disk.

Every failure message names the missing file AND the env var an operator
would set to point at a different location, so the fix is one line:
    export DATA_DIR=/somewhere/else
    export LOGS_DIR=/somewhere/else

Bug classes this test prevents:
- (Incident 2) "FireBeats matrix file not found: /app/logs/beats.bin" from
  a stack whose logs/ was empty because someone symlinked data/ but not
  logs/.
- (Incident 3) growth_poisson_v1.pkl missing -> generic 500 with no hint.
- (Incident 9) fire_simulator binary missing / not executable.

Runs in well under a second. Meant to be the FIRST thing preflight.sh runs.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest


# --------------------------------------------------------------------------- #
# Required (must pass on any deploy)
# --------------------------------------------------------------------------- #

# (relative path under DATA_DIR, env var name that overrides its parent)
REQUIRED_DATA_FILES: list[tuple[str, str]] = [
    ("stations_with_apparatus.csv",              "DATA_DIR"),
    ("NFDResponse.csv",                          "DATA_DIR"),
    ("bounds.geojson",                           "DATA_DIR"),
    ("zones.csv",                                "DATA_DIR"),
    ("beats_shpfile.geojson",                    "DATA_DIR"),
    ("response_time_summary2.csv",               "DATA_DIR"),
    ("interpolation_data/mean_zone_travel_time_matrix.json",   "DATA_DIR"),
    ("interpolation_data/std_zone_travel_time_matrix.json",    "DATA_DIR"),
    ("interpolation_data/zone_fire_station_info.json",         "DATA_DIR"),
    ("interpolation_fire/mean_zone_travel_time_matrix.json",   "DATA_DIR"),
    ("interpolation_fire/std_zone_travel_time_matrix.json",    "DATA_DIR"),
    ("interpolation_fire/zone_fire_station_info.json",         "DATA_DIR"),
    ("models/fire_incident_gb_model.onnx",                     "DATA_DIR"),
    ("models/fire_model_features_mapping.json",                "DATA_DIR"),
    ("models/ems_model/fire_incident_gb_model.onnx",           "DATA_DIR"),
    ("models/ems_model/fire_model_features_mapping.json",      "DATA_DIR"),
    ("ems_stats/hospital_locations.csv",                       "DATA_DIR"),
    ("ems_stats/scene_time_by_category.csv",                   "DATA_DIR"),
    ("ems_stats/transport_prob_by_category.csv",               "DATA_DIR"),
    ("ems_stats/hospital_turnaround_overall.csv",              "DATA_DIR"),
    ("ems_stats/hospital_zone_probs.csv",                      "DATA_DIR"),
    ("ems_stats/scene_time_model_params.csv",                  "DATA_DIR"),
    ("ems_stats/hospital_turnaround_by_dest.csv",              "DATA_DIR"),
    ("ems_stats/transport_multi_medic_dist.csv",               "DATA_DIR"),
    ("incidents_export_apparatus.csv",                         "DATA_DIR"),
    ("incidents_export_apparatus_fire.csv",                    "DATA_DIR"),
]

# Optional (predictive / synthetic flows only). Skipped by preflight.sh.
OPTIONAL_DATA_FILES: list[tuple[str, str]] = [
    ("models/growth_poisson_v1/growth_poisson_v1.pkl",          "DATA_DIR"),
    ("models/growth_poisson_v1/cell_features_yearly.csv",       "DATA_DIR"),
    ("models/growth_poisson_v1/clustering_data.csv",            "DATA_DIR"),
    ("models/growth_poisson_v1/cluster_type_marginal.json",     "DATA_DIR"),
    ("models/growth_poisson_v1/grid.geojson",                   "DATA_DIR"),
]

# Directories whose presence matters but whose contents vary per training.
OPTIONAL_DATA_DIRS: list[tuple[str, str]] = [
    ("models/incident_prediction_system",       "DATA_DIR"),
    ("models/incident_prediction_system_fire",  "DATA_DIR"),
]


def _fmt_missing(kind: str, abs_path: Path, rel: str, env_var: str, extra: str = "") -> str:
    return (
        f"\n\nPREFLIGHT: missing {kind}:\n"
        f"  expected: {abs_path}\n"
        f"  relative: {rel}\n"
        f"  fix:      place the file at that path, or override its parent by\n"
        f"            setting the {env_var} env var (see src/core/config.py).\n"
        f"{extra}"
    )


# --------------------------------------------------------------------------- #
# Required data files
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("rel,env_var", REQUIRED_DATA_FILES, ids=[p for p, _ in REQUIRED_DATA_FILES])
def test_required_data_file_exists(real_data_dir: Path, rel: str, env_var: str):
    abs_path = real_data_dir / rel
    assert abs_path.is_file(), _fmt_missing("required data file", abs_path, rel, env_var)


def test_fire_simulator_binary_present_and_executable(real_data_dir: Path):
    """The C++ simulator is invoked as `./data/fire_simulator` -- it has to
    exist AND be marked executable. The binary itself is checked into DATA_DIR
    because engine.simulation.py runs it from there."""
    binary = real_data_dir / "fire_simulator"
    assert binary.is_file(), _fmt_missing(
        "fire_simulator binary", binary, "fire_simulator", "DATA_DIR",
        extra="            (Also verify HOST_ONNXRUNTIME_DIR is set correctly\n"
              "            in .env so the binary can load libonnxruntime.)\n",
    )
    mode = binary.stat().st_mode
    is_exec = bool(mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    assert is_exec, (
        f"\n\nPREFLIGHT: fire_simulator exists but is not executable:\n"
        f"  path: {binary}\n"
        f"  fix:  chmod +x {binary}\n"
    )


def test_beats_matrix_present_in_logs_dir(real_logs_dir: Path):
    """The FireBeats dispatch matrix is a *shared* file at LOGS_DIR/beats.bin
    (see engine/simulation.py: FIREBEATS_MATRIX_PATH). If this stack has its
    own logs/ (e.g. `-next` stack) and never got a beats.bin copy, every
    firebeats run fails at startup with 'FireBeats matrix file not found'."""
    beats = real_logs_dir / "beats.bin"
    assert beats.is_file(), _fmt_missing(
        "FireBeats matrix", beats, "beats.bin", "LOGS_DIR",
        extra="            (Symptom if missing: C++ simulator errors with\n"
              "            'FireBeats matrix file not found: <path>'.)\n",
    )


# --------------------------------------------------------------------------- #
# Optional bundles (skipped with -m "not optional")
# --------------------------------------------------------------------------- #

@pytest.mark.optional
@pytest.mark.parametrize("rel,env_var", OPTIONAL_DATA_FILES, ids=[p for p, _ in OPTIONAL_DATA_FILES])
def test_optional_data_file_exists(real_data_dir: Path, rel: str, env_var: str):
    abs_path = real_data_dir / rel
    assert abs_path.is_file(), _fmt_missing(
        "optional bundle file", abs_path, rel, env_var,
        extra="            (Only required if synthetic-incident generation is used.)\n",
    )


@pytest.mark.optional
@pytest.mark.parametrize("rel,env_var", OPTIONAL_DATA_DIRS, ids=[p for p, _ in OPTIONAL_DATA_DIRS])
def test_optional_data_directory_exists(real_data_dir: Path, rel: str, env_var: str):
    abs_path = real_data_dir / rel
    assert abs_path.is_dir(), _fmt_missing(
        "optional predictive-model directory", abs_path, rel, env_var,
        extra="            (Only required if incident-prediction endpoints are used.)\n",
    )
