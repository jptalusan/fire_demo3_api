from fastapi import FastAPI, Request
import os
from pathlib import Path
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import subprocess
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

@app.get("/get-incidents")
def get_incidents():
    data_dir = Path(__file__).parent.parent / "data"
    files = os.listdir(data_dir)
    incidents = [f for f in files if f.startswith("incidents")]
    return {"incidents": incidents}

@app.api_route("/run-simulation", methods=["GET", "POST"])
async def run_simulation(request: Request):
    payload = None
    if request.method == "POST":
        payload = await request.json()
        print("Received payload:", payload)
    await asyncio.sleep(1)
    return {"status": "success", "total_incidents": 5545451, "payload": payload}

@app.post("/run-simulation2")
async def run_simulation2(request: Request):
    # Define the JSON configuration
    config = {
        "OSRM_URL": "http://localhost:8080/table/v1/driving/",
        "BASE_OSRM_URL": "http://localhost:8080",
        "DISPATCH_POLICY": "NEAREST",
        "INCIDENTS_CSV_PATH": "/Users/jose/Developer/git/fire_simulator/data/incidents_ammar.csv",
        "STATIONS_CSV_PATH": "/Users/jose/Developer/git/fire_simulator/data/stations.csv",
        "APPARATUS_CSV_PATH": "/Users/jose/Developer/git/fire_simulator/data/stations_with_apparatus.csv",
        "BOUNDS_GEOJSON_PATH": "/Users/jose/Developer/git/fire_simulator/data/bounds.geojson",
        "NFD_RESPONSE_CSV_PATH": "/Users/jose/Developer/git/fire_simulator/data/NFDResponse.csv",
        "RESOLUTION_STATS_CSV_PATH": "/Users/jose/Developer/git/fire_simulator/data/response_time_summary.csv",
        "REPORT_CSV_PATH": "/Users/jose/Developer/git/fire_simulator/logs/incident_report.csv",
        "STATION_REPORT_CSV_PATH": "/Users/jose/Developer/git/fire_simulator/logs/station_report.csv",
        "DURATION_MATRIX_PATH": "/Users/jose/Developer/git/fire_simulator/logs/duration_matrix.bin",
        "DISTANCE_MATRIX_PATH": "/Users/jose/Developer/git/fire_simulator/logs/distance_matrix.bin",
        "MATRIX_CSV_PATH": "/Users/jose/Developer/git/fire_simulator/logs/matrix.csv",
        "FIREBEATS_MATRIX_PATH": "/Users/jose/Developer/git/fire_simulator/logs/beats.bin",
        "ZONE_MAP_PATH": "/Users/jose/Developer/git/fire_simulator/data/zones.csv",
        "BEATS_SHAPEFILE_PATH": "/Users/jose/Developer/git/fire_simulator/data/beats_shpfile.geojson",
        "RANDOM_SEED": 42,
        "PYTHON_PATH": "../../venvBOC/bin/python"
    }

    # Parse the incoming JSON payload
    payload = await request.json()
    # print("Received payload:", payload)
    # print("Current config before update:", config)
    # Update the config with any overrides from the payload
    config.update(payload)

    # Construct the command for the C++ simulator
    command = [
        "./data/fire_simulator",
        f"--INCIDENTS_CSV_PATH={config['INCIDENTS_CSV_PATH']}",
        f"--STATIONS_CSV_PATH={config['STATIONS_CSV_PATH']}",
        f"--APPARATUS_CSV_PATH={config['APPARATUS_CSV_PATH']}",
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
    # print("Executing command:", " ".join(command))
    # Execute the command
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        station_report = summarize_station_report_as_json(config['STATION_REPORT_CSV_PATH'])
        return {"status": "success", "output": result.stdout, "total_incidents": 5545451, "station_report": station_report, "average_response_time": 15.4,}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "error": e.stderr}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
