import pandas as pd
from typing import Dict, Any, List, Optional

import numpy as np
from pathlib import Path

def _calculate_aggregate_metrics(sim_data: pd.DataFrame, gt_data: pd.DataFrame, vehicle_type: str) -> Dict[str, Any]:
    """
    Calculate aggregate metrics for a specific vehicle type (Engine or Medic).
    
    Args:
        sim_data: Simulation data for the vehicle type
        gt_data: Ground truth data for the vehicle type
        vehicle_type: 'Engine' or 'Medic'
    
    Returns:
        Dictionary containing aggregate metrics and distribution data
    """
    if len(sim_data) == 0 or len(gt_data) == 0:
        return None
    
    # Overall aggregate metrics
    aggregate_metrics = {
        'total_incidents_sim': int(sim_data['IncidentID'].nunique()),
        'total_incidents_gt': int(gt_data['incident_id'].nunique()),
        
        # Travel time (alarm-arrive time)
        'travel_time_mean_sim': float(sim_data['AlarmArriveTime'].mean()),
        'travel_time_mean_gt': float(gt_data['travel_time'].mean()),
        'travel_time_p90_sim': float(sim_data['AlarmArriveTime'].quantile(0.9)),
        'travel_time_p90_gt': float(gt_data['travel_time'].quantile(0.9)),
        
        # Coverage (incidents within 320 seconds)
        'coverage_percentage_sim': float((sim_data['AlarmArriveTime'] <= 320).sum() / len(sim_data) * 100),
        'coverage_percentage_gt': float((gt_data['travel_time'] <= 320).sum() / len(gt_data) * 100),
    }
    
    # Calculate differences
    aggregate_metrics['travel_time_mean_diff'] = abs(aggregate_metrics['travel_time_mean_sim'] - aggregate_metrics['travel_time_mean_gt'])
    aggregate_metrics['travel_time_p90_diff'] = abs(aggregate_metrics['travel_time_p90_sim'] - aggregate_metrics['travel_time_p90_gt'])
    aggregate_metrics['coverage_percentage_diff'] = abs(aggregate_metrics['coverage_percentage_sim'] - aggregate_metrics['coverage_percentage_gt'])
    
    # Distribution data for plotting
    distribution_data = {
        'travel_time_values_sim': sim_data['AlarmArriveTime'].dropna().tolist(),
        'travel_time_values_gt': gt_data['travel_time'].dropna().tolist(),
    }
    
    # Per-station metrics
    per_station_metrics = _calculate_per_station_metrics(sim_data, gt_data)
    
    return {
        'aggregate_metrics': aggregate_metrics,
        'distribution_data': distribution_data,
        'per_station_metrics': per_station_metrics
    }

