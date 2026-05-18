"""FastAPI application for simulation-db API."""

from fastapi import APIRouter, Body, Response
import hashlib
import io
import pandas as pd
import src.core.config as constants
from src.engine.incidents import predict_incidents_with_types_and_coordinates
from src.engine.incidents_variants import predict_incidents as predict_incidents_growth_v1
from src.schemas.incidents import GenerateIncidentsRequest, GetIncidentsRequest, ProcessIncidentsResponse
from src.engine.simulation import get_or_create_historical_incidents
router = APIRouter()

data_dir = constants.DATA_DIR

@router.post(
    "/get-incidents",
    responses={
        200: {
            "content": {
                "text/csv": {
                    "schema": {"type": "string"},
                }
            },
            "description": "CSV data",
        }
    },
)
async def get_incidents(payload: GetIncidentsRequest):
    try:
        payload_dict = payload.model_dump()
        print(payload_dict)

        model_id = payload.model_id
        filters = payload.filters.model_dump()
        
        # Only handle historical_incidents model
        if model_id != "historical_incidents":
            return {"status": "error", "error": "Only historical_incidents model is supported"}
        
        # Extract date range from filters
        date_range = filters.get("date_range", {})
        start_date = date_range.get("start")
        end_date = date_range.get("end")
        incident_type = filters.get("incident_type")
        
        if not start_date or not end_date:
            return {"status": "error", "error": "Date range with start and end dates is required"}
        
        # Use the centralized helper function
        
        
        try:
            query_path = get_or_create_historical_incidents(start_date, end_date, incident_type, data_dir)
        except ValueError as e:
            return {"status": "error", "error": str(e)}
        
        # Read and return the CSV content
        with open(query_path, 'r') as f:
            csv_content = f.read()
        
        return Response(content=csv_content, media_type="text/csv")
        
    except Exception as e:
        print(f"Error in get_incidents: {str(e)}")
        return {"status": "error", "error": str(e)}

@router.post("/process-incidents", response_model=ProcessIncidentsResponse)
async def process_incidents(csv_data: str = Body(..., media_type="text/csv")):
    try:
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

@router.post(
    "/generate-incidents",
    responses={
        200: {
            "content": {
                "text/csv": {
                    "schema": {"type": "string"},
                }
            },
            "description": "CSV data",
        }
    },
)
async def generate_incidents(payload: GenerateIncidentsRequest):

    from fastapi import Response
    
    try:
        payload_dict = payload.model_dump()
        print(payload_dict)

        start_date = payload.date_range.start
        end_date = payload.date_range.end
        incident_type = payload.incident_type
        model_name = payload.model
        seed = payload.seed

        print(f"Generating {incident_type} incidents [{model_name}] from {start_date} to {end_date}")

        if not start_date or not end_date:
            print("Invalid input")
            return {"status": "error", "error": "startDate and endDate are required"}

        # Extract date part for filename (YYYY-MM-DD)
        start_date_str = start_date[:10] if 'T' in start_date else start_date
        end_date_str = end_date[:10] if 'T' in end_date else end_date

        cache_key = f"synthetic_incidents_{model_name}_{start_date_str}_{end_date_str}_seed{seed}"
        query_hash = hashlib.md5(cache_key.encode()).hexdigest()
        query_filename = f"synthetic_{model_name}_{start_date_str}_{end_date_str}_{query_hash[:8]}.csv"

        # Define paths (use the same DATA_DIR as the rest of the app)
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
            print(f"Creating new synthetic query for {incident_type} [{model_name}]: {query_filename}")

            if model_name == "growth_v1":
                df = predict_incidents_growth_v1(start_date, end_date, seed=seed,
                                                 incident_type=incident_type)
                # Map to legacy CSV schema. growth_v1 has no incident_level; assign uniformly random.
                if not df.empty:
                    import numpy as np
                    rng = np.random.default_rng(seed)
                    df = df.copy()
                    df["incident_level"] = rng.choice(
                        ["Low", "Moderate", "High"], size=len(df), p=[0.4, 0.4, 0.2]
                    )
                predicted_incidents_df = df
            else:
                predicted_incidents_df = predict_incidents_with_types_and_coordinates(
                    start_date, end_date, incident_type=incident_type
                )

            # Convert DataFrame to list of dictionaries for CSV generation
            incidents = predicted_incidents_df.to_dict('records') if not predicted_incidents_df.empty else []

            # Convert to CSV format (legacy schema for client compatibility)
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
