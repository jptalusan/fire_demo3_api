// Data processing utilities for map markers and popups

export interface Apparatus {
  id: string;
  type: 'Engine' | 'Ladder' | 'Rescue' | 'Ambulance' | 'Chief';
  name: string;
  status: 'Available' | 'Out of Service' | 'In Use';
  crew: number;
}

export interface ProcessedStation {
  id: string;
  name: string;
  address: string;
  lat: number;
  lon: number;
  lng?: number; // Alternative to lon for consistency with ghost stations
  stationNumber: number;
  displayName: string;
  apparatus: Apparatus[]; // Updated to use Apparatus interface
  serviceZone?: string; // Optional service zone for firebeats
  isGhost?: boolean; // Flag for ghost stations in counterfactual mode
  city?: string; // Additional fields for ghost stations
  state?: string;
  zip?: string;
  resources?: string[];
}

export interface ProcessedIncident {
  id: string;
  incidentType: string;
  lat: number;
  lon: number;
  datetime: string;
  category: string;
  incidentTypeCategory: 'ems' | 'warning' | 'fire';
}

export interface StationReport {
  stationName: string;
  travelTimeMean: number;
  travelTimeP90: number;
  incidentCount: number;
}

export interface StationTravelTimes {
  stationName: string;
  travelTimes: number[]; // Array of travel times in seconds
  travelTimesMinutes: number[]; // Array of travel times in minutes
  min: number;
  q1: number;
  median: number;
  q3: number;
  max: number;
  mean: number;
}

/**
 * Calculates box plot statistics (min, q1, median, q3, max) for an array of numbers
 * @param values - Array of numeric values
 * @returns Object with box plot statistics
 */
function calculateBoxPlotStats(values: number[]): {
  min: number;
  q1: number;
  median: number;
  q3: number;
  max: number;
  mean: number;
} {
  if (values.length === 0) {
    return { min: 0, q1: 0, median: 0, q3: 0, max: 0, mean: 0 };
  }

  const sorted = [...values].sort((a, b) => a - b);
  const n = sorted.length;

  const min = sorted[0];
  const max = sorted[n - 1];
  const mean = values.reduce((sum, val) => sum + val, 0) / n;

  const median = n % 2 === 0 
    ? (sorted[Math.floor(n / 2) - 1] + sorted[Math.floor(n / 2)]) / 2
    : sorted[Math.floor(n / 2)];

  const q1Index = Math.floor((n - 1) * 0.25);
  const q3Index = Math.floor((n - 1) * 0.75);
  
  const q1 = sorted[q1Index];
  const q3 = sorted[q3Index];

  return { min, q1, median, q3, max, mean };
}

/**
 * Processes station travel times from simulation results for box plot visualization
 * @param stationReportData - Array of station report objects from simulation
 * @returns Array of processed station travel time objects with box plot statistics
 */
export function processStationTravelTimes(stationReportData: any[]): StationTravelTimes[] {
  if (!Array.isArray(stationReportData)) {
    console.warn('Station report data is not an array:', stationReportData);
    return [];
  }

  return stationReportData.map(reportItem => {
    // Each item is an object with a single key (station ID) and value (metrics)
    const stationName = Object.keys(reportItem)[0];
    const stationData = reportItem[stationName];
    // Support both snake_case and space-separated keys for compatibility
    const travelTimes = stationData['travel_times'] || stationData['travel times'] || [];
    const travelTimesMinutes = travelTimes.map((time: number) => time / 60); // Convert seconds to minutes
    
    const stats = calculateBoxPlotStats(travelTimesMinutes);
    
    return {
      stationName,
      travelTimes,
      travelTimesMinutes,
      ...stats
    };
  }).filter(station => station.travelTimes.length > 0);
}

/**
 * Processes station report data from simulation results
 * @param stationReportData - Array of station report objects from simulation
 * @returns Array of processed station report objects
 */
export function processStationReport(stationReportData: any[]): StationReport[] {
  if (!Array.isArray(stationReportData)) {
    console.warn('Station report data is not an array:', stationReportData);
    return [];
  }

  return stationReportData.map(reportItem => {
    // Each item is an object with a single key (station ID) and value (metrics)
    const stationName = Object.keys(reportItem)[0];
    const metrics = reportItem[stationName];
    
    return {
      stationName,
      // Support both snake_case and space-separated keys for compatibility
      travelTimeMean: metrics['travel_time_mean'] || metrics['travel time mean'] || 0,
      travelTimeP90: metrics['travel_time_p90'] || metrics['travel time p90'] || 0,
      incidentCount: metrics['incident_count'] || metrics['incident count'] || 0
    };
  }).filter(report => report.stationName && !isNaN(report.travelTimeMean));
}