def _calculate_per_station_metrics(sim_data: pd.DataFrame, gt_data: pd.DataFrame) -> Dict[str, Any]:
    """
    Calculate per-station comparisons for incident counts and travel time P90.
    """
    # Incident counts per station
    sim_counts = sim_data.groupby('StationID')['IncidentID'].nunique().reset_index(name='count_sim')
    gt_counts = gt_data.groupby('StationID')['incident_id'].nunique().reset_index(name='count_gt')
    merged_counts = sim_counts.merge(gt_counts, on='StationID', how='outer').fillna(0)
    
    # Travel time P90 per station
    sim_travel_p90 = sim_data.groupby('StationID')['AlarmArriveTime'].quantile(0.9).reset_index(name='travel_p90_sim')
    gt_travel_p90 = gt_data.groupby('StationID')['travel_time'].quantile(0.9).reset_index(name='travel_p90_gt')
    merged_travel_p90 = sim_travel_p90.merge(gt_travel_p90, on='StationID', how='outer')
    
    # Travel time Mean per station
    sim_travel_mean = sim_data.groupby('StationID')['AlarmArriveTime'].mean().reset_index(name='travel_mean_sim')
    gt_travel_mean = gt_data.groupby('StationID')['travel_time'].mean().reset_index(name='travel_mean_gt')
    merged_travel_mean = sim_travel_mean.merge(gt_travel_mean, on='StationID', how='outer')
    
    # Combine all station metrics
    station_metrics = merged_counts.merge(merged_travel_p90, on='StationID', how='outer')
    station_metrics = station_metrics.merge(merged_travel_mean, on='StationID', how='outer')
    
    # Calculate differences
    station_metrics['count_diff'] = station_metrics['count_sim'] - station_metrics['count_gt']
    station_metrics['travel_p90_diff'] = station_metrics['travel_p90_sim'] - station_metrics['travel_p90_gt']
    station_metrics['travel_mean_diff'] = station_metrics['travel_mean_sim'] - station_metrics['travel_mean_gt']
    
    # Calculate aggregate errors across stations (only for matched stations)
    matched_counts = station_metrics.dropna(subset=['count_sim', 'count_gt'])
    mae_incident_counts = float(np.abs(matched_counts['count_diff']).mean()) if len(matched_counts) > 0 else None
    
    matched_travel_p90 = station_metrics.dropna(subset=['travel_p90_sim', 'travel_p90_gt'])
    mae_travel_p90 = float(np.abs(matched_travel_p90['travel_p90_diff']).mean()) if len(matched_travel_p90) > 0 else None
    
    matched_travel_mean = station_metrics.dropna(subset=['travel_mean_sim', 'travel_mean_gt'])
    mae_travel_mean = float(np.abs(matched_travel_mean['travel_mean_diff']).mean()) if len(matched_travel_mean) > 0 else None
    
    # Distribution data for per-station P90s
    station_distribution = {
        'travel_p90_values_sim': matched_travel_p90['travel_p90_sim'].dropna().tolist(),
        'travel_p90_values_gt': matched_travel_p90['travel_p90_gt'].dropna().tolist(),
        'travel_mean_values_sim': matched_travel_mean['travel_mean_sim'].dropna().tolist(),
        'travel_mean_values_gt': matched_travel_mean['travel_mean_gt'].dropna().tolist(),
    }
    
    # Replace NaN values with None for JSON serialization
    station_metrics = station_metrics.replace({np.nan: None})
    
    return {
        'station_comparison': station_metrics.to_dict('records'),
        'mae_incident_counts': mae_incident_counts,
        'mae_travel_p90': mae_travel_p90,
        'mae_travel_mean': mae_travel_mean,
        'station_distribution': station_distribution,
        'matched_stations_count': len(matched_counts),
        'unmatched_stations_sim_only': station_metrics[station_metrics['count_gt'] == 0]['StationID'].tolist(),
        'unmatched_stations_gt_only': station_metrics[station_metrics['count_sim'] == 0]['StationID'].tolist(),
    }

