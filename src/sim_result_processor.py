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
    # Read the station report CSV file
    df = pd.read_csv(station_report_path)
    # Group by StationName and calculate metrics
    summary_df = (
        df.groupby("StationID")
        .agg(
            AverageTravelTime=("TravelTimeToIncident", "mean"),
            IncidentCount=("IncidentID", "count")
        )
        .reset_index()
    )

    # Convert to JSON-like structure and ensure native Python types
    summary_json = []
    for _, row in summary_df.iterrows():
        station_id = str(row["StationID"])
        travel_time_mean = float(row["AverageTravelTime"])
        incident_count = int(row["IncidentCount"])
        
        summary_json.append({
            station_id: {
                "travel time mean": travel_time_mean,
                "incident count": incident_count
            }
        })
    return summary_json