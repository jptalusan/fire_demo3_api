"""Stations endpoints. Roster asserts the chief split lands correctly."""
from __future__ import annotations


def test_get_stations_lists_csv_filenames(auth_http):
    status, body = auth_http.get("/api/stations/get-stations")
    assert status == 200, f"HTTP {status} body={body!r}"
    assert isinstance(body, dict), body
    assert isinstance(body.get("stations"), list), body
    assert all(isinstance(f, str) for f in body["stations"]), body
    assert any(f.startswith("stations") and f.endswith(".csv") for f in body["stations"]), body


def test_get_shapes_lists_geojson_filenames(auth_http):
    status, body = auth_http.get("/api/stations/get-shapes")
    assert status == 200, f"HTTP {status} body={body!r}"
    assert isinstance(body, dict), body
    assert isinstance(body.get("shapes"), list), body
    assert any(f.endswith(".geojson") for f in body["shapes"]), body


def test_roster_returns_expected_shape(auth_http):
    status, body = auth_http.get("/api/stations/roster")
    assert status == 200, f"HTTP {status} body={body!r}"
    assert isinstance(body, dict), body
    for field in ("file", "count", "stations"):
        assert field in body, f"missing {field}: {body!r}"
    assert body["count"] == len(body["stations"]), body
    assert body["count"] > 0, "empty roster"

    # Per-station schema
    for s in body["stations"]:
        for k in ("id", "name", "lat", "lon", "apparatus"):
            assert k in s, f"station missing {k}: {s!r}"
        assert isinstance(s["apparatus"], list), f"station apparatus not list: {s!r}"
        for a in s["apparatus"]:
            assert "type" in a and "count" in a, f"apparatus missing fields: {a!r}"
            assert isinstance(a["count"], int) and a["count"] > 0, (
                f"apparatus count non-positive: {a!r} in station {s['name']}"
            )


def test_roster_chief_split_is_present(auth_http):
    """Every station apparatus list, aggregated, must contain
    Suppression_Chief and/or EMS_Chief entries — never the legacy 'Chief'
    type — otherwise the CSV columns aren't being read correctly."""
    _, body = auth_http.get("/api/stations/roster")
    seen_types: set[str] = set()
    for s in body["stations"]:
        seen_types.update(a["type"] for a in s["apparatus"])
    assert "Chief" not in seen_types, (
        f"legacy 'Chief' apparatus type in roster response — the endpoint "
        f"should split into Suppression_Chief + EMS_Chief. types={sorted(seen_types)}"
    )
    assert seen_types & {"Suppression_Chief", "EMS_Chief"}, (
        f"neither Suppression_Chief nor EMS_Chief present in roster — the "
        f"CSV columns may be empty or the endpoint may be reading them wrong. "
        f"types={sorted(seen_types)}"
    )


def test_roster_path_traversal_is_rejected(auth_http):
    """`?file=../etc/passwd` must not escape data/."""
    status, body = auth_http.get("/api/stations/roster?file=../etc/passwd")
    assert status == 400, f"expected 400 for path traversal, got {status} body={body!r}"
    assert isinstance(body, dict) and "detail" in body, body


def test_roster_unknown_file_returns_404(auth_http):
    status, body = auth_http.get("/api/stations/roster?file=stations_does_not_exist.csv")
    assert status == 404, f"expected 404, got {status} body={body!r}"
    assert isinstance(body, dict) and "detail" in body, body
