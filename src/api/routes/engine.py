"""FastAPI application for simulation-db API."""

import asyncio
import hashlib
import subprocess
import pandas as pd
from fastapi import APIRouter

import src.core.config as constants
from src.engine.incidents import predict_incidents_with_types_and_coordinates
from src.engine.results import calculate_average_response_times_by_incident_type, evaluate_simulation_performance, summarize_station_report_as_json
from src.engine.simulation import calculate_comparison_stats, create_stations_csv_from_payload, run_simulation_internal
from src.schemas.engine import (
    RunComparisonRequest,
    RunComparisonResponse,
    RunSimulationRequest,
    SimulationRunResponse,
)

router = APIRouter()

# Define paths
data_dir = constants.DATA_DIR
logs_dir = constants.BASE_DIR / "logs"
models_dir = constants.DATA_DIR / "models"

@router.post("/run-comparison", response_model=RunComparisonResponse)
async def run_comparison(payload: RunComparisonRequest):
    """
    Runs simulations for both baseline and new configurations and returns comparative statistics.
    """
    try:
        payload_dict = payload.model_dump(by_alias=True)
        print("Received payload for comparison:", payload_dict)

        baseline_config = payload_dict.get('baseline', {})
        new_config = payload_dict.get('newConfig', {})
        
        if not baseline_config or not new_config:
            return {"status": "error", "error": "Both baseline and newConfig are required"}
        
        # Create temporary directories for comparison runs
        import time
        timestamp = int(time.time())
        baseline_temp_dir = logs_dir / "comparison_temp" / f"baseline_{timestamp}"
        new_config_temp_dir = logs_dir / "comparison_temp" / f"newconfig_{timestamp}"
        baseline_temp_dir.mkdir(parents=True, exist_ok=True)
        new_config_temp_dir.mkdir(parents=True, exist_ok=True)
        
        # ==================== RUN SIMULATIONS IN PARALLEL ====================
        print("\n=== Running Simulations in Parallel ===")
        baseline_task = run_simulation_internal(
            config=baseline_config,
            data_dir=data_dir,
            logs_dir=baseline_temp_dir,
            models_dir=models_dir,
            config_name="baseline"
        )

        new_task = run_simulation_internal(
            config=new_config,
            data_dir=data_dir,
            logs_dir=new_config_temp_dir,
            models_dir=models_dir,
            config_name="newconfig"
        )

        # Await both tasks to complete
        baseline_result, new_result = await asyncio.gather(baseline_task, new_task)

        if baseline_result.get('status') != 'success':
            return {
                "status": "error",
                "error": "Baseline simulation failed",
                "baseline_result": baseline_result
            }

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


