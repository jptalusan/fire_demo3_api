import React, { useState, useEffect } from 'react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Separator } from './ui/separator';
import { Play, Settings, ChevronLeft, ChevronRight, Download, GitCompare } from 'lucide-react';
import { ProcessedStation, Apparatus } from '../utils/dataProcessing';
import controlPanelConfig from '../config/controlPanelConfig.json';
import { Switch } from './ui/switch';
import { runJob } from '../services/jobs';
import { apiFetch } from '../services/api';
import { useJobs } from '../context/JobsContext';

// Interface for apparatus counts (matching App.tsx and MapSection)
interface ApparatusCounts {
  [key: string]: number;
}

// Translate the UI's camelCase payload into the snake_case "intent" shape that
// the v2 simulator engine (run_simulation_internal) expects. Anything not mapped
// here falls back to engine defaults.
function toSimIntent(p: any): any {
  return {
    models: p.models,
    date_range: p.dateRange
      ? { start_date: p.dateRange.startDate, end_date: p.dateRange.endDate }
      : undefined,
    incident_type: p.incidentType,
    dispatch_policy: p.dispatchPolicy,
    station_data: p.stationData,
    stations: p.stations,
    disable_ems: p.disable_ems ?? false,
  };
}

interface ControlPanelProps {
  onRunSimulation: () => void;
  selectedIncidentFile: string;
  onIncidentFileChange: (file: string) => void;
  onClearSettings: () => void;
  onSimulationSuccess?: (result: any) => void;
  selectedStationFile: string;
  onStationFileChange: (file: string) => void;
  stations: ProcessedStation[];
  stationApparatus: Map<string, Apparatus[]>;
  stationApparatusCounts: Map<string, ApparatusCounts>;
  originalApparatusCounts: Map<string, ApparatusCounts>;
  selectedStationData?: string;
  onStationDataChange?: (data: string) => void;
  selectedGridSize?: string;
  onGridSizeChange?: (gridSize: string) => void;
  selectedNewStations?: number;
  onNewStationsChange?: (count: number) => void;
  onStationsChange: (stations: ProcessedStation[]) => void;
  selectedDispatchPolicy?: string;
  onDispatchPolicyChange?: (policy: string) => void;
  selectedServiceZoneFile?: string;
  onServiceZoneFileChange?: (file: string) => void;
  selectedIncidentModel?: string;
  onIncidentModelChange?: (model: string) => void;
  selectedIncidentType?: string;
  onIncidentTypeChange?: (type: string) => void;
  startDate?: Date;
  endDate?: Date;
  onStartDateChange?: (date: Date | undefined) => void;
  onEndDateChange?: (date: Date | undefined) => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
  incidentsCount?: number;
  onHistoricalIncidentStatsChange?: (stats: any) => void;
  onHistoricalIncidentErrorChange?: (error: string | null) => void;
  onIncidentsChange?: (incidents: any[]) => void;
  isCounterfactualMode?: boolean;
  onCounterfactualModeChange?: (mode: boolean) => void;
  baselineResults?: any;
  onBaselineResultsChange?: (results: any) => void;
  selectedTravelTimeModel?: string;
  onTravelTimeModelChange?: (model: string) => void;
  selectedServiceTimeModel?: string;
  onServiceTimeModelChange?: (model: string) => void;
}

