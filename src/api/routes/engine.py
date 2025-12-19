"""FastAPI application for simulation-db API."""

import asyncio
import hashlib
from pathlib import Path
import subprocess
from fastapi import APIRouter, Request

import src.core.config as constants
from src.engine.results import calculate_average_response_times_by_incident_type, evaluate_simulation_performance, summarize_station_report_as_json
from src.engine.simulation import calculate_comparison_stats, create_stations_csv_from_payload, run_simulation_internal

router = APIRouter()

# Define paths
data_dir = constants.DATA_DIR
logs_dir = constants.BASE_DIR / "logs"
models_dir = constants.BASE_DIR / "models"

@router.api_route("/run-comparison", methods=["POST"])
async def run_comparison(request: Request):
    """
    Runs simulations for both baseline and new configurations and returns comparative statistics.
    """
    if request.method == "GET":
        return {"status": "error", "error": "POST method required"}
    
    try:
        payload = await request.json()
        print("Received payload for comparison:", payload)
        
        baseline_config = payload.get('baseline', {})
        new_config = payload.get('newConfig', {})
        
        if not baseline_config or not new_config:
            return {"status": "error", "error": "Both baseline and newConfig are required"}
        
        # Create temporary directories for comparison runs
        import time
        timestamp = int(time.time())
        baseline_temp_dir = logs_dir / "comparison_temp" / f"baseline_{timestamp}"
        new_config_temp_dir = logs_dir / "comparison_temp" / f"newconfig_{timestamp}"
        baseline_temp_dir.mkdir(parents=True, exist_ok=True)
        new_config_temp_dir.mkdir(parents=True, exist_ok=True)
        
        # ==================== RUN BASELINE SIMULATION ====================
        print("\n=== Running Baseline Simulation ===")
        baseline_result = await run_simulation_internal(
            config=baseline_config,
            data_dir=data_dir,
            logs_dir=baseline_temp_dir,
            models_dir=models_dir,
            config_name="baseline"
        )
        
        if baseline_result.get('status') != 'success':
            return {
                "status": "error",
                "error": "Baseline simulation failed",
                "baseline_result": baseline_result
            }
        
        # ==================== RUN NEW CONFIGURATION SIMULATION ====================
        print("\n=== Running New Configuration Simulation ===")
        new_result = await run_simulation_internal(
            config=new_config,
            data_dir=data_dir,
            logs_dir=new_config_temp_dir,
            models_dir=models_dir,
            config_name="newconfig"
        )
        
        if new_result.get('status') != 'success':
            return {
                "status": "error",
                "error": "New configuration simulation failed",
                "new_result": new_result
            }
        print("\n=== Both Simulations Completed Successfully ===")

        
        # ==================== CALCULATE COMPARATIVE STATISTICS ====================
        comparison_stats = calculate_comparison_stats(baseline_result, new_result)
        
        # Clean up temporary directories (optional - comment out for debugging)
        # import shutil
        # shutil.rmtree(baseline_temp_dir, ignore_errors=True)
        # shutil.rmtree(new_config_temp_dir, ignore_errors=True)
        
        # Return comprehensive comparison results
        return_body = {
            "status": "success",
            "baseline": {
                "total_incidents": baseline_result.get('total_incidents'),
                "average_response_time": baseline_result.get('average_response_time'),
                "coverage_percent": baseline_result.get('coverage_percent'),
                "P90_continuous": baseline_result.get('P90_continuous'),
                "station_report": baseline_result.get('station_report'),
                "vehicle_report": baseline_result.get('vehicle_report'),
                "average_response_time_per_incident_type": baseline_result.get('average_response_time_per_incident_type')
            },
            "newConfig": {
                "total_incidents": new_result.get('total_incidents'),
                "average_response_time": new_result.get('average_response_time'),
                "coverage_percent": new_result.get('coverage_percent'),
                "P90_continuous": new_result.get('P90_continuous'),
                "station_report": new_result.get('station_report'),
                "vehicle_report": new_result.get('vehicle_report'),
                "average_response_time_per_incident_type": new_result.get('average_response_time_per_incident_type')
            },
            "comparison": comparison_stats,

        }

        
        # Clean up temporary directories forcefully
        import shutil
        comparison_temp_dir = logs_dir / "comparison_temp"
        if comparison_temp_dir.exists():
            shutil.rmtree(comparison_temp_dir, ignore_errors=True)

        
        print("return_body:", return_body)
        return return_body
        
    except Exception as e:
        print(f"Error in run_comparison: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


@router.post("/run-simulation")
async def run_simulation(request: Request):
    # Parse the incoming JSON payload first
    payload = await request.json()
    
    # Create user-defined stations file if stations are provided
    user_stations_path = data_dir / "stations_with_apparatus_by_user.csv"
    if 'stations' in payload and payload['stations']:
        create_stations_csv_from_payload(payload['stations'], user_stations_path)
    
    # Determine incident file path based on payload
    incidents_path = str(data_dir / "incidents_small.csv")  # default
    incident_type= payload.get('incidentType', 'fire')
    
    if payload.get('models', {}).get('incident') == 'historical_incidents':
        # Use the filtered incidents from get-incidents endpoint
        date_range = payload.get('dateRange', {})
        if date_range.get('startDate') and date_range.get('endDate'):
            
            start_date = date_range['startDate'][:10]  # Extract date part (YYYY-MM-DD)
            end_date = date_range['endDate'][:10]
            query_hash = hashlib.md5(f"historical_incidents_{start_date}_{end_date}".encode()).hexdigest()
            query_filename = f"historical_{start_date}_{end_date}_{query_hash[:8]}.csv"
            query_path = data_dir / "incidents" / "historical" / incident_type / "query" / query_filename
            if query_path.exists():
                incidents_path = str(query_path)
                print(f"Using filtered incidents: {incidents_path}")
    
    if payload.get('models', {}).get('incident') == 'synthetic_incidents':
        # Use synthetic incidents file
        date_range = payload.get('dateRange', {})
        if date_range.get('startDate') and date_range.get('endDate'):
            start_date = date_range['startDate'][:10]  # Extract date part (YYYY-MM-DD)
            end_date = date_range['endDate'][:10]
            query_hash = hashlib.md5(f"synthetic_incidents_{start_date}_{end_date}".encode()).hexdigest()
            query_filename = f"synthetic_{start_date}_{end_date}_{query_hash[:8]}.csv"
            query_path = data_dir / "incidents" / "synthetic" / incident_type / "query" / query_filename
            if query_path.exists():
                incidents_path = str(query_path)
                print(f"Using filtered incidents: {incidents_path}")
            print(f"Using synthetic incidents: {incidents_path}")
    
    # Map dispatch policy from payload
    dispatch_policy = "FIREBEATS"  # default
    if payload.get('dispatchPolicy') == 'nearest':
        dispatch_policy = "NEAREST"
    elif payload.get('models', {}).get('dispatch') == 'nearest':
        dispatch_policy = "NEAREST"
        
    travel_time_model = payload.get('models', {}).get('travelTime', 'OSRM')
    if travel_time_model == 'ARCGIS':
        travel_time_model = "OSRM"

    # Map fire model type from payload
    fire_model_type = "ML"  # default
    service_time_model = payload.get('models', {}).get('serviceTime', 'ml_based')
    if service_time_model == 'ml_based':
        fire_model_type = "ML"
    elif service_time_model == 'constant':
        fire_model_type = "CONSTANT"
    elif service_time_model == 'empirical_servicetimes':
        fire_model_type = "HISTORICAL"
    station_data_option = payload.get('stationData', 'default_stations')

    #create log directory based on configuration and date-range
    if station_data_option == 'default_stations':
        logs_dir_save = logs_dir / f"{dispatch_policy}_{fire_model_type}_{travel_time_model}_{start_date}_{end_date}"
    else:
        logs_dir_save = logs_dir / station_data_option / f"{dispatch_policy}_{fire_model_type}_{travel_time_model}_{start_date}_{end_date}"
    logs_dir_save.mkdir(parents=True, exist_ok=True)
    # Define the JSON configuration
    await asyncio.sleep(1)
    config = {
        "OSRM_URL": f"http://{constants.OSRM_HOST}:{constants.OSRM_PORT}/table/v1/driving/",
        "BASE_OSRM_URL": f"http://{constants.OSRM_HOST}:{constants.OSRM_PORT}",
        "DISPATCH_POLICY": dispatch_policy,
        "FIRE_MODEL_TYPE": fire_model_type,
        "MODEL_PATH": str(models_dir / "fire_incident_gb_model.onnx") if incident_type == 'fire' else str(models_dir / "ems_model" / "fire_incident_gb_model.onnx"),
        "FEATURES_PATH": str(models_dir / "fire_model_features_mapping.json") if incident_type == 'fire' else str(models_dir / "ems_model" / "fire_model_features_mapping.json"),
        "TRAVEL_TIME_MODEL_TYPE": travel_time_model,
        
        "INCIDENTS_CSV_PATH": incidents_path,
        "APPARATUS_CSV_PATH": str(user_stations_path if user_stations_path.exists() else constants.DATA_DIR / "stations_with_apparatus.csv"),
        "BOUNDS_GEOJSON_PATH": str(constants.DATA_DIR / "bounds.geojson"),
        "NFD_RESPONSE_CSV_PATH": str(constants.DATA_DIR / "NFDResponse.csv"),
        "RESOLUTION_STATS_CSV_PATH": str(constants.DATA_DIR / "response_time_summary2.csv"),
        
        "MEAN_MATRIX_PATH": str(constants.DATA_DIR / "interpolation_fire/mean_zone_travel_time_matrix.json") if incident_type == 'fire' else str(constants.DATA_DIR / "interpolation_data/mean_zone_travel_time_matrix.json"),
        "STD_MATRIX_PATH": str(constants.DATA_DIR / "interpolation_fire/std_zone_travel_time_matrix.json") if incident_type == 'fire' else str(constants.DATA_DIR / "interpolation_data/std_zone_travel_time_matrix.json"),
        "ZONE_INFO_PATH": str(constants.DATA_DIR / "interpolation_fire/zone_fire_station_info.json") if incident_type == 'fire' else str(constants.DATA_DIR / "interpolation_data/zone_fire_station_info.json"),

        "REPORT_CSV_PATH": str(logs_dir_save / "incident_report.csv"),
        "STATION_REPORT_CSV_PATH": str(logs_dir_save / "station_report.csv"),
        "DURATION_MATRIX_PATH": str(logs_dir / "duration_matrix.bin"),
        "DISTANCE_MATRIX_PATH": str(logs_dir / "distance_matrix.bin"),
        "MATRIX_CSV_PATH": str(logs_dir / "matrix.csv"),
        "FIREBEATS_MATRIX_PATH": str(logs_dir / "beats.bin"),
        "ZONE_MAP_PATH": str(constants.DATA_DIR / "zones.csv"),
        "BEATS_SHAPEFILE_PATH": str(constants.DATA_DIR / "beats_shpfile.geojson"),
        "RANDOM_SEED": 42,
        "PYTHON_PATH": "../../venvBOC/bin/python"
    }


    # Update config with any direct overrides from the payload (excluding processed fields)
    config_overrides = {k: v for k, v in payload.items() 
                       if k not in ['stations', 'dateRange', 'models', 'dispatchPolicy', 'stationData', 
                                   'selectedIncidentFile', 'selectedStationFile', 'responseTime', 
                                   'maxDistance', 'options']}
    config.update(config_overrides)
    

    # Construct the command for the C++ simulator
    # Construct the command for the C++ simulator
    command = [
        "./data/fire_simulator",
        f"--OSRM_URL={config['OSRM_URL']}",
        f"--BASE_OSRM_URL={config['BASE_OSRM_URL']}",
        f"--INCIDENTS_CSV_PATH={config['INCIDENTS_CSV_PATH']}",
        f"--APPARATUS_CSV_PATH={config['APPARATUS_CSV_PATH']}",
        f"--FIRE_MODEL_TYPE={config['FIRE_MODEL_TYPE']}",
        f"--MODEL_PATH={config['MODEL_PATH']}",
        f"--FEATURES_PATH={config['FEATURES_PATH']}",
        f"--TRAVEL_TIME_MODEL_TYPE={config['TRAVEL_TIME_MODEL_TYPE']}",
        f"--OSRM_URL={config['OSRM_URL']}",
        f"--BASE_OSRM_URL={config['BASE_OSRM_URL']}",
        f"--MEAN_MATRIX_PATH={config['MEAN_MATRIX_PATH']}",
        f"--STD_MATRIX_PATH={config['STD_MATRIX_PATH']}",
        f"--ZONE_INFO_PATH={config['ZONE_INFO_PATH']}",
        f"--DISPATCH_POLICY={config['DISPATCH_POLICY']}",
        f"--BOUNDS_GEOJSON_PATH={config['BOUNDS_GEOJSON_PATH']}",
        f"--NFD_RESPONSE_CSV_PATH={config['NFD_RESPONSE_CSV_PATH']}",
        f"--RESOLUTION_STATS_CSV_PATH={config['RESOLUTION_STATS_CSV_PATH']}",
        f"--REPORT_CSV_PATH={config['REPORT_CSV_PATH']}",
        f"--STATION_REPORT_CSV_PATH={config['STATION_REPORT_CSV_PATH']}",
        f"--DURATION_MATRIX_PATH={config['DURATION_MATRIX_PATH']}",
        f"--DISTANCE_MATRIX_PATH={config['DISTANCE_MATRIX_PATH']}",
        f"--MATRIX_CSV_PATH={config['MATRIX_CSV_PATH']}",
        f"--FIREBEATS_MATRIX_PATH={config['FIREBEATS_MATRIX_PATH']}",
        f"--ZONE_MAP_PATH={config['ZONE_MAP_PATH']}",
        f"--BEATS_SHAPEFILE_PATH={config['BEATS_SHAPEFILE_PATH']}",
        f"--RANDOM_SEED={config['RANDOM_SEED']}",
        f"--PYTHON_PATH={config['PYTHON_PATH']}",
    ]
    print("Executing command:", " ".join(command))
    # Execute the command
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        station_report, total_incidents, average_response_time, coverage_percent, vehicle_json, P90_continuous = summarize_station_report_as_json(config['STATION_REPORT_CSV_PATH'], config['REPORT_CSV_PATH'])
        average_response_time_per_incident_type = calculate_average_response_times_by_incident_type(config['STATION_REPORT_CSV_PATH'], config['REPORT_CSV_PATH'],incidents_path)
        print("Simulation completed successfully.")
        if (station_data_option == 'default_stations')&(payload.get('models', {}).get('incident') == 'historical_incidents'):
            if incident_type == 'fire':
                evaluation= evaluate_simulation_performance(config['REPORT_CSV_PATH'], config['STATION_REPORT_CSV_PATH'], data_dir / "incident_resolution_times_fire.csv", incident_type='fire')
                
            else:
                evaluation= evaluate_simulation_performance(config['REPORT_CSV_PATH'], config['STATION_REPORT_CSV_PATH'], data_dir / "incident_resolution_times.csv")
            
            result = {"status": "success", "total_incidents": total_incidents, "station_report": station_report, "average_response_time": float(average_response_time), "coverage_percent": coverage_percent, "vehicle_report": vehicle_json, "average_response_time_per_incident_type": average_response_time_per_incident_type, "P90_continuous": float(P90_continuous), "evaluation": evaluation}
            print(evaluation['overall_summary'])
            print("average_response_time:", float(average_response_time), "coverage_percent:", coverage_percent, "P90_continuous:", float(P90_continuous))
            return result
        #print simulator stdout and stderr for debugging

        result = {"status": "success", "total_incidents": total_incidents, "station_report": station_report, "average_response_time": float(average_response_time), "coverage_percent": coverage_percent, "vehicle_report": vehicle_json, "average_response_time_per_incident_type": average_response_time_per_incident_type, "P90_continuous": float(P90_continuous)}

        return result
    except subprocess.CalledProcessError as e:
        print("Error executing simulation:", e.stderr)
        return {"status": "error", "error": e.stderr}