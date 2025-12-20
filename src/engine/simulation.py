
import hashlib
import subprocess
import pandas as pd

from src.engine.results import summarize_station_report_as_json, calculate_average_response_times_by_incident_type

def create_stations_csv_from_payload(stations_data, output_path):
    """
    Create a stations_with_apparatus.csv file from the payload stations data
    
    Args:
        stations_data: List of station dictionaries from the payload
        output_path: Path where to save the CSV file
    """
    # Define all possible apparatus types based on your example
    apparatus_types = ['Engine_ID', 'Truck', 'Rescue', 'Hazard', 'Squad', 'FAST', 'Medic', 'Brush', 'Boat', 'UTV', 'REACH', 'Chief']
    
    rows = []
    for station in stations_data:
        # Initialize apparatus counts to empty
        apparatus_counts = {app_type: '' for app_type in apparatus_types}
        
        # Fill in the apparatus counts from the payload
        for apparatus in station.get('apparatus', []):
            app_type = apparatus['type']
            count = apparatus['count']
            
            # Map apparatus types to CSV column names
            if app_type == 'Engine':
                apparatus_counts['Engine_ID'] = count
            else:
                apparatus_counts[app_type] = count
        
        # Create row for CSV
        row = {
            'StationID': station['id'],
            'Stations': station['name'],
            'lat': station['lat'],
            'lon': station['lon'],
            'Nashville Fire Stations': f"User Station {station['id']}",  # Generic address for user-defined stations
            **apparatus_counts
        }
        rows.append(row)
    
    # Create DataFrame and save to CSV
    df = pd.DataFrame(rows)
    # Ensure columns are in the right order
    columns = ['StationID', 'Stations', 'lat', 'lon', 'Nashville Fire Stations'] + apparatus_types
    df = df[columns]
    df.to_csv(output_path, index=False)
    print(f"Created user stations file: {output_path}")


