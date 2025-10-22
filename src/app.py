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
from src.sim_result_processor import summarize_station_report_as_json

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



@app.post("/get-incidents")
async def get_incidents(request: Request):
    import hashlib
    from fastapi import Response
    
    try:
        body = await request.json()
        model_id = body["modelId"]
        filters = body.get("filters", {})
        
        # Only handle historical_incidents model
        if model_id != "historical_incidents":
            return {"status": "error", "error": "Only historical_incidents model is supported"}
        
        # Extract date range from filters
        date_range = filters.get("dateRange", {})
        start_date = date_range.get("start")
        end_date = date_range.get("end")
        
        if not start_date or not end_date:
            return {"status": "error", "error": "Date range with start and end dates is required"}
        
        # Generate a unique filename based on the query parameters
        query_hash = hashlib.md5(f"{model_id}_{start_date}_{end_date}".encode()).hexdigest()
        query_filename = f"historical_{start_date}_{end_date}_{query_hash[:8]}.csv"
        
        # Define paths
        data_dir = Path(__file__).parent.parent / "data"
        query_dir = data_dir / "incidents" / "historical" / "query"
        query_path = query_dir / query_filename
        source_file = data_dir / "incidents_export_apparatus.csv"
        
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

@app.api_route("/run-simulation", methods=["GET", "POST"])
async def run_simulation(request: Request):
    payload = None
    if request.method == "POST":
        payload = await request.json()
        print("Received payload:", payload)
    await asyncio.sleep(1)
    return {"status": "success", "total_incidents": 100, "payload": payload}

@app.post("/run-simulation2")
async def run_simulation2(request: Request):
    # Define the JSON configuration
    await asyncio.sleep(5)
    data_dir = Path(__file__).parent.parent / "data"
    logs_dir = Path(__file__).parent.parent / "logs"
    models_dir = Path(__file__).parent.parent / "models"
    config = {
        "OSRM_URL": "http://localhost:8080/table/v1/driving/",
        "BASE_OSRM_URL": "http://localhost:8080",
        "DISPATCH_POLICY": "FIREBEATS",
        "FIRE_MODEL_TYPE": "ML",
        "MODEL_PATH": str(models_dir / "fire_incident_gb_model.onnx"),
        "FEATURES_PATH": str(models_dir / "fire_model_features_mapping.json"),
        
        "INCIDENTS_CSV_PATH": str(data_dir / "incidents_small.csv"),
        # "STATIONS_CSV_PATH": str(data_dir / "stations.csv"),
        "APPARATUS_CSV_PATH": str(data_dir / "stations_with_apparatus.csv"),
        "BOUNDS_GEOJSON_PATH": str(data_dir / "bounds.geojson"),
        "NFD_RESPONSE_CSV_PATH": str(data_dir / "NFDResponse.csv"),
        "RESOLUTION_STATS_CSV_PATH": str(data_dir / "response_time_summary.csv"),
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
    print("config before parsing payload:", config)
    # Parse the incoming JSON payload
    payload = await request.json()
    print("Received payload:", payload)

    # print("Current config before update:", config)
    # Update the config with any overrides from the payload
    config.update(payload)

    # print("Updated config:", config)
    # Construct the command for the C++ simulator
    command = [
        "./data/fire_simulator",
        f"--INCIDENTS_CSV_PATH={config['INCIDENTS_CSV_PATH']}",
        # f"--STATIONS_CSV_PATH={config['STATIONS_CSV_PATH']}",
        f"--APPARATUS_CSV_PATH={config['APPARATUS_CSV_PATH']}",
        f"--FIRE_MODEL_TYPE={config['FIRE_MODEL_TYPE']}",
        f"--MODEL_PATH={config['MODEL_PATH']}",
        f"--FEATURES_PATH={config['FEATURES_PATH']}",
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
        station_report, total_incidents, average_response_time, coverage_percent = summarize_station_report_as_json(config['STATION_REPORT_CSV_PATH'])
        print("Simulation completed successfully.")

        result = {"status": "success", "total_incidents": total_incidents, "station_report": station_report, "average_response_time": float(average_response_time), "coverage_percent": coverage_percent}
        print(result)
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

@app.post("/generate-incidents")
async def generate_incidents(request: Request):
    from fastapi import Response
    
    try:
        payload = await request.json()
        print(payload)
        start_date = payload.get("start_date")
        end_date = payload.get("end_date")

        if not start_date or not end_date:
            print("Invalid input")
            # Return error as JSON for invalid input
            return {"status": "error", "error": "startDate and endDate are required"}
        
        print("HEllo")
        # Generate random incidents
        incidents = generate_random_incidents(start_date, end_date)
        
        # Convert to CSV format
        csv_header = "incident_id,lat,lon,incident_type,incident_level,datetime,category\n"
        csv_rows = []
        for incident in incidents:
            row = f"{incident['incident_id']},{incident['lat']},{incident['lon']},{incident['incident_type']},{incident['incident_level']},{incident['datetime']},{incident['category']}"
            csv_rows.append(row)
        
        csv_content = csv_header + "\n".join(csv_rows)
        print(csv_content)
        # Return raw CSV with proper content type
        return Response(content=csv_content, media_type="text/csv")
        
    except Exception as e:
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
