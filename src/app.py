from fastapi import FastAPI, Request
import os
from pathlib import Path
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import subprocess
import pandas as pd
from datetime import datetime, timedelta
import io
import random
from src.sim_result_processor import summarize_station_report_as_json, calculate_average_response_times_by_incident_type, evaluate_simulation_performance
import hashlib

import os
import sklearn
import pickle
import json
import pandas as pd
import geopandas as gpd
import numpy as np
from shapely.geometry import Point

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/get-stations")
def get_stations():
    data_dir = Path(__file__).parent.parent / "data"
    files = os.listdir(data_dir)
    stations = [f for f in files if f.startswith("stations")]
    return {"stations": stations}


@app.get("/status")
def status():
    return "Hello World"

@app.post("/get-incidents")
async def get_incidents(request: Request):
    import hashlib
    from fastapi import Response
    
    try:
        
        body = await request.json()
        print(body)
        model_id = body["modelId"]
        filters = body.get("filters", {})
        
        # Only handle historical_incidents model
        if model_id != "historical_incidents":
            return {"status": "error", "error": "Only historical_incidents model is supported"}
        
        # Extract date range from filters
        date_range = filters.get("dateRange", {})
        start_date = date_range.get("start")
        end_date = date_range.get("end")
        incident_type= filters.get("incidentType")
        
        if not start_date or not end_date:
            return {"status": "error", "error": "Date range with start and end dates is required"}
        
        # Generate a unique filename based on the query parameters
        query_hash = hashlib.md5(f"{model_id}_{start_date}_{end_date}".encode()).hexdigest()
        query_filename = f"historical_{start_date}_{end_date}_{query_hash[:8]}.csv"
        
        # Define paths
        data_dir = Path(__file__).parent.parent / "data"
        query_dir = data_dir / "incidents" / "historical" / incident_type / "query"

        query_path = query_dir / query_filename

        
        if incident_type == "ems_fire":
            source_file = data_dir / "incidents_export_apparatus.csv"
        else:
            source_file = data_dir / "incidents_export_apparatus_fire.csv"
        
        # Ensure query directory exists
        query_dir.mkdir(parents=True, exist_ok=True)
        
        # Check if the filtered query already exists
        if query_path.exists():
            print(f"Using cached query: {query_filename}")
            # Read the existing filtered CSV
            with open(query_path, 'r') as f:
                csv_content = f.read()
        else:
            print(f"Creating new filtered query: {query_filename}")
            # Load the source data and filter by date range
            df = pd.read_csv(source_file)
            df['datetime'] = pd.to_datetime(df['datetime'])
            
            # Filter by date range
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            filtered_df = df[(df['datetime'] >= start_dt) & (df['datetime'] <= end_dt)]
            
            if filtered_df.empty:
                return {"status": "error", "error": f"No incidents found in date range {start_date} to {end_date}"}
            
            # Convert back to string format for CSV
            filtered_df['datetime'] = filtered_df['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')
            
            # Save the filtered query
            filtered_df.to_csv(query_path, index=False)
            csv_content = filtered_df.to_csv(index=False)
            


        # Return the CSV content
        return Response(content=csv_content, media_type="text/csv")
        
    except Exception as e:
        print(f"Error in get_incidents: {str(e)}")
        return {"status": "error", "error": str(e)}
    

@app.get("/get-shapes")
def get_shapes():
    data_dir = Path(__file__).parent.parent / "data"
    files = os.listdir(data_dir)
    shapes = [f for f in files if f.endswith(".geojson")]
    return {"shapes": shapes}


@app.api_route("/run-comparison", methods=["GET", "POST"])
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
        
        # Define paths
        data_dir = Path(__file__).parent.parent / "data"
        logs_dir = Path(__file__).parent.parent / "logs"
        models_dir = Path(__file__).parent.parent / "models"
        
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
        incident_type = config.get('incidentType', 'fire')
        
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
        if config.get('dispatchPolicy') == 'nearest':
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
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        
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
        
        baseline_time = baseline_data.get('average travel time', 0)
        new_time = new_data.get('average travel time', 0)
        baseline_count = baseline_data.get('incident count', 0)
        new_count = new_data.get('incident count', 0)
        
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
                                             if s["average_travel_time"].get("improved") == True),
        "stations_with_worse_response": sum(1 for s in comparison["station_comparison"] 
                                            if s["average_travel_time"].get("improved") == False),
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