async def run_simulation_internal(config, data_dir, logs_dir, models_dir, config_name="simulation"):
    """
    Internal function to run a single simulation with the given configuration.
    This is similar to run_simulation2 but accepts config dict and custom paths.
    
    Args:
        config: Configuration dictionary (baseline or newConfig)
        data_dir: Path to data directory
        logs_dir: Path to logs directory for this simulation
        models_dir: Path to models directory
        config_name: Name identifier for this configuration
    
    Returns:
        dict: Simulation results
    """
    try:
        # Create user-defined stations file if stations are provided
        user_stations_path = data_dir / f"stations_with_apparatus_by_user_{config_name}.csv"
        print("Config stations:", config.get('stations'))
        if 'stations' in config and config['stations']:
            create_stations_csv_from_payload(config['stations'], user_stations_path)
        
        # Determine incident file path based on config
        incidents_path = str(data_dir / "incidents_small.csv")  # default
        incident_type = config.get('incident_type', 'fire')
        
        if config.get('models', {}).get('incident') == 'historical_incidents':
            # Use the filtered incidents from get-incidents endpoint
            date_range = config.get('dateRange', {})
            if date_range.get('startDate') and date_range.get('endDate'):
                start_date = date_range['startDate'][:10]  # Extract date part (YYYY-MM-DD)
                end_date = date_range['endDate'][:10]
                query_hash = hashlib.md5(f"historical_incidents_{start_date}_{end_date}".encode()).hexdigest()
                query_filename = f"historical_{start_date}_{end_date}_{query_hash[:8]}.csv"
                query_path = data_dir / "incidents" / "historical" / incident_type / "query" / query_filename
                if query_path.exists():
                    incidents_path = str(query_path)
                    print(f"Using filtered incidents: {incidents_path}")
        
        if config.get('models', {}).get('incident') == 'synthetic_incidents':
            # Use synthetic incidents file
            date_range = config.get('dateRange', {})
            if date_range.get('startDate') and date_range.get('endDate'):
                start_date = date_range['startDate'][:10]  # Extract date part (YYYY-MM-DD)
                end_date = date_range['endDate'][:10]
                query_hash = hashlib.md5(f"synthetic_incidents_{start_date}_{end_date}".encode()).hexdigest()
                query_filename = f"synthetic_{start_date}_{end_date}_{query_hash[:8]}.csv"
                query_path = data_dir / "incidents" / "synthetic" / incident_type / "query" / query_filename
                if query_path.exists():
                    incidents_path = str(query_path)
                    print(f"Using synthetic incidents: {incidents_path}")
        
        # Map dispatch policy from config
        dispatch_policy = "FIREBEATS"  # default
        if config.get('dispatch_policy') == 'nearest':
            dispatch_policy = "NEAREST"
        elif config.get('models', {}).get('dispatch') == 'nearest':
            dispatch_policy = "NEAREST"
            
        travel_time_model = config.get('models', {}).get('travelTime', 'OSRM')
        if travel_time_model == 'ARCGIS':
            travel_time_model = "OSRM"
        
        # Map fire model type from config
        fire_model_type = "ML"  # default
        service_time_model = config.get('models', {}).get('serviceTime', 'ml_based')
        if service_time_model == 'ml_based':
            fire_model_type = "ML"
        elif service_time_model == 'constant':
            fire_model_type = "CONSTANT"
        elif service_time_model == 'empirical_servicetimes':
            fire_model_type = "HISTORICAL"
        
        # Define the simulator configuration
        sim_config = {
            "OSRM_URL": "http://localhost:8080/table/v1/driving/",
            "BASE_OSRM_URL": "http://localhost:8080",
            "DISPATCH_POLICY": dispatch_policy,
            "FIRE_MODEL_TYPE": fire_model_type,
            "MODEL_PATH": str(models_dir / "fire_incident_gb_model.onnx") if incident_type == 'fire' else str(models_dir / "ems_model" / "fire_incident_gb_model.onnx"),
            "FEATURES_PATH": str(models_dir / "fire_model_features_mapping.json") if incident_type == 'fire' else str(models_dir / "ems_model" / "fire_model_features_mapping.json"),
            "TRAVEL_TIME_MODEL_TYPE": travel_time_model,
            
            "INCIDENTS_CSV_PATH": incidents_path,
            "APPARATUS_CSV_PATH": str(user_stations_path if user_stations_path.exists() else data_dir / "stations_with_apparatus.csv"),
            "BOUNDS_GEOJSON_PATH": str(data_dir / "bounds.geojson"),
            "NFD_RESPONSE_CSV_PATH": str(data_dir / "NFDResponse.csv"),
            "RESOLUTION_STATS_CSV_PATH": str(data_dir / "response_time_summary2.csv"),
            
            "MEAN_MATRIX_PATH": str(data_dir / "interpolation_fire/mean_zone_travel_time_matrix.json") if incident_type == 'fire' else str(data_dir / "interpolation_data/mean_zone_travel_time_matrix.json"),
            "STD_MATRIX_PATH": str(data_dir / "interpolation_fire/std_zone_travel_time_matrix.json") if incident_type == 'fire' else str(data_dir / "interpolation_data/std_zone_travel_time_matrix.json"),
            "ZONE_INFO_PATH": str(data_dir / "interpolation_fire/zone_fire_station_info.json") if incident_type == 'fire' else str(data_dir / "interpolation_data/zone_fire_station_info.json"),

            "REPORT_CSV_PATH": str(logs_dir / "incident_report.csv"),
            "STATION_REPORT_CSV_PATH": str(logs_dir / "station_report.csv"),
            "DURATION_MATRIX_PATH": str(logs_dir / "duration_matrix.bin"),
            "DISTANCE_MATRIX_PATH": str(logs_dir / "distance_matrix.bin"),
            "MATRIX_CSV_PATH": str(logs_dir / "matrix.csv"),
            "FIREBEATS_MATRIX_PATH": str(logs_dir / "beats.bin"),
            "ZONE_MAP_PATH": str(data_dir / "zones.csv"),
            "BEATS_SHAPEFILE_PATH": str(data_dir / "beats_shpfile.geojson"),
            "RANDOM_SEED": 42,
            "PYTHON_PATH": "../../venvBOC/bin/python"
        }

        # Construct the command for the C++ simulator
        command = [
            "./data/fire_simulator",
            f"--OSRM_URL={sim_config['OSRM_URL']}",
            f"--BASE_OSRM_URL={sim_config['BASE_OSRM_URL']}",
            f"--INCIDENTS_CSV_PATH={sim_config['INCIDENTS_CSV_PATH']}",
            f"--APPARATUS_CSV_PATH={sim_config['APPARATUS_CSV_PATH']}",
            f"--FIRE_MODEL_TYPE={sim_config['FIRE_MODEL_TYPE']}",
            f"--MODEL_PATH={sim_config['MODEL_PATH']}",
            f"--FEATURES_PATH={sim_config['FEATURES_PATH']}",
            f"--TRAVEL_TIME_MODEL_TYPE={sim_config['TRAVEL_TIME_MODEL_TYPE']}",
            f"--MEAN_MATRIX_PATH={sim_config['MEAN_MATRIX_PATH']}",
            f"--STD_MATRIX_PATH={sim_config['STD_MATRIX_PATH']}",
            f"--ZONE_INFO_PATH={sim_config['ZONE_INFO_PATH']}",
            f"--DISPATCH_POLICY={sim_config['DISPATCH_POLICY']}",
            f"--BOUNDS_GEOJSON_PATH={sim_config['BOUNDS_GEOJSON_PATH']}",
            f"--NFD_RESPONSE_CSV_PATH={sim_config['NFD_RESPONSE_CSV_PATH']}",
            f"--RESOLUTION_STATS_CSV_PATH={sim_config['RESOLUTION_STATS_CSV_PATH']}",
            f"--REPORT_CSV_PATH={sim_config['REPORT_CSV_PATH']}",
            f"--STATION_REPORT_CSV_PATH={sim_config['STATION_REPORT_CSV_PATH']}",
            f"--DURATION_MATRIX_PATH={sim_config['DURATION_MATRIX_PATH']}",
            f"--DISTANCE_MATRIX_PATH={sim_config['DISTANCE_MATRIX_PATH']}",
            f"--MATRIX_CSV_PATH={sim_config['MATRIX_CSV_PATH']}",
            f"--FIREBEATS_MATRIX_PATH={sim_config['FIREBEATS_MATRIX_PATH']}",
            f"--ZONE_MAP_PATH={sim_config['ZONE_MAP_PATH']}",
            f"--BEATS_SHAPEFILE_PATH={sim_config['BEATS_SHAPEFILE_PATH']}",
            f"--RANDOM_SEED={sim_config['RANDOM_SEED']}",
            f"--PYTHON_PATH={sim_config['PYTHON_PATH']}",
        ]
        
        print(f"Executing {config_name} simulation...")
        print("Command:", " ".join(command))
        
        # Execute the command
        _ = subprocess.run(command, capture_output=True, text=True, check=True)
        
        # Process results
        station_report, total_incidents, average_response_time, coverage_percent, vehicle_json, P90_continuous = summarize_station_report_as_json(
            sim_config['STATION_REPORT_CSV_PATH'], 
            sim_config['REPORT_CSV_PATH']
        )
        average_response_time_per_incident_type = calculate_average_response_times_by_incident_type(
            sim_config['STATION_REPORT_CSV_PATH'], 
            sim_config['REPORT_CSV_PATH'],
            incidents_path
        )
        
        print(f"{config_name} simulation completed successfully.")
        
        return {
            "status": "success", 
            "total_incidents": total_incidents, 
            "station_report": station_report, 
            "average_response_time": float(average_response_time), 
            "coverage_percent": coverage_percent, 
            "vehicle_report": vehicle_json, 
            "average_response_time_per_incident_type": average_response_time_per_incident_type, 
            "P90_continuous": float(P90_continuous)
        }
        
    except subprocess.CalledProcessError as e:
        print(f"Error executing {config_name} simulation:", e.stderr)
        return {"status": "error", "error": e.stderr}
    except Exception as e:
        print(f"Error in {config_name} simulation:", str(e))
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}



