"""Regression: CRLF line endings in a data/*.csv the simulator parses cause
`std::stoi()` to throw `std::invalid_argument` on the last field of every
row, because the C++ loader's `std::getline(ss, tok, ',')` leaves a trailing
'\\r' attached to that final token.

Observed failure signature (2026-07-20):
    [info] [HistoricalFireModel] Loading apparatus requirements from:
           /app/data/NFDResponse.csv
    terminate called after throwing an instance of 'std::invalid_argument'
      what():  stoi

Cells in the offending file looked like plain integers ('1', '0', ...) but
carried an invisible CR from a Windows/Excel edit that changed the file's
line-endings to CRLF.

This test synthesises both a valid LF-only fixture and a broken CRLF
fixture, and runs the two preflight checks that guard against this class
of bug -- `test_csv_files_use_lf_line_endings_only` and
`test_apparatus_cells_contain_only_digits_or_empty`. The regression is that
BOTH checks must catch the CRLF variant when it's present in any file the
simulator reads by row/column index.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


PREFLIGHT_MODULE = "tests.preflight.test_csv_column_schema"


@pytest.fixture()
def real_data_like_dir(tmp_path: Path) -> Path:
    """Build a minimal but structurally correct data/ tree for the preflight
    tests to operate on. Only the two files whose contents actually differ
    between the good and bad cases are populated; the rest can be absent
    because the preflight tests skip missing optional files."""
    stations_hdr = (
        "StationID,Stations,lat,lon,Nashville Fire Stations,"
        "Engine_ID,Truck,Rescue,Hazard,Squad,FAST,Medic,Brush,Boat,UTV,REACH,"
        "Suppression_Chief,EMS_Chief"
    )
    stations_row = "0,Station 01,36.229,-86.756,User Station 0,1,,1,,1,,,,,,,1,"

    nfd_hdr = (
        "Enum,Category,Description,"
        "Engine_ID,Truck,Rescue,Hazard,Squad,FAST,Medic,Brush,Boat,UTV,REACH,"
        "Suppression_Chief,EMS_Chief"
    )
    nfd_row = "Nine,9,CATEGORY 9 - Level A Medical Calls,1,,,,,,1,,,,,,1"

    (tmp_path / "stations_with_apparatus.csv").write_text(
        stations_hdr + "\n" + stations_row + "\n"
    )
    (tmp_path / "NFDResponse.csv").write_text(nfd_hdr + "\n" + nfd_row + "\n")
    return tmp_path


def test_lf_only_files_pass_preflight(real_data_like_dir: Path):
    """Sanity: the LF-only fixture doesn't false-positive."""
    mod = importlib.import_module(PREFLIGHT_MODULE)
    # No exception -> pass.
    mod.test_csv_files_use_lf_line_endings_only(real_data_like_dir)
    mod.test_apparatus_cells_contain_only_digits_or_empty(real_data_like_dir)


def test_crlf_in_nfdresponse_is_flagged_by_line_endings_preflight(
    real_data_like_dir: Path,
):
    """The line-endings preflight must fail loudly on a CRLF NFDResponse.csv,
    with a message that names the file, the CR count, and the fix command."""
    nfd = real_data_like_dir / "NFDResponse.csv"
    nfd.write_bytes(nfd.read_bytes().replace(b"\n", b"\r\n"))

    mod = importlib.import_module(PREFLIGHT_MODULE)
    with pytest.raises(AssertionError) as excinfo:
        mod.test_csv_files_use_lf_line_endings_only(real_data_like_dir)

    msg = str(excinfo.value)
    assert "NFDResponse.csv" in msg
    assert "CR byte" in msg
    assert "sed" in msg  # fix hint present


def test_crlf_in_stations_is_flagged_by_line_endings_preflight(
    real_data_like_dir: Path,
):
    """Same guarantee for stations_with_apparatus.csv."""
    stations = real_data_like_dir / "stations_with_apparatus.csv"
    stations.write_bytes(stations.read_bytes().replace(b"\n", b"\r\n"))

    mod = importlib.import_module(PREFLIGHT_MODULE)
    with pytest.raises(AssertionError) as excinfo:
        mod.test_csv_files_use_lf_line_endings_only(real_data_like_dir)

    assert "stations_with_apparatus.csv" in str(excinfo.value)


def test_python_csv_reader_masks_crlf_but_line_ending_check_still_catches(
    real_data_like_dir: Path,
):
    """Note for future maintainers: Python's default text-mode file open
    performs universal-newline conversion, so when the numeric-cell preflight
    walks the CSV via `csv.reader(open(path))`, it does NOT see the trailing
    '\\r' that the C++ loader would see. That's exactly why the line-endings
    preflight above is the primary guard for this bug class -- it works at the
    raw byte level. This test pins that behaviour so nobody accidentally
    'improves' the numeric check into a false sense of coverage."""
    nfd = real_data_like_dir / "NFDResponse.csv"
    nfd.write_bytes(nfd.read_bytes().replace(b"\n", b"\r\n"))

    mod = importlib.import_module(PREFLIGHT_MODULE)
    # The line-endings check DOES catch it (byte level).
    with pytest.raises(AssertionError):
        mod.test_csv_files_use_lf_line_endings_only(real_data_like_dir)
    # The numeric check does NOT (Python strips the CR). If somebody rewrites
    # the numeric check to open bytes/newline='', this assertion should be
    # updated to expect an AssertionError instead.
    mod.test_apparatus_cells_contain_only_digits_or_empty(real_data_like_dir)


def test_whitespace_and_unit_strings_flagged_by_numeric_apparatus_check(
    real_data_like_dir: Path,
):
    """Other non-integer contents (' 1', '1B', quoted) also fail the preflight."""
    stations_hdr = (
        "StationID,Stations,lat,lon,Nashville Fire Stations,"
        "Engine_ID,Truck,Rescue,Hazard,Squad,FAST,Medic,Brush,Boat,UTV,REACH,"
        "Suppression_Chief,EMS_Chief"
    )
    # Engine_ID column has a trailing space, Suppression_Chief has a unit suffix.
    (real_data_like_dir / "stations_with_apparatus.csv").write_text(
        stations_hdr + "\n0,Station 01,36.2,-86.7,User Station 0,1 ,,,,,,,,,,,1B,\n"
    )

    mod = importlib.import_module(PREFLIGHT_MODULE)
    with pytest.raises(AssertionError) as excinfo:
        mod.test_apparatus_cells_contain_only_digits_or_empty(real_data_like_dir)

    msg = str(excinfo.value)
    assert "'1 '" in msg
    assert "'1B'" in msg
