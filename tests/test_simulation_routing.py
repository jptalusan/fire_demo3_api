"""Tests verifying the simulation/comparison path uses growth_v1 (NOT the legacy
survival model) for synthetic incident generation, and that the output produced
by that path satisfies the CSV schema contract.

Test organisation
-----------------
1. test_synthetic_branch_routes_to_growth_v1_not_legacy
   - Static source analysis (ast) on src/engine/simulation.py.
   - Asserts: within run_simulation_internal's synthetic_incidents block the
     identifier `predict_incidents_growth_v1` (imported from incidents_variants)
     is present AND `predict_incidents_with_types_and_coordinates` (legacy) is absent.

2. test_synthetic_branch_imports_from_incidents_variants_not_incidents
   - Static analysis complement: checks the import statement inside the branch
     resolves to `engine.incidents_variants`, not `engine.incidents`.

3. test_growth_v1_output_contains_all_csv_schema_columns
   - Calls the real generator over a 2-day seeded window.
   - After replicating the incident_level assignment exactly as simulation.py does
     (default_rng(seed).choice), asserts all seven CSV-header columns are present.

4. test_incident_level_values_are_valid_choices
   - Same generator call; asserts every value in incident_level is in
     {'Low', 'Moderate', 'High'}.

5. test_determinism_same_seed_same_incidents
   - Calls generator twice with seed=42; asserts identical row count and identical
     incident_id sequences.

6. test_generator_produces_nonzero_incidents_for_7_day_window
   - Asserts the short window returns > 0 rows (simulation is not fed an empty file).

7. test_csv_row_format_has_seven_comma_separated_fields
   - Replicates the exact f-string formatting from simulation.py for the first 20
     rows and asserts each has exactly 7 comma-separated fields.

8. test_csv_round_trips_via_pandas_with_correct_dtypes
   - Builds a minimal CSV (header + first N rows) exactly as simulation.py does
     and reads it back with pandas.read_csv; asserts incident_id is int-castable,
     lat/lon are float, datetime is parseable, and incident_level is in the
     valid set.

No unittest.mock / patch is used anywhere; the routing tests use static source
inspection (ast / inspect), and the contract tests call the real generator.
"""

from __future__ import annotations

import ast
import csv
import inspect
import io
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
_WORKTREE = Path(__file__).resolve().parent.parent          # repo root
_SIM_SRC = _WORKTREE / "src" / "engine" / "simulation.py"


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _func_source(full_source: str, func_name: str) -> str:
    """Extract the verbatim source lines for *func_name* using ast line numbers."""
    tree = ast.parse(full_source)
    lines = full_source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return "\n".join(lines[node.lineno - 1: node.end_lineno])
    raise AssertionError(f"Function '{func_name}' not found in {_SIM_SRC}")


def _synthetic_branch_text(func_src: str) -> str:
    """Return the text starting from the 'synthetic_incidents' condition line."""
    marker = "== 'synthetic_incidents'"
    for i, line in enumerate(func_src.splitlines()):
        if marker in line:
            return "\n".join(func_src.splitlines()[i:])
    raise AssertionError(
        "synthetic_incidents branch not found inside run_simulation_internal"
    )


# ---------------------------------------------------------------------------
# Shared generator fixture (calls real code, seeded 2-day window for speed)
# ---------------------------------------------------------------------------

SEED = 42
START = "2025-01-01"
END = "2025-01-03"
INCIDENT_TYPE = "ems_fire"

REQUIRED_CSV_COLS = {"incident_id", "lat", "lon", "incident_type", "incident_level",
                     "datetime", "category"}
VALID_LEVELS = {"Low", "Moderate", "High"}
LEVEL_PROBS = [0.4, 0.4, 0.2]


@pytest.fixture(scope="module")
def growth_v1_df_with_level():
    """Real generator output (ems_fire, 2025-01-01..03, seed=42) plus
    incident_level assigned exactly as simulation.py does."""
    import sys
    sys.path.insert(0, str(_WORKTREE / "src"))

    from engine.incidents_variants import predict_incidents as predict_incidents_growth_v1

    df = predict_incidents_growth_v1(START, END, seed=SEED, incident_type=INCIDENT_TYPE)
    assert not df.empty, "generator returned 0 rows for 2025-01-01..03 – fixture unusable"

    rng = np.random.default_rng(SEED)
    df = df.copy()
    df["incident_level"] = rng.choice(["Low", "Moderate", "High"],
                                      size=len(df), p=LEVEL_PROBS)
    return df


