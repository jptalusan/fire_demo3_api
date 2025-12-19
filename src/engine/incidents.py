import pandas as pd
import numpy as np
import pickle
import json
import os
import geopandas as gpd
from pathlib import Path

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
                
                # BUG: Ensure unique incident IDs
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
