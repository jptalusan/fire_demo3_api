import pandas as pd
from typing import Dict, Any, List

def summarize_station_report_as_json(station_report_path: str) -> List[Dict[str, Dict[str, Any]]]:
    """
    Summarize the station report to calculate average travel time per station
    and the number of incidents served by each station, returning as JSON.

    Args:
        station_report_path (str): Path to the station report CSV file.

    Returns:
        List[Dict[str, Dict[str, Any]]]: A list of dictionaries with station summaries.
    """
    # Load and preprocess the station report data
    df = pd.read_csv(station_report_path)
    df["ArrivalTime"] = pd.to_datetime(df["Time"]) + pd.to_timedelta(df["TravelTimeToIncident"], unit='s')
    df = df.sort_values(by=["StationID", 'IncidentID', 'ArrivalTime']).reset_index(drop=True)
    
    # Get the first responder for each incident (fastest response per station-incident pair)
    firstdf = df.groupby(["StationID", 'IncidentID']).first().reset_index()
    total_incidents = firstdf["IncidentID"].nunique()
    
    # Calculate overall response time metrics
    average_response_time = firstdf["TravelTimeToIncident"].mean()
    target_response_minutes = 5
    target_seconds = target_response_minutes * 60
    
    # Calculate coverage percentage (incidents responded to within target time)
    within_target = firstdf[firstdf['TravelTimeToIncident'] <= target_seconds]
    coverage_incidents = within_target['IncidentID'].nunique()
    coverage_percent = (coverage_incidents / total_incidents * 100) if total_incidents > 0 else 0
    
    # Aggregate statistics per station
    summary_df = (firstdf.groupby("StationID").agg(
                AverageTravelTime=("TravelTimeToIncident", "mean"),
                IncidentCount=("IncidentID", "count"),
                TravelTimes=("TravelTimeToIncident", list)
            ).reset_index())

    # Convert to the required JSON format
    summary_json = []
    for _, row in summary_df.iterrows():
            station_id = str(row["StationID"])
            travel_time_mean = float(row["AverageTravelTime"])
            incident_count = int(row["IncidentCount"])
            travel_times = row["TravelTimes"]

            summary_json.append({
                station_id: {
                    "travel time mean": travel_time_mean,
                    "incident count": incident_count,
                    "travel times": travel_times
                }
            })
    
    return summary_json, total_incidents, average_response_time, coverage_percent