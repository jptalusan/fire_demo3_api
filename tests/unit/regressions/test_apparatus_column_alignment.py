"""Regression: apparatus column names must agree across every place that
names them.

Fixed in commit 4efcfff ("Include Suppression_Chief + EMS_Chief in
/api/stations/roster output"): a bare 'Chief' -> Suppression_Chief/EMS_Chief
schema split (c76b35c) landed everywhere except one lookup table
(backend/routes/stations.py's CSV<->payload map), so the roster API silently
dropped both chief counts. This test pins that the five places that name
apparatus columns -- simulation.py's writer, the stations route, the
ApparatusSpec schema, and both apparatus CSV headers -- never drift apart
again.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import get_args

from backend.routes.stations import APPARATUS_COLUMNS
from backend.schemas.sim import ApparatusSpec

REPO_ROOT = Path(__file__).resolve().parents[3]
SIM_SRC = REPO_ROOT / "src" / "engine" / "simulation.py"
STATIONS_CSV = REPO_ROOT / "data" / "stations_with_apparatus.csv"
NFD_CSV = REPO_ROOT / "data" / "NFDResponse.csv"

# Payload -> CSV-column rename convention shared by create_stations_csv_from_payload
# and backend.routes.stations._CSV_TO_TYPE.
PAYLOAD_TO_COLUMN = {"Engine": "Engine_ID"}


def _csv_header(path: Path) -> list[str]:
    with open(path) as f:
        return f.readline().rstrip("\n").split(",")


def _extract_apparatus_types_list() -> list[str]:
    """Pull the literal `apparatus_types = [...]` assignment out of
    create_stations_csv_from_payload via AST, without importing/executing
    engine.simulation (which pulls in pandas etc. at import time anyway, but
    this keeps the extraction independent of import side effects)."""
    tree = ast.parse(SIM_SRC.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "create_stations_csv_from_payload":
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "apparatus_types" for t in stmt.targets
                ):
                    return ast.literal_eval(stmt.value)
    raise AssertionError(
        "apparatus_types assignment not found in create_stations_csv_from_payload "
        f"({SIM_SRC})"
    )


APPARATUS_TYPES_IN_SIMULATION = _extract_apparatus_types_list()


def test_both_csv_headers_have_split_chief_columns_not_bare_chief():
    for path in (STATIONS_CSV, NFD_CSV):
        header = _csv_header(path)
        assert "Suppression_Chief" in header, f"{path.name} is missing Suppression_Chief"
        assert "EMS_Chief" in header, f"{path.name} is missing EMS_Chief"
        assert "Chief" not in header, (
            f"{path.name} still has a bare 'Chief' column (pre-split schema); "
            "it must be Suppression_Chief / EMS_Chief (see 4efcfff)"
        )


def test_simulation_apparatus_types_matches_stations_csv_header():
    stations_apparatus_cols = _csv_header(STATIONS_CSV)[5:]  # after the 5 fixed columns
    assert set(APPARATUS_TYPES_IN_SIMULATION) == set(stations_apparatus_cols), (
        f"create_stations_csv_from_payload's apparatus_types "
        f"{sorted(APPARATUS_TYPES_IN_SIMULATION)} != stations_with_apparatus.csv columns "
        f"{sorted(stations_apparatus_cols)} (see 4efcfff)"
    )


def test_simulation_apparatus_types_matches_nfd_response_csv_header():
    nfd_apparatus_cols = _csv_header(NFD_CSV)[3:]  # after Enum, Category, Description
    assert set(APPARATUS_TYPES_IN_SIMULATION) == set(nfd_apparatus_cols), (
        "create_stations_csv_from_payload's apparatus_types must match NFDResponse.csv's "
        "apparatus columns exactly, or the C++ simulator's column-index lookup silently "
        "reads zeros for the misnamed column (the root cause behind 4efcfff)."
    )


def test_stations_route_apparatus_columns_matches_csv_header():
    stations_apparatus_cols = _csv_header(STATIONS_CSV)[5:]
    assert set(APPARATUS_COLUMNS) == set(stations_apparatus_cols), (
        f"backend.routes.stations.APPARATUS_COLUMNS {sorted(APPARATUS_COLUMNS)} != "
        f"stations_with_apparatus.csv columns {sorted(stations_apparatus_cols)} (see 4efcfff)"
    )


def test_stations_route_apparatus_columns_matches_simulation_apparatus_types():
    assert set(APPARATUS_COLUMNS) == set(APPARATUS_TYPES_IN_SIMULATION), (
        "backend/routes/stations.py::APPARATUS_COLUMNS drifted from "
        "engine/simulation.py::create_stations_csv_from_payload's apparatus_types "
        "(this exact drift caused the 4efcfff bug)."
    )


def test_apparatus_spec_literal_members_map_onto_known_columns():
    """Every Literal member of ApparatusSpec.type must resolve (via the
    'Engine' -> 'Engine_ID' rename, identity otherwise) to a real apparatus
    column shared by the CSV headers and the writer."""
    literal_members = get_args(ApparatusSpec.model_fields["type"].annotation)
    assert literal_members, "could not read ApparatusSpec.type Literal members"

    known_columns = set(APPARATUS_TYPES_IN_SIMULATION)
    for member in literal_members:
        col = PAYLOAD_TO_COLUMN.get(member, member)
        assert col in known_columns, (
            f"ApparatusSpec.type member {member!r} maps to column {col!r}, which is not "
            f"a real apparatus column ({sorted(known_columns)})"
        )