@router.post("/run-simulation", response_model=SimulationRunResponse)
async def run_simulation(payload: RunSimulationRequest):
    # Parse the incoming JSON payload first
    payload_dict = payload.model_dump(by_alias=True)
    

    models = payload_dict.get('models') or {}
    
    # Create user-defined stations file if stations are provided
    user_stations_path = data_dir / "stations_with_apparatus_by_user.csv"
    if 'stations' in payload_dict and payload_dict['stations']:
        create_stations_csv_from_payload(payload_dict['stations'], user_stations_path)
    
    # Determine incident file path based on payload
    incidents_path = str(data_dir / "incidents_small.csv")  # default
    incident_type = payload_dict.get('incident_type') or 'fire'

    # Ensure these exist for log directory naming even when dateRange isn't provided.
    start_date = "NA"
    end_date = "NA"
    
    if models.get('incident') == 'historical_incidents':
        # Use the filtered incidents from get-incidents endpoint
        date_range = payload_dict.get('date_range', {}) or {}
        if date_range.get('start_date') and date_range.get('end_date'):
            start_date = date_range['start_date'][:10]  # Extract date part (YYYY-MM-DD)
            end_date = date_range['end_date'][:10]
            
            from src.engine.simulation import get_or_create_historical_incidents
            try:
                incidents_path = get_or_create_historical_incidents(start_date, end_date, incident_type, data_dir)
            except ValueError as e:
                return {"status": "error", "error": str(e)}
            
                
    
    if models.get('incident') == 'synthetic_incidents':
        # Use synthetic incidents file
        date_range = payload_dict.get('date_range', {}) or {}
        if date_range.get('start_date') and date_range.get('end_date'):
            start_date = date_range['start_date'][:10]  # Extract date part (YYYY-MM-DD)
            end_date = date_range['end_date'][:10]
            query_hash = hashlib.md5(f"synthetic_incidents_{start_date}_{end_date}".encode()).hexdigest()
            query_filename = f"synthetic_{start_date}_{end_date}_{query_hash[:8]}.csv"
            query_path = data_dir / "incidents" / "synthetic" / incident_type / "query" / query_filename
            if not query_path.exists():
                predicted_incidents_df = predict_incidents_with_types_and_coordinates(start_date, end_date, incident_type=incident_type)
            
                # Convert DataFrame to list of dictionaries for CSV generation
                incidents = predicted_incidents_df.to_dict('records') if not predicted_incidents_df.empty else []
                
                # Convert to CSV format
                csv_header = "incident_id,lat,lon,incident_type,incident_level,datetime,category\n"
                csv_rows = []
                for incident in incidents:
                    row = f"{incident['incident_id']},{incident['lat']},{incident['lon']},{incident['incident_type']},{incident['incident_level']},{incident['datetime']},{incident['category']}"
                    csv_rows.append(row)
                
                csv_content = csv_header + "\n".join(csv_rows)
                
                # Save the synthetic query for future use
                with open(query_path, 'w') as f:
                    f.write(csv_content)
                
                print(f"Generated {len(incidents)} synthetic incidents and saved to {query_filename}")
            incidents_path = str(query_path)
            print(f"Using filtered incidents: {incidents_path}")
            print(f"Using synthetic incidents: {incidents_path}")
    
    # Map dispatch policy from payload
    dispatch_policy = "FIREBEATS"  # default
    if payload_dict.get('dispatch_policy') == 'nearest':
        dispatch_policy = "NEAREST"
    elif models.get('dispatch') == 'nearest':
        dispatch_policy = "NEAREST"
        
    travel_time_model = models.get('travelTime', 'OSRM')
    if travel_time_model == 'ARCGIS':
        travel_time_model = "OSRM"

    # Map fire model type from payload
    fire_model_type = "ML"  # default
    service_time_model = models.get('serviceTime', 'ml_based')
    if service_time_model == 'ml_based':
        fire_model_type = "ML"
    elif service_time_model == 'constant':
        fire_model_type = "CONSTANT"
    elif service_time_model == 'empirical_servicetimes':
        fire_model_type = "HISTORICAL"
    station_data_option = payload_dict.get('station_data', 'default_stations')

    #create log directory based on configuration and date-range
    station_data_option = station_data_option or "default"
    dispatch_policy = dispatch_policy or "default"
    fire_model_type = fire_model_type or "default"
    travel_time_model = travel_time_model or "default"
    start_date = start_date or "NA"
    end_date = end_date or "NA"
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
        "APPARATUS_CSV_PATH": str(user_stations_path if user_stations_path.exists() else data_dir / "stations_with_apparatus.csv"),
        "BOUNDS_GEOJSON_PATH": str(data_dir / "bounds.geojson"),
        "NFD_RESPONSE_CSV_PATH": str(data_dir / "NFDResponse.csv"),
        "RESOLUTION_STATS_CSV_PATH": str(data_dir / "response_time_summary2.csv"),
        
        "MEAN_MATRIX_PATH": str(data_dir / "interpolation_fire/mean_zone_travel_time_matrix.json") if incident_type == 'fire' else str(data_dir / "interpolation_data/mean_zone_travel_time_matrix.json"),
        "STD_MATRIX_PATH": str(data_dir / "interpolation_fire/std_zone_travel_time_matrix.json") if incident_type == 'fire' else str(data_dir / "interpolation_data/std_zone_travel_time_matrix.json"),
        "ZONE_INFO_PATH": str(data_dir / "interpolation_fire/zone_fire_station_info.json") if incident_type == 'fire' else str(data_dir / "interpolation_data/zone_fire_station_info.json"),

        "REPORT_CSV_PATH": str(logs_dir_save / "incident_report.csv"),
        "STATION_REPORT_CSV_PATH": str(logs_dir_save / "station_report.csv"),
        "DURATION_MATRIX_PATH": str(logs_dir / "duration_matrix.bin"),
        "DISTANCE_MATRIX_PATH": str(logs_dir / "distance_matrix.bin"),
        "MATRIX_CSV_PATH": str(logs_dir / "matrix.csv"),
        "FIREBEATS_MATRIX_PATH": str(logs_dir / "beats.bin"),
        "ZONE_MAP_PATH": str(data_dir / "zones.csv"),
        "BEATS_SHAPEFILE_PATH": str(data_dir / "beats_shpfile.geojson"),
        "RANDOM_SEED": 42,
        "PYTHON_PATH": "../../venvBOC/bin/python",
        "INCIDENT_MODEL_TYPE": "EMPIRICAL",
        "HOSPITALS_CSV_PATH": str(data_dir / "ems_stats" / "hospitals.csv"),
        "EMS_SCENE_TIME_STATS_PATH": str(data_dir / "ems_stats" / "ems_scene_time_stats.csv"),
        "EMS_TRANSPORT_STATS_PATH": str(data_dir / "ems_stats" / "ems_transport_stats.csv"),
        "HOSPITAL_TIME_STATS_PATH": str(data_dir / "ems_stats" / "hospital_time_stats.csv"),
        "ZONE_HOSPITAL_PROBS_PATH": str(data_dir / "ems_stats" / "zone_to_hospital_probs.csv"),
        "EMS_TRANSPORT_REPORT_PATH": str(logs_dir_save / "ems_transport_report.csv"),
    }

    # Update config with any direct overrides from the payload (excluding processed fields)
    config_overrides = {
        k: v
        for k, v in payload_dict.items()
        if k
        not in [
            # snake_case
            'stations',
            'date_range',
            'models',
            'dispatch_policy',
            'station_data',
            # camelCase (backward compatibility)
            'dateRange',
            # other historical exclusions
            'selectedIncidentFile',
            'selectedStationFile',
            'responseTime',
            'maxDistance',
            'options',
        ]
    }
    config.update(config_overrides)


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
        f"--INCIDENT_MODEL_TYPE={config['INCIDENT_MODEL_TYPE']}",
        f"--HOSPITALS_CSV_PATH={config['HOSPITALS_CSV_PATH']}",
        f"--EMS_SCENE_TIME_STATS_PATH={config['EMS_SCENE_TIME_STATS_PATH']}",
        f"--EMS_TRANSPORT_STATS_PATH={config['EMS_TRANSPORT_STATS_PATH']}",
        f"--HOSPITAL_TIME_STATS_PATH={config['HOSPITAL_TIME_STATS_PATH']}",
        f"--ZONE_HOSPITAL_PROBS_PATH={config['ZONE_HOSPITAL_PROBS_PATH']}",
        f"--EMS_TRANSPORT_REPORT_PATH={config['EMS_TRANSPORT_REPORT_PATH']}",
    ]
    print("Executing command:", " ".join(command))
    # Execute the command
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        station_report, total_incidents, average_response_time, coverage_percent, vehicle_json, P90_continuous = summarize_station_report_as_json(config['STATION_REPORT_CSV_PATH'], config['REPORT_CSV_PATH'])
        average_response_time_per_incident_type = calculate_average_response_times_by_incident_type(config['STATION_REPORT_CSV_PATH'], config['REPORT_CSV_PATH'],incidents_path)
        print("Simulation completed successfully.")
        if (station_data_option == 'default_stations') & (models.get('incident') == 'historical_incidents'):
            if incident_type == 'fire':
                evaluation= evaluate_simulation_performance(config['REPORT_CSV_PATH'], config['STATION_REPORT_CSV_PATH'], data_dir / "incident_resolution_times_fire.csv", incident_type='fire')
                
            else:
                evaluation= evaluate_simulation_performance(config['REPORT_CSV_PATH'], config['STATION_REPORT_CSV_PATH'], data_dir / "incident_resolution_times.csv")
            
            result = {"status": "success", "total_incidents": total_incidents, "station_report": station_report, "average_response_time": float(average_response_time), "coverage_percent": coverage_percent, "vehicle_report": vehicle_json, "average_response_time_per_incident_type": average_response_time_per_incident_type, "P90_continuous": float(P90_continuous), "evaluation": evaluation}
            # print(evaluation['overall_summary'])
            print("average_response_time:", float(average_response_time), "coverage_percent:", coverage_percent, "P90_continuous:", float(P90_continuous))
            return result
        #print simulator stdout and stderr for debugging

        result = {"status": "success", "total_incidents": total_incidents, "station_report": station_report, "average_response_time": float(average_response_time), "coverage_percent": coverage_percent, "vehicle_report": vehicle_json, "average_response_time_per_incident_type": average_response_time_per_incident_type, "P90_continuous": float(P90_continuous)}
        print(result)
        return result
    except subprocess.CalledProcessError as e:
        print("Error executing simulation:", e.stderr)
        return {"status": "error", "error": e.stderr}