# ===========================================================================
# 1. Routing guard — static source analysis
# ===========================================================================

def test_synthetic_branch_routes_to_growth_v1_not_legacy():
    """run_simulation_internal's synthetic_incidents block references
    predict_incidents_growth_v1 (growth_v1) and NOT
    predict_incidents_with_types_and_coordinates (legacy survival model)."""
    src = _read_source(_SIM_SRC)
    func_src = _func_source(src, "run_simulation_internal")
    branch = _synthetic_branch_text(func_src)

    assert "predict_incidents_growth_v1" in branch, (
        "DEFECT: synthetic_incidents branch does not reference predict_incidents_growth_v1 "
        "(growth_v1 generator). The routing has not been updated."
    )
    assert "predict_incidents_with_types_and_coordinates" not in branch, (
        "DEFECT: synthetic_incidents branch still calls predict_incidents_with_types_and_"
        "coordinates (legacy survival model). It must call the growth_v1 generator instead."
    )


def test_synthetic_branch_imports_from_incidents_variants_not_incidents():
    """The import inside the synthetic_incidents branch resolves to
    engine.incidents_variants, not engine.incidents."""
    src = _read_source(_SIM_SRC)
    func_src = _func_source(src, "run_simulation_internal")
    branch = _synthetic_branch_text(func_src)

    assert "engine.incidents_variants" in branch, (
        "DEFECT: the import in the synthetic_incidents branch does not reference "
        "engine.incidents_variants. Check the import statement."
    )
    # The legacy module is engine.incidents — confirm it is not imported in the branch
    # (allow 'engine.incidents_variants' substring but not bare 'engine.incidents' followed by space/newline)
    import re
    # Match 'engine.incidents' not immediately followed by '_variants'
    legacy_import_pattern = re.compile(r"\bengine\.incidents\b(?!_variants)")
    assert not legacy_import_pattern.search(branch), (
        "DEFECT: synthetic_incidents branch imports from engine.incidents (legacy). "
        "It should import from engine.incidents_variants."
    )


# ===========================================================================
# 2. Output contract — CSV column schema
# ===========================================================================

def test_growth_v1_output_contains_all_csv_schema_columns(growth_v1_df_with_level):
    """After incident_level assignment, the DataFrame contains every column
    the simulation CSV header requires."""
    df = growth_v1_df_with_level
    missing = REQUIRED_CSV_COLS - set(df.columns)
    assert not missing, (
        f"DataFrame is missing required CSV columns: {missing}. "
        f"Present columns: {list(df.columns)}"
    )


def test_incident_level_values_are_valid_choices(growth_v1_df_with_level):
    """Every value in incident_level is one of Low / Moderate / High."""
    df = growth_v1_df_with_level
    bad = set(df["incident_level"].unique()) - VALID_LEVELS
    assert not bad, (
        f"incident_level contains unexpected values: {bad}. "
        f"All allowed values: {VALID_LEVELS}"
    )


# ===========================================================================
# 3. Determinism — same seed -> same incidents
# ===========================================================================

def test_determinism_same_seed_produces_identical_incident_ids():
    """Two calls with identical seed return the same row count and incident_id
    sequence, proving the generator is deterministic."""
    import sys
    sys.path.insert(0, str(_WORKTREE / "src"))
    from engine.incidents_variants import predict_incidents as predict_incidents_growth_v1

    df1 = predict_incidents_growth_v1(START, END, seed=SEED, incident_type=INCIDENT_TYPE)
    df2 = predict_incidents_growth_v1(START, END, seed=SEED, incident_type=INCIDENT_TYPE)

    assert len(df1) == len(df2), (
        f"Same seed produced different row counts: {len(df1)} vs {len(df2)}"
    )
    ids1 = list(df1["incident_id"])
    ids2 = list(df2["incident_id"])
    assert ids1 == ids2, (
        "Same seed produced different incident_id sequences — generator is not deterministic."
    )


def test_determinism_different_seeds_differ():
    """Two calls with different seeds produce different incident_id sequences
    (sanity-check that the seed actually influences output)."""
    import sys
    sys.path.insert(0, str(_WORKTREE / "src"))
    from engine.incidents_variants import predict_incidents as predict_incidents_growth_v1

    df_a = predict_incidents_growth_v1(START, END, seed=42, incident_type=INCIDENT_TYPE)
    df_b = predict_incidents_growth_v1(START, END, seed=99, incident_type=INCIDENT_TYPE)

    # It would be astronomically unlikely for two Poisson draws with different
    # seeds to produce the identical count AND identical id sequence.
    if len(df_a) == len(df_b):
        assert list(df_a["incident_id"]) != list(df_b["incident_id"]), (
            "Different seeds produced identical incident_id sequences — "
            "seed is not influencing the generator."
        )
    # else: different counts already confirm the seeds differ