/**
 * Processes raw incident data from CSV and extracts relevant information
 * @param rawIncidents - Array of raw incident objects from CSV parsing
 * @returns Array of processed incident objects with extracted data
 */
export function processIncidents(rawIncidents: any[]): ProcessedIncident[] {
  return rawIncidents.map(incident => {
    const incidentType = incident.incident_type || incident.type || '';
    const incidentTypeCategory = categorizeIncidentType(incidentType);

    return {
      id: incident.incident_id || incident.id || '',
      incidentType,
      lat: parseFloat(incident.lat),
      lon: parseFloat(incident.lon),
      datetime: incident.datetime || '',
      category: incident.category || '',
      incidentTypeCategory
    };
  }).filter(incident => !isNaN(incident.lat) && !isNaN(incident.lon));
}

/**
 * Categorizes incident type for icon selection
 * @param incidentType - The incident type string
 * @returns The category for icon selection
 */
export function categorizeIncidentType(incidentType: string): 'ems' | 'warning' | 'fire' {
  if (incidentType.toLowerCase().includes('ems & rescue')) {
    return 'ems';
  } else if (incidentType.toLowerCase().includes('good intent call')) {
    return 'warning';
  } else {
    return 'fire';
  }
}

/**
 * Creates popup content for incident markers
 * @param incident - Processed incident object
 * @returns HTML string for the popup
 */
export function createIncidentPopup(incident: ProcessedIncident): string {
  return `
    <div style="font-family: Arial, sans-serif; max-width: 200px;">
      <b>${incident.incidentType}</b><br>
      <span style="color: #666; font-size: 12px;">${incident.datetime}</span><br>
      <span style="color: #666; font-size: 12px;">Category: ${incident.category}</span>
    </div>
  `;
}

/**
 * Creates the HTML content for incident marker icons
 * @param incident - Processed incident object
 * @returns HTML string for the marker icon
 */
export function createIncidentIcon(incident: ProcessedIncident): string {
  const iconHtml = getIncidentIconHtml(incident.incidentTypeCategory);

  return `
    <div style="
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 16px;
    ">
      ${iconHtml}
    </div>
  `;
}

/**
 * Gets the HTML for the incident icon based on category
 * @param category - The incident type category
 * @returns HTML string for the icon
 */
function getIncidentIconHtml(category: 'ems' | 'warning' | 'fire'): string {
  switch (category) {
    case 'ems':
      return '🚑'; // Heart icon for EMS & Rescue
    case 'warning':
      return '⚠️'; // Warning icon for Good Intent Call
    case 'fire':
    default:
      return '🔥'; // Fire icon for everything else
  }
}

/**
 * Gets the background color for incident icons
 * @param category - The incident type category
 * @returns Color string
 */
function getIncidentIconColor(category: 'ems' | 'warning' | 'fire'): string {
  switch (category) {
    case 'ems':
      return '#dc2626'; // Red for EMS
    case 'warning':
      return '#f59e0b'; // Orange for warning
    case 'fire':
    default:
      return '#7c2d12'; // Dark red for fire
  }
}

/**
 * Processes raw station data from CSV and extracts relevant information
 * @param rawStations - Array of raw station objects from CSV parsing
 * @returns Array of processed station objects with extracted data
 */
export function processStations(rawStations: any[]): ProcessedStation[] {
  return rawStations.map(station => {
    // Extract station number from "Facility Name" (e.g., "Station 01" -> 1)
    const facilityName = station['Facility Name'] || station.name || '';
    const stationNumber = extractStationNumber(facilityName);

    return {
      id: station.StationID || station.id || '',
      name: facilityName,
      address: station.Address || '',
      lat: parseFloat(station.lat),
      lon: parseFloat(station.lon),
      stationNumber,
      displayName: `Station ${stationNumber.toString().padStart(2, '0')}`,
      apparatus: [] // Will be populated by MapSection component
    };
  }).filter(station => !isNaN(station.lat) && !isNaN(station.lon));
}