@app.api_route("/run-simulation", methods=["GET", "POST"])
async def run_simulation(request: Request):
    payload = None
    if request.method == "POST":
        payload = await request.json()
        print("Received payload:", payload)
    await asyncio.sleep(1)
    return {"status": "success", "total_incidents": 100, "payload": payload}

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

@app.post("/run-simulation2")
async def run_simulation2(request: Request):
    # Parse the incoming JSON payload first
    payload = await request.json()

    # Define paths
    data_dir = Path(__file__).parent.parent / "data"
    logs_dir = Path(__file__).parent.parent / "logs"
    models_dir = Path(__file__).parent.parent / "models"
    
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
            print(query_path)
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

        "REPORT_CSV_PATH": str(logs_dir_save / "incident_report.csv"),
        "STATION_REPORT_CSV_PATH": str(logs_dir_save / "station_report.csv"),
        "DURATION_MATRIX_PATH": str(logs_dir / "duration_matrix.bin"),
        "DISTANCE_MATRIX_PATH": str(logs_dir / "distance_matrix.bin"),
        "MATRIX_CSV_PATH": str(logs_dir / "matrix.csv"),
        "FIREBEATS_MATRIX_PATH": str(logs_dir / "beats.bin"),
        "ZONE_MAP_PATH": str(data_dir / "zones.csv"),
        "BEATS_SHAPEFILE_PATH": str(data_dir / "beats_shpfile.geojson"),
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

@app.post("/process-incidents")
async def process_incidents(request: Request):
    try:
        # Get raw CSV content from request body
        csv_data = await request.body()
        csv_data = csv_data.decode('utf-8')
        
        if not csv_data.strip():
            return {"status": "error", "error": "No CSV data provided"}
        
        # Read CSV data from string
        df = pd.read_csv(io.StringIO(csv_data))
        
        # Count incidents per type
        incident_counts = df['incident_type'].value_counts().to_dict()
        
        # Convert datetime strings to datetime objects for time calculations
        df['datetime'] = pd.to_datetime(df['datetime'])
        df = df.sort_values('datetime')
        
        # Calculate time differences between consecutive incidents (in minutes)
        time_diffs = df['datetime'].diff().dt.total_seconds() / 60.0
        # Remove NaN (first incident has no previous incident)
        time_diffs = time_diffs.dropna()
        
        # Calculate average time between incidents
        avg_time_between_incidents = float(time_diffs.mean()) if len(time_diffs) > 0 else 0.0
        result = {
            "status": "success",
            "incident_counts": incident_counts,
            "average_time_between_incidents_minutes": avg_time_between_incidents,
            "total_incidents": len(df)
        }
        print(result)
        return result

    except Exception as e:
        return {"status": "error", "error": str(e)}


# Load function for use in another repository
def load_incident_prediction_system(load_directory):
    """
    Loads all components of the incident prediction system.
    
    Returns:
        dict: Dictionary containing all loaded components
    """
    try:
        # Import here to avoid module-level import issues with uvicorn
        from models.survival_forecaster import SurvivalRegressionForecaster
        
        # Make the class available in the global namespace for pickle
        import sys
        sys.modules['__main__'].SurvivalRegressionForecaster = SurvivalRegressionForecaster
        
        components = {}
        
        # Load configuration first
        with open(os.path.join(load_directory, 'config.json'), 'r') as f:
            config = json.load(f)
        components['config'] = config

        
        # Load the trained model
        with open(os.path.join(load_directory, 'survival_model.pkl'), 'rb') as f:
            model = pickle.load(f)
        components['model'] = model

        
        # Load the scaler
        with open(os.path.join(load_directory, 'scaler.pkl'), 'rb') as f:
            scaler = pickle.load(f)
        components['scaler'] = scaler

        
        # Load grid geometry
        grid_geometry = gpd.read_file(os.path.join(load_directory, 'grid_geometry.geojson'))
        components['grid_geometry'] = grid_geometry

        
        # Load clustering data
        clustering_data = pd.read_csv(os.path.join(load_directory, 'clustering_data.csv'))
        components['clustering_data'] = clustering_data

        
        # Load incident probabilities
        with open(os.path.join(load_directory, 'incident_probabilities.pkl'), 'rb') as f:
            incident_probabilities = pickle.load(f)
        components['incident_probabilities'] = incident_probabilities

        
        return components
        
    except Exception as e:
        print(f"Error loading prediction system: {e}")
        raise e