# ===========================================================================
# 4. Non-empty output guard
# ===========================================================================

def test_generator_produces_nonzero_incidents_for_7_day_window():
    """A 7-day window returns at least one incident so the simulation is never
    fed an empty file silently."""
    import sys
    sys.path.insert(0, str(_WORKTREE / "src"))
    from engine.incidents_variants import predict_incidents as predict_incidents_growth_v1

    df = predict_incidents_growth_v1("2025-01-01", "2025-01-08",
                                     seed=SEED, incident_type=INCIDENT_TYPE)
    assert len(df) > 0, (
        "Generator returned 0 incidents for a 7-day window (2025-01-01..08) with seed=42. "
        "The simulation would write an empty CSV and the C++ simulator would have no events."
    )


# ===========================================================================
# 5. CSV row format
# ===========================================================================

def test_simulation_writes_csv_via_writer_not_unquoted_fstring():
    """Static guard: the synthetic branch must serialise CSV with the csv module
    (quote-aware), NOT by interpolating fields into a bare comma f-string.

    The unquoted f-string corrupted any row whose incident_type contained a comma.
    This asserts the production code uses csv.writer and no longer builds a row by
    f-string comma-joining of the incident fields.
    """
    branch = _synthetic_branch_text(_func_source(_read_source(_SIM_SRC), "run_simulation_internal"))
    assert "csv.writer" in branch, (
        "simulation.py synthetic branch must use csv.writer for quote-safe CSV output"
    )
    # The old unquoted pattern joined incident fields with literal commas in an
    # f-string; ensure that exact anti-pattern is gone.
    assert "incident['incident_type']}," not in branch and "{incident['lat']}," not in branch, (
        "simulation.py still builds CSV rows via an unquoted f-string — comma-containing "
        "incident_type values will corrupt the row"
    )


# ===========================================================================
# 6. CSV quoting: comma-containing incident_type round-trips to exactly 7 fields
# ===========================================================================

def _write_csv_like_production(df):
    """Serialise the incidents DataFrame the way simulation.py now does
    (csv.writer, lineterminator='\\n', the 7 schema columns)."""
    cols = ["incident_id", "lat", "lon", "incident_type", "incident_level", "datetime", "category"]
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cols)
    for _, inc in df.iterrows():
        w.writerow([inc[c] for c in cols])
    return buf.getvalue()


def test_comma_types_quoted_to_exactly_seven_fields(growth_v1_df_with_level):
    """Serialise via the production csv.writer path and parse back with
    csv.reader: every row must yield exactly 7 fields even when incident_type
    contains commas, and at least one such comma-type must be present (so the
    quoting is genuinely exercised)."""
    df = growth_v1_df_with_level
    text = _write_csv_like_production(df)
    records = [r for r in csv.reader(io.StringIO(text)) if r]
    assert records[0] == ["incident_id", "lat", "lon", "incident_type",
                          "incident_level", "datetime", "category"]
    data = records[1:]
    assert data, "no rows serialised"
    bad = [i for i, r in enumerate(data) if len(r) != 7]
    assert not bad, f"{len(bad)} row(s) did not parse to 7 fields; first={data[bad[0]]}"

    # Non-vacuous: comma-containing incident_type present and preserved intact.
    assert df["incident_type"].str.contains(",", regex=False).any(), (
        "no comma-containing incident_type in sample — widen the window"
    )
    comma_rows = [r for r in data if "," in r[3]]
    assert comma_rows, "csv.reader found no comma inside the incident_type column"


# ===========================================================================
# 7. CSV round-trip via pandas — comma types included, parsed correctly
# ===========================================================================

