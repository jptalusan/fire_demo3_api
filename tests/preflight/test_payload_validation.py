"""Preflight: pydantic payload validation for simulation jobs.

Bug classes this test prevents:
- (Incident 5) Frontend sending `{"type":"Chief"}` after the Suppression/EMS
  split -> silently dropped by the writer (Chief is no longer in the
  ApparatusSpec literal). We XFAIL that test here with a follow-up note
  because JobSubmitRequest.payload is currently `dict[str, Any]` and
  therefore doesn't enforce ApparatusSpec at all.
- Malformed incident_type / dispatch_policy / missing date_range.

Every assertion message names the offending field and the expected values.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.schemas.sim import (
    ApparatusSpec,
    ComparisonPayload,
    JobSubmitRequest,
    SimConfig,
)


# --------------------------------------------------------------------------- #
# Good payloads
# --------------------------------------------------------------------------- #

MINIMAL_SIMCONFIG = {
    "models": {"incident": "historical_incidents"},
    "date_range": {"start_date": "2024-06-01", "end_date": "2024-06-03"},
    "incident_type": "fire",
}


ALL_APPARATUS_TYPES = [
    "Engine", "Truck", "Rescue", "Hazard", "Squad", "FAST", "Medic",
    "Brush", "Boat", "UTV", "REACH", "Suppression_Chief", "EMS_Chief",
]


def _full_custom_stations_payload() -> dict:
    apparatus = [{"type": t, "count": 1} for t in ALL_APPARATUS_TYPES]
    return {
        **MINIMAL_SIMCONFIG,
        "station_data": "custom_stations",
        "stations": [{
            "id": "0", "name": "Station 01", "lat": 36.22, "lon": -86.75,
            "apparatus": apparatus,
        }],
    }


def test_minimal_simconfig_validates():
    cfg = SimConfig(**MINIMAL_SIMCONFIG)
    # Defaults, if the fields exist in the schema, must match schema doc.
    assert cfg.incident_type == "fire"
    assert cfg.dispatch_policy in {"nearest", "firebeats"}
    assert cfg.station_data == "default_stations"


def test_full_custom_stations_with_every_apparatus_type_validates():
    """After the Chief split, both Suppression_Chief and EMS_Chief must be
    valid apparatus types side-by-side (Incident 5's regression surface)."""
    cfg = SimConfig(**_full_custom_stations_payload())
    types = {a.type for a in cfg.stations[0].apparatus}
    assert "Suppression_Chief" in types
    assert "EMS_Chief" in types
    assert types == set(ALL_APPARATUS_TYPES), (
        f"ApparatusSpec.type literal missing values: {set(ALL_APPARATUS_TYPES) - types}"
    )


def test_comparison_payload_validates():
    payload = {"baseline": MINIMAL_SIMCONFIG, "newConfig": _full_custom_stations_payload()}
    ComparisonPayload(**payload)


# --------------------------------------------------------------------------- #
# Bad payloads that MUST be rejected today
# --------------------------------------------------------------------------- #

def test_bad_incident_type_is_rejected():
    with pytest.raises(ValidationError) as exc:
        SimConfig(**{**MINIMAL_SIMCONFIG, "incident_type": "not-a-type"})
    msg = str(exc.value)
    assert "incident_type" in msg, (
        f"Rejection did not mention incident_type; got:\n{msg}\n"
        f"Expected values: 'fire' | 'ems_fire'."
    )


def test_bad_dispatch_policy_is_rejected():
    with pytest.raises(ValidationError) as exc:
        SimConfig(**{**MINIMAL_SIMCONFIG, "dispatch_policy": "roundrobin"})
    msg = str(exc.value)
    assert "dispatch_policy" in msg, (
        f"Rejection did not mention dispatch_policy; got:\n{msg}\n"
        f"Expected values: 'firebeats' | 'nearest'."
    )


def test_missing_date_range_is_rejected():
    bad = {k: v for k, v in MINIMAL_SIMCONFIG.items() if k != "date_range"}
    with pytest.raises(ValidationError) as exc:
        SimConfig(**bad)
    assert "date_range" in str(exc.value), (
        f"Rejection did not mention date_range; got:\n{exc.value}"
    )


def test_bad_apparatus_type_is_rejected_by_apparatus_spec():
    """The ApparatusSpec literal is the authoritative gate on apparatus
    types. This is what SHOULD catch a frontend still sending Chief."""
    with pytest.raises(ValidationError) as exc:
        ApparatusSpec(type="Chief", count=1)
    assert "Chief" in str(exc.value) or "type" in str(exc.value), (
        f"Rejection did not mention the bad apparatus type; got:\n{exc.value}"
    )


# --------------------------------------------------------------------------- #
# XFAILs -- currently accepted but shouldn't be
# --------------------------------------------------------------------------- #

@pytest.mark.xfail(
    reason=(
        "JobSubmitRequest.payload is dict[str, Any] and does not run "
        "SimConfig validation. Frontend still sending {'type':'Chief', "
        "'count':1} after the Suppression/EMS split is silently accepted "
        "by the queue submit path; it fails downstream in the C++ loader "
        "or (worse) as a zero-apparatus dispatch. Follow-up: swap "
        "payload's type for a discriminated union of (SimConfig | "
        "ComparisonPayload) keyed on `kind`."
    ),
    strict=True,
)
def test_legacy_chief_apparatus_is_rejected_at_job_submit():
    bad_payload = {
        **MINIMAL_SIMCONFIG,
        "station_data": "custom_stations",
        "stations": [{
            "id": "0", "name": "S", "lat": 36.0, "lon": -86.0,
            "apparatus": [{"type": "Chief", "count": 1}],
        }],
    }
    with pytest.raises(ValidationError):
        JobSubmitRequest(kind="run-simulation", payload=bad_payload)


@pytest.mark.xfail(
    reason=(
        "SimConfig.date_range currently accepts start_date > end_date "
        "(both are strings; no cross-field validator). Runs through the "
        "engine and produces an empty incidents CSV, which then errors "
        "with 'No incidents found in date range' -- confusing when the "
        "real problem is the range being backwards. Follow-up: add a "
        "@model_validator to DateRange that parses + compares."
    ),
    strict=True,
)
def test_reversed_date_range_is_rejected():
    with pytest.raises(ValidationError):
        SimConfig(**{
            **MINIMAL_SIMCONFIG,
            "date_range": {"start_date": "2024-06-10", "end_date": "2024-06-01"},
        })