# Global variable to store components (loaded lazily) - one per incident type
components_cache = {}

def get_prediction_components(incident_type='fire'):
    """Lazy loading of prediction system components based on incident type"""
    global components_cache
    
    # Check if this incident type is already cached
    if incident_type not in components_cache:
        try:
            # Determine the correct model directory based on incident type
            if incident_type == 'fire':
                models_dir = Path(__file__).parent.parent / "models" / "incident_prediction_system_fire"
            elif incident_type == 'ems_fire':
                models_dir = Path(__file__).parent.parent / "models" / "incident_prediction_system"
            else:
                models_dir = Path(__file__).parent.parent / "models" / "incident_prediction_system"
                
            print(f"Loading incident prediction system for '{incident_type}' from {models_dir}")
            components_cache[incident_type] = load_incident_prediction_system(str(models_dir))
        except Exception as e:
            print(f"Warning: Could not load prediction system for '{incident_type}': {e}")
            components_cache[incident_type] = {}
    
    return components_cache[incident_type]

def generate_random_incidents(start_date: str, end_date: str):
    """Generate random incidents within the given date range."""
    # Sample Nashville coordinates
    nashville_locations = [
        (36.160913, -86.776837),
        (36.16272, -86.775347),
        (36.160659, -86.777427),
        (36.216591, -86.790614),
        (36.167447, -86.79742),
        (36.17946, -86.798507),
        (36.161285, -86.775956),
        (36.160388, -86.778176),
        (36.045748, -86.674218),
        (36.16095, -86.775805)
    ]
    
    incident_types = ["EMS & Rescue", "Fire", "Service Call", "False Alarm False Call"]
    incident_levels = ["Low", "Moderate", "High"]
    categories = ["Nine", "Four", "Five", "ThreeF"]
    
    # Parse dates
    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    
    # Generate random number of incidents (10-100)
    num_incidents = random.randint(10, 100)
    
    incidents = []
    for i in range(num_incidents):
        # Random timestamp within the date range
        time_diff = end_dt - start_dt
        random_seconds = random.randint(0, int(time_diff.total_seconds()))
        incident_time = start_dt + timedelta(seconds=random_seconds)
        
        # Random location from Nashville coordinates
        lat, lon = random.choice(nashville_locations)
        
        incident = {
            "incident_id": 289724 + i,
            "lat": lat,
            "lon": lon,
            "incident_type": random.choice(incident_types),
            "incident_level": random.choice(incident_levels),
            "datetime": incident_time.strftime("%Y-%m-%d %H:%M:%S"),
            "category": random.choice(categories)
        }
        incidents.append(incident)
    
    return incidents


def random_incident_selector(cluster_label, probability_dict):
    """
    Randomly selects a category and incident type for a given cluster based on historical probabilities.
    
    Returns:
        tuple: (selected_category, selected_incident_type)
    """
    if cluster_label not in probability_dict:
        return None, None
    
    cluster_probs = probability_dict[cluster_label]
    
    # Step 1: Randomly select category based on probabilities
    categories = list(cluster_probs['categories'].keys())
    category_weights = list(cluster_probs['categories'].values())
    selected_category = np.random.choice(categories, p=category_weights)
    
    # Step 2: Randomly select incident type within the selected category
    if selected_category in cluster_probs['incident_types']:
        incident_types = list(cluster_probs['incident_types'][selected_category].keys())
        incident_type_weights = list(cluster_probs['incident_types'][selected_category].values())
        selected_incident_type = np.random.choice(incident_types, p=incident_type_weights)
    else:
        selected_incident_type = None
    
    return selected_category, selected_incident_type

# Function to generate random coordinates within a cell
def generate_random_coordinates_in_cell(cell_id, dav_grids2):
    """
    Generates random latitude and longitude coordinates within a specific cell.
    
    Args:
        cell_id: The ID of the cell
        dav_grids2: The GeoDataFrame containing cell geometries
    
    Returns:
        tuple: (latitude, longitude) coordinates within the cell
    """
    # Get the geometry for the specific cell
    cell_geometry = dav_grids2[dav_grids2['cell_id'] == cell_id]['geometry'].iloc[0]
    
    # Get the bounds of the cell
    minx, miny, maxx, maxy = cell_geometry.bounds
    
    # Generate random points until one falls within the cell geometry
    max_attempts = 100
    for _ in range(max_attempts):
        # Generate random coordinates within the bounding box
        random_lon = np.random.uniform(minx, maxx)
        random_lat = np.random.uniform(miny, maxy)
        
        # Create a point and check if it's within the cell geometry
        from shapely.geometry import Point
        test_point = Point(random_lon, random_lat)
        
        if cell_geometry.contains(test_point) or cell_geometry.touches(test_point):
            return random_lat, random_lon
    
    # If no point found within geometry after max_attempts, return centroid
    centroid = cell_geometry.centroid
    return centroid.y, centroid.x