/**
 * Extracts the station number from facility name
 * @param facilityName - The facility name string (e.g., "Station 01")
 * @returns The extracted station number
 */
export function extractStationNumber(facilityName: string): number {
  // Match patterns like "Station 01", "Station 1", "01", "1"
  const match = facilityName.match(/(\d+)/);
  return match ? parseInt(match[1], 10) : 0;
}

/**
 * Creates popup content for station markers
 * @param station - Processed station object
 * @returns HTML string for the popup
 */
export function createStationPopup(station: ProcessedStation): string {
  return `
    <div style="font-family: Arial, sans-serif; max-width: 200px;">
      <b>${station.displayName}</b><br>
      <span style="color: #666; font-size: 12px;">${station.address}</span>
    </div>
  `;
}

/**
 * Creates detailed popup content for station markers with apparatus and delete option
 * @param station - Processed station object
 * @param onDelete - Callback function for delete action
 * @param selectedStationData - Current station dataset to determine if delete should be enabled
 * @returns HTML string for the detailed popup
 */
export function createDetailedStationPopup(station: ProcessedStation, onDelete?: () => void, selectedStationData?: string, zoneInfo?: string): string {
  return `
    <div style="font-family: Arial, sans-serif; min-width: 250px; padding: 8px;">
      <div style="border-bottom: 1px solid #ddd; padding-bottom: 8px; margin-bottom: 8px;">
        <h3 style="margin: 0; color: #dc2626; font-size: 16px;">${station.displayName}</h3>
        <p style="margin: 4px 0 0 0; color: #666; font-size: 12px;">${station.address}</p>
      </div>
      
      ${zoneInfo ? `
      <div style="margin-bottom: 12px;">
        <h4 style="margin: 0 0 4px 0; font-size: 14px; color: #333;">Zone:</h4>
        <p style="margin: 0; padding: 6px 8px; background-color: #eff6ff; border-left: 3px solid #3b82f6; font-size: 13px; color: #1e40af; border-radius: 2px;">
          ${zoneInfo}
        </p>
      </div>
      ` : ''}
      
      <div style="display: flex; gap: 6px; justify-content: flex-end; flex-wrap: wrap; margin-top: 8px;">
        <button 
          onclick="console.log('Apparatus clicked for ${station.id}'); window.openApparatusManager && window.openApparatusManager('${station.id}')"
          style="
            background-color: #059669;
            color: white;
            border: none;
            padding: 6px 10px;
            border-radius: 4px;
            font-size: 11px;
            cursor: pointer;
            transition: background-color 0.2s;
            margin-bottom: 4px;
          "
          onmouseover="this.style.backgroundColor='#047857'"
          onmouseout="this.style.backgroundColor='#059669'"
        >
          🚒 Apparatus
        </button>
        ${selectedStationData === 'custom_stations' ? `
        <button 
          id="delete-station-${station.id}" 
          onclick="console.log('Delete clicked for ${station.id}'); window.deleteStation && window.deleteStation('${station.id}')"
          style="
            background-color: #dc2626;
            color: white;
            border: none;
            padding: 6px 10px;
            border-radius: 4px;
            font-size: 11px;
            cursor: pointer;
            transition: background-color 0.2s;
            margin-bottom: 4px;
          "
          onmouseover="this.style.backgroundColor='#b91c1c'"
          onmouseout="this.style.backgroundColor='#dc2626'"
        >
          🗑️ Delete
        </button>
        ` : ''}
        <button 
          onclick="this.closest('.leaflet-popup').querySelector('.leaflet-popup-close-button').click()"
          style="
            background-color: #6b7280;
            color: white;
            border: none;
            padding: 6px 10px;
            border-radius: 4px;
            font-size: 11px;
            cursor: pointer;
            transition: background-color 0.2s;
            margin-bottom: 4px;
          "
          onmouseover="this.style.backgroundColor='#4b5563'"
          onmouseout="this.style.backgroundColor='#6b7280'"
        >
          Close
        </button>
      </div>
    </div>
  `;
}

/**
 * Creates a popup for assigning a service zone to a station (for Firebeats dispatch policy).
 * @param station - The processed station object.
 * @returns HTML string for the popup.
 */
