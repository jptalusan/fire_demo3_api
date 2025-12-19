# {
#   "stations": [{
#   "id": "S1",
#   "name": "Station 1",
#   "lat": 36.2293898,
#   "lon": -86.75674762,
#   "apparatus": [{"type": "Engine", "count": 1}, {"type": "Medic", "count": 1}]
#   }],
#   "incident_type": "fire",
#   "models": {
#     "incident": "historical_incidents",
#     "dispatch": "nearest",
#     "travelTime": "string",
#     "serviceTime": "ml_based"
#   },
#   "dispatch_policy": "string",
#   "station_data": "string",
#   "date_range": {
#     "start_date": "string",
#     "end_date": "string"
#   }
# }

Run this for simulation (single)
```
curl -sS -X POST "http://127.0.0.1:8000/api/engine/run-simulation" \
  -H "Content-Type: application/json" \
  -d '{
    "stations": [{
      "id": "0",
      "name": "Station 01",
      "lat": 36.2293898,
      "lon": -86.75674762,
      "apparatus": [
        {"type": "Engine", "count": 1},
        {"type": "Medic", "count": 1}
      ]
    }],
    "incident_type": "fire",
    "models": {
      "incident": "historical_incidents",
      "dispatch": "nearest",
      "travelTime": "OSRM",
      "serviceTime": "empirical_servicetimes"
    },
    "dispatch_policy": "string",
    "station_data": "string",
    "date_range": {
      "start_date": "string",
      "end_date": "string"
    }
  }'
```

For comparison
```
curl -sS -X POST "http://127.0.0.1:8000/api/engine/run-comparison" \
  -H "Content-Type: application/json" \
  -d '{
    "baseline": {
      "stations": [{
        "id": "0",
        "name": "Station 01",
        "lat": 36.2293898,
        "lon": -86.75674762,
        "apparatus": [
          {"type": "Engine", "count": 1},
          {"type": "Medic", "count": 1}
        ]
      }],
      "incident_type": "fire",
      "models": {
        "incident": "historical_incidents",
        "dispatch": "nearest",
        "travelTime": "OSRM",
        "serviceTime": "empirical_servicetimes"
      },
      "dispatch_policy": "string",
      "station_data": "string",
      "date_range": {
        "start_date": "string",
        "end_date": "string"
      }
    },
    "new_config": {
      "stations": [{
        "id": "0",
        "name": "Station 01",
        "lat": 36.2293898,
        "lon": -86.75674762,
        "apparatus": [
          {"type": "Engine", "count": 2},
          {"type": "Medic", "count": 2}
        ]
      }],
      "incident_type": "fire",
      "models": {
        "incident": "historical_incidents",
        "dispatch": "nearest",
        "travelTime": "OSRM",
        "serviceTime": "empirical_servicetimes"
      },
      "dispatch_policy": "string",
      "station_data": "string",
      "date_range": {
        "start_date": "string",
        "end_date": "string"
      }
    }
  }'
```