# Enhanced incident prediction function with random category/type assignment and coordinates
def predict_incidents_with_types_and_coordinates(start_date, end_date, incident_type='fire'):
    """
    Predicts incidents with randomly assigned categories, types, and coordinates based on historical probabilities.
    """
    # Get prediction components lazily
    components = get_prediction_components(incident_type=incident_type)
    if not components:
        raise ValueError("Prediction system not available")
    
    # Convert to datetime
    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)
    clustering_df=components['clustering_data']
    features=components['config']['features']
    reg_columns=components['config']['reg_columns']
    cat_columns=components['config']['cat_columns']
    scaler=components['scaler']
    model=components['model']
    dav_grids2=components['grid_geometry']
    incident_prob_dict=components['incident_probabilities']
    
    # Get unique cells from clustering_df
    unique_cells = clustering_df['cell_id'].unique()
    
    # Get the expected feature columns from training (excluding the original categorical columns)
    expected_features = [col for col in features if col not in reg_columns]
    
    all_incidents = []
    
    for cell_id in unique_cells:
        # Get cell information
        cell_info = clustering_df[clustering_df['cell_id'] == cell_id].iloc[0]
        
        # Start generating incidents from start_date
        current_time = start_date
        
        while current_time < end_date:
            # Create features for current time
            prediction_row = {
                'cell_id': cell_id,
                'cluster_label': cell_info['cluster_label'],
                'historical_density': cell_info['historical_density'],
                'hour': current_time.hour,
                'day': current_time.day,
                'month': current_time.month,
                'weekday': int(current_time.weekday() >= 5),
                'year': current_time.year
            }
            
            # Create window feature
            if 0 <= current_time.hour <= 3:
                prediction_row['window'] = 0
            elif 4 <= current_time.hour <= 7:
                prediction_row['window'] = 1
            elif 8 <= current_time.hour <= 11:
                prediction_row['window'] = 2
            elif 12 <= current_time.hour <= 15:
                prediction_row['window'] = 3
            elif 16 <= current_time.hour <= 19:
                prediction_row['window'] = 4
            else:
                prediction_row['window'] = 5
            
            # Convert to DataFrame for processing
            temp_df = pd.DataFrame([prediction_row])
            
            # Create dummy variables manually to match training structure
            temp_df_encoded = temp_df.copy()
            
            # Initialize all expected categorical features to 0
            for feature in expected_features:
                temp_df_encoded[feature] = 0
            
            # Set the appropriate dummy variables to 1 based on current values
            # Hour dummies (skip hour_0 as it's dropped)
            if current_time.hour > 0:
                hour_col = f'hour_{current_time.hour}'
                if hour_col in temp_df_encoded.columns:
                    temp_df_encoded[hour_col] = 1
            
            # Month dummies (skip month_1 as it's dropped)
            if current_time.month > 1:
                month_col = f'month_{current_time.month}'
                if month_col in temp_df_encoded.columns:
                    temp_df_encoded[month_col] = 1
            
            # Weekday dummies (skip weekday_0 as it's dropped)
            weekday_val = int(current_time.weekday() >= 5)
            if weekday_val > 0:
                weekday_col = f'weekday_{weekday_val}'
                if weekday_col in temp_df_encoded.columns:
                    temp_df_encoded[weekday_col] = 1
            
            # Window dummies (skip window_0 as it's dropped)
            window_val = prediction_row['window']
            if window_val > 0:
                window_col = f'window_{window_val}'
                if window_col in temp_df_encoded.columns:
                    temp_df_encoded[window_col] = 1
            
            # Year dummies (skip the first year as it's dropped)
            year_cols = [col for col in expected_features if col.startswith('year_')]
            if year_cols:
                min_year = min([int(col.split('_')[1]) for col in year_cols])
                if current_time.year > min_year:
                    year_col = f'year_{current_time.year}'
                    if year_col in temp_df_encoded.columns:
                        temp_df_encoded[year_col] = 1
            
            # Drop original categorical columns
            for col in cat_columns:
                if col in temp_df_encoded.columns:
                    temp_df_encoded.drop(columns=[col], inplace=True)
            
            # Scale regression columns
            temp_df_encoded[reg_columns] = scaler.transform(temp_df_encoded[reg_columns])
            
            # Ensure all features are present and in correct order
            temp_df_encoded = temp_df_encoded.reindex(columns=['cell_id', 'cluster_label'] + features, fill_value=0)
            
            # Predict time until next incident
            temp_df_encoded = model.predict(temp_df_encoded, {'features': features})
            predicted_time_bet = temp_df_encoded['predicted_time_bet'].iloc[0]
            
            # Add the predicted time to current time to get next incident time
            next_incident_time = current_time + pd.Timedelta(hours=predicted_time_bet)
            next_incident_time = next_incident_time.round('s')
            
            # If next incident is within our time range, record it
            if next_incident_time <= end_date:
                # Randomly select category and incident type based on cluster
                cluster_label = cell_info['cluster_label']
                selected_category, selected_incident_type = random_incident_selector(cluster_label, incident_prob_dict)
                
                # Generate random coordinates within the cell
                random_lat, random_lon = generate_random_coordinates_in_cell(cell_id, dav_grids2)
                
                # Generate a unique incident ID (could use counter or timestamp-based)
                incident_id = len(all_incidents) + 1000000  # Start from 1000000 to avoid conflicts
                
                incident_record = {
                    'incident_id': incident_id,
                    'lat': random_lat,
                    'lon': random_lon,
                    'incident_type': selected_incident_type if selected_incident_type else 'Unknown',
                    'incident_level': np.random.choice(['Low', 'Moderate', 'High'], p=[0.4, 0.4, 0.2]),  # Random level
                    'datetime': next_incident_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'category': selected_category if selected_category else 'Unknown'
                }
                all_incidents.append(incident_record)
                
                # Update current time to the incident time
                current_time = next_incident_time
            else:
                break
    
    # Convert to DataFrame and sort by time
    predicted_data = pd.DataFrame(all_incidents)
    if not predicted_data.empty:
        predicted_data = predicted_data.sort_values('datetime').reset_index(drop=True)
    
    return predicted_data