export function ControlPanel({
  onRunSimulation,
  selectedIncidentFile,
  onIncidentFileChange,
  onClearSettings,
  onSimulationSuccess,
  selectedStationFile,
  onStationFileChange,
  stations,
  stationApparatus,
  stationApparatusCounts,
  originalApparatusCounts,
  selectedStationData,
  onStationDataChange,
  selectedGridSize,
  onGridSizeChange,
  selectedNewStations,
  onNewStationsChange,
  onStationsChange, // Add this line
  selectedDispatchPolicy = controlPanelConfig.dispatchPolicies.default,
  onDispatchPolicyChange,
  selectedServiceZoneFile = '',
  onServiceZoneFileChange,
  selectedIncidentModel = controlPanelConfig.incidentModels.default,
  onIncidentModelChange,
  selectedIncidentType = 'ems_fire',
  onIncidentTypeChange,
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
  isCollapsed = false,
  onToggleCollapse,
  onHistoricalIncidentStatsChange,
  onHistoricalIncidentErrorChange,
  onIncidentsChange,
  incidentsCount = 0,
  isCounterfactualMode = false,
  onCounterfactualModeChange,
  baselineResults,
  onBaselineResultsChange,
  selectedTravelTimeModel = controlPanelConfig.travelTimeModels.default,
  onTravelTimeModelChange,
  selectedServiceTimeModel = controlPanelConfig.serviceTimeModels.default,
  onServiceTimeModelChange,
}: ControlPanelProps) {
  const [fireStationsFile, setFireStationsFile] = useState<File | null>(null);
  const [incidentsFile, setIncidentsFile] = useState<File | null>(null);
  const [responseTime, setResponseTime] = useState('5');
  const [maxDistance, setMaxDistance] = useState('10');
  const [incidentFiles, setIncidentFiles] = useState<string[]>([]);
  const [stationFiles, setStationFiles] = useState<string[]>([]);
  const [serviceZoneFiles, setServiceZoneFiles] = useState<string[]>([]);
  const { refresh: refreshJobs } = useJobs();
  const [isSimulating, setIsSimulating] = useState(false);
  // Live job-queue progress for the simulating overlay.
  const [jobProgress, setJobProgress] = useState<{
    id: number | null;
    status: string;
    attempts: number;
    startedAt: number;
  } | null>(null);
  const [jobElapsed, setJobElapsed] = useState(0);
  const [incidentProgress, setIncidentProgress] = useState<{ processed: number; total: number; percent: number } | null>(null);
  const [isLoadingIncidents, setIsLoadingIncidents] = useState(false);
  const [incidentLoadError, setIncidentLoadError] = useState<string | null>(null);
  
  // Track the date range for currently loaded incidents
  const [loadedIncidentsDateRange, setLoadedIncidentsDateRange] = useState<{
    startDate: Date | null;
    endDate: Date | null;
  }>({ startDate: null, endDate: null });
  
  // Travel/service-time model are now lifted to the parent (App) so a restored
  // job can repopulate them. Reset to defaults when parent selections are cleared.
  useEffect(() => {
    if (!selectedStationData) {
      onTravelTimeModelChange?.(controlPanelConfig.travelTimeModels.default);
      onServiceTimeModelChange?.(controlPanelConfig.serviceTimeModels.default);
    }
  }, [selectedStationData]);

  // Tick an elapsed-seconds counter while a job is in flight.
  useEffect(() => {
    if (!jobProgress) return;
    const t = setInterval(() => {
      setJobElapsed(Math.floor((Date.now() - jobProgress.startedAt) / 1000));
    }, 1000);
    return () => clearInterval(t);
  }, [jobProgress]);

  // Clear incident load error when parameters change
  useEffect(() => {
    setIncidentLoadError(null);
  }, [selectedIncidentModel, startDate, endDate]);

  useEffect(() => {
    if (!selectedDispatchPolicy) {
      // Reset models when dispatch policy is cleared
    }
  }, [selectedDispatchPolicy]);

  // Automatically switch away from firebeats when optimized stations are selected
  useEffect(() => {
    if (selectedStationData === 'optimized_stations' && selectedDispatchPolicy === 'firebeats') {
      // Switch to nearest available policy (default)
      onDispatchPolicyChange?.('nearest');
    }
  }, [selectedStationData, selectedDispatchPolicy, onDispatchPolicyChange]);

  // Helper function to check if current date range matches loaded incidents date range
  const isDateRangeMatching = () => {
    // If no date range is selected, consider it matching (for models that don't use date ranges)
    if (!startDate || !endDate) {
      return !loadedIncidentsDateRange.startDate && !loadedIncidentsDateRange.endDate;
    }
    
    // Compare the current date range with the loaded incidents date range
    return loadedIncidentsDateRange.startDate?.getTime() === startDate.getTime() &&
           loadedIncidentsDateRange.endDate?.getTime() === endDate.getTime();
  };

  // Validation function to check if all required fields are selected
  const isFormValid = () => {
    const requiredFields = [
      selectedStationData,
      selectedIncidentModel,
      selectedTravelTimeModel,
      selectedServiceTimeModel,
      selectedDispatchPolicy
    ];
    
    // Check if all required fields have values
    const allFieldsSelected = requiredFields.every(field => field && field.trim() !== '');
    
    // Incidents are no longer required to be loaded before running simulation
    // The backend will handle loading incidents based on the date range and model
    
    return allFieldsSelected;
  };

  // Get list of missing required fields for better user feedback
  const getMissingFields = () => {
    const missing = [];
    if (!selectedStationData) missing.push('Station Data');
    if (!selectedIncidentModel) missing.push('Incident Model');
    if (!selectedTravelTimeModel) missing.push('Travel Time Model');
    if (!selectedServiceTimeModel) missing.push('Service Time Model');
    if (!selectedDispatchPolicy) missing.push('Dispatch Policy');
    return missing;
  };

  // Utility function to handle API responses consistently
  const handleApiResponse = (data: any, key: string) => {
    console.log('Raw response data:', data); // Log the entire response object
    const result = data[key]; // Extract the specified key from the response
    console.log(`Extracted ${key}:`, result); // Debugging log
    return result;
  };

  // Removed automatic fetch on mount - incident files will be loaded only when needed
  // useEffect(() => {
  //   const fetchIncidentFiles = async () => {
  //     // 1. Create a new AbortController instance
  //     const controller = new AbortController();
  //     const signal = controller.signal;

  //     // Define your desired timeout duration in milliseconds (e.g., 10 seconds)
  //     const TIMEOUT_MS = 600000; 

  //     // 2. Set a timer to abort the request after the timeout
  //     const timeoutId = setTimeout(() => {
  //       controller.abort();
  //     }, TIMEOUT_MS);

  //     try {
  //       const response = await fetch(
  //         `http://localhost:9999/get-incidents`,
  //         { signal } // 3. Pass the signal to the fetch options
  //       );

  //       // 4. Clear the timeout if the request completes before the timer fires
  //       clearTimeout(timeoutId); 

  //       if (!response.ok) {
  //         throw new Error(`HTTP error! status: ${response.status}`);
  //       }
        
  //       const data = await response.json();
  //       const incidents = handleApiResponse(data, 'incidents');
  //       setIncidentFiles(incidents);

  //     } catch (error) {
  //           // Use a type guard to safely check if the error is an object
  //           // and has a 'name' property of type string.
  //           if (
  //             error instanceof Error && 
  //             error.name === 'AbortError'
  //           ) {
  //             console.error('Fetch aborted due to timeout:', error);
  //             // Add logic for timeout handling here (e.g., set a state flag)
  //           } else {
  //             // This handles all other errors (network issues, JSON parsing, etc.)
  //             console.error('Error fetching incident files:', error);
  //           }
  //     }
  //   };

  //   fetchIncidentFiles(); 
  //   // You may also want to return a cleanup function from useEffect 
  //   // to abort the request if the component unmounts before it completes:
  //   // return () => { controller.abort(); };

  // }, []);

  useEffect(() => {
    const fetchStationFiles = async () => {
      try {
        const response = await apiFetch(
          `/api/stations/get-stations`
        ); // Fetch station files
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json(); // Parse the JSON response
        const stations = handleApiResponse(data, 'stations'); // Extract 'stations' from response
        setStationFiles(stations);
      } catch (error) {
        console.error('Error fetching station files:', error);
      }
    };

    fetchStationFiles();
  }, []);



  // Process historical incidents when model changes to historical_incidents
  // Note: Historical incident processing is now handled by the manual "Load Incidents" button
  // and automatic loading in MapSection component. The old CSV-based processing is removed.

  // Process synthetic incidents when model changes to synthetic_incidents
  useEffect(() => {
    const processSyntheticIncidents = async () => {
      if (selectedIncidentModel === 'synthetic_incidents') {
        try {
          // Validate date range
          if (!startDate || !endDate) {
            if (onHistoricalIncidentErrorChange) {
              onHistoricalIncidentErrorChange('Please select both start and end dates for synthetic incident generation.');
            }
            return;
          }

          console.log('Generating synthetic incidents for date range:', startDate, 'to', endDate);

          // Import the incident API service
          const { incidentAPI } = await import('../services/incidentAPI');

          // Step 1: Generate incidents using the API service
          const generateResponse = await incidentAPI.generateIncidents(
            selectedStationData || 'default_stations',
            {
              start: startDate.toISOString(),
              end: endDate.toISOString()
            },
            { incidentType: selectedIncidentType } // Include incident type
          );

          if (generateResponse.status !== 'success') {
            throw new Error(`Backend failed to generate incidents: ${generateResponse.message}`);
          }

          console.log('Synthetic incidents generated successfully:', generateResponse.data);

          // Step 2: Get incident statistics from the API
          const statsResponse = await incidentAPI.getIncidentStatistics(
            'synthetic_incidents',
            {
              start: startDate.toISOString(),
              end: endDate.toISOString()
            }
          );

          if (statsResponse.status === 'success' && statsResponse.data) {
            console.log('Synthetic incident statistics:', statsResponse.data);
            
            // Update statistics
            if (onHistoricalIncidentStatsChange) {
              onHistoricalIncidentStatsChange(statsResponse.data);
            }
          }

          // Set timestamp to trigger map reload
          localStorage.setItem('synth-incidents-timestamp', Date.now().toString());
          console.log('Synthetic incidents ready for use');
          
          // No longer need localStorage CSV storage since we're using API

          // Clear any previous errors
          if (onHistoricalIncidentErrorChange) {
            onHistoricalIncidentErrorChange(null);
          }

        } catch (error) {
          console.error('Error processing synthetic incidents:', error);
          let errorMessage = 'An error occurred while processing synthetic incidents.';
          
          if (error instanceof Error) {
            if (error.message.includes('select both start and end dates')) {
              errorMessage = 'Please select both start and end dates for synthetic incident generation.';
            } else if (error.message.includes('Backend failed to generate')) {
              errorMessage = 'Backend server failed to generate synthetic incidents.';
            } else if (error.message.includes('Backend failed to process')) {
              errorMessage = 'Backend server failed to process the incidents data.';
            } else if (error.message.includes('NetworkError') || error.message.includes('Failed to fetch')) {
              errorMessage = 'Backend server is not reachable.';
            }
          }
          
          // Clear stats and incidents on error
          if (onHistoricalIncidentStatsChange) {
            onHistoricalIncidentStatsChange(null);
          }
          // No longer using onIncidentsChange - using localStorage approach
          if (onHistoricalIncidentErrorChange) {
            onHistoricalIncidentErrorChange(errorMessage);
          }
        }
      } else if (selectedIncidentModel !== 'historical_incidents') {
        // Clear synthetic incidents from localStorage when switching to other models
        localStorage.removeItem('synth-incidents.csv');
        console.log('Cleared synthetic incidents from localStorage');
        
        // No longer using onIncidentsChange - using localStorage approach
      }
    };

  }, [selectedIncidentModel]);

  // Helper function to parse CSV into incident objects for the map
  const parseCSVToIncidents = (csvData: string) => {
    const lines = csvData.trim().split('\n');
    if (lines.length < 2) return []; // No data rows
    
    const headers = lines[0].split(',').map(h => h.trim());
    const incidents = [];

    for (let i = 1; i < lines.length; i++) {
      const values = lines[i].split(',');
      const incident: any = {};
      
      headers.forEach((header, index) => {
        incident[header] = values[index]?.trim();
      });

      // Convert to the format expected by the map (ProcessedIncident interface)
      if (incident.lat && incident.lon) {
        const incidentType = incident.incident_type || 'Unknown';
        
        // Map incident type to category
        let incidentTypeCategory: 'ems' | 'warning' | 'fire' = 'warning';
        if (incidentType.toLowerCase().includes('fire') || incidentType.toLowerCase().includes('smoke')) {
          incidentTypeCategory = 'fire';
        } else if (incidentType.toLowerCase().includes('medical') || incidentType.toLowerCase().includes('ems')) {
          incidentTypeCategory = 'ems';
        }
        
        incidents.push({
          id: incident.incident_id || `synthetic_${i}`,
          incidentType: incidentType,
          lat: parseFloat(incident.lat),
          lon: parseFloat(incident.lon),
          datetime: incident.datetime || new Date().toISOString(),
          category: incident.category || 'Unknown',
          incidentTypeCategory: incidentTypeCategory
        });
      }
    }

    console.log('Parsed incidents for map:', incidents);
    return incidents;
  };

  const handleFileUpload = (
    file: File | null,
    type: 'stations' | 'incidents'
  ) => {
    if (type === 'stations') {
      setFireStationsFile(file);
    } else {
      setIncidentsFile(file);
    }
  };

  // Helper function to convert apparatus counts to simple apparatus array for payload
  const convertApparatusCountsToSimpleArray = (counts: ApparatusCounts) => {
    const apparatusArray: Array<{type: string, count: number}> = [];
    
    // APPARATUS_TYPES mapping to match MapSection
    const APPARATUS_TYPES = [
      { key: 'Engine_ID', name: 'Engine', csvColumn: 'Engine_ID' },
      { key: 'Truck', name: 'Truck', csvColumn: 'Truck' },
      { key: 'Rescue', name: 'Rescue', csvColumn: 'Rescue' },
      { key: 'Hazard', name: 'Hazard', csvColumn: 'Hazard' },
      { key: 'Squad', name: 'Squad', csvColumn: 'Squad' },
      { key: 'FAST', name: 'FAST', csvColumn: 'FAST' },
      { key: 'Medic', name: 'Medic', csvColumn: 'Medic' },
      { key: 'Brush', name: 'Brush', csvColumn: 'Brush' },
      { key: 'Boat', name: 'Boat', csvColumn: 'Boat' },
      { key: 'UTV', name: 'UTV', csvColumn: 'UTV' },
      { key: 'REACH', name: 'REACH', csvColumn: 'REACH' },
      { key: 'Chief', name: 'Chief', csvColumn: 'Chief' }
    ];

    APPARATUS_TYPES.forEach(type => {
      const count = counts[type.key] || 0;
      if (count > 0) {
        apparatusArray.push({
          type: type.name,
          count: count
        });
      }
    });
    
    return apparatusArray;
  };

  const handleSaveStationConfiguration = async () => {
    try {
      // Prepare CSV headers
      const headers = [
        'StationID',
        'Stations',
        'Address', 
        'lat',
        'lon',
        'Service Zone',
        'Engine_ID',
        'Truck',
        'Rescue',
        'Hazard',
        'Squad',
        'FAST',
        'Medic',
        'Brush',
        'Boat',
        'UTV',
        'REACH',
        'Chief'
      ];

      // Prepare CSV rows
      const rows = stations.map(station => {
        const apparatusCounts = stationApparatusCounts.get(station.id) || {};
        
        return [
          station.id,
          station.name || station.displayName || '',
          station.address || '',
          station.lat.toString(),
          station.lon.toString(),
          station.serviceZone || '',
          (apparatusCounts['Engine_ID'] || 0).toString(),
          (apparatusCounts['Truck'] || 0).toString(),
          (apparatusCounts['Rescue'] || 0).toString(),
          (apparatusCounts['Hazard'] || 0).toString(),
          (apparatusCounts['Squad'] || 0).toString(),
          (apparatusCounts['FAST'] || 0).toString(),
          (apparatusCounts['Medic'] || 0).toString(),
          (apparatusCounts['Brush'] || 0).toString(),
          (apparatusCounts['Boat'] || 0).toString(),
          (apparatusCounts['UTV'] || 0).toString(),
          (apparatusCounts['REACH'] || 0).toString(),
          (apparatusCounts['Chief'] || 0).toString()
        ];
      });

      // Create CSV content
      const csvContent = [headers, ...rows]
        .map(row => row.map(cell => `"${cell}"`).join(','))
        .join('\n');

      // Generate default filename with timestamp
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
      const defaultFilename = `station_configuration_${timestamp}.csv`;

      // Check if File System Access API is supported and we're in a secure context
      const hasFileSystemAccess = 'showSaveFilePicker' in window && window.isSecureContext;
      console.log('File System Access API available:', hasFileSystemAccess);
      
      if (hasFileSystemAccess) {
        try {
          console.log('Attempting to show native save dialog...');
          const fileHandle = await (window as any).showSaveFilePicker({
            suggestedName: defaultFilename,
            types: [{
              description: 'CSV files',
              accept: { 'text/csv': ['.csv'] }
            }],
            excludeAcceptAllOption: true
          });
          
          console.log('User selected file, writing content...');
          const writable = await fileHandle.createWritable();
          await writable.write(csvContent);
          await writable.close();
          
          console.log('Station configuration saved successfully via native dialog');
          return;
        } catch (error) {
          // User cancelled or error occurred, fall back to download method
          if (error instanceof Error && error.name === 'AbortError') {
            console.log('User cancelled save dialog');
            return; // Don't fall back if user explicitly cancelled
          } else {
            console.warn('File System Access API failed, falling back to download:', error);
          }
        }
      } else {
        console.log('File System Access API not available, using download method');
      }

      // Fallback: Ask user for filename using browser prompt, then download
      let finalFilename = defaultFilename;
      const userFilename = prompt('Save as filename:', defaultFilename);
      if (userFilename === null) {
        console.log('User cancelled save');
        return; // User cancelled
      }
      if (userFilename.trim()) {
        finalFilename = userFilename.trim();
        if (!finalFilename.endsWith('.csv')) {
          finalFilename += '.csv';
        }
      }

      // Use traditional download method with user-specified filename
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      const url = URL.createObjectURL(blob);
      link.setAttribute('href', url);
      link.setAttribute('download', finalFilename);
      
      // Trigger download
      link.style.visibility = 'hidden';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      // Clean up
      URL.revokeObjectURL(url);
      
      console.log('Station configuration saved successfully as:', finalFilename);
    } catch (error) {
      console.error('Error saving station configuration:', error);
      alert('Error saving station configuration. Please try again.');
    }
  };

  // Helper function to run baseline simulation in counterfactual mode
  const runBaselineSimulation = async (controller: AbortController, signal: AbortSignal) => {
    const baselinePayload = {
      stationData: 'default_stations', // Always use default stations for baseline
      dateRange: {
        startDate: startDate ? startDate.toISOString() : null,
        endDate: endDate ? endDate.toISOString() : null
      },
      models: {
        incident: selectedIncidentModel,
        travelTime: selectedTravelTimeModel,
        serviceTime: selectedServiceTimeModel,
        dispatch: selectedDispatchPolicy
      },
      selectedIncidentFile,
      selectedStationFile,
      selectedServiceZoneFile: selectedDispatchPolicy === 'firebeats' ? selectedServiceZoneFile : undefined,
      dispatchPolicy: selectedDispatchPolicy,
      stations: stations.map(station => {
        const apparatusCounts = stationApparatusCounts.get(station.id);
        const apparatus = apparatusCounts 
          ? convertApparatusCountsToSimpleArray(apparatusCounts)
          : []; 
        return {
          id: station.id,
          name: station.displayName,
          lat: station.lat,
          lon: station.lon, 
          apparatus: apparatus,
          serviceZone: station.serviceZone, 
        };
      }),
      responseTime: parseInt(responseTime),
      maxDistance: parseFloat(maxDistance),
      options: {
        coverageAnalysis: true,
        responseTimeAnalysis: true,
        resourceOptimization: false
      }
    };

    console.log('Running baseline simulation job...');
    const baselineResult = await runJob('run-simulation', toSimIntent(baselinePayload));
    console.log('Baseline simulation complete:', baselineResult);

    if (baselineResult.status === 'success' && onBaselineResultsChange) {
      onBaselineResultsChange(baselineResult);
    }

    return baselineResult;
  };

  const handleRunSimulation = async () => {
    // Define the timeout duration (e.g., 120 seconds)
    const TIMEOUT_MS = 12000000; 

    // 1. Create a new AbortController instance
    const controller = new AbortController();
    const signal = controller.signal;

    // 2. Set a timer to abort the request after the timeout
    const timeoutId = setTimeout(() => {
        controller.abort();
    }, TIMEOUT_MS);

    try {
      setIsSimulating(true); // Disable the button and show loading state
      setJobElapsed(0);
      setIncidentProgress(null);
      setJobProgress({ id: null, status: 'submitting', attempts: 0, startedAt: Date.now() });

      // Start timing the API call
      const startTime = performance.now();

      // Counterfactual mode: call comparison endpoint
      if (isCounterfactualMode) {
        const comparisonPayload = {
          // Baseline configuration (always default stations)
          baseline: {
            stationData: 'default_stations',
            dateRange: {
              startDate: startDate ? startDate.toISOString() : null,
              endDate: endDate ? endDate.toISOString() : null
            },
            incidentType: selectedIncidentType,
            models: {
              incident: selectedIncidentModel,
              travelTime: selectedTravelTimeModel,
              serviceTime: selectedServiceTimeModel,
              dispatch: selectedDispatchPolicy
            },
            selectedIncidentFile,
            selectedStationFile,
            selectedServiceZoneFile: selectedDispatchPolicy === 'firebeats' ? selectedServiceZoneFile : undefined,
            dispatchPolicy: selectedDispatchPolicy,
            responseTime: parseInt(responseTime),
            maxDistance: parseFloat(maxDistance),
            options: {
              coverageAnalysis: true,
              responseTimeAnalysis: true,
              resourceOptimization: false
            }
          },
          
          // New configuration (custom or optimized stations)
          newConfig: {
            stationData: selectedStationData,
            dateRange: {
              startDate: startDate ? startDate.toISOString() : null,
              endDate: endDate ? endDate.toISOString() : null
            },
            incidentType: selectedIncidentType,
            models: {
              incident: selectedIncidentModel,
              travelTime: selectedTravelTimeModel,
              serviceTime: selectedServiceTimeModel,
              dispatch: selectedDispatchPolicy
            },
            selectedIncidentFile,
            selectedStationFile,
            selectedServiceZoneFile: selectedDispatchPolicy === 'firebeats' ? selectedServiceZoneFile : undefined,
            dispatchPolicy: selectedDispatchPolicy,
            stations: stations.map(station => {
              const apparatusCounts = stationApparatusCounts.get(station.id);
              const apparatus = apparatusCounts 
                ? convertApparatusCountsToSimpleArray(apparatusCounts)
                : []; 
              return {
                id: station.id,
                name: station.displayName,
                lat: station.lat,
                lon: station.lon, 
                apparatus: apparatus,
                serviceZone: station.serviceZone, 
              };
            }),
            responseTime: parseInt(responseTime),
            maxDistance: parseFloat(maxDistance),
            options: {
              coverageAnalysis: true,
              responseTimeAnalysis: true,
              resourceOptimization: false
            }
          }
        };

        console.log('Submitting counterfactual comparison job with payload:', comparisonPayload);

        // Run via the async job queue: submit + poll until done.
        const result = await runJob(
          'run-comparison',
          {
            baseline: toSimIntent(comparisonPayload.baseline),
            newConfig: toSimIntent(comparisonPayload.newConfig),
          },
          { onTick: (job) => { setJobProgress((prev) => ({ id: job.id, status: job.status, attempts: job.attempts, startedAt: prev?.startedAt ?? Date.now() })); refreshJobs(); }, onProgress: (p) => setIncidentProgress({ processed: p.processed, total: p.total, percent: p.percent }) },
        );

        clearTimeout(timeoutId);

        // Calculate API call duration
        const endTime = performance.now();
        const apiCallDuration = (endTime - startTime) / 1000;
        result.api_call_duration = apiCallDuration;
        
        console.log('Comparison result:', result);
        console.log(`API call took ${apiCallDuration.toFixed(2)} seconds`);

        // Store baseline results and trigger success callback with comparison data
        if (result.status === 'success') {
          if (result.baseline && onBaselineResultsChange) {
            onBaselineResultsChange(result.baseline);
          }
          if (onSimulationSuccess) {
            // Pass the entire result object which includes baseline, newConfig, and comparison
            onSimulationSuccess(result);
          }
        }

      } else {
        // Standard mode: call regular simulation endpoint
        const payload = {
          // Input configurations
          stationData: selectedStationData,
          dateRange: {
            startDate: startDate ? startDate.toISOString() : null,
            endDate: endDate ? endDate.toISOString() : null
          },
          incidentType: selectedIncidentType,
          
          // Model configurations
          models: {
            incident: selectedIncidentModel,
            travelTime: selectedTravelTimeModel,
            serviceTime: selectedServiceTimeModel,
            dispatch: selectedDispatchPolicy
          },
          
          // Legacy fields for backward compatibility
          selectedIncidentFile,
          selectedStationFile,
          selectedServiceZoneFile: selectedDispatchPolicy === 'firebeats' ? selectedServiceZoneFile : undefined,
          dispatchPolicy: selectedDispatchPolicy,
          
          stations: stations.map(station => {
            const apparatusCounts = stationApparatusCounts.get(station.id);
            const apparatus = apparatusCounts 
              ? convertApparatusCountsToSimpleArray(apparatusCounts)
              : []; 
            return {
              id: station.id,
              name: station.displayName,
              lat: station.lat,
              lon: station.lon, 
              apparatus: apparatus,
              serviceZone: station.serviceZone, 
            };
          }),
          responseTime: parseInt(responseTime),
          maxDistance: parseFloat(maxDistance),
          options: {
            coverageAnalysis: true,
            responseTimeAnalysis: true,
            resourceOptimization: false
          }
        };
          
        console.log('Submitting simulation job with payload:', payload);

        // Run via the async job queue: submit + poll until done.
        const result = await runJob(
          'run-simulation',
          toSimIntent(payload),
          { onTick: (job) => { setJobProgress((prev) => ({ id: job.id, status: job.status, attempts: job.attempts, startedAt: prev?.startedAt ?? Date.now() })); refreshJobs(); }, onProgress: (p) => setIncidentProgress({ processed: p.processed, total: p.total, percent: p.percent }) },
        );

        clearTimeout(timeoutId);

        // Calculate API call duration
        const endTime = performance.now();
        const apiCallDuration = (endTime - startTime) / 1000; 
        
        // Add timing to the result
        result.api_call_duration = apiCallDuration;
        
        console.log('Simulation result:', result);
        console.log(`API call took ${apiCallDuration.toFixed(2)} seconds`);

        // Check if the status is success
        if (result.status === 'success') {
          if (onSimulationSuccess) {
              onSimulationSuccess(result);
          }
        }
      }
    } catch (error) {
      // Use a type guard to safely check for the AbortError (timeout)
      if (error instanceof Error && error.name === 'AbortError') {
          console.error('Simulation request timed out.');
          alert('The simulation request timed out. The server took too long to respond.');
      } else {
          console.error('Error running simulation:', error);
          alert(`Simulation failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
      }
    } finally {
      // Ensure the timeout is cleared if the error wasn't an abort (e.g., network error)
      clearTimeout(timeoutId);
      setIsSimulating(false); // Re-enable the button
      setJobProgress(null);
      setIncidentProgress(null);
    }
  };
  
  // Remove the enableTabs function as it's no longer needed
  // Tab enabling logic should be handled in the parent component

  return (
    <div style={{ flex: '1 1 0%', overflowY: 'auto', minHeight: 0, position: 'relative' }}>
      {/* Disabled overlay when simulating */}
      {isSimulating && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '320px',
          height: '100vh',
          backgroundColor: 'rgba(255, 255, 255, 0.9)',
          zIndex: 1000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'not-allowed'
        }}>
          <div className="text-center px-6 w-full">
            <div className="animate-spin rounded-full h-12 w-12 border-b-4 border-blue-600 mx-auto mb-4"></div>
            <p className="text-lg font-semibold text-gray-700">
              {isCounterfactualMode ? 'Running Comparison' : 'Running Simulation'}
            </p>

            {/* Live job-queue status panel */}
            {(() => {
              const status = jobProgress?.status ?? 'submitting';
              const labels: Record<string, string> = {
                submitting: 'Submitting job…',
                pending: 'Queued — waiting for a worker',
                running: 'Worker is running the simulation',
                done: 'Done',
                failed: 'Failed',
              };
              const dotColor: Record<string, string> = {
                submitting: '#9ca3af',
                pending: '#f59e0b',
                running: '#3b82f6',
                done: '#16a34a',
                failed: '#dc2626',
              };
              const steps = ['submitting', 'pending', 'running', 'done'];
              const activeIdx = Math.max(steps.indexOf(status), 0);
              return (
                <div className="mt-4 mx-auto max-w-[260px] rounded-lg border border-gray-200 bg-white/90 p-4 text-left shadow-sm">
                  <div className="flex items-center gap-2 mb-2">
                    <span
                      className="inline-block h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: dotColor[status] ?? '#9ca3af' }}
                    />
                    <span className="text-sm font-medium text-gray-800">{labels[status] ?? status}</span>
                  </div>
                  {/* step bar */}
                  <div className="flex gap-1 mb-3">
                    {steps.map((s, i) => (
                      <div
                        key={s}
                        className="h-1.5 flex-1 rounded-full"
                        style={{ backgroundColor: i <= activeIdx ? (dotColor[status] ?? '#3b82f6') : '#e5e7eb' }}
                      />
                    ))}
                  </div>
                  {/* incident progress (from simulator logs) */}
                  {incidentProgress && incidentProgress.total > 0 && (
                    <div className="mb-3">
                      <div className="flex justify-between text-xs text-gray-600 mb-1">
                        <span>Incidents processed</span>
                        <span className="font-mono">
                          {incidentProgress.processed.toLocaleString()} / {incidentProgress.total.toLocaleString()} ({incidentProgress.percent}%)
                        </span>
                      </div>
                      <div className="h-2 w-full rounded-full bg-gray-200 overflow-hidden">
                        <div
                          className="h-full rounded-full transition-[width] duration-500"
                          style={{ width: `${incidentProgress.percent}%`, backgroundColor: '#3b82f6' }}
                        />
                      </div>
                    </div>
                  )}
                  <dl className="text-xs text-gray-500 space-y-1">
                    <div className="flex justify-between">
                      <dt>Job ID</dt>
                      <dd className="font-mono text-gray-700">{jobProgress?.id ?? '—'}</dd>
                    </div>
                    <div className="flex justify-between">
                      <dt>Elapsed</dt>
                      <dd className="font-mono text-gray-700">{jobElapsed}s</dd>
                    </div>
                    {(jobProgress?.attempts ?? 0) > 1 && (
                      <div className="flex justify-between">
                        <dt>Attempt</dt>
                        <dd className="font-mono text-gray-700">{jobProgress?.attempts}</dd>
                      </div>
                    )}
                  </dl>
                </div>
              );
            })()}
          </div>
        </div>
      )}
      
      <Card 
        className="border-0 rounded-none flex flex-col" 
        style={{ 
          minHeight: '100%',
          borderTop: isCounterfactualMode ? '3px solid #3b82f6' : 'none'
        }}
      >
        {/* Header - Fixed with Collapse Button */}
        <CardHeader 
          className="flex-shrink-0 pb-4"
          style={{
            backgroundColor: isCounterfactualMode ? '#eff6ff' : 'transparent',
            transition: 'background-color 0.3s ease'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
            <CardTitle className="flex items-center gap-2">
              <Settings className="w-5 h-5" />
              Simulation Controls
            </CardTitle>
            <button
              onClick={onToggleCollapse}
              style={{
                padding: '0.5rem',
                border: '1px solid #e5e7eb',
                borderRadius: '4px',
                cursor: 'pointer',
                backgroundColor: '#ffffff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
          </div>
          
          {/* Mode Toggle */}
          <div className="mt-4 p-3 bg-white rounded-lg border border-gray-200 shadow-sm">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <GitCompare className={`w-4 h-4 ${isCounterfactualMode ? 'text-blue-600' : 'text-gray-400'}`} />
                <span className="text-sm font-medium">
                  {isCounterfactualMode ? 'Counterfactual Mode' : 'Standard Mode'}
                </span>
              </div>
              <Switch
                checked={isCounterfactualMode}
                onCheckedChange={(checked: boolean) => {
                  console.log('Switch toggled, new value:', checked);
                  if (onCounterfactualModeChange) {
                    console.log('Calling onCounterfactualModeChange with:', checked);
                    onCounterfactualModeChange(checked);
                  } else {
                    console.error('onCounterfactualModeChange is not defined!');
                  }
                }}
              />
            </div>
            {/* Debug button - can be removed after testing */}
            <Button
              size="sm"
              variant="outline"
              className="w-full text-xs"
              onClick={() => {
                console.log('Debug button clicked, current mode:', isCounterfactualMode);
                if (onCounterfactualModeChange) {
                  onCounterfactualModeChange(!isCounterfactualMode);
                }
              }}
            >
              {isCounterfactualMode ? 'Switch to Standard Mode' : 'Switch to Counterfactual Mode'}
            </Button>
            {isCounterfactualMode && (
              <p className="text-xs text-blue-600 mt-2">
                📊 Compare response metrics with hypothetical station placement
              </p>
            )}
          </div>
        </CardHeader>

        {/* Scrollable Content */}
        <CardContent className="space-y-6 pb-6">
          {/* Clear Settings Button */}
          <div className="space-y-4">
            <Button
              onClick={onClearSettings}
              variant="outline"
              className="w-full"
            >
              Clear Settings
            </Button>
          </div>

          <Separator />

          {/* Input Section */}
          <div className="space-y-4">
            <h4 className="font-semibold text-gray-900">Input</h4>
            
            {/* Station Data - Hidden in Counterfactual Mode */}
            {!isCounterfactualMode && (
              <div>
                <Label>Station Data</Label>
                <div className="mt-2">
                  <select
                    value={selectedStationData || ''}
                    onChange={(e) => onStationDataChange?.(e.target.value)}
                    className="w-full p-2 border rounded text-gray-400"
                    style={{ color: selectedStationData ? '#111827' : '#9CA3AF' }}
                  >
                    <option value="" disabled className="text-gray-400">Select station data</option>
                    {controlPanelConfig.stationData.options.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.name}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-gray-500 mt-1">
                    {selectedStationData 
                      ? controlPanelConfig.stationData.options.find(opt => opt.id === selectedStationData)?.description
                      : 'Select station data'
                    }
                  </p>
                </div>
              </div>
            )}

            {/* Optimized Stations Options - Show when optimized_stations is selected in either mode */}
            {selectedStationData === 'optimized_stations' && !isCounterfactualMode && (
              <div className="space-y-4 p-4 bg-blue-50 rounded-lg border border-blue-200">
                <h5 className="font-medium text-blue-900">Optimization Parameters</h5>
                
                {/* Grid Size Selection */}
                <div>
                  <Label>Grid Size</Label>
                  <div className="mt-2">
                    <select
                      value={selectedGridSize || '1_mile'}
                      onChange={(e) => onGridSizeChange?.(e.target.value)}
                      className="w-full p-2 border rounded"
                    >
                      <option value="0.5_mile">0.5 Mile Grid</option>
                      <option value="1_mile">1 Mile Grid</option>
                    </select>
                    <p className="text-xs text-gray-500 mt-1">
                      Grid resolution for station optimization
                    </p>
                  </div>
                </div>

                {/* Number of New Stations */}
                <div>
                  <Label>Number of New Stations</Label>
                  <div className="mt-2">
                    <select
                      value={selectedNewStations || 1}
                      onChange={(e) => onNewStationsChange?.(parseInt(e.target.value))}
                      className="w-full p-2 border rounded"
                    >
                      {(() => {
                        // Get max stations for current grid size
                        const optimizedOption = controlPanelConfig.stationData.options.find(opt => opt.id === 'optimized_stations');
                        const currentGrid = optimizedOption?.gridSizes?.find(grid => grid.id === (selectedGridSize || '1_mile'));
                        const maxStations = currentGrid?.maxNewStations || 5;
                        
                        return Array.from({ length: maxStations }, (_, i) => i + 1).map(num => (
                          <option key={num} value={num}>
                            {num} New Station{num > 1 ? 's' : ''}
                          </option>
                        ));
                      })()}
                    </select>
                    <p className="text-xs text-gray-500 mt-1">
                      Additional optimized stations (1 Engine + 1 Ambulance each)
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Counterfactual Mode: Configuration */}
            {isCounterfactualMode && (
              <div className="space-y-3 p-4 bg-blue-50 rounded-lg border border-blue-200">
                <div className="flex items-center gap-2">
                  <GitCompare className="w-4 h-4 text-blue-600" />
                  <h5 className="font-medium text-blue-900">Counterfactual Analysis</h5>
                </div>
                <p className="text-xs text-blue-700">
                  Compare baseline configuration against a hypothetical scenario.
                </p>
                <div className="space-y-3">
                  <div className="bg-white p-2 rounded border border-blue-200">
                    <p className="text-xs font-medium text-gray-700 mb-1">
                      📍 Baseline (Fixed)
                    </p>
                    <p className="text-xs text-gray-600">
                      Default Fire Stations
                    </p>
                  </div>
                  
                  <div>
                    <Label className="text-xs font-medium text-gray-700">New Station Configuration</Label>
                    <select
                      value={selectedStationData || ''}
                      onChange={(e) => onStationDataChange?.(e.target.value)}
                      className="w-full p-2 border rounded text-sm mt-1"
                      style={{ color: selectedStationData ? '#111827' : '#9CA3AF' }}
                    >
                      <option value="" disabled className="text-gray-400">Select configuration</option>
                      <option value="custom_stations">Custom Stations Layout</option>
                      <option value="optimized_stations">Optimized New Stations</option>
                    </select>
                    {selectedStationData === 'custom_stations' && (
                      <p className="text-xs text-gray-500 mt-1">
                        Add/move stations manually on the map
                      </p>
                    )}
                    {selectedStationData === 'optimized_stations' && (
                      <p className="text-xs text-gray-500 mt-1">
                        Use algorithmically optimized station placements
                      </p>
                    )}
                  </div>
                  
                  {/* Optimized Stations Parameters - Show when optimized is selected */}
                  {selectedStationData === 'optimized_stations' && (
                    <div className="space-y-3 p-3 bg-white rounded border border-blue-200">
                      <h6 className="text-xs font-medium text-gray-700">Optimization Parameters</h6>
                      
                      {/* Grid Size Selection */}
                      <div>
                        <Label className="text-xs">Grid Size</Label>
                        <div className="mt-1">
                          <select
                            value={selectedGridSize || '1_mile'}
                            onChange={(e) => onGridSizeChange?.(e.target.value)}
                            className="w-full p-2 border rounded text-sm"
                          >
                            <option value="0.5_mile">0.5 Mile Grid</option>
                            <option value="1_mile">1 Mile Grid</option>
                          </select>
                          <p className="text-xs text-gray-500 mt-1">
                            Grid resolution for station optimization
                          </p>
                        </div>
                      </div>

                      {/* Number of New Stations */}
                      <div>
                        <Label className="text-xs">Number of New Stations</Label>
                        <div className="mt-1">
                          <select
                            value={selectedNewStations || 1}
                            onChange={(e) => onNewStationsChange?.(parseInt(e.target.value))}
                            className="w-full p-2 border rounded text-sm"
                          >
                            {(() => {
                              const optimizedOption = controlPanelConfig.stationData.options.find(opt => opt.id === 'optimized_stations');
                              const currentGrid = optimizedOption?.gridSizes?.find(grid => grid.id === (selectedGridSize || '1_mile'));
                              const maxStations = currentGrid?.maxNewStations || 5;
                              
                              return Array.from({ length: maxStations }, (_, i) => i + 1).map(num => (
                                <option key={num} value={num}>
                                  {num} New Station{num > 1 ? 's' : ''}
                                </option>
                              ));
                            })()}
                          </select>
                          <p className="text-xs text-gray-500 mt-1">
                            Additional optimized stations (1 Engine + 1 Ambulance each)
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                  
                  {baselineResults && (
                    <div className="text-xs text-green-700 bg-green-50 p-2 rounded border border-green-200">
                      ✓ Baseline captured: {baselineResults.total_incidents || 0} incidents
                    </div>
                  )}
                </div>
              </div>
            )}

          </div>

          <Separator />

          {/* Incident Type Section */}
          <div className="space-y-4">
            <h4 className="font-semibold text-gray-900">Incident Type</h4>
            <div>
              <Label>Type</Label>
              <div className="mt-2">
                <select
                  value={selectedIncidentType || 'ems_fire'}
                  onChange={(e) => onIncidentTypeChange?.(e.target.value)}
                  className="w-full p-2 border rounded"
                  style={{ color: '#111827' }}
                >
                  <option value="ems_fire">EMS + Fire</option>
                  <option value="fire">Fire Only</option>
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  {selectedIncidentType === 'fire' ? 'Fire incidents only' : 'Both EMS and Fire incidents'}
                </p>
              </div>
            </div>
          </div>

          <Separator />

          {/* Models Section */}
          <div className="space-y-4">
            <h4 className="font-semibold text-gray-900">Models</h4>
            
            {/* Incident Model */}
            <div>
              <Label>Incident</Label>
              <div className="mt-2">
                <select
                  value={selectedIncidentModel || ''}
                  onChange={(e) => onIncidentModelChange?.(e.target.value)}
                  className="w-full p-2 border rounded text-gray-400"
                  style={{ color: selectedIncidentModel ? '#111827' : '#9CA3AF' }}
                >
                  <option value="" disabled className="text-gray-400">Select incident model</option>
                  {controlPanelConfig.incidentModels.options.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  {selectedIncidentModel 
                    ? controlPanelConfig.incidentModels.options.find(model => model.id === selectedIncidentModel)?.description
                    : 'Select an incident model'
                  }
                </p>
              </div>
            </div>

            {/* Date Range Selector - Only show when incident model is selected */}
            {selectedIncidentModel && (
              <div>
                <Label>Date Range</Label>
                <div className="mt-2 space-y-2">
                  {/* Start Date */}
                  <div>
                    <Label className="text-sm text-gray-600">From</Label>
                    <input
                      type="date"
                      value={startDate ? startDate.toISOString().split('T')[0] : ''}
                      onChange={(e) => {
                        const date = e.target.value ? new Date(e.target.value) : undefined;
                        onStartDateChange?.(date);
                      }}
                      max={endDate ? endDate.toISOString().split('T')[0] : new Date().toISOString().split('T')[0]}
                      className="w-full p-2 border rounded"
                    />
                  </div>

                  {/* End Date */}
                  <div>
                    <Label className="text-sm text-gray-600">To</Label>
                    <input
                      type="date"
                      value={endDate ? endDate.toISOString().split('T')[0] : ''}
                      onChange={(e) => {
                        const date = e.target.value ? new Date(e.target.value) : undefined;
                        onEndDateChange?.(date);
                      }}
                      min={startDate ? startDate.toISOString().split('T')[0] : undefined}
                      max={new Date().toISOString().split('T')[0]}
                      className="w-full p-2 border rounded"
                    />
                  </div>

                  <div className="flex items-center justify-between">
                    <p className="text-xs text-gray-500">
                      Select range for incidents
                    </p>
                    {startDate && endDate && (
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={isLoadingIncidents}
                        onClick={async () => {
                          try {
                            setIsLoadingIncidents(true);
                            setIncidentLoadError(null);
                            console.log('Manual incident load triggered for:', selectedIncidentModel, startDate, endDate);
                            
                            // Import the API instance
                            const { incidentAPI } = await import('../services/incidentAPI');
                            
                            // Check if synthetic incidents are selected
                            if (selectedIncidentModel === 'synthetic_incidents') {
                              // Generate synthetic incidents
                              console.log('Generating synthetic incidents for date range:', startDate, 'to', endDate);
                              
                              // Step 1: Generate incidents using the API service
                              const generateResponse = await incidentAPI.generateIncidents(
                                selectedStationData || 'default_stations',
                                {
                                  start: startDate.toISOString(),
                                  end: endDate.toISOString()
                                },
                                { incidentType: selectedIncidentType } // Include incident type
                              );

                              if (generateResponse.status !== 'success') {
                                throw new Error(`Backend failed to generate incidents: ${generateResponse.message}`);
                              }

                              console.log('Synthetic incidents generated successfully:', generateResponse.data);

                              // Step 2: Parse the generated CSV content directly
                              if (generateResponse.data && generateResponse.data.csvContent) {
                                const csvContent = generateResponse.data.csvContent;
                                
                                // Parse CSV into incidents array using the existing helper
                                const incidents = parseCSVToIncidents(csvContent);
                                
                                if (incidents.length > 0) {
                                  onIncidentsChange?.(incidents);
                                  console.log(`Loaded ${incidents.length} synthetic incidents manually`);
                                  setIncidentLoadError(null);
                                  
                                  // Update the loaded incidents date range
                                  setLoadedIncidentsDateRange({
                                    startDate: startDate ? new Date(startDate) : null,
                                    endDate: endDate ? new Date(endDate) : null
                                  });
                                  
                                  // Create simple stats from the generated incidents
                                  const stats = {
                                    total: incidents.length,
                                    dateRange: {
                                      start: startDate.toISOString().split('T')[0],
                                      end: endDate.toISOString().split('T')[0]
                                    }
                                  };
                                  onHistoricalIncidentStatsChange?.(stats);
                                } else {
                                  throw new Error('No incidents were generated');
                                }
                              } else {
                                throw new Error('No CSV content received from generation');
                              }
                            } else {
                              // Load historical incidents (existing logic)
                              const response = await incidentAPI.getIncidents(
                                selectedIncidentModel!,
                                {
                                  dateRange: {
                                    start: startDate.toISOString().split('T')[0],
                                    end: endDate.toISOString().split('T')[0]
                                  },
                                  incidentType: selectedIncidentType
                                }
                              );
                              
                              // Update the incidents via the callback if successful
                              if (response.status === 'success' && response.data) {
                                onIncidentsChange?.(response.data);
                                console.log(`Loaded ${response.data.length} historical incidents manually`);
                                setIncidentLoadError(null);
                                
                                // Update the loaded incidents date range
                                setLoadedIncidentsDateRange({
                                  startDate: startDate ? new Date(startDate) : null,
                                  endDate: endDate ? new Date(endDate) : null
                                });
                              } else {
                                const errorMsg = response.message || 'Failed to load incidents';
                                setIncidentLoadError(errorMsg);
                                console.error('API call failed:', errorMsg);
                              }
                            }
                          } catch (error) {
                            const errorMsg = error instanceof Error ? error.message : 'Unknown error occurred';
                            setIncidentLoadError(errorMsg);
                            console.error('Failed to load incidents manually:', error);
                          } finally {
                            setIsLoadingIncidents(false);
                          }
                        }}
                        className={`ml-2 px-3 py-1 text-xs ${incidentLoadError ? 'border-red-500 text-red-600' : ''}`}
                      >
                        {isLoadingIncidents ? (
                          <>
                            <div className="animate-spin rounded-full h-3 w-3 border-b-2 border-current mr-1"></div>
                            Loading...
                          </>
                        ) : (
                          selectedIncidentModel === 'synthetic_incidents' ? 'Generate Incidents' : 'Load Incidents'
                        )}
                      </Button>
                    )}
                  </div>
                  
                  {/* Error message display */}
                  {incidentLoadError && (
                    <div className="mt-2 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-600">
                      <strong>Error:</strong> {incidentLoadError}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Travel Time Model */}
            <div>
              <Label>Travel Time</Label>
              <div className="mt-2">
                <select
                  value={selectedTravelTimeModel || ''}
                  onChange={(e) => onTravelTimeModelChange?.(e.target.value)}
                  className="w-full p-2 border rounded text-gray-400"
                  style={{ color: selectedTravelTimeModel ? '#111827' : '#9CA3AF' }}
                >
                  <option value="" disabled className="text-gray-400">Select travel time model</option>
                  {controlPanelConfig.travelTimeModels.options.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  {selectedTravelTimeModel 
                    ? controlPanelConfig.travelTimeModels.options.find(model => model.id === selectedTravelTimeModel)?.description
                    : 'Select a travel time model'
                  }
                </p>
              </div>
            </div>

            {/* Service Time Model */}
            <div>
              <Label>Service Time</Label>
              <div className="mt-2">
                <select
                  value={selectedServiceTimeModel || ''}
                  onChange={(e) => onServiceTimeModelChange?.(e.target.value)}
                  className="w-full p-2 border rounded text-gray-400"
                  style={{ color: selectedServiceTimeModel ? '#111827' : '#9CA3AF' }}
                >
                  <option value="" disabled className="text-gray-400">Select service time model</option>
                  {controlPanelConfig.serviceTimeModels.options.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  {selectedServiceTimeModel 
                    ? controlPanelConfig.serviceTimeModels.options.find(model => model.id === selectedServiceTimeModel)?.description
                    : 'Select a service time model'
                  }
                </p>
              </div>
            </div>

            {/* Dispatch Policy */}
            <div>
              <Label>Dispatch Policy</Label>
              <div className="mt-2">
                <select
                  value={selectedDispatchPolicy || ''}
                  onChange={(e) => onDispatchPolicyChange?.(e.target.value)}
                  className="w-full p-2 border rounded text-gray-400"
                  style={{ color: selectedDispatchPolicy ? '#111827' : '#9CA3AF' }}
                >
                  <option value="" disabled className="text-gray-400">Select dispatch policy</option>
                  {controlPanelConfig.dispatchPolicies.options.map((policy) => {
                    const isFirebeats = policy.id === 'firebeats';
                    const isOptimizedStations = selectedStationData === 'optimized_stations';
                    const isDisabled = isFirebeats && isOptimizedStations;
                    
                    return (
                      <option 
                        key={policy.id} 
                        value={policy.id}
                        disabled={isDisabled}
                        className={isDisabled ? 'text-gray-400' : ''}
                      >
                        {policy.name}{isDisabled ? ' (Not available for optimized stations)' : ''}
                      </option>
                    );
                  })}
                </select>
                <p className="text-xs text-gray-500 mt-1">
                  {selectedDispatchPolicy 
                    ? controlPanelConfig.dispatchPolicies.options.find(policy => policy.id === selectedDispatchPolicy)?.description
                    : 'Select a dispatch policy'
                  }
                </p>
              </div>
            </div>


          </div>

          <Separator />

          {/* Configuration Parameters */}
          {/* <div className="space-y-4">
            <h4 className="font-semibold text-gray-900">Simulation Parameters</h4>

            <div>
              <Label htmlFor="response-time">
                Target Response Time (minutes)
              </Label>
              <Input
                id="response-time"
                type="number"
                value={responseTime}
                onChange={(e) => setResponseTime(e.target.value)}
                className="mt-1"
              />
            </div>

            <div>
              <Label htmlFor="max-distance">Max Coverage Distance (km)</Label>
              <Input
                id="max-distance"
                type="number"
                value={maxDistance}
                onChange={(e) => setMaxDistance(e.target.value)}
                className="mt-1"
              />
            </div>
          </div>

          <Separator /> */}

          {/* Additional Options */}
          {/* <div className="space-y-3">
            <h4 className="font-semibold text-gray-900">Analysis Options</h4>
            <div className="space-y-2">
              <label className="flex items-center space-x-2">
                <input type="checkbox" defaultChecked className="rounded" />
                <span className="text-sm">Coverage Analysis</span>
              </label>
              <label className="flex items-center space-x-2">
                <input type="checkbox" defaultChecked className="rounded" />
                <span className="text-sm">Response Time Analysis</span>
              </label>
              <label className="flex items-center space-x-2">
                <input type="checkbox" className="rounded" />
                <span className="text-sm">Resource Optimization</span>
              </label>
            </div>
          </div>

          <Separator /> */}
          
          <Separator />

          {/* Run Simulation Button */}
          <div className="pt-4 space-y-3">
            <Button
              onClick={handleRunSimulation}
              disabled={isSimulating || !isFormValid()}
              className="w-full h-12 font-semibold"
              style={{
                backgroundColor: !isFormValid() && !isSimulating 
                  ? '#d1d5db' 
                  : isCounterfactualMode 
                    ? '#2563eb' 
                    : '#16a34a',
                color: 'white',
                border: !isFormValid() && !isSimulating ? '2px solid #9ca3af' : 'none',
                opacity: !isFormValid() && !isSimulating ? 0.7 : 1,
                cursor: !isFormValid() && !isSimulating ? 'not-allowed' : 'pointer'
              }}
              size="lg"
            >
              {isSimulating ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                  {isCounterfactualMode ? 'RUNNING COMPARISON...' : 'SIMULATING...'}
                </>
              ) : (
                <>
                  {isCounterfactualMode ? <GitCompare className="w-4 h-4 mr-2" /> : <Play className="w-4 h-4 mr-2" />}
                  {isCounterfactualMode ? 'RUN COMPARISON' : 'RUN SIMULATION'}
                </>
              )}
            </Button>
            
            {/* Validation message area with consistent height */}
            <div className="min-h-[3rem] flex items-center justify-center">
              {!isFormValid() && !isSimulating && (
                <div className="text-xs text-center">
                  <div className="text-red-600 font-semibold bg-red-50 border border-red-200 rounded p-2">
                    <p className="font-bold mb-1">Missing Required Fields:</p>
                    {getMissingFields().map((field, index) => (
                      <p key={index} className="mt-1">• {field}</p>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Save Station Configuration Button */}
            <Button
              onClick={handleSaveStationConfiguration}
              disabled={stations.length === 0}
              variant="outline"
              className={`w-full h-10 ${stations.length === 0 ? "opacity-50 cursor-not-allowed" : ""}`}
              size="lg"
            >
              <Download className="w-4 h-4 mr-2" />
              SAVE STATION CONFIG
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
