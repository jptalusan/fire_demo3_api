"""FastAPI application for simulation-db API."""

from fastapi import APIRouter, Request, Response
import hashlib
from pathlib import Path
import io
import pandas as pd
import src.core.config as constants
from src.engine.incidents import predict_incidents_with_types_and_coordinates

router = APIRouter()

data_dir = constants.DATA_DIR

@router.post("/get-incidents")
async def get_incidents(request: Request):
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

@router.post("/process-incidents")
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

@router.post("/generate-incidents")
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