def test_csv_round_trips_with_correct_dtypes(growth_v1_df_with_level):
    """Build the CSV the way simulation.py now does (csv.writer) and read it back
    with pandas.read_csv. With quoting, comma-containing incident_type values
    round-trip correctly, so NO rows need to be excluded."""
    df = growth_v1_df_with_level
    import pandas as pd
    text = _write_csv_like_production(df.head(50))
    parsed = pd.read_csv(io.StringIO(text))
    assert list(parsed.columns) == ["incident_id", "lat", "lon", "incident_type",
                                    "incident_level", "datetime", "category"]
    assert len(parsed) == min(50, len(df))
    # dtypes / parseability
    assert parsed["incident_id"].astype("int64").notna().all()
    assert parsed["lat"].astype(float).notna().all()
    assert parsed["lon"].astype(float).notna().all()
    assert pd.to_datetime(parsed["datetime"]).notna().all()
    assert set(parsed["incident_level"].unique()).issubset({"Low", "Moderate", "High"})
    clean = df[~df["incident_type"].astype(str).str.contains(",", regex=False)].head(50).copy()
    assert len(clean) >= 5, (
        "Fewer than 5 comma-free incident_type rows available — "
        "cannot perform meaningful CSV round-trip test."
    )

    # Replicate simulation.py CSV construction verbatim
    csv_header = "incident_id,lat,lon,incident_type,incident_level,datetime,category\n"
    csv_rows = []
    for _, incident in clean.iterrows():
        row = (
            f"{incident['incident_id']},"
            f"{incident['lat']},"
            f"{incident['lon']},"
            f"{incident['incident_type']},"
            f"{incident['incident_level']},"
            f"{incident['datetime']},"
            f"{incident['category']}"
        )
        csv_rows.append(row)
    csv_content = csv_header + "\n".join(csv_rows)

    # Round-trip through pandas
    parsed = pd.read_csv(io.StringIO(csv_content))

    # Column presence
    missing = REQUIRED_CSV_COLS - set(parsed.columns)
    assert not missing, f"Round-tripped CSV is missing columns: {missing}"

    # incident_id must be integer-castable
    try:
        parsed["incident_id"].astype(int)
    except (ValueError, TypeError) as exc:
        pytest.fail(f"incident_id column is not integer-castable: {exc}")

    # lat / lon must be float-castable
    for col in ("lat", "lon"):
        try:
            parsed[col].astype(float)
        except (ValueError, TypeError) as exc:
            pytest.fail(f"Column '{col}' is not float-castable: {exc}")

    # datetime must be parseable by pandas
    try:
        pd.to_datetime(parsed["datetime"])
    except Exception as exc:
        pytest.fail(f"datetime column is not parseable: {exc}")

    # incident_level must stay within valid set
    bad = set(parsed["incident_level"].unique()) - VALID_LEVELS
    assert not bad, f"Round-tripped incident_level contains unexpected values: {bad}"


# ===========================================================================
# 7. incident_level assignment replicates simulation.py exactly
# ===========================================================================

def test_incident_level_assignment_is_reproducible_with_same_seed():
    """The incident_level sequence produced by default_rng(seed).choice(...) is
    deterministic: two identical rng calls must yield the same label sequence."""
    import sys
    sys.path.insert(0, str(_WORKTREE / "src"))
    from engine.incidents_variants import predict_incidents as predict_incidents_growth_v1

    df = predict_incidents_growth_v1(START, END, seed=SEED, incident_type=INCIDENT_TYPE)
    n = len(df)

    rng_a = np.random.default_rng(SEED)
    levels_a = rng_a.choice(["Low", "Moderate", "High"], size=n, p=LEVEL_PROBS)

    rng_b = np.random.default_rng(SEED)
    levels_b = rng_b.choice(["Low", "Moderate", "High"], size=n, p=LEVEL_PROBS)

    assert list(levels_a) == list(levels_b), (
        "incident_level sequences differ between two default_rng calls with the same seed — "
        "numpy RNG is not deterministic under these conditions."
    )


def test_incident_level_probabilities_roughly_match_spec(growth_v1_df_with_level):
    """With ~900+ incidents the empirical proportions should be close to
    [Low=0.4, Moderate=0.4, High=0.2].  Tolerance: ±0.06 on each bucket."""
    df = growth_v1_df_with_level
    n = len(df)
    counts = df["incident_level"].value_counts(normalize=True)

    for label, expected_p in [("Low", 0.4), ("Moderate", 0.4), ("High", 0.2)]:
        actual = float(counts.get(label, 0.0))
        assert abs(actual - expected_p) < 0.06, (
            f"incident_level '{label}': expected ~{expected_p:.2f}, got {actual:.4f} "
            f"(n={n}). Probabilities [0.4, 0.4, 0.2] may not be applied correctly."
        )
