"""Health, version, and OpenAPI-spec discoverability."""
from __future__ import annotations


def test_health_returns_ok(http):
    """`GET /health` returns 200 with `{"status": "ok"}`. No auth."""
    status, body = http.get("/health")
    assert status == 200, f"HTTP {status} body={body!r}"
    assert isinstance(body, dict), f"body should be JSON dict, got {type(body).__name__}"
    assert body.get("status") == "ok", f"body={body!r}"


def test_version_returns_a_service_string(http):
    """`GET /version` returns 200 with a non-empty string."""
    status, body = http.get("/version")
    assert status == 200, f"HTTP {status} body={body!r}"
    # Some deployments return a plain string, others {"service": "...", "version": "..."}.
    # Accept either as long as it's non-empty.
    if isinstance(body, dict):
        combined = " ".join(str(v) for v in body.values())
    else:
        combined = str(body)
    assert combined.strip(), f"empty /version body={body!r}"


def test_openapi_spec_is_reachable(http):
    """`GET /api/v1/openapi.json` returns a valid OpenAPI 3.x doc."""
    status, body = http.get("/api/v1/openapi.json")
    assert status == 200, f"HTTP {status} body={body!r}"
    assert isinstance(body, dict), f"body={body!r}"
    assert body.get("openapi", "").startswith("3."), (
        f"missing/invalid 'openapi' field: {body.get('openapi')!r}"
    )
    paths = body.get("paths") or {}
    assert paths, "openapi spec has no paths"
    # A handful of endpoints every deployment must expose.
    required = {
        "/health",
        "/auth/portal-login",
        "/api/jobs",
        "/api/stations/roster",
        "/api/incidents/get-incidents",
    }
    missing = required - set(paths.keys())
    assert not missing, f"openapi missing required paths: {sorted(missing)}"