def calculate_comparison_stats(baseline_result, new_result):
    """
    Calculate comparative statistics between baseline and new configuration.
    
    Returns detailed comparison metrics including improvements and differences.
    """
    comparison = {
        "overall_metrics": {},
        "station_comparison": [],
        "incident_type_comparison": [],
        "improvements": {},
        "summary": {}
    }
    
    # Overall metrics comparison
    baseline_avg_response = baseline_result.get('average_response_time', 0)
    new_avg_response = new_result.get('average_response_time', 0)
    baseline_coverage = baseline_result.get('coverage_percent', 0)
    new_coverage = new_result.get('coverage_percent', 0)
    baseline_p90 = baseline_result.get('P90_continuous', 0)
    new_p90 = new_result.get('P90_continuous', 0)
    
    comparison["overall_metrics"] = {
        "average_response_time": {
            "baseline": round(baseline_avg_response, 2),
            "new": round(new_avg_response, 2),
            "difference": round(new_avg_response - baseline_avg_response, 2),
            "percent_change": round(((new_avg_response - baseline_avg_response) / baseline_avg_response * 100), 2) if baseline_avg_response > 0 else 0,
            "improved": new_avg_response < baseline_avg_response
        },
        "coverage_percent": {
            "baseline": round(baseline_coverage, 2),
            "new": round(new_coverage, 2),
            "difference": round(new_coverage - baseline_coverage, 2),
            "percent_change": round(((new_coverage - baseline_coverage) / baseline_coverage * 100), 2) if baseline_coverage > 0 else 0,
            "improved": new_coverage > baseline_coverage
        },
        "p90_response_time": {
            "baseline": round(baseline_p90, 2),
            "new": round(new_p90, 2),
            "difference": round(new_p90 - baseline_p90, 2),
            "percent_change": round(((new_p90 - baseline_p90) / baseline_p90 * 100), 2) if baseline_p90 > 0 else 0,
            "improved": new_p90 < baseline_p90
        }
    }
    
    # Station-level comparison
    baseline_stations = baseline_result.get('station_report', [])
    new_stations = new_result.get('station_report', [])
    
    # Create lookup dictionaries - station_report is a list of dicts with station name as key
    baseline_station_dict = {}
    for station_dict in baseline_stations:
        for station_name, station_data in station_dict.items():
            baseline_station_dict[station_name] = station_data
    
    new_station_dict = {}
    for station_dict in new_stations:
        for station_name, station_data in station_dict.items():
            new_station_dict[station_name] = station_data
    
    all_station_names = set(baseline_station_dict.keys()) | set(new_station_dict.keys())
    
    for station_name in sorted(all_station_names):
        baseline_station = baseline_station_dict.get(station_name, {})
        new_station = new_station_dict.get(station_name, {})
        
        baseline_incidents = baseline_station.get('incident count', 0)
        new_incidents = new_station.get('incident count', 0)
        baseline_avg = baseline_station.get('travel time mean', 0)
        new_avg = new_station.get('travel time mean', 0)
        baseline_p90 = baseline_station.get('travel time p90', 0)
        new_p90 = new_station.get('travel time p90', 0)
        
        station_comparison = {
            "station_id": station_name,
            "station_name": station_name,
            "total_incidents": {
                "baseline": baseline_incidents,
                "new": new_incidents,
                "difference": new_incidents - baseline_incidents
            },
            "average_travel_time": {
                "baseline": round(baseline_avg, 2) if baseline_avg else None,
                "new": round(new_avg, 2) if new_avg else None,
                "difference": round(new_avg - baseline_avg, 2) if (baseline_avg and new_avg) else None,
                "improved": new_avg < baseline_avg if (baseline_avg and new_avg) else None
            },
            "p90_travel_time": {
                "baseline": round(baseline_p90, 2) if baseline_p90 else None,
                "new": round(new_p90, 2) if new_p90 else None,
                "difference": round(new_p90 - baseline_p90, 2) if (baseline_p90 and new_p90) else None,
                "improved": new_p90 < baseline_p90 if (baseline_p90 and new_p90) else None
            },
            "status": "new_station" if station_name not in baseline_station_dict else (
                "removed_station" if station_name not in new_station_dict else "existing_station"
            )
        }
        comparison["station_comparison"].append(station_comparison)
    
    # Incident type comparison - it's a list of dicts
    baseline_incident_types_list = baseline_result.get('average_response_time_per_incident_type', [])
    new_incident_types_list = new_result.get('average_response_time_per_incident_type', [])
    
    # Convert to dictionaries for easier lookup
    baseline_incident_types = {}
    for item in baseline_incident_types_list:
        for incident_type, data in item.items():
            baseline_incident_types[incident_type] = data
    
    new_incident_types = {}
    for item in new_incident_types_list:
        for incident_type, data in item.items():
            new_incident_types[incident_type] = data
    
    all_incident_types = set(baseline_incident_types.keys()) | set(new_incident_types.keys())
    
    for incident_type in sorted(all_incident_types):
        baseline_data = baseline_incident_types.get(incident_type, {})
        new_data = new_incident_types.get(incident_type, {})
        
        baseline_time = baseline_data.get('average_travel_time', 0)
        new_time = new_data.get('average_travel_time', 0)
        baseline_count = baseline_data.get('incident_count', 0)
        new_count = new_data.get('incident_count', 0)
        
        incident_comparison = {
            "incident_type": incident_type,
            "incident_count": {
                "baseline": baseline_count,
                "new": new_count,
                "difference": new_count - baseline_count
            },
            "average_travel_time": {
                "baseline": round(baseline_time, 2) if baseline_time else None,
                "new": round(new_time, 2) if new_time else None,
                "difference": round(new_time - baseline_time, 2) if (baseline_time and new_time) else None,
                "percent_change": round(((new_time - baseline_time) / baseline_time * 100), 2) if baseline_time > 0 else None,
                "improved": new_time < baseline_time if (baseline_time and new_time) else None
            }
        }
        comparison["incident_type_comparison"].append(incident_comparison)
    
    # Calculate improvements summary
    improvements = {
        "response_time_improved": new_avg_response < baseline_avg_response,
        "coverage_improved": new_coverage > baseline_coverage,
        "p90_improved": new_p90 < baseline_p90,
        "stations_with_better_response": sum(1 for s in comparison["station_comparison"] 
                                             if s["average_travel_time"].get("improved")),
        "stations_with_worse_response": sum(1 for s in comparison["station_comparison"] 
                                            if not s["average_travel_time"].get("improved")),
        "new_stations_added": sum(1 for s in comparison["station_comparison"] if s["status"] == "new_station"),
        "stations_removed": sum(1 for s in comparison["station_comparison"] if s["status"] == "removed_station")
    }
    comparison["improvements"] = improvements
    
    # Summary text
    summary = {
        "overall_assessment": "improved" if (improvements["response_time_improved"] and improvements["coverage_improved"]) else 
                             "mixed" if (improvements["response_time_improved"] or improvements["coverage_improved"]) else 
                             "degraded",
        "key_findings": []
    }
    
    if improvements["response_time_improved"]:
        summary["key_findings"].append(f"Average response time improved by {abs(comparison['overall_metrics']['average_response_time']['difference']):.2f} seconds ({abs(comparison['overall_metrics']['average_response_time']['percent_change']):.1f}%)")
    else:
        summary["key_findings"].append(f"Average response time increased by {abs(comparison['overall_metrics']['average_response_time']['difference']):.2f} seconds ({abs(comparison['overall_metrics']['average_response_time']['percent_change']):.1f}%)")
    
    if improvements["coverage_improved"]:
        summary["key_findings"].append(f"Coverage improved by {comparison['overall_metrics']['coverage_percent']['difference']:.2f} percentage points")
    else:
        summary["key_findings"].append(f"Coverage decreased by {abs(comparison['overall_metrics']['coverage_percent']['difference']):.2f} percentage points")
    
    if improvements["new_stations_added"] > 0:
        summary["key_findings"].append(f"{improvements['new_stations_added']} new station(s) added")
    
    if improvements["stations_removed"] > 0:
        summary["key_findings"].append(f"{improvements['stations_removed']} station(s) removed")
    
    comparison["summary"] = summary
    
    return comparison