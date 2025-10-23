import pandas as pd
from typing import Dict, Any, List

def summarize_station_report_as_json(station_report_path: str, incident_report_path: str) -> List[Dict[str, Dict[str, Any]]]:
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
    df = df.sort_values(by=['IncidentID', 'ArrivalTime']).reset_index(drop=True)
    
    # Get the first responder for each incident (fastest response)
    firstdf = df.groupby(['IncidentID']).first().reset_index()
    total_incidents = firstdf["IncidentID"].nunique()
    
    # Calculate overall response time metrics
    average_response_time = firstdf["TravelTimeToIncident"].mean()
    target_response_minutes = 5
    target_seconds = target_response_minutes * 60
    
    # Calculate coverage percentage (incidents responded to within target time)
    within_target = firstdf[firstdf['TravelTimeToIncident'] <= target_seconds]
    coverage_incidents = within_target['IncidentID'].nunique()
    coverage_percent = (coverage_incidents / total_incidents * 100) if total_incidents > 0 else 0

    incident_report=pd.read_csv(incident_report_path)
    firstdf.rename(columns={"IncidentID":"IncidentIndex"}, inplace=True)
    firstdf=firstdf.merge(incident_report[['IncidentIndex','Resolved']], on='IncidentIndex', how='inner')
    firstdf['Total_Service_Time'] = (pd.to_datetime(firstdf['Resolved']) - pd.to_datetime(firstdf['ArrivalTime'])).dt.total_seconds()
    


    
    # Aggregate statistics per station
    summary_df = (firstdf.groupby("StationID").agg(
                AverageTravelTime=("TravelTimeToIncident", "mean"),
                IncidentCount=("IncidentIndex", "count"),
                TravelTimes=("TravelTimeToIncident", list),
                AverageServiceTime=("Total_Service_Time", "mean"),
                ServiceTimes=("Total_Service_Time", list)
            ).reset_index())

    average_travel_time_per_vehicle_df=(df.groupby("Type").agg(
                AverageTravelTime=("TravelTimeToIncident", "mean"),
                IncidentCount=("IncidentID", "count"),
            ).reset_index())
    
    
    vehicle_json = []
    for _, row in average_travel_time_per_vehicle_df.iterrows():
            station_id = str(row["Type"])
            travel_time_mean = float(row["AverageTravelTime"])
            incident_count = int(row["IncidentCount"])


            vehicle_json.append({
                station_id: {
                    "travel time mean": travel_time_mean,
                    "incident count": incident_count,
                }
            })

    # Convert to the required JSON format
    summary_json = []
    for _, row in summary_df.iterrows():
            station_id = str(row["StationID"])
            travel_time_mean = float(row["AverageTravelTime"])
            incident_count = int(row["IncidentCount"])
            travel_times = row["TravelTimes"]
            average_service_time = row["AverageServiceTime"]
            service_times = row["ServiceTimes"]

            summary_json.append({
                station_id: {
                    "travel time mean": travel_time_mean,
                    "incident count": incident_count,
                    "travel times": travel_times,
                    "average service time": average_service_time,
                    "service times": service_times
                }
            })
    
    return summary_json, total_incidents, average_response_time, coverage_percent, vehicle_json

def calculate_average_response_times_by_incident_type(station_report_path, incident_report_path, incident_path):
    """
    Calculate average response times by category of incident.

    Args:
        station_report_path (str): Path to the station report CSV file.
        incident_report_path (str): Path to the incident report CSV file.
        incident_path (str): Path to the incident CSV file.

    Returns:
        Dict[str, Any]: A dictionary with average response times by incident type.
    """
    
    station_report=pd.read_csv(station_report_path)
    incident_report=pd.read_csv(incident_report_path)
    incident_data=pd.read_csv(incident_path)
    #create the first responder dataframe
    station_report["ArrivalTime"] = pd.to_datetime(station_report["Time"]) + pd.to_timedelta(station_report["TravelTimeToIncident"], unit='s')
    station_report = station_report.sort_values(by=['IncidentID', 'ArrivalTime']).reset_index(drop=True)
    firstdf = station_report.groupby(['IncidentID']).first().reset_index()
    
    
    firstdf.rename(columns={"IncidentID":"IncidentIndex"}, inplace=True)

    merged_df=incident_report.merge(firstdf[['IncidentIndex','ArrivalTime','TravelTimeToIncident']], on='IncidentIndex', how='inner')
    merged_df=merged_df.merge(incident_data[['incident_id','incident_type']], left_on='IncidentID', right_on='incident_id', how='inner')
    type_summary = merged_df.groupby('incident_type').agg(
        AverageTravelTime=('TravelTimeToIncident', 'mean'),
        IncidentCount=('IncidentID', 'count')
    )
  
    type_summary.sort_values(by='IncidentCount', ascending=False, inplace=True)
    type_summary=type_summary.head(10)
    summary_json = []
    for incident_type, row in type_summary.iterrows():
        summary_json.append({
            incident_type: {
                "average travel time": float(row["AverageTravelTime"]),
                "incident count": int(row["IncidentCount"])
        
            }
        })
        
    return summary_json