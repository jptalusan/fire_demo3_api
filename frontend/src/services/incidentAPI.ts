// API service for incident data retrieval
import { apiFetch } from './api';
import { API_BASE } from './config';

export interface IncidentData {
  id: string;
  incident_type: string;
  incident_level?: string;
  lat: number;
  lon: number;
  datetime: string;
  category: string;
}

export interface IncidentFilters {
  dateRange?: {
    start: string;
    end: string;
  };
  bounds?: {
    north: number;
    south: number;
    east: number;
    west: number;
  };
  incidentTypes?: string[];
  incidentType?: string;
}

export interface APIResponse<T> {
  status: 'success' | 'error';
  data?: T;
  message?: string;
  total?: number;
}

class IncidentAPI {
  private baseURL = API_BASE;

  /**
   * Get incidents from backend based on model and filters
   */
  async getIncidents(
    modelId: string, 
    filters: IncidentFilters = {}
  ): Promise<APIResponse<IncidentData[]>> {
    try {
      const response = await apiFetch(`${this.baseURL}/api/incidents/get-incidents`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model_id: modelId,
          filters: {
            date_range: filters.dateRange,
            incident_type: filters.incidentType,
            bounds: filters.bounds,
            incident_types: filters.incidentTypes
          }
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const contentType = response.headers.get('content-type');
      
      // Handle CSV response
      if (contentType && contentType.includes('text/csv')) {
        const csvContent = await response.text();
        
        // Parse CSV content into incidents array
        const incidents = this.parseCSVToIncidents(csvContent);
        
        return {
          status: 'success',
          data: incidents,
          total: incidents.length
        };
      }
      
      // Handle JSON response (error cases)
      const jsonResponse = await response.json();
      if (jsonResponse.status === 'error') {
        return {
          status: 'error',
          message: jsonResponse.error || jsonResponse.message || 'Unknown error'
        };
      }
      
      return jsonResponse;
    } catch (error) {
      console.error('Error fetching incidents:', error);
      return {
        status: 'error',
        message: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }

  /**
   * Parse CSV content into IncidentData array
   */
  private parseCSVToIncidents(csvContent: string): IncidentData[] {
    const lines = csvContent.trim().split('\n');
    if (lines.length < 2) return []; // No data rows
    
    const headers = lines[0].split(',').map(h => h.trim());
    const incidents: IncidentData[] = [];
    
    for (let i = 1; i < lines.length; i++) {
      const values = lines[i].split(',').map(v => v.trim());
      if (values.length >= headers.length) {
        // Find column indices
        const incidentIdIdx = headers.indexOf('incident_id');
        const incidentTypeIdx = headers.indexOf('incident_type');
        const incidentLevelIdx = headers.indexOf('incident_level');
        const latIdx = headers.indexOf('lat');
        const lonIdx = headers.indexOf('lon');
        const datetimeIdx = headers.indexOf('datetime');
        const categoryIdx = headers.indexOf('category');
        
        const incident: IncidentData = {
          id: values[incidentIdIdx] || `incident_${i}`,
          incident_type: values[incidentTypeIdx] || 'Unknown',
          incident_level: incidentLevelIdx >= 0 ? values[incidentLevelIdx] : undefined,
          lat: parseFloat(values[latIdx] || '0'),
          lon: parseFloat(values[lonIdx] || '0'),
          datetime: values[datetimeIdx] || '',
          category: values[categoryIdx] || 'Unknown'
        };
        incidents.push(incident);
      }
    }
    
    return incidents;
  }

  /**
   * Get available incident models from backend
   */
  async getIncidentModels(): Promise<APIResponse<any[]>> {
    try {
      const response = await apiFetch(`${this.baseURL}/get-incident-models`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Error fetching incident models:', error);
      return {
        status: 'error',
        message: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }

  /**
   * Generate synthetic incidents for a date range
   */
  async generateIncidents(
    stationDataId: string,
    dateRange: { start: string; end: string },
    parameters: any = {}
  ): Promise<APIResponse<any>> {
    try {
      const response = await apiFetch(`${this.baseURL}/api/incidents/generate-incidents`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          date_range: dateRange,
          incident_type: parameters.incidentType,
          model: parameters.model ?? 'growth_v1',
          seed: parameters.seed ?? 42,
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const contentType = response.headers.get('content-type');
      
      // Handle CSV response (successful generation)
      if (contentType && contentType.includes('text/csv')) {
        const csvContent = await response.text();
        console.log('Generated incidents CSV:', csvContent.substring(0, 200) + '...');
        
        return {
          status: 'success',
          data: { csvContent },
          message: 'Incidents generated successfully'
        };
      }
      
      // Handle JSON response (error cases)
      const jsonResponse = await response.json();
      if (jsonResponse.status === 'error') {
        return {
          status: 'error',
          message: jsonResponse.error || jsonResponse.message || 'Unknown error'
        };
      }
      
      return jsonResponse;
    } catch (error) {
      console.error('Error generating incidents:', error);
      return {
        status: 'error',
        message: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }

  /**
   * Get incident statistics for a model and date range
   */
  async getIncidentStatistics(
    modelId: string,
    dateRange?: { start: string; end: string }
  ): Promise<APIResponse<any>> {
    try {
      const params = new URLSearchParams({ modelId });
      if (dateRange) {
        params.append('start', dateRange.start);
        params.append('end', dateRange.end);
      }

      const response = await apiFetch(`${this.baseURL}/get-incident-stats?${params}`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Error fetching incident statistics:', error);
      return {
        status: 'error',
        message: error instanceof Error ? error.message : 'Unknown error'
      };
    }
  }
}

export const incidentAPI = new IncidentAPI();