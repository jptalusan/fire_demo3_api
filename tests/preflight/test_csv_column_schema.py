"""Preflight: CSV headers must match what the code (and the C++ loader)
assumes, in the right order.

The C++ simulator reads apparatus counts by column index -- if
stations_with_apparatus.csv and NFDResponse.csv drift out of alignment,
every dispatch decision silently reads the wrong apparatus. That was
Incident 1 in the motivating list (old binary + new NFDResponse.csv =>
'No apparatus requirements for Thirteen' silently).

Bug classes this test prevents:
- (Incident 1) Column drift between stations csv and NFDResponse csv.
- (Incident 8) Commas in incident_type shifting every column right.
- (Incident 9) 15 vs 16 column mismatch between binary and CSV.

Every failure message includes the expected header, the actual header,
and a per-column diff so an operator can see exactly which column is off.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest


# --------------------------------------------------------------------------- #
# Canonical headers -- these are the source of truth. If the C++ binary is
# rebuilt with a different column layout, update BOTH the binary and these
# constants in the same commit. Otherwise preflight will (correctly) fail.
# --------------------------------------------------------------------------- #

EXPECTED_STATIONS_HEADER = [
    "StationID", "Stations", "lat", "lon", "Nashville Fire Stations",
    "Engine_ID", "Truck", "Rescue", "Hazard", "Squad", "FAST", "Medic",
    "Brush", "Boat", "UTV", "REACH", "Suppression_Chief", "EMS_Chief",
]

EXPECTED_NFDRESPONSE_HEADER = [
    "Enum", "Category", "Description",
    "Engine_ID", "Truck", "Rescue", "Hazard", "Squad", "FAST", "Medic",
    "Brush", "Boat", "UTV", "REACH", "Suppression_Chief", "EMS_Chief",
]

# Apparatus columns in stations_with_apparatus.csv are positions 5-17.
STATIONS_APPARATUS_SLICE = slice(5, 18)
# Apparatus columns in NFDResponse.csv are positions 3-15.
NFDRESPONSE_APPARATUS_SLICE = slice(3, 16)

EXPECTED_INCIDENTS_HEADER = [
    "incident_id", "lat", "lon", "incident_type", "incident_level",
    "datetime", "category",
]

# Categories that legitimately have no non-chief apparatus in NFDResponse.
# Kept as an explicit allow-list so the test surfaces newly-broken categories
# instead of quietly ignoring anything chief-only.
CHIEF_ONLY_CATEGORIES_XFAIL = {"Thirteen"}


def _diff_headers(expected: list[str], actual: list[str]) -> str:
    lines = ["\n  column diff (expected -> actual):"]
    for i in range(max(len(expected), len(actual))):
        e = expected[i] if i < len(expected) else "<missing>"
        a = actual[i] if i < len(actual) else "<missing>"
        marker = "   " if e == a else "!! "
        lines.append(f"    {marker}[{i:2d}] {e!r:30s} vs {a!r}")
    return "\n".join(lines)


def _read_header(path: Path) -> list[str]:
    assert path.is_file(), f"CSV not found: {path}"
    with path.open() as f:
        reader = csv.reader(f)
        return next(reader)


# --------------------------------------------------------------------------- #
# Headers
# --------------------------------------------------------------------------- #

def test_stations_with_apparatus_header_matches(real_data_dir: Path):
    path = real_data_dir / "stations_with_apparatus.csv"
    actual = _read_header(path)
    assert actual == EXPECTED_STATIONS_HEADER, (
        f"\n\nPREFLIGHT: {path} header drift.\n"
        f"  expected: {EXPECTED_STATIONS_HEADER}\n"
        f"  actual:   {actual}"
        f"{_diff_headers(EXPECTED_STATIONS_HEADER, actual)}\n"
        f"  fix: regenerate stations_with_apparatus.csv with the header above,\n"
        f"       or bump the C++ simulator to match the new layout.\n"
    )


def test_nfdresponse_header_matches(real_data_dir: Path):
    path = real_data_dir / "NFDResponse.csv"
    actual = _read_header(path)
    assert actual == EXPECTED_NFDRESPONSE_HEADER, (
        f"\n\nPREFLIGHT: {path} header drift.\n"
        f"  expected: {EXPECTED_NFDRESPONSE_HEADER}\n"
        f"  actual:   {actual}"
        f"{_diff_headers(EXPECTED_NFDRESPONSE_HEADER, actual)}\n"
        f"  fix: regenerate NFDResponse.csv with the header above.\n"
    )


def test_apparatus_columns_align_between_stations_and_nfdresponse(real_data_dir: Path):
    """The C++ loader reads apparatus counts by column INDEX, then joins
    stations with NFDResponse rows by that same index. Any drift silently
    corrupts dispatch. Fail loudly here instead."""
    stations_header = _read_header(real_data_dir / "stations_with_apparatus.csv")
    nfd_header = _read_header(real_data_dir / "NFDResponse.csv")

    stations_apparatus = stations_header[STATIONS_APPARATUS_SLICE]
    nfd_apparatus = nfd_header[NFDRESPONSE_APPARATUS_SLICE]

    assert stations_apparatus == nfd_apparatus, (
        f"\n\nPREFLIGHT: apparatus column alignment mismatch.\n"
        f"  stations_with_apparatus.csv cols [5:18]: {stations_apparatus}\n"
        f"  NFDResponse.csv            cols [3:16]: {nfd_apparatus}"
        f"{_diff_headers(nfd_apparatus, stations_apparatus)}\n"
        f"  fix: both CSVs share the same apparatus list, in the same order.\n"
        f"       The C++ binary loads by index, so any drift is a silent bug.\n"
    )


# --------------------------------------------------------------------------- #
# Incidents CSV
# --------------------------------------------------------------------------- #

def test_incidents_export_apparatus_header_and_first_row(real_data_dir: Path):
    """incidents_export_apparatus.csv is the source that engine.simulation's
    get_or_create_historical_incidents filters + writes to the C++ binary."""
    path = real_data_dir / "incidents_export_apparatus.csv"
    with path.open() as f:
        reader = csv.reader(f)
        header = next(reader)
        first = next(reader, None)

    assert header == EXPECTED_INCIDENTS_HEADER, (
        f"\n\nPREFLIGHT: {path} header drift.\n"
        f"  expected: {EXPECTED_INCIDENTS_HEADER}\n"
        f"  actual:   {header}"
        f"{_diff_headers(EXPECTED_INCIDENTS_HEADER, header)}\n"
    )
    assert first is not None and len(first) == len(EXPECTED_INCIDENTS_HEADER), (
        f"\n\nPREFLIGHT: first data row of {path} has the wrong column count "
        f"(got {len(first) if first else 0}, expected {len(EXPECTED_INCIDENTS_HEADER)}). "
        f"Often caused by unquoted commas in incident_type (Incident 8).\n"
    )


def test_every_incident_category_has_a_dispatch_row(real_data_dir: Path):
    """Every `category` value that shows up in incidents_export_apparatus.csv
    must exist as an `Enum` in NFDResponse.csv, otherwise the simulator
    errors with 'No apparatus requirements for <category>' at first dispatch.
    """
    incidents_path = real_data_dir / "incidents_export_apparatus.csv"
    nfd_path = real_data_dir / "NFDResponse.csv"

    with nfd_path.open() as f:
        nfd_enums = {row["Enum"] for row in csv.DictReader(f) if row.get("Enum")}

    with incidents_path.open() as f:
        incident_categories: set[str] = set()
        for row in csv.DictReader(f):
            cat = row.get("category")
            if cat:
                incident_categories.add(cat)

    missing = sorted(incident_categories - nfd_enums)
    assert not missing, (
        f"\n\nPREFLIGHT: incidents reference categories with no NFDResponse row:\n"
        f"  missing enums: {missing}\n"
        f"  fix: add these Enums to {nfd_path}, or fix the category values in\n"
        f"       {incidents_path}.\n"
        f"       (Symptom if unfixed: 'No apparatus requirements for <enum>' at\n"
        f"        the first dispatch.)\n"
    )


def test_every_category_has_at_least_one_non_chief_apparatus(real_data_dir: Path):
    """Every NFDResponse row that a real incident hits must have at least one
    non-chief apparatus in its apparatus columns -- otherwise the simulator
    can't actually assign anyone (chief-only rows are a known-broken case
    still being fixed on the C++ side; xfail those explicitly)."""
    incidents_path = real_data_dir / "incidents_export_apparatus.csv"
    nfd_path = real_data_dir / "NFDResponse.csv"

    with incidents_path.open() as f:
        used_categories = {r["category"] for r in csv.DictReader(f) if r.get("category")}

    # Non-chief apparatus columns = apparatus slice minus the two chief cols.
    non_chief_cols = [
        c for c in EXPECTED_NFDRESPONSE_HEADER[NFDRESPONSE_APPARATUS_SLICE]
        if c not in {"Suppression_Chief", "EMS_Chief"}
    ]

    with nfd_path.open() as f:
        rows = list(csv.DictReader(f))

    chief_only = []
    for row in rows:
        enum = row.get("Enum") or ""
        if enum not in used_categories:
            continue
        counts = [int(row[c]) if row.get(c) not in (None, "") else 0 for c in non_chief_cols]
        if sum(counts) == 0:
            chief_only.append(enum)

    unexpected = sorted(set(chief_only) - CHIEF_ONLY_CATEGORIES_XFAIL)
    if unexpected:
        pytest.fail(
            f"\n\nPREFLIGHT: these NFDResponse categories are hit by real\n"
            f"incidents but have zero non-chief apparatus:\n"
            f"  {unexpected}\n"
            f"  fix: give each row at least one non-chief unit, or add the\n"
            f"       category to CHIEF_ONLY_CATEGORIES_XFAIL in this file with\n"
            f"       a note.\n"
        )

    known = sorted(set(chief_only) & CHIEF_ONLY_CATEGORIES_XFAIL)
    if known:
        pytest.xfail(
            f"chief-only NFDResponse rows tolerated pending C++ fix: {known}. "
            f"Symptom: 'No apparatus requirements for <enum>' when a matching "
            f"incident is dispatched by the old binary. Follow-up: update the "
            f"C++ loader to treat chiefs as dispatchable so these rows work."
        )


# --------------------------------------------------------------------------- #
# Line-ending / hidden-character checks
#
# CSV loaders in the C++ simulator use `std::getline(ss, tok, ',')` which does
# NOT strip a trailing '\r'. On the last field of every row, that leaves the
# token as e.g. "1\r", which then goes into `std::stoi()`; stoi treats the CR
# as an invalid leading character and throws `std::invalid_argument`. This
# crashes every run after someone edits a CSV in Excel or a Windows text
# editor and saves with CRLF line endings.
#
# Failure mode observed: the sim died right after
#   [info] [HistoricalFireModel] Loading apparatus requirements from: NFDResponse.csv
# with
#   terminate called after throwing an instance of 'std::invalid_argument'
#   what():  stoi
# despite every EMS_Chief cell "looking" like a plain integer (`1`, `0`, etc.)
# in a text editor -- the `\r` is invisible.
# --------------------------------------------------------------------------- #

# Every CSV the simulator reads directly by row/column index. If any of these
# is CRLF, the sim crashes on the last field of each row.
_CSVS_THAT_MUST_BE_LF_ONLY = (
    "stations_with_apparatus.csv",
    "NFDResponse.csv",
    "zones.csv",
    "response_time_summary2.csv",
)


def test_csv_files_use_lf_line_endings_only(real_data_dir: Path):
    """No `\\r` bytes allowed in any CSV the C++ simulator parses.

    The last field of every CRLF line becomes `<value>\\r`, and the loader's
    downstream `std::stoi()` throws `invalid_argument` on the trailing CR.
    """
    offenders: list[str] = []
    for name in _CSVS_THAT_MUST_BE_LF_ONLY:
        path = real_data_dir / name
        if not path.is_file():
            # Some deployments legitimately lack response_time_summary2.csv;
            # the "required files" preflight covers presence separately.
            continue
        with path.open("rb") as f:
            data = f.read()
        cr_count = data.count(b"\r")
        if cr_count:
            # Locate the first offending line for the operator to jump to.
            first_cr_offset = data.index(b"\r")
            line_no = data.count(b"\n", 0, first_cr_offset) + 1
            offenders.append(f"{name}: {cr_count} CR byte(s), first at line {line_no}")

    assert not offenders, (
        "\n\nPREFLIGHT: CRLF line endings detected in files the C++ simulator\n"
        "parses. The last field of every CRLF row keeps its trailing '\\r',\n"
        "which then trips std::stoi() with 'invalid_argument'.\n\n"
        "  offenders:\n    " + "\n    ".join(offenders) + "\n\n"
        "  fix (one-liner):  sed -i 's/\\r$//' data/<file>\n"
        "  or:              dos2unix data/<file>\n\n"
        "  root cause: the CSV was edited/exported on Windows (Excel, Notepad,\n"
        "  etc.) and saved with CRLF. Convert to LF and re-run.\n"
    )


def test_apparatus_cells_contain_only_digits_or_empty(real_data_dir: Path):
    """Every apparatus cell in stations_with_apparatus.csv + NFDResponse.csv
    must be empty or a plain integer -- no whitespace, no trailing CR, no
    quoted numbers, no unit strings.

    Empty is fine (loader treats it as zero); anything else feeds a bad
    token into `std::stoi()` and crashes the simulator with
    `std::invalid_argument`.
    """
    def _bad_cells(path: Path, apparatus_slice: slice, key_col_index: int, key_name: str):
        bad: list[str] = []
        with path.open() as f:
            reader = csv.reader(f)
            header = next(reader)
            for row_no, row in enumerate(reader, start=2):
                if len(row) < len(header):
                    row = row + [""] * (len(header) - len(row))
                for col_index, value in enumerate(
                    row[apparatus_slice], start=apparatus_slice.start
                ):
                    if value == "" or (value.lstrip("-").isdigit()):
                        continue
                    bad.append(
                        f"    {path.name}:{row_no} "
                        f"{key_name}={row[key_col_index]!r} "
                        f"col{col_index}({header[col_index]!r}) = {value!r}"
                    )
        return bad

    problems = []
    stations = real_data_dir / "stations_with_apparatus.csv"
    if stations.is_file():
        problems += _bad_cells(stations, STATIONS_APPARATUS_SLICE, 1, "station")
    nfd = real_data_dir / "NFDResponse.csv"
    if nfd.is_file():
        problems += _bad_cells(nfd, NFDRESPONSE_APPARATUS_SLICE, 0, "category")

    assert not problems, (
        "\n\nPREFLIGHT: apparatus cells must be empty or plain integers.\n"
        "The C++ simulator feeds each cell to std::stoi() -- anything with a\n"
        "trailing '\\r', a whitespace, a unit suffix, or a quoted number\n"
        "throws std::invalid_argument and terminates the run.\n\n"
        "  offending cells:\n" + "\n".join(problems) + "\n\n"
        "  fix: edit each cell to be an integer or clear it entirely.\n"
    )