export function createFirebeatsStationPopup(station: ProcessedStation, selectedStationData?: string): string {
  const serviceZone = station.serviceZone || '';

  return `
    <div style="font-family: Arial, sans-serif; min-width: 250px; padding: 8px;">
      <div style="border-bottom: 1px solid #ddd; padding-bottom: 8px; margin-bottom: 8px;">
        <h3 style="margin: 0; color: #dc2626; font-size: 16px;">${station.displayName}</h3>
        <p style="margin: 4px 0 0 0; color: #666; font-size: 12px;">${station.address}</p>
      </div>
      
      <div style="margin-bottom: 12px;">
        <h4 style="margin: 0 0 4px 0; font-size: 14px; color: #333;">Service Zone:</h4>
        <input 
          type="text" 
          id="service-zone-input-${station.id}" 
          value="${serviceZone}" 
          placeholder="N/A"
          style="width: 100%; box-sizing: border-box; padding: 6px; border: 1px solid #ccc; border-radius: 4px;"
        />
      </div>
      
      <div style="display: flex; gap: 6px; justify-content: flex-end; flex-wrap: wrap; margin-top: 8px;">
        <button 
          onclick="console.log('Apparatus clicked for ${station.id}'); window.openApparatusManager && window.openApparatusManager('${station.id}')"
          style="
            background-color: #059669;
            color: white;
            border: none;
            padding: 6px 10px;
            border-radius: 4px;
            font-size: 11px;
            cursor: pointer;
            margin-bottom: 4px;
          "
          onmouseover="this.style.backgroundColor='#047857'"
          onmouseout="this.style.backgroundColor='#059669'"
        >
          🚒 Apparatus
        </button>
        <button 
          onclick="
            console.log('Update clicked for ${station.id}');
            const input = document.getElementById('service-zone-input-${station.id}');
            if (input && window.firebeatsUpdateServiceZone) {
              console.log('Updating zone to:', input.value);
              window.firebeatsUpdateServiceZone('${station.id}', input.value);
            } else {
              console.log('Input or function not found');
            }
          "
          style="
            background-color: #2563eb;
            color: white;
            border: none;
            padding: 6px 10px;
            border-radius: 4px;
            font-size: 11px;
            cursor: pointer;
            margin-bottom: 4px;
          "
          onmouseover="this.style.backgroundColor='#1d4ed8'"
          onmouseout="this.style.backgroundColor='#2563eb'"
        >
          Update
        </button>
        ${selectedStationData === 'custom_stations' ? `
        <button 
          id="delete-station-${station.id}" 
          onclick="console.log('Delete clicked for ${station.id}'); window.deleteStation && window.deleteStation('${station.id}')"
          style="
            background-color: #dc2626;
            color: white;
            border: none;
            padding: 6px 10px;
            border-radius: 4px;
            font-size: 11px;
            cursor: pointer;
            transition: background-color 0.2s;
            margin-bottom: 4px;
          "
          onmouseover="this.style.backgroundColor='#b91c1c'"
          onmouseout="this.style.backgroundColor='#dc2626'"
        >
          🗑️ Delete
        </button>
        ` : ''}
        <button 
          onclick="this.closest('.leaflet-popup-content-wrapper').parentNode.querySelector('.leaflet-popup-close-button').click()"
          style="
            background-color: #6b7280;
            color: white;
            border: none;
            padding: 6px 10px;
            border-radius: 4px;
            font-size: 11px;
            cursor: pointer;
            margin-bottom: 4px;
          "
          onmouseover="this.style.backgroundColor='#4b5563'"
          onmouseout="this.style.backgroundColor='#6b7280'"
        >
          Close
        </button>
      </div>
    </div>
  `;
}


/**
 * Creates the HTML content for station marker icons
 * @param station - Processed station object
 * @returns HTML string for the marker icon
 */
export function createStationIcon(station: ProcessedStation): string {
  const size = 32; // Increased from 24px for better visibility
  return `
    <div style="
      background-color: #dc2626;
      width: ${size}px;
      height: ${size}px;
      border-radius: 50%;
      border: 3px solid white;
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
      font-weight: bold;
      font-size: 12px;
      font-family: Arial, sans-serif;
      box-shadow: 0 3px 6px rgba(0,0,0,0.3);
    ">
      ${station.stationNumber}
    </div>
  `;
}