def evaluate_simulation_performance(
    incident_report_path: str,
    station_report_path: str,
    ground_truth_path: str = "logs/incident_resolution_times_fire.csv",
    incident_type: Optional[str] = None
) -> dict:
    """
    Evaluates simulation performance against ground truth data with aggregate-level metrics.
    Separates Engine and Medic responses for comprehensive comparison.
    
    ID Mapping (IMPORTANT):
    - station_report.IncidentID == incident_report.IncidentIndex
    - ground_truth.incident_id == incident_report.IncidentID
    
    Vehicle Type Classification:
    - Engine/Fire: All apparatus types except Medic (Engine, Truck, Rescue, Chief, Squad, etc.)
    - Medic/EMS: Type == 'Medic' only
    
    Args:
        station_report_path (str): Path to the simulated station report CSV file
        incident_report_path (str): Path to the simulated incident report CSV file
        ground_truth_path (str): Path to the ground truth resolution times CSV file
    
    Returns:
        dict: Dictionary containing:
            - engine_evaluation: Aggregate metrics, per-station metrics, and distribution data for engines
            - medic_evaluation: Aggregate metrics, per-station metrics, and distribution data for medics
            - overall_summary: Combined high-level statistics
            - Legacy fields (for backward compatibility): mae_response_time, mae_alarm_arrive_time, etc.
    """
    
    # Load data
    station_report = pd.read_csv(station_report_path)
    incident_report = pd.read_csv(incident_report_path)
    ground_truth = pd.read_csv(ground_truth_path)
    ground_truth=ground_truth[ground_truth.incident_id.isin(incident_report['IncidentID'].values)]
    


    
    # Process station report to get first responders
    # Note: station_report.IncidentID is actually the IncidentIndex in incident_report

    station_report["ArrivalTime"] = pd.to_datetime(station_report["Time"]) + pd.to_timedelta(
        station_report["TravelTimeToIncident"], unit='s'
    )
    station_report = station_report.sort_values(by=['IncidentID', 'ArrivalTime']).reset_index(drop=True)
    station_report_Medic = station_report[station_report['Type'].str.upper() == 'MEDIC'].sort_values(by=['IncidentID', 'ArrivalTime']).reset_index(drop=True)
    station_report_Engine = station_report[station_report['Type'].str.upper() != 'MEDIC'].sort_values(by=['IncidentID', 'ArrivalTime']).reset_index(drop=True)
    first_responders_Medic = station_report_Medic.groupby(['IncidentID']).first().reset_index()
    first_responders_Engine = station_report_Engine.groupby(['IncidentID']).first().reset_index()
    first_responders=station_report.groupby(['IncidentID']).first().reset_index()
    
    
    
    # Rename for clarity: station_report.IncidentID is actually IncidentIndex
    first_responders_Medic.rename(columns={"IncidentID": "IncidentIndex"}, inplace=True)
    first_responders_Engine.rename(columns={"IncidentID": "IncidentIndex"}, inplace=True)
    first_responders.rename(columns={"IncidentID": "IncidentIndex"}, inplace=True)
    
    # Merge with incident_report to get the actual IncidentID and resolution times
    # This joins: first_responders.IncidentIndex -> incident_report.IncidentIndex
    # And gets: incident_report.IncidentID (which matches ground_truth.incident_id)
    sim_data_Medic = first_responders_Medic.merge(
        incident_report[['IncidentIndex', 'IncidentID', 'Responded', 'Resolved']], 
        on='IncidentIndex', 
        how='inner'
    )
    sim_data_Engine = first_responders_Engine.merge(
        incident_report[['IncidentIndex', 'IncidentID', 'Responded', 'Resolved']], 
        on='IncidentIndex', 
        how='inner'
    )
    sim_data = first_responders.merge(
        incident_report[['IncidentIndex', 'IncidentID', 'Responded', 'Resolved']], 
        on='IncidentIndex', 
        how='inner'
    )
    
    # Calculate simulation metrics
    sim_data_Medic['AlarmArriveTime'] = (
        pd.to_datetime(sim_data_Medic['ArrivalTime']) - pd.to_datetime(sim_data_Medic['Responded'])
    ).dt.total_seconds()
    
    sim_data_Engine['AlarmArriveTime'] = (
        pd.to_datetime(sim_data_Engine['ArrivalTime']) - pd.to_datetime(sim_data_Engine['Responded'])
    ).dt.total_seconds()

    sim_data['AlarmArriveTime'] = (
        pd.to_datetime(sim_data['ArrivalTime']) - pd.to_datetime(sim_data['Responded'])
    ).dt.total_seconds()
    sim_data['response_time'] = (
        pd.to_datetime(sim_data['Resolved']) - pd.to_datetime(sim_data['Responded'])
    ).dt.total_seconds()
    
    

    
    
   
    if incident_type == 'fire':
        ground_truth_travel_time_mean = ground_truth['FirstEngineTravelTime'].mean()
        ground_truth_P90_continuous = (ground_truth['FirstEngineTravelTime']).quantile(0.9)
        target_seconds = 320
        total_incidents = ground_truth['incident_id'].nunique()
        within_target = ground_truth[(ground_truth['FirstEngineTravelTime']) <= target_seconds]
        coverage_incidents = within_target['incident_id'].nunique()
        gt_coverage_percent = (coverage_incidents / total_incidents * 100) if total_incidents > 0 else 0
    else:
        ground_truth_travel_time_mean = ground_truth[['FirstEngineTravelTime','FirstEMSTravelTime']].min(axis=1).mean()
        ground_truth_P90_continuous = (ground_truth[['FirstEngineTravelTime','FirstEMSTravelTime']].min(axis=1)).quantile(0.9)
        target_seconds = 320
        total_incidents = ground_truth['incident_id'].nunique()
        within_target = ground_truth[(ground_truth[['FirstEngineTravelTime','FirstEMSTravelTime']].min(axis=1)) <= target_seconds]
        coverage_incidents = within_target['incident_id'].nunique()
        gt_coverage_percent = (coverage_incidents / total_incidents * 100) if total_incidents > 0 else 0
    
    overall_gt_summary = {
        'ground_truth_travel_time_mean': float(ground_truth_travel_time_mean),
        'ground_truth_P90_continuous': float(ground_truth_P90_continuous),
        'ground_truth_coverage_percent': float(gt_coverage_percent),
    }

    # Prepare ground truth data - split by vehicle type
    gt_data = ground_truth.copy()
    
    # Split ground truth into Engine and EMS datasets
    gt_data_Engine = gt_data[gt_data['FirstEngineTravelTime'].notna()].copy()
    gt_data_Engine['StationID'] = gt_data_Engine['Facility Name_ENG'].str.strip() if 'Facility Name_ENG' in gt_data_Engine.columns else gt_data_Engine['Facility Name'].str.strip()
    gt_data_Engine['travel_time'] = gt_data_Engine['FirstEngineTravelTime']
    
    gt_data_Medic = gt_data[gt_data['FirstEMSTravelTime'].notna()].copy()
    gt_data_Medic['StationID'] = gt_data_Medic['Facility Name_EMS'].str.strip() if 'Facility Name_EMS' in gt_data_Medic.columns else gt_data_Medic['Facility Name'].str.strip()
    gt_data_Medic['travel_time'] = gt_data_Medic['FirstEMSTravelTime']
    
    # Standardize StationID for simulation data
    sim_data_Engine['StationID'] = sim_data_Engine['StationID'].str.strip()
    sim_data_Medic['StationID'] = sim_data_Medic['StationID'].str.strip()
    
    # --- Calculate separate metrics for Engine and Medic ---
    engine_evaluation = _calculate_aggregate_metrics(sim_data_Engine, gt_data_Engine, 'Engine')
    medic_evaluation = _calculate_aggregate_metrics(sim_data_Medic, gt_data_Medic, 'Medic')
    
    
    # Return results
    evaluation_results = {
        'engine_evaluation': engine_evaluation,
        'medic_evaluation': medic_evaluation,
        'overall_summary': overall_gt_summary,
    }
    
    return evaluation_results

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
    P90_continuous = firstdf["TravelTimeToIncident"].quantile(0.9)

    target_seconds = 320
    
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
                P90TravelTime=("TravelTimeToIncident", lambda x: x.quantile(0.9)),
                IncidentCount=("IncidentIndex", "count"),
                TravelTimes=("TravelTimeToIncident", list),
                AverageServiceTime=("Total_Service_Time", "mean"),
                ServiceTimes=("Total_Service_Time", list)
            ).reset_index())

    average_travel_time_per_vehicle_df=(df.groupby("Type").agg(
                AverageTravelTime=("TravelTimeToIncident", "mean"),
                P90TravelTime=("TravelTimeToIncident", lambda x: x.quantile(0.9)),
                IncidentCount=("IncidentID", "count"),
            ).reset_index())
    
    
    vehicle_json = []
    for _, row in average_travel_time_per_vehicle_df.iterrows():
            station_id = str(row["Type"])
            travel_time_mean = float(row["AverageTravelTime"])
            incident_count = int(row["IncidentCount"])
            travel_time_p90 = float(row["P90TravelTime"])


            vehicle_json.append({
                station_id: {
                    "travel_time_mean": travel_time_mean,
                    "incident_count": incident_count,
                    "travel_time_p90": travel_time_p90
                }
            })

    # Convert to the required JSON format
    summary_json = []
    for _, row in summary_df.iterrows():
            station_id = str(row["StationID"])
            travel_time_mean = float(row["AverageTravelTime"])
            travel_time_p90 = float(row["P90TravelTime"])
            incident_count = int(row["IncidentCount"])
            travel_times = row["TravelTimes"]
            average_service_time = row["AverageServiceTime"]
            service_times = row["ServiceTimes"]
            

            summary_json.append({
                station_id: {
                    "travel_time_mean": travel_time_mean,
                    "incident_count": incident_count,
                    "travel_times": travel_times,
                    "average_service_time": average_service_time,
                    "service_times": service_times,
                    "travel_time_p90": travel_time_p90
                }
            })
    
    return summary_json, total_incidents, average_response_time, coverage_percent, vehicle_json, P90_continuous

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
        average_travel_time=('TravelTimeToIncident', 'mean'),
        p90_travel_time=('TravelTimeToIncident', lambda x: x.quantile(0.9)),
        incident_count=('IncidentID', 'count')
    )
  
    type_summary.sort_values(by='incident_count', ascending=False, inplace=True)
    type_summary=type_summary.head(10)
    summary_json = []
    for incident_type, row in type_summary.iterrows():
        summary_json.append({
            incident_type: {
                "average_travel_time": float(row["average_travel_time"]),
                "p90_travel_time": float(row["p90_travel_time"]),
                "incident_count": int(row["incident_count"])
        
            }
        })
        
    return summary_json