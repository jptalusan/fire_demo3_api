from __future__ import annotations

from typing import Dict, Literal, Union

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    error: str

    model_config = ConfigDict(extra="allow")


# ----------------------------
# Request Models
# ----------------------------


class DateRangeStartEnd(BaseModel):
    """Date range used by the incidents endpoints.

    Supports multiple client key styles:
    - start/end (used by /get-incidents filters)
    - start_date/end_date
    - startDate/endDate
    """

    start: str = Field(validation_alias=AliasChoices("start", "start_date", "startDate"))
    end: str = Field(validation_alias=AliasChoices("end", "end_date", "endDate"))

    model_config = ConfigDict(populate_by_name=True)


class GetIncidentsFilters(BaseModel):
    date_range: DateRangeStartEnd = Field(alias="date_range")
    incident_type: Literal["fire", "ems_fire"]

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class GetIncidentsRequest(BaseModel):
    model_id: Literal["historical_incidents"]
    filters: GetIncidentsFilters

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class GenerateIncidentsRequest(BaseModel):
    date_range: DateRangeStartEnd
    incident_type: Literal["fire", "ems_fire"] = "fire"

    model_config = ConfigDict(populate_by_name=True, extra="allow")


# ----------------------------
# Response Models
# ----------------------------


class ProcessIncidentsSuccess(BaseModel):
    status: Literal["success"] = "success"
    incident_counts: Dict[str, int]
    average_time_between_incidents_minutes: float
    total_incidents: int

    model_config = ConfigDict(extra="allow")


ProcessIncidentsResponse = Union[ProcessIncidentsSuccess, ErrorResponse]
