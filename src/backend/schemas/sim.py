"""Simulation job schemas (queued via /api/jobs).

A job wraps a simulation request. `kind` selects what runs; `payload` carries the
simulation configuration. The payload is intentionally a free-form object (the
worker forwards it to the simulation engine), but its expected shape is fully
documented by the models below and surfaced as request examples in /docs.

Two payload shapes:

* kind="run-simulation"  -> payload is a single SimConfig.
* kind="run-comparison"  -> payload is {"baseline": SimConfig, "newConfig": SimConfig}.
"""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


JobKind = Literal["run-simulation", "run-comparison"]


# --------------------------------------------------------------------------- #
# Documentation models for the simulation config (the contents of `payload`).
# These describe the shape; they are not enforced on submit (payload stays a
# dict so the engine can evolve), but they render in /docs as reference schemas.
# --------------------------------------------------------------------------- #

class ApparatusSpec(BaseModel):
    """One apparatus entry on a station."""
    type: Literal[
        "Engine", "Truck", "Rescue", "Hazard", "Squad", "FAST",
        "Medic", "Brush", "Boat", "UTV", "REACH", "Chief",
    ] = Field(description="Apparatus type. Fire incidents need an Engine; EMS need a Medic.")
    count: int = Field(ge=0, description="How many of this apparatus at the station.")


class StationSpec(BaseModel):
    """A station in a custom layout (used when station_data='custom_stations')."""
    id: str = Field(description="Station id, e.g. '0'.")
    name: str = Field(description="Display name, e.g. 'Station 01'.")
    lat: float = Field(description="Latitude.")
    lon: float = Field(description="Longitude.")
    apparatus: list[ApparatusSpec] = Field(default_factory=list, description="Apparatus at this station.")


class SimModels(BaseModel):
    """Model selections for a run."""
    incident: Literal["historical_incidents", "synthetic_incidents"] = Field(
        description="historical_incidents replays real incidents in the date range; "
        "synthetic_incidents generates them."
    )
    travelTime: Literal["OSRM", "ARCGIS", "INTERPOLATED"] = Field(
        default="OSRM", description="Travel-time model (ARCGIS is treated as OSRM)."
    )
    serviceTime: Literal["ml_based", "constant", "empirical_servicetimes"] = Field(
        default="ml_based", description="On-scene service-time model."
    )


class DateRange(BaseModel):
    """Inclusive date window. Date-only (YYYY-MM-DD) or full ISO timestamps both work."""
    start_date: str = Field(description="e.g. '2024-06-01' or '2024-06-01T05:00:00.000Z'.")
    end_date: str = Field(description="e.g. '2024-06-03'.")


class SimConfig(BaseModel):
    """The simulation configuration — the `payload` for a run-simulation job,
    and each side of a run-comparison job."""
    models: SimModels
    date_range: DateRange
    incident_type: Literal["fire", "ems_fire"] = Field(description="Incident set to simulate.")
    dispatch_policy: Literal["firebeats", "nearest"] = Field(
        default="nearest", description="Unit selection policy."
    )
    station_data: Literal["default_stations", "custom_stations", "optimized_stations"] = Field(
        default="default_stations", description="Which station layout to use."
    )
    stations: Optional[list[StationSpec]] = Field(
        default=None,
        description="Custom station layout (positions + apparatus). Provide when "
        "station_data='custom_stations'. Omit to use the default roster.",
    )
    disable_ems: bool = Field(
        default=False, description="True = fire-only; false = include EMS/medic operations."
    )


class ComparisonPayload(BaseModel):
    """The `payload` for a run-comparison job: baseline vs new configuration."""
    baseline: SimConfig = Field(description="Reference config (typically default stations).")
    newConfig: SimConfig = Field(description="Modified config to compare against baseline.")


# --------------------------------------------------------------------------- #
# Request / response models actually used by the routes.
# --------------------------------------------------------------------------- #

