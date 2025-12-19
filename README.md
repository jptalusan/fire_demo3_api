# Fire Demo3 API

A FastAPI application that serves data files.

## Installation

Install dependencies:

```bash
pip install -e .
```

## Running

Run the application:

```bash
python src/app.py
```

Or with uvicorn:

```bash
uvicorn src.app:app --reload

# With debug
uv run uvicorn src.app:app --reload --log-level debug --host 0.0.0.0 --port 8000
```

## API

- GET /files: Returns a JSON list of files in the data directory.

## TRY THIS FROM GPT
Got it — you’re on **RHEL 8** and want to install everything needed to run this FastAPI app.

Here’s a clean, step-by-step setup guide:

---

### 🧰 1. Install system dependencies

RHEL 8 ships with an older Python by default, so you’ll need to ensure Python ≥3.9 is available.

```bash
sudo dnf install -y python3 python3-pip python3-virtualenv git
```

## Files Needed and File Output

### Files and Paths from data
- mean_zone_travel_time_matrix.json
- std_zone_travel_time_matrix.json
- zone_fire_station_info.json
- response_time_summary2.csv
- zones.csv
- beats_shpfile.geojson
- stations_with_apparatus.csv
- stations_with_apparatus_by_user.csv
- `data/incidents/historical/ems_fire/query/historical_<date_range>_<hash>.csv`
- `data/incidents/synthetic/ems_fire/query/synthetic_<date_range>_<hash>.csv`
- fire_simulator

### Logs Written to logs
- `logs/incident_report.csv`
- `logs/station_report.csv`
- `logs/duration_matrix.bin`
- `logs/distance_matrix.bin`
- `logs/matrix.csv`
- `logs/beats.bin`
- `logs/<dispatch_policy>_<fire_model_type>_<travel_time_model>_<start_date>_<end_date>/incident_report.csv`
- `logs/<dispatch_policy>_<fire_model_type>_<travel_time_model>_<start_date>_<end_date>/station_report.csv`

This list includes both static and dynamically generated paths (e.g., those with `<date_range>` or `<hash>` placeholders). Let me know if you need further clarification or assistance!