@app.post("/generate-incidents")
async def generate_incidents(request: Request):

    from fastapi import Response
    
    try:
        payload = await request.json()
        print(payload)

        date_range = payload.get("dateRange", {})
        start_date = date_range.get("startDate") or date_range.get("start")
        end_date = date_range.get("endDate") or date_range.get("end")
        incident_type = payload.get("incidentType", "fire")  # Extract incident type from payload
        
        print(f"Generating {incident_type} incidents from {start_date} to {end_date}")

        if not start_date or not end_date:
            print("Invalid input")
            return {"status": "error", "error": "startDate and endDate are required"}
        
        # Extract date part for filename (YYYY-MM-DD)
        start_date_str = start_date[:10] if 'T' in start_date else start_date
        end_date_str = end_date[:10] if 'T' in end_date else end_date
        
        # Generate a unique filename based on the query parameters (matching run-simulation2 logic)
        query_hash = hashlib.md5(f"synthetic_incidents_{start_date_str}_{end_date_str}".encode()).hexdigest()
        query_filename = f"synthetic_{start_date_str}_{end_date_str}_{query_hash[:8]}.csv"
        
        # Define paths
        data_dir = Path(__file__).parent.parent / "data"
        query_dir = data_dir / "incidents" / "synthetic" / incident_type / "query"  # Use synthetic directory
        query_path = query_dir / query_filename
        
        # Ensure query directory exists
        query_dir.mkdir(parents=True, exist_ok=True)
        
        # Check if the synthetic query already exists
        if query_path.exists():
            print(f"Using cached synthetic query: {query_filename}")
            # Read the existing synthetic CSV
            with open(query_path, 'r') as f:
                csv_content = f.read()
        else:
            print(f"Creating new synthetic query for {incident_type}: {query_filename}")

            # Generate random incidents using the prediction system with incident type
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
        
        # Return raw CSV with proper content type
        return Response(content=csv_content, media_type="text/csv")
        
    except Exception as e:
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
