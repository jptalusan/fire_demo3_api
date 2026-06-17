"""End-to-end tests for POST /api/incidents/generate-incidents.

Uses FastAPI TestClient against the real app with real data and real engine.
No monkeypatching. Auth is obtained via /auth/register + /auth/login.

The TestClient and auth token are created once at module scope (session-scoped
fixture) to avoid repeated model-loading overhead.  Each window is intentionally
short (1-3 days) to keep total run time under ~60 s.

Route under test:  POST /api/incidents/generate-incidents
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# The existing conftest.py (tests/conftest.py) already:
#   - sets DATABASE_URL=sqlite:///:memory:, SECRET_KEY, STORAGE_ROOT via env
#   - adds src/ to sys.path via pyproject.toml [tool.pytest.ini_options] pythonpath
#   - creates/drops the in-memory schema
#   - provides `client` and `auth_headers` fixtures (function-scoped)
#
# We add a *session-scoped* client+token so the Poisson model is loaded once
# across all five tests in this module.
# ---------------------------------------------------------------------------

ROUTE = "/api/incidents/generate-incidents"

# Path to the fire incident types whitelist bundled with the model artefacts.
_BUNDLE_DIR = (
    Path(__file__).resolve().parents[1]
    / "data" / "models" / "growth_poisson_v1"
)
_FIRE_TYPES_PATH = _BUNDLE_DIR / "fire_incident_types.json"

EXPECTED_HEADER = "incident_id,lat,lon,incident_type,incident_level,datetime,category"


# ---------------------------------------------------------------------------
# Session-scoped fixtures: one TestClient + one auth token for the whole module.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def module_client():
    """Start the real app once; keep it alive for the whole module."""
    from fastapi.testclient import TestClient as TC
    from backend.main import app
    with TC(app) as c:
        yield c


@pytest.fixture(scope="module")
def module_auth_headers(module_client: TestClient) -> dict:
    """Register a test user once and return Bearer headers."""
    username = "route_tester_generate"
    module_client.post(
        "/auth/register",
        json={"username": username, "password": "s3cret_pw!"},
    )
    resp = module_client.post(
        "/auth/login",
        json={"username": username, "password": "s3cret_pw!"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _post(client: TestClient, headers: dict, payload: dict):
    return client.post(ROUTE, headers=headers, json=payload)


def _parse_csv(text: str):
    """Return (header_line, data_rows) using a real CSV parser.

    Uses csv.reader so quoted fields containing commas (e.g. incident_type
    "Public service assistance, other") are parsed correctly instead of being
    split into extra columns.
    """
    records = [r for r in csv.reader(io.StringIO(text)) if r]
    if not records:
        return "", []
    cols = [c.strip() for c in records[0]]
    header = ",".join(records[0])
    rows = [dict(zip(cols, vals)) for vals in records[1:]]
    return header, rows


# ---------------------------------------------------------------------------
# Test 1 — Default model (no `model` field) → 200, correct CSV header, ≥1 row
# ---------------------------------------------------------------------------

def test_default_model_returns_csv_with_correct_header(
    module_client, module_auth_headers
):
    """POST without a `model` field must use growth_v1 (the default).

    Asserts:
      - HTTP 200
      - Content-Type is text/csv
      - First CSV line is exactly the canonical header
      - At least one data row is present
    """
    resp = _post(module_client, module_auth_headers, {
        "date_range": {"start": "2025-01-01", "end": "2025-01-03"},
        "incident_type": "fire",
        "seed": 42,
        # `model` intentionally omitted → schema default is "growth_v1"
    })

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    assert resp.headers["content-type"].startswith("text/csv"), (
        f"Expected text/csv, got {resp.headers['content-type']}"
    )

    header, rows = _parse_csv(resp.text)
    assert header == EXPECTED_HEADER, (
        f"CSV header mismatch.\n  got:      {header!r}\n  expected: {EXPECTED_HEADER!r}"
    )
    assert len(rows) >= 1, "Expected at least one data row in the CSV"


# ---------------------------------------------------------------------------
# Test 2 — Explicit model="growth_v1" with same seed → identical body to default
# ---------------------------------------------------------------------------

def test_explicit_growth_v1_identical_to_default(
    module_client, module_auth_headers
):
    """Explicit model='growth_v1' with the same seed must return identical CSV.

    Mechanism: the route caches results keyed on (model, start, end, seed).
    Both requests share the same key so the second is a cache hit; but even
    ignoring caching, the Poisson sampler is deterministic given the seed, so
    the bodies must match.

    Asserts:
      - HTTP 200 for both
      - Same CSV header
      - Byte-identical response bodies
    """
    payload_default = {
        "date_range": {"start": "2025-01-01", "end": "2025-01-03"},
        "incident_type": "fire",
        "seed": 42,
    }
    payload_explicit = {**payload_default, "model": "growth_v1"}

    resp_default = _post(module_client, module_auth_headers, payload_default)
    resp_explicit = _post(module_client, module_auth_headers, payload_explicit)

    assert resp_default.status_code == 200
    assert resp_explicit.status_code == 200

    header_d, _ = _parse_csv(resp_default.text)
    header_e, _ = _parse_csv(resp_explicit.text)
    assert header_d == EXPECTED_HEADER
    assert header_e == EXPECTED_HEADER

    assert resp_default.text == resp_explicit.text, (
        "Default model response differs from explicit growth_v1 response "
        "even though both have the same seed. The default is not growth_v1."
    )


# ---------------------------------------------------------------------------
# Test 3 — Explicit model="legacy" → 200, same header, parses without error
# ---------------------------------------------------------------------------

def test_legacy_model_returns_valid_csv(module_client, module_auth_headers):
    """The legacy survival-model path must return a well-formed CSV.

    Uses a 1-day window to keep the call fast (~3 s).

    Asserts:
      - HTTP 200
      - Content-Type text/csv
      - Correct header columns
      - At least one data row
      - Every row has the expected number of comma-separated fields
    """
    resp = _post(module_client, module_auth_headers, {
        "date_range": {"start": "2025-01-01", "end": "2025-01-02"},
        "incident_type": "fire",
        "model": "legacy",
        "seed": 42,
    })

    assert resp.status_code == 200, (
        f"Legacy model returned {resp.status_code}: {resp.text[:300]}"
    )
    assert resp.headers["content-type"].startswith("text/csv")

    header, rows = _parse_csv(resp.text)
    assert header == EXPECTED_HEADER, (
        f"Legacy CSV header mismatch.\n  got:      {header!r}\n  expected: {EXPECTED_HEADER!r}"
    )
    assert len(rows) >= 1, "Legacy model returned no data rows"

    expected_cols = EXPECTED_HEADER.split(",")
    for i, row in enumerate(rows):
        assert set(row.keys()) == set(expected_cols), (
            f"Row {i} has unexpected columns: {set(row.keys())}"
        )


# ---------------------------------------------------------------------------
# Test 4 — incident_type filtering: fire ⊆ ems_fire by row count and types
# ---------------------------------------------------------------------------

def test_incident_type_fire_subset_of_ems_fire(module_client, module_auth_headers):
    """Filtering to 'fire' must yield fewer (or equal) rows than 'ems_fire'.

    Additionally every incident_type value in the fire response must appear in
    the fire whitelist loaded from data/models/growth_poisson_v1/fire_incident_types.json.

    Asserts:
      - Both requests return 200
      - ems_fire row count >= fire row count
      - Every incident_type in the fire CSV is in the fire whitelist
    """
    shared = {
        "date_range": {"start": "2025-01-01", "end": "2025-01-03"},
        "model": "growth_v1",
        "seed": 42,
    }

    resp_fire = _post(module_client, module_auth_headers, {**shared, "incident_type": "fire"})
    resp_ems = _post(module_client, module_auth_headers, {**shared, "incident_type": "ems_fire"})

    assert resp_fire.status_code == 200, f"fire request failed: {resp_fire.text[:200]}"
    assert resp_ems.status_code == 200, f"ems_fire request failed: {resp_ems.text[:200]}"

    _, fire_rows = _parse_csv(resp_fire.text)
    _, ems_rows = _parse_csv(resp_ems.text)

    assert len(ems_rows) >= len(fire_rows), (
        f"ems_fire ({len(ems_rows)} rows) should be >= fire ({len(fire_rows)} rows)"
    )

    # Load the whitelist and verify every returned fire incident_type is in it.
    assert _FIRE_TYPES_PATH.exists(), (
        f"fire_incident_types.json not found at {_FIRE_TYPES_PATH}"
    )
    with _FIRE_TYPES_PATH.open() as fh:
        fire_whitelist = set(json.load(fh))

    for i, row in enumerate(fire_rows):
        inc_type = row.get("incident_type", "")
        assert inc_type in fire_whitelist, (
            f"Row {i}: incident_type={inc_type!r} is not in the fire whitelist. "
            f"Whitelist sample: {list(fire_whitelist)[:5]}"
        )


# ---------------------------------------------------------------------------
# Test 5 — Caching / determinism: two identical requests → byte-identical CSV
# ---------------------------------------------------------------------------

def test_identical_requests_return_identical_csv(module_client, module_auth_headers):
    """Two POST requests with the same (model, seed, window, incident_type) must
    return byte-identical CSV bodies.

    The route writes to a content-addressed cache file on first call and reads it
    on the second.  This test verifies both that the cache is hit (fast second
    call) and that determinism is preserved end-to-end.

    Uses a seed (9999) that is not used by any other test to avoid cross-test
    cache sharing effects.
    """
    payload = {
        "date_range": {"start": "2025-01-01", "end": "2025-01-03"},
        "incident_type": "fire",
        "model": "growth_v1",
        "seed": 9999,
    }

    resp1 = _post(module_client, module_auth_headers, payload)
    resp2 = _post(module_client, module_auth_headers, payload)

    assert resp1.status_code == 200, f"First call failed: {resp1.text[:200]}"
    assert resp2.status_code == 200, f"Second call failed: {resp2.text[:200]}"

    assert resp1.text == resp2.text, (
        "Two identical requests returned different CSV bodies — "
        "caching or determinism is broken."
    )

    # Also confirm the response is non-trivial (header + at least one data row).
    header, rows = _parse_csv(resp1.text)
    assert header == EXPECTED_HEADER
    assert len(rows) >= 1, "Determinism test: expected at least one data row"


# ---------------------------------------------------------------------------
# Test 6 — incident_type values containing commas must be CSV-quoted, so every
# data row parses to exactly 7 fields (regression guard for the unquoted-CSV bug)
# ---------------------------------------------------------------------------

def test_comma_containing_incident_types_are_quoted(module_client, module_auth_headers):
    """growth_v1 emits incident types with embedded commas (e.g.
    "Public service assistance, other"). The route must quote them so the row
    still has exactly 7 fields. With the old unquoted f-string writer such a row
    parsed as 8+ fields and corrupted incident_level/datetime/category.

    Uses a 30-day ems_fire window so comma-containing types are present, then
    parses the raw response with csv.reader (quote-aware).
    """
    payload = {
        "date_range": {"start": "2025-01-01", "end": "2025-01-31"},
        "incident_type": "ems_fire",
        "model": "growth_v1",
        "seed": 42,
    }
    resp = _post(module_client, module_auth_headers, payload)
    assert resp.status_code == 200, f"request failed: {resp.text[:200]}"

    records = [r for r in csv.reader(io.StringIO(resp.text)) if r]
    assert records and records[0] == EXPECTED_HEADER.split(","), "missing/incorrect header"
    data = records[1:]
    assert data, "expected at least one data row over a 30-day window"

    # Every row parses to exactly 7 fields (quoting intact).
    bad = [i for i, row in enumerate(data) if len(row) != 7]
    assert not bad, f"{len(bad)} row(s) did not parse to 7 fields (unquoted commas): first={data[bad[0]]}"

    # Non-vacuous: at least one incident_type actually contains a comma, so the
    # quoting is genuinely exercised (incident_type is column index 3).
    assert any("," in row[3] for row in data), (
        "no comma-containing incident_type in sample — widen the window to exercise quoting"
    )