_EXAMPLE_RUN_SIMULATION = {
    "summary": "Run a single simulation",
    "value": {
        "kind": "run-simulation",
        "payload": {
            "models": {"incident": "historical_incidents", "travelTime": "OSRM", "serviceTime": "ml_based"},
            "date_range": {"start_date": "2024-06-01", "end_date": "2024-06-03"},
            "incident_type": "ems_fire",
            "dispatch_policy": "nearest",
            "station_data": "default_stations",
            "disable_ems": False,
        },
        "priority": 0,
    },
}

_EXAMPLE_RUN_COMPARISON = {
    "summary": "Compare default vs a custom station layout",
    "value": {
        "kind": "run-comparison",
        "payload": {
            "baseline": {
                "models": {"incident": "historical_incidents", "travelTime": "OSRM", "serviceTime": "ml_based"},
                "date_range": {"start_date": "2024-06-01", "end_date": "2024-06-03"},
                "incident_type": "ems_fire",
                "dispatch_policy": "nearest",
                "station_data": "default_stations",
                "disable_ems": False,
            },
            "newConfig": {
                "models": {"incident": "historical_incidents", "travelTime": "OSRM", "serviceTime": "ml_based"},
                "date_range": {"start_date": "2024-06-01", "end_date": "2024-06-03"},
                "incident_type": "ems_fire",
                "dispatch_policy": "nearest",
                "station_data": "custom_stations",
                "disable_ems": False,
                "stations": [
                    {
                        "id": "0",
                        "name": "Station 01",
                        "lat": 36.2293898,
                        "lon": -86.75674762,
                        "apparatus": [{"type": "Engine", "count": 1}, {"type": "Medic", "count": 1}],
                    }
                ],
            },
        },
        "priority": 0,
    },
}


class JobSubmitRequest(BaseModel):
    """Submit a simulation job to the queue.

    - kind="run-simulation": `payload` is a SimConfig.
    - kind="run-comparison": `payload` is {baseline: SimConfig, newConfig: SimConfig}.
    """
    kind: JobKind = Field(default="run-simulation", description="What to run.")
    payload: dict[str, Any] = Field(
        description="Simulation config. SimConfig for run-simulation; "
        "{baseline, newConfig} for run-comparison. See examples."
    )
    priority: int = Field(default=0, description="Higher runs first in the queue.")

    model_config = {
        "json_schema_extra": {
            "examples": [_EXAMPLE_RUN_SIMULATION["value"], _EXAMPLE_RUN_COMPARISON["value"]]
        }
    }


class JobResponse(BaseModel):
    """A job row. `result` is null until status='done'; `error` is set on 'failed'."""
    id: int = Field(description="Job id.")
    user_id: Optional[int] = Field(description="Owner user id.")
    kind: str = Field(description="run-simulation | run-comparison.")
    status: str = Field(description="pending | running | done | failed.")
    payload: dict[str, Any] | None = Field(description="The submitted config (echoed).")
    result: dict[str, Any] | None = Field(
        description="Simulation output once done. Shape depends on kind "
        "(see SimulationResult / ComparisonResult in the reference)."
    )
    error: Optional[str] = Field(description="Failure reason when status='failed'.")
    attempts: int = Field(description="How many times the worker has attempted this job.")
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = Field(
        default=None, description="Wall-clock run time (finished - started); null until terminal."
    )
    queue_position: Optional[int] = Field(
        default=None, description="1-based position in the global pending queue; null unless pending."
    )

    class Config:
        from_attributes = True


class JobProgress(BaseModel):
    """Live progress for a running job, derived from the simulator log."""
    job_id: int
    status: str
    processed: int = Field(description="Incidents reported so far (summed across legs).")
    total: int = Field(description="Total incidents expected (summed across legs).")
    percent: float = Field(description="processed/total * 100.")
    legs: dict[str, Any] = Field(
        description="Per-leg {processed,total}: {'simulation':…} or {'baseline':…, 'newConfig':…}."
    )


class QueueStatus(BaseModel):
    """Snapshot of the queue across all users plus this user's standing."""
    pending_total: int = Field(description="Pending jobs across everyone.")
    running_total: int = Field(description="Running jobs across everyone.")
    your_pending: int = Field(description="Your pending jobs.")
    your_running: int = Field(description="Your running jobs.")
    your_next_position: Optional[int] = Field(
        default=None, description="1-based position of your earliest pending job; null if none."
    )
