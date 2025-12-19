from __future__ import annotations

from typing import Dict, List, Literal, Optional, Union

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, RootModel


# ----------------------------
# Common / Request Models
# ----------------------------


class DateRange(BaseModel):
    start_date: str = Field(validation_alias=AliasChoices("start_date", "startDate"))
    end_date: str = Field(validation_alias=AliasChoices("end_date", "endDate"))

    model_config = ConfigDict(populate_by_name=True)


class ModelOptions(BaseModel):
    incident: Optional[Literal["historical_incidents", "synthetic_incidents"]] = None
    dispatch: Optional[Literal["nearest"]] = None
    travel_time: Optional[str] = Field(default=None, alias="travelTime")
    service_time: Optional[Literal["ml_based", "constant", "empirical_servicetimes"]] = Field(
        default=None, alias="serviceTime"
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class ApparatusInput(BaseModel):
    type: str
    count: int


class StationInput(BaseModel):
    id: Union[str, int]
    name: str
    lat: float
    lon: float
    apparatus: List[ApparatusInput] = Field(default_factory=list)


class RunSimulationRequest(BaseModel):
    """Payload accepted by POST /run-simulation.

    Note: the implementation also forwards unknown top-level keys as config overrides.
    We keep backwards-compatibility by allowing extra fields.
    """

    stations: Optional[List[StationInput]] = Field(
        default=None, validation_alias=AliasChoices("stations")
    )
    incident_type: Optional[Literal["fire", "ems_fire"]] = Field(default=None)
    models: Optional[ModelOptions] = None
    dispatch_policy: Optional[str] = Field(default=None)
    station_data: Optional[str] = Field(default=None)
    date_range: Optional[DateRange] = Field(default=None)

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class RunComparisonRequest(BaseModel):
    baseline: RunSimulationRequest
    new_config: RunSimulationRequest = Field(alias="newConfig")

    model_config = ConfigDict(populate_by_name=True)


# ----------------------------
# Response Models
# ----------------------------


class ErrorResponse(BaseModel):
    status: Literal["error"] = "error"
    error: str

    model_config = ConfigDict(extra="allow")


class StationSummary(BaseModel):
    travel_time_mean: float
    incident_count: int
    travel_times: List[float]
    average_service_time: Optional[float] = None
    service_times: List[float]
    travel_time_p90: float

    model_config = ConfigDict(populate_by_name=True)


class StationReportEntry(RootModel[Dict[str, StationSummary]]):
    pass


class VehicleSummary(BaseModel):
    travel_time_mean: float
    incident_count: int
    travel_time_p90: float

    model_config = ConfigDict(populate_by_name=True)


class VehicleReportEntry(RootModel[Dict[str, VehicleSummary]]):
    pass


class IncidentTypeSummary(BaseModel):
    average_travel_time: float
    travel_time_p90: float
    incident_count: int

    model_config = ConfigDict(populate_by_name=True)

#TODO: Str here should or might be an enum?
class IncidentTypeReportEntry(RootModel[Dict[str, IncidentTypeSummary]]):
    pass


# ---- Evaluation models (from src/engine/results.py) ----


class EvaluationAggregateMetrics(BaseModel):
    total_incidents_sim: int
    total_incidents_gt: int
    travel_time_mean_sim: float
    travel_time_mean_gt: float
    travel_time_p90_sim: float
    travel_time_p90_gt: float
    coverage_percentage_sim: float
    coverage_percentage_gt: float
    travel_time_mean_diff: float
    travel_time_p90_diff: float
    coverage_percentage_diff: float


class EvaluationDistributionData(BaseModel):
    travel_time_values_sim: List[float]
    travel_time_values_gt: List[float]


class EvaluationStationComparisonRow(BaseModel):
    station_id: Optional[str] = Field(default=None, alias="StationID")

    count_sim: Optional[float] = None
    count_gt: Optional[float] = None
    travel_p90_sim: Optional[float] = None
    travel_p90_gt: Optional[float] = None
    travel_mean_sim: Optional[float] = None
    travel_mean_gt: Optional[float] = None
    count_diff: Optional[float] = None
    travel_p90_diff: Optional[float] = None
    travel_mean_diff: Optional[float] = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class EvaluationStationDistribution(BaseModel):
    travel_p90_values_sim: List[float]
    travel_p90_values_gt: List[float]
    travel_mean_values_sim: List[float]
    travel_mean_values_gt: List[float]


class EvaluationPerStationMetrics(BaseModel):
    station_comparison: List[EvaluationStationComparisonRow]
    mae_incident_counts: Optional[float] = None
    mae_travel_p90: Optional[float] = None
    mae_travel_mean: Optional[float] = None
    station_distribution: EvaluationStationDistribution
    matched_stations_count: int
    unmatched_stations_sim_only: List[Optional[str]]
    unmatched_stations_gt_only: List[Optional[str]]


class VehicleEvaluation(BaseModel):
    aggregate_metrics: EvaluationAggregateMetrics
    distribution_data: EvaluationDistributionData
    per_station_metrics: EvaluationPerStationMetrics


class OverallGroundTruthSummary(BaseModel):
    ground_truth_travel_time_mean: float
    ground_truth_P90_continuous: float
    ground_truth_coverage_percent: float


class SimulationEvaluation(BaseModel):
    engine_evaluation: Optional[VehicleEvaluation] = None
    medic_evaluation: Optional[VehicleEvaluation] = None
    overall_summary: OverallGroundTruthSummary


class SimulationRunSuccess(BaseModel):
    status: Literal["success"] = "success"

    total_incidents: int
    station_report: List[StationReportEntry]
    average_response_time: float
    coverage_percent: float
    vehicle_report: List[VehicleReportEntry]
    average_response_time_per_incident_type: List[IncidentTypeReportEntry]
    P90_continuous: float

    # Only returned for some runs
    evaluation: Optional[SimulationEvaluation] = None

    model_config = ConfigDict(extra="allow")


SimulationRunResponse = Union[SimulationRunSuccess, ErrorResponse]


# ---- Comparison response models ----


class SimulationSummary(BaseModel):
    total_incidents: Optional[int] = None
    average_response_time: Optional[float] = None
    coverage_percent: Optional[float] = None
    P90_continuous: Optional[float] = None
    station_report: Optional[List[StationReportEntry]] = None
    vehicle_report: Optional[List[VehicleReportEntry]] = None
    average_response_time_per_incident_type: Optional[List[IncidentTypeReportEntry]] = None

    model_config = ConfigDict(extra="allow")


class ComparisonMetricDelta(BaseModel):
    baseline: float
    new: float
    difference: float
    percent_change: Optional[float] = None
    improved: Optional[bool] = None


class OverallMetricsComparison(BaseModel):
    average_response_time: ComparisonMetricDelta
    coverage_percent: ComparisonMetricDelta
    p90_response_time: ComparisonMetricDelta


class StationComparisonTotalIncidents(BaseModel):
    baseline: int
    new: int
    difference: int


class StationComparisonTimeMetric(BaseModel):
    baseline: Optional[float] = None
    new: Optional[float] = None
    difference: Optional[float] = None
    improved: Optional[bool] = None


class StationComparisonRow(BaseModel):
    station_id: str
    station_name: str
    total_incidents: StationComparisonTotalIncidents
    average_travel_time: StationComparisonTimeMetric
    p90_travel_time: StationComparisonTimeMetric
    status: Literal["new_station", "removed_station", "existing_station"]


class IncidentTypeComparisonCount(BaseModel):
    baseline: int
    new: int
    difference: int


class IncidentTypeComparisonMetric(BaseModel):
    baseline: Optional[float] = None
    new: Optional[float] = None
    difference: Optional[float] = None
    percent_change: Optional[float] = None
    improved: Optional[bool] = None


class IncidentTypeComparisonRow(BaseModel):
    incident_type: str
    incident_count: IncidentTypeComparisonCount
    average_travel_time: IncidentTypeComparisonMetric


class ComparisonImprovements(BaseModel):
    response_time_improved: bool
    coverage_improved: bool
    p90_improved: bool
    stations_with_better_response: int
    stations_with_worse_response: int
    new_stations_added: int
    stations_removed: int


class ComparisonSummary(BaseModel):
    overall_assessment: Literal["improved", "mixed", "degraded"]
    key_findings: List[str]


class ComparisonReport(BaseModel):
    overall_metrics: OverallMetricsComparison
    station_comparison: List[StationComparisonRow]
    incident_type_comparison: List[IncidentTypeComparisonRow]
    improvements: ComparisonImprovements
    summary: ComparisonSummary

    model_config = ConfigDict(extra="allow")


class RunComparisonSuccess(BaseModel):
    status: Literal["success"] = "success"
    baseline: SimulationSummary
    newConfig: SimulationSummary
    comparison: ComparisonReport


RunComparisonResponse = Union[RunComparisonSuccess, ErrorResponse]
