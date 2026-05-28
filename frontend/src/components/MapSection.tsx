import React, { useEffect, useState, useCallback, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { categoryColors } from '../config/categoryColors';
import { processStations, createDetailedStationPopup, createFirebeatsStationPopup, createStationIcon, ProcessedStation, processIncidents, createIncidentPopup, createIncidentIcon, ProcessedIncident, Apparatus } from '../utils/dataProcessing';
import { createDraggableStationMarker, createStaticStationMarker, defaultDragHandlers, setupGlobalDeleteHandler } from '../utils/markerControl';
import config from '../config/mapConfig.json';
import controlPanelConfig from '../config/controlPanelConfig.json';

// Apparatus counts interface for the new design
interface ApparatusCounts {
  [key: string]: number;
}

// All possible apparatus types from CSV columns
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

// Extend the Window interface to include our custom global functions
declare global {
  interface Window {
    deleteStation?: (stationId: string) => void;
    firebeatsUpdateServiceZone?: (stationId: string, zone: string) => void;
    openApparatusManager?: (stationId: string) => void;
  }
}

interface MapSectionProps {
  simulationResults: any;
  selectedIncidentFile: string;
  selectedStationFile: string;
  selectedDispatchPolicy: string;
  selectedServiceZoneFile: string;
  selectedStationData?: string;
  selectedGridSize?: string;
  selectedNewStations?: number;
  stations: ProcessedStation[];
  injectedStations?: ProcessedStation[] | null;
  onStationsChange: (stations: ProcessedStation[]) => void;
  onApparatusChange?: (stationId: string, apparatus: Apparatus[]) => void;
  stationApparatusCounts: Map<string, ApparatusCounts>;
  setStationApparatusCounts: React.Dispatch<React.SetStateAction<Map<string, ApparatusCounts>>>;
  originalApparatusCounts: Map<string, ApparatusCounts>;
  setOriginalApparatusCounts: React.Dispatch<React.SetStateAction<Map<string, ApparatusCounts>>>;
  selectedIncidentModel?: string;
  startDate?: Date;
  endDate?: Date;
  incidents?: any[]; // Incidents passed from parent component
  onIncidentsCountChange?: (count: number) => void;
  onClearLayers?: () => void;
  onMapInstanceChange?: (map: L.Map | null) => void;
  isCounterfactualMode?: boolean;
}

interface FireStation {
  id: string;
  name: string;
  lat: number;
  lng: number;
  resources: string[];
}

interface Incident {
  id: string;
  type: string;
  lat: number;
  lng: number;
  timestamp: string;
  severity: 'low' | 'medium' | 'high';
}

export function MapSection({ 
  simulationResults, 
  selectedIncidentFile, 
  selectedStationFile, 
  selectedDispatchPolicy,
  selectedServiceZoneFile,
  selectedStationData,
  selectedGridSize,
  selectedNewStations,
  stations,
  injectedStations,
  onStationsChange,
  onApparatusChange,
  stationApparatusCounts,
  setStationApparatusCounts,
  originalApparatusCounts,
  setOriginalApparatusCounts,
  selectedIncidentModel,
  startDate,
  endDate,
  incidents: externalIncidents = [],
  onIncidentsCountChange,
  onClearLayers,
  onMapInstanceChange,
  isCounterfactualMode = false
}: MapSectionProps) {
  const [incidents, setIncidents] = useState<ProcessedIncident[]>([]);
  const [mapInstance, setMapInstance] = useState<L.Map | null>(null);
  const [isLoadingIncidents, setIsLoadingIncidents] = useState(false);
  const [isLoadingStations, setIsLoadingStations] = useState(false);
  
  // Refs to access current state in drag handlers
  const stationInitialZonesRef = useRef<Map<string, any>>(new Map());
  const zoneGeometriesRef = useRef<L.GeoJSON | null>(null);

  // Sync external incidents with internal state
  useEffect(() => {
    if (externalIncidents.length > 0) {
      console.log('Syncing external incidents to MapSection:', externalIncidents.length);
      setIncidents(externalIncidents);
      if (onIncidentsCountChange) onIncidentsCountChange(externalIncidents.length);
    }
  }, [externalIncidents, onIncidentsCountChange]);
  
  // State to trigger reload when synthetic incidents are generated
  const [synthIncidentsTimestamp, setSynthIncidentsTimestamp] = useState<string | null>(null);

  // Watch for changes in synthetic incidents
  useEffect(() => {
    const checkSynthIncidents = () => {
      if (selectedIncidentModel === 'synthetic_incidents') {
        const timestamp = localStorage.getItem('synth-incidents-timestamp');
        if (timestamp && timestamp !== synthIncidentsTimestamp) {
          console.log('Detected new synthetic incidents, triggering reload');
          setSynthIncidentsTimestamp(timestamp);
        }
      }
    };
    
    // Check immediately
    checkSynthIncidents();
    
    // Set up interval to check for changes
    const interval = setInterval(checkSynthIncidents, 1000);
    
    return () => clearInterval(interval);
  }, [selectedIncidentModel, synthIncidentsTimestamp]);

  // No longer syncing with external incidents - using localStorage approach
  const [markerLayer, setMarkerLayer] = useState<L.LayerGroup | null>(null);
  const [serviceZoneLayer, setServiceZoneLayer] = useState<L.LayerGroup | null>(null);
  const [stationMarkers, setStationMarkers] = useState<Map<string, L.Marker>>(new Map()); // Track station markers
  const [apparatusManagerOpen, setApparatusManagerOpen] = useState(false);
  const [selectedStationForApparatus, setSelectedStationForApparatus] = useState<ProcessedStation | null>(null);
  const [stationApparatus, setStationApparatus] = useState<Map<string, Apparatus[]>>(new Map());
  const [editingApparatus, setEditingApparatus] = useState<string | null>(null);
  
  // Layer toggle states
  const [gridsLayer, setGridsLayer] = useState<L.LayerGroup | null>(null);
  const [zonesLayer, setZonesLayer] = useState<L.LayerGroup | null>(null);
  const [showGrids, setShowGrids] = useState(false);
  const [showZones, setShowZones] = useState(false);
  const [showStations, setShowStations] = useState(true);
  const [showIncidents, setShowIncidents] = useState(true);
  const [currentStationData, setCurrentStationData] = useState<string>('');
  const [isAddingStation, setIsAddingStation] = useState(false);
  
  // Track zone geometries and station initial zones for drag restrictions
  const [zoneGeometries, setZoneGeometries] = useState<L.GeoJSON | null>(null);
  const [stationInitialZones, setStationInitialZones] = useState<Map<string, any>>(new Map());
  
  // Update refs when state changes
  useEffect(() => {
    zoneGeometriesRef.current = zoneGeometries;
  }, [zoneGeometries]);
  
  useEffect(() => {
    stationInitialZonesRef.current = stationInitialZones;
  }, [stationInitialZones]);

  // Caches and refs to avoid duplicate/network-heavy loads
  const jsonCacheRef = useRef<Map<string, any>>(new Map());
  const textCacheRef = useRef<Map<string, string>>(new Map());
  const gridsUrlRef = useRef<string | null>(null);
  const zonesUrlRef = useRef<string | null>(null);
  const stationsLengthRef = useRef<number>(0);

  const fetchJsonCached = useCallback(async (url: string) => {
    const cache = jsonCacheRef.current;
    if (cache.has(url)) {
      return cache.get(url);
    }
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to fetch ${url}: ${res.status}`);
    const data = await res.json();
    cache.set(url, data);
    return data;
  }, []);

  const fetchTextCached = useCallback(async (url: string) => {
    const cache = textCacheRef.current;
    if (cache.has(url)) {
      return cache.get(url) as string;
    }
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Failed to fetch ${url}: ${res.status}`);
    const text = await res.text();
    cache.set(url, text);
    return text;
  }, []);

  // Helper function to get apparatus data for payload
  const getStationWithApparatus = useCallback((station: ProcessedStation) => {
    const apparatus = stationApparatus.get(station.id) || [];
    return {
      ...station,
      apparatus: apparatus.map(app => ({
        id: app.id,
        type: app.type,
        name: app.name,
        status: app.status,
        crew: app.crew
      }))
    };
  }, [stationApparatus]);

  // Create apparatus from CSV equipment columns
  const createApparatusFromCSV = useCallback((stationRow: any, stationId: string, stationNumber: number): Apparatus[] => {
    const apparatus: Apparatus[] = [];
    const equipmentColumns = ['Engine_ID', 'Truck', 'Rescue', 'Hazard', 'Squad', 'FAST', 'Medic', 'Brush', 'Boat', 'UTV', 'REACH', 'Chief'];
    
    equipmentColumns.forEach(column => {
      const count = parseInt(stationRow[column]) || 0;
      if (count > 0) {
        for (let i = 1; i <= count; i++) {
          let apparatusType: Apparatus['type'];
          let apparatusName: string;
          
          switch (column) {
            case 'Engine_ID':
              apparatusType = 'Engine';
              apparatusName = `Engine ${stationNumber.toString().padStart(2, '0')}${count > 1 ? `-${i}` : ''}`;
              break;
            case 'Truck':
              apparatusType = 'Ladder';
              apparatusName = `Truck ${stationNumber.toString().padStart(2, '0')}${count > 1 ? `-${i}` : ''}`;
              break;
            case 'Rescue':
              apparatusType = 'Rescue';
              apparatusName = `Rescue ${stationNumber.toString().padStart(2, '0')}${count > 1 ? `-${i}` : ''}`;
              break;
            case 'Medic':
              apparatusType = 'Ambulance';
              apparatusName = `Medic ${stationNumber.toString().padStart(2, '0')}${count > 1 ? `-${i}` : ''}`;
              break;
            case 'Chief':
              apparatusType = 'Chief';
              apparatusName = `Chief ${stationNumber.toString().padStart(2, '0')}${count > 1 ? `-${i}` : ''}`;
              break;
            default:
              apparatusType = 'Engine'; // Default fallback
              apparatusName = `${column} ${stationNumber.toString().padStart(2, '0')}${count > 1 ? `-${i}` : ''}`;
          }
          
          apparatus.push({
            id: `${column.toLowerCase()}-${stationId}-${i}`,
            type: apparatusType,
            name: apparatusName,
            status: 'Available',
            crew: 1 // Each apparatus represents a count of 1
          });
        }
      }
    });
    
    return apparatus;
  }, []);

  // Extract apparatus counts from CSV row
  const extractApparatusCountsFromCSV = useCallback((stationRow: any): ApparatusCounts => {
    const counts: ApparatusCounts = {};
    APPARATUS_TYPES.forEach(apparatusType => {
      counts[apparatusType.key] = parseInt(stationRow[apparatusType.csvColumn]) || 0;
    });
    return counts;
  }, []);

  // Parse CSV data
  const parseCSV = useCallback((csvText: string) => {
    const lines = csvText.trim().split('\n');
    if (lines.length < 2) return [];
    const headers = lines[0].split(',').map(h => h.trim());
    return lines.slice(1).map(line => {
      if (!line.trim()) return null;
      const values = line.split(',');
      return headers.reduce((obj, header, index) => {
        obj[header] = values[index]?.trim() || '';
        return obj;
      }, {} as any);
    }).filter(Boolean); // Filter out any null entries from empty lines
  }, []);

  // Clear grids layer when grid size changes for optimized stations
  useEffect(() => {
    if (currentStationData === 'optimized_stations' && gridsLayer && mapInstance) {
      mapInstance.removeLayer(gridsLayer);
      setGridsLayer(null);
      setShowGrids(false);
    }
  }, [selectedGridSize, currentStationData, mapInstance]);

  // Prepare layer URLs and (optionally) load default stations for selected station dataset.
  const loadGeographicalLayers = useCallback(async (stationDataId: string) => {
    if (!mapInstance) return;



    // Mark as current immediately to avoid duplicate re-entrancy while async work runs
    setCurrentStationData(stationDataId);
    setIsLoadingStations(true);

    const controlPanel = await import('../config/controlPanelConfig.json');
    const stationConfig = controlPanel.stationData.options.find(opt => opt.id === stationDataId);
    if (!stationConfig) return;

    // Set URLs for lazy-loading on demand via toggles
    let gridFile = stationConfig.grids;
    
    // For optimized stations, use the grid file from the selected grid size configuration
    if (stationDataId === 'optimized_stations' && selectedGridSize && stationConfig.gridSizes) {
      const selectedGridConfig = stationConfig.gridSizes.find(gs => gs.id === selectedGridSize);
      if (selectedGridConfig && selectedGridConfig.grids) {
        gridFile = selectedGridConfig.grids;
      }
    }
    
    gridsUrlRef.current = gridFile ? `/data/${gridFile}` : null;
    zonesUrlRef.current = stationConfig.zones ? `/data/${stationConfig.zones}` : null;

    // Clear existing apparatus data to prevent duplicates
    setStationApparatus(new Map());
    setStationApparatusCounts(new Map());
    setOriginalApparatusCounts(new Map());

    // Clear existing layers from map but don't fetch new ones yet
    // Only clear if we're changing to a different station dataset, not just reloading the same one
    if (gridsLayer && currentStationData !== stationDataId) {
      mapInstance.removeLayer(gridsLayer);
      setGridsLayer(null);
      setShowGrids(false);
    }
    
    if (zonesLayer && currentStationData !== stationDataId) {
      mapInstance.removeLayer(zonesLayer);
      setZonesLayer(null);
      setShowZones(false);
    }

    // Load stations from the configured CSV file
    if (stationConfig.stations && !selectedStationFile) {
      try {
        // Always load existing stations first
        const existingStationsUrl = `/data/${stationConfig.stations}`;
        console.log('Loading existing stations from:', existingStationsUrl);
        const existingCsvText = await fetchTextCached(existingStationsUrl);
        const existingParsedStations = parseCSV(existingCsvText);

        // Process existing stations
        const existingStations = existingParsedStations.slice(0, 100).map((row, index) => {
          const stationNumberMatch = row.Stations?.match(/(\d+)/) || row['Facility Name']?.match(/(\d+)/);
          const stationNumber = stationNumberMatch ? parseInt(stationNumberMatch[1]) : index + 1;
          const stationName = row.Stations || row['Facility Name'] || `Station ${stationNumber}`;
          const stationId = row.StationID || row.id || `station-${index}`;

          const station: ProcessedStation = {
            id: stationId,
            name: stationName,
            address: row.Address || 'Address not available',
            lat: parseFloat(row.lat),
            lon: parseFloat(row.lon),
            stationNumber: stationNumber,
            displayName: `Station ${stationNumber.toString().padStart(2, '0')}`,
            apparatus: []
          };

          // Process existing station apparatus
          const apparatus = createApparatusFromCSV(row, station.id, stationNumber);
          setStationApparatus(prev => new Map(prev).set(station.id, apparatus));

          const apparatusCounts = extractApparatusCountsFromCSV(row);
          setStationApparatusCounts(prev => new Map(prev).set(station.id, apparatusCounts));
          setOriginalApparatusCounts(prev => new Map(prev).set(station.id, { ...apparatusCounts }));

          return station;
        }).filter(station => !isNaN(station.lat) && !isNaN(station.lon));

        let allStations = [...existingStations];

        // If optimized stations is selected, load and add new stations
        if (stationDataId === 'optimized_stations') {
          const gridSize = selectedGridSize || '1_mile';
          const newStationCount = selectedNewStations || 1;
          
          // Handle different grid size formats for file paths
          let folderName: string;
          let fileName: string;
          
          if (gridSize === '0.5_mile') {
            folderName = 'grid_0.5';
            fileName = 'grid05';
          } else {
            // Default to 1 mile
            folderName = 'grid_1';
            fileName = 'grid1';
          }
          
          const optimizedStationsUrl = `/data/optimized_firestations/${folderName}/optimized_fire_stations_${fileName}_new_stations${newStationCount}.csv`;
          console.log('Loading new optimized stations from:', optimizedStationsUrl);
          
          try {
            const optimizedCsvText = await fetchTextCached(optimizedStationsUrl);
            const optimizedParsedStations = parseCSV(optimizedCsvText);

            // Process new optimized stations
            const newStations = optimizedParsedStations.map((row, index) => {
              const stationId = row.StationID || `new-station-${index}`;
              const stationName = row.Stations || `Station ${index + 1}`;
              const nameMatch = stationName.match(/(\d+)/);
              const stationNumber = nameMatch ? parseInt(nameMatch[1]) : index + 40; // Start from 40+ for new stations

              const station: ProcessedStation = {
                id: stationId,
                name: stationName,
                address: 'New Optimized Station',
                lat: parseFloat(row.lat),
                lon: parseFloat(row.lon),
                stationNumber: stationNumber,
                displayName: `Station ${stationNumber.toString().padStart(2, '0')}`,
                apparatus: []
              };

              // Add default apparatus for new stations: 1 Engine + 1 Ambulance
              const apparatus: Apparatus[] = [
                {
                  id: `${station.id}-engine-1`,
                  type: 'Engine',
                  name: 'Engine 1',
                  status: 'Available',
                  crew: 4
                },
                {
                  id: `${station.id}-ambulance-1`,
                  type: 'Ambulance',
                  name: 'Ambulance 1',
                  status: 'Available',
                  crew: 2
                }
              ];
              setStationApparatus(prev => new Map(prev).set(station.id, apparatus));

              // Set apparatus counts for new stations (matching the actual apparatus created above)
              const apparatusCounts = {
                Engine_ID: 1,    // We create 1 Engine
                Truck: 0,
                Rescue: 0,
                Hazard: 0,
                Squad: 0,
                FAST: 0,
                Medic: 1,        // We create 1 Ambulance (but system uses "Medic" in counts)
                Brush: 0,
                Boat: 0,
                UTV: 0,
                REACH: 0,
                Chief: 0
              };
              setStationApparatusCounts(prev => new Map(prev).set(station.id, apparatusCounts));
              setOriginalApparatusCounts(prev => new Map(prev).set(station.id, { ...apparatusCounts }));

              return station;
            }).filter(station => !isNaN(station.lat) && !isNaN(station.lon));

            allStations = [...existingStations, ...newStations];
            console.log(`Added ${newStations.length} new optimized stations to ${existingStations.length} existing stations`);
          } catch (optimizedError) {
            console.error('Error loading optimized stations, using existing only:', optimizedError);
          }
        }

        console.log('Total processed stations:', allStations.length);
        onStationsChange(allStations);
      } catch (error) {
        console.error('Error loading default stations from CSV:', error);
      } finally {
        setIsLoadingStations(false);
      }
    } else {
      // No stations to load from config
      setIsLoadingStations(false);
    }
  }, [mapInstance, fetchTextCached, parseCSV, createApparatusFromCSV, extractApparatusCountsFromCSV, onStationsChange, selectedStationFile, gridsLayer, zonesLayer, selectedGridSize, selectedNewStations]);
  const toggleGridsLayer = useCallback(async () => {
    if (!mapInstance) return;

    // Lazy-load grids layer on first toggle
    if (!gridsLayer) {
      let gridUrl = gridsUrlRef.current;
      
      if (!gridUrl) return;
      
      try {
        const gridsData = await fetchJsonCached(gridUrl);
        if (!gridsData || !gridsData.features) {
          console.error('Invalid grid data received');
          return;
        }
        const gridsLayerGroup = L.layerGroup();
        
        L.geoJSON(gridsData, {
          style: {
            color: '#2563eb',
            weight: 2,
            opacity: 0.8,
            fillColor: '#3b82f6',
            fillOpacity: 0.1
          },
          onEachFeature: (feature, layer) => {
            if (feature.properties) {
              const props = feature.properties;
              // Handle different property formats
              const gridId = props.grid_id || props.cell_id || 'N/A';
              const primaryZone = props.primary_zone || 'N/A';
              const intersectingZones = props.intersecting_zones || 'N/A';
              const coordinates = props.x && props.y ? `(${props.x.toFixed(4)}, ${props.y.toFixed(4)})` : '';
              
              const popupContent = `
                <div class="p-2">
                  <h4 class="font-semibold">Grid Information</h4>
                  <p><strong>Grid ID:</strong> ${gridId}</p>
                  ${coordinates ? `<p><strong>Coordinates:</strong> ${coordinates}</p>` : ''}
                  <p><strong>Primary Zone:</strong> ${primaryZone}</p>
                  <p><strong>Intersecting Zones:</strong> ${intersectingZones}</p>
                </div>
              `;
              layer.bindPopup(popupContent);
            }
          }
        }).addTo(gridsLayerGroup);
        setGridsLayer(gridsLayerGroup);
        gridsLayerGroup.addTo(mapInstance);
        setShowGrids(true);
        return;
      } catch (error) {
        console.error('Error loading grids layer:', error);
        return;
      }
    }

    // Toggle visibility
    if (showGrids) {
      mapInstance.removeLayer(gridsLayer);
      setShowGrids(false);
    } else {
      gridsLayer.addTo(mapInstance);
      setShowGrids(true);
    }
  }, [mapInstance, gridsLayer, showGrids, fetchJsonCached, currentStationData, selectedGridSize]);

  // Toggle zones layer
  const toggleZonesLayer = useCallback(async () => {
    if (!mapInstance) return;

    // Lazy-load zones layer on first toggle
    if (!zonesLayer) {
      if (!zonesUrlRef.current) return;
      try {
        const zonesData = await fetchJsonCached(zonesUrlRef.current);
        const zonesLayerGroup = L.layerGroup();
        L.geoJSON(zonesData, {
          style: {
            color: '#dc2626',
            weight: 2,
            opacity: 0.8,
            fillColor: '#ef4444',
            fillOpacity: 0.1
          },
          onEachFeature: (feature, layer) => {
            if (feature.properties) {
              const { ZONE, NAME, ZONE_ID, TYPE } = feature.properties;
              const popupContent = `
                <div class="p-2">
                  <h4 class="font-semibold">Zone Information</h4>
                  <p><strong>Zone:</strong> ${ZONE || 'N/A'}</p>
                  <p><strong>Name:</strong> ${NAME || 'N/A'}</p>
                  <p><strong>Zone ID:</strong> ${ZONE_ID !== undefined ? ZONE_ID : 'N/A'}</p>
                  <p><strong>Type:</strong> ${TYPE || 'N/A'}</p>
                </div>
              `;
              layer.bindPopup(popupContent);
            }
          }
        }).addTo(zonesLayerGroup);
        setZonesLayer(zonesLayerGroup);
        zonesLayerGroup.addTo(mapInstance);
        setShowZones(true);
        return;
      } catch (error) {
        console.error('Error loading zones layer:', error);
        return;
      }
    }

    // Toggle visibility
    if (showZones) {
      mapInstance.removeLayer(zonesLayer);
      setShowZones(false);
    } else {
      zonesLayer.addTo(mapInstance);
      setShowZones(true);
    }
  }, [mapInstance, zonesLayer, showZones, fetchJsonCached]);

  // Toggle stations visibility
  const toggleStationsLayer = useCallback(() => {
    if (!mapInstance || !markerLayer) return;

    if (showStations) {
      mapInstance.removeLayer(markerLayer);
      setShowStations(false);
    } else {
      markerLayer.addTo(mapInstance);
      setShowStations(true);
    }
  }, [mapInstance, markerLayer, showStations]);

  // Toggle incidents visibility  
  const toggleIncidentsLayer = useCallback(() => {
    if (!mapInstance) return;

    // Find all incident markers and toggle their visibility
    mapInstance.eachLayer((layer: any) => {
      if (layer.options && layer.options.isIncidentMarker) {
        if (showIncidents) {
          mapInstance.removeLayer(layer);
        }
      }
    });

    if (!showIncidents) {
      // Re-add incident markers if we're showing them - use simple circle markers
      incidents.forEach(incident => {
        const marker = L.circleMarker([incident.lat, incident.lon], {
          radius: 6,
          fillColor: '#fbbf24', // Yellow color
          color: '#000000', // Black outline
          weight: 2,
          opacity: 1,
          fillOpacity: 0.8,
          // @ts-ignore - Add custom property to identify incident markers
          isIncidentMarker: true
        });
        marker.bindPopup(createIncidentPopup(incident));
        marker.addTo(mapInstance);
      });
    }

    setShowIncidents(!showIncidents);
  }, [mapInstance, incidents, showIncidents]);

  // Point in polygon check
  const isPointInPolygon = (point: L.LatLng, polygon: L.LatLng[]) => {
    let isInside = false;
    for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
      const xi = polygon[i].lat, yi = polygon[i].lng;
      const xj = polygon[j].lat, yj = polygon[j].lng;
      const intersect = ((yi > point.lng) !== (yj > point.lng))
          && (point.lat < (xj - xi) * (point.lng - yi) / (yj - yi) + xi);
      if (intersect) isInside = !isInside;
    }
    return isInside;
  };

  // Handle manual service zone update from popup
  const handleServiceZoneUpdate = useCallback((stationId: string, newZone: string) => {
    console.log(`handleServiceZoneUpdate called - stationId: ${stationId}, newZone: ${newZone}`);
    const updatedStations = stations.map(station => 
      station.id === stationId ? { ...station, serviceZone: newZone } : station
    );
    console.log('Updated stations array:', updatedStations);
    onStationsChange(updatedStations);

    // Force popup to refresh its content after update
    const marker = stationMarkers.get(stationId);
    const updatedStation = updatedStations.find(s => s.id === stationId);
    console.log('Found marker and updated station:', marker ? 'yes' : 'no', updatedStation ? 'yes' : 'no');
    if (marker && updatedStation) {
      // Re-bind the popup with the new station data to show the change immediately
      marker.unbindPopup();
      marker.bindPopup(createFirebeatsStationPopup(updatedStation));
      if (marker.isPopupOpen()) {
        marker.openPopup();
      }
      console.log('Popup updated successfully');
    }
  }, [stations, onStationsChange, stationMarkers]);

  // Handle apparatus manager opening
  const handleOpenApparatusManager = useCallback((stationId: string) => {
    console.log('handleOpenApparatusManager called with stationId:', stationId);
    const station = stations.find(s => s.id === stationId);
    console.log('Found station:', station);
    if (station) {
      setSelectedStationForApparatus(station);
      setApparatusManagerOpen(true);
      console.log('Apparatus manager opened for station:', station.displayName);
    } else {
      console.error('Station not found with ID:', stationId);
    }
  }, [stations]);

  // Handle apparatus update
  const handleApparatusUpdate = useCallback((stationId: string, apparatusId: string, updatedApparatus: Partial<Apparatus>) => {
    let updatedApparatusList: Apparatus[] = [];
    setStationApparatus(prev => {
      const newMap = new Map(prev);
      const stationApparatusList = newMap.get(stationId) || [];
      updatedApparatusList = stationApparatusList.map(app => 
        app.id === apparatusId ? { ...app, ...updatedApparatus } : app
      );
      newMap.set(stationId, updatedApparatusList);
      return newMap;
    });
    setEditingApparatus(null);
    
    // Notify parent component of apparatus changes
    if (onApparatusChange) {
      onApparatusChange(stationId, updatedApparatusList);
    }
  }, [onApparatusChange]);

  // Handle apparatus count update
  const handleApparatusCountUpdate = useCallback((stationId: string, apparatusKey: string, count: number) => {
    setStationApparatusCounts(prev => {
      const newMap = new Map(prev);
      const currentCounts = newMap.get(stationId) || {};
      const updatedCounts = { ...currentCounts, [apparatusKey]: Math.max(0, count) };
      newMap.set(stationId, updatedCounts);
      return newMap;
    });
  }, []);

  // Get current apparatus counts for a station
  const getApparatusCounts = useCallback((stationId: string): ApparatusCounts => {
    return stationApparatusCounts.get(stationId) || {};
  }, [stationApparatusCounts]);

  // Check if an apparatus count has been modified from the original CSV value
  const isApparatusCountModified = useCallback((stationId: string, apparatusKey: string): boolean => {
    const originalCounts = originalApparatusCounts.get(stationId) || {};
    const currentCounts = stationApparatusCounts.get(stationId) || {};
    const originalCount = originalCounts[apparatusKey] || 0;
    const currentCount = currentCounts[apparatusKey] || 0;
    return originalCount !== currentCount;
  }, [originalApparatusCounts, stationApparatusCounts]);

  // Initialize default apparatus for new stations
  useEffect(() => {
    stations.forEach(station => {
      if (!stationApparatus.has(station.id)) {
        const defaultApparatus: Apparatus[] = [
          {
            id: `engine-${station.id}`,
            type: 'Engine',
            name: `Engine ${station.stationNumber.toString().padStart(2, '0')}`,
            status: 'Available',
            crew: 4
          },
          {
            id: `ambulance-${station.id}`,
            type: 'Ambulance',
            name: `Ambulance ${station.stationNumber.toString().padStart(2, '0')}`,
            status: 'Available',
            crew: 2
          }
        ];
        setStationApparatus(prev => new Map(prev).set(station.id, defaultApparatus));
      }
    });
  }, [stations, stationApparatus]);

  // Inject a restored station layout (from re-opening a past job). Render those
  // exact positions/apparatus and suppress the default CSV reload for one cycle.
  const suppressLoadRef = useRef(false);
  const injectedRef = useRef<ProcessedStation[] | null>(null);
  useEffect(() => {
    if (!injectedStations || !mapInstance) return;
    if (injectedRef.current === injectedStations) return; // already applied this layout
    injectedRef.current = injectedStations;
    suppressLoadRef.current = true;       // skip the next default reload
    setCurrentStationData('custom_stations');
    onStationsChange(injectedStations);   // drives the markers effect
  }, [injectedStations, mapInstance, onStationsChange]);

  // Load geo configuration (URLs and default stations) when station dataset changes
  useEffect(() => {
    if (!mapInstance) return;

    // Only load if a station data type is explicitly selected
    if (!selectedStationData) {
      console.log('No station data selected, skipping load');
      return;
    }

    // A restored layout was just injected — consume one suppression and don't
    // clobber it with a fresh CSV load.
    if (suppressLoadRef.current) {
      suppressLoadRef.current = false;
      setCurrentStationData(selectedStationData);
      return;
    }

    console.log(`Station data change - selectedStationData: ${selectedStationData}, currentStationData: ${currentStationData}`);

    const shouldReload = selectedStationData !== currentStationData ||
                        (selectedStationData === 'optimized_stations');

    if (shouldReload) {
      console.log(`Loading station dataset config: ${selectedStationData} (prev: ${currentStationData})`);
      loadGeographicalLayers(selectedStationData);
    } else {
      console.log(`No change needed - already loaded: ${currentStationData}`);
    }
  }, [mapInstance, selectedStationData, currentStationData, loadGeographicalLayers, selectedGridSize, selectedNewStations]);

  // Set up global handlers
  useEffect(() => {
    window.firebeatsUpdateServiceZone = handleServiceZoneUpdate;
    window.openApparatusManager = handleOpenApparatusManager;
    return () => {
      delete window.firebeatsUpdateServiceZone;
      delete window.openApparatusManager;
    };
  }, [handleServiceZoneUpdate, handleOpenApparatusManager]);

  // Helper function to reassign station IDs dynamically (0 to totalStations-1)
  const reassignStationIds = useCallback((stationsList: ProcessedStation[]) => {
    return stationsList.map((station, index) => ({
      ...station,
      id: index.toString(), // Station ID becomes 0, 1, 2, 3, etc.
      apparatus: station.apparatus.map(app => ({
        ...app,
        id: `${index}_${app.type.toLowerCase()}_${app.id.split('_').pop()}` // Update apparatus IDs to match new station ID
      }))
    }));
  }, []);

  // Handle station deletion using useCallback to ensure we always have the latest state
  const handleStationDelete = useCallback((stationId: string) => {
    console.log(`Attempting to delete station with ID: ${stationId}`);
    
    // Remove from stations array and reassign IDs
    const filteredStations = stations.filter(station => station.id !== stationId);
    console.log(`Filtered stations count: ${filteredStations.length} (was ${stations.length})`);
    
    // Reassign IDs after deletion
    const stationsWithNewIds = reassignStationIds(filteredStations);
    onStationsChange(stationsWithNewIds);
    
    console.log('Updating apparatus data after station deletion...');
    console.log('Stations before deletion:', stations.map(s => ({ id: s.id, name: s.name })));
    console.log('Stations after deletion and ID reassignment:', stationsWithNewIds.map(s => ({ id: s.id, name: s.name })));

    // Update apparatus counts for all stations with new IDs
    setStationApparatusCounts(prev => {
      const newMap = new Map();
      console.log('Previous apparatus counts:', Array.from(prev.entries()));
      
      stationsWithNewIds.forEach((station, index) => {
        // Find the original station before ID reassignment to preserve its apparatus counts
        const originalStation = stations.find(s => 
          s.name === station.name && 
          s.displayName === station.displayName &&
          Math.abs(s.lat - station.lat) < 0.000001 && 
          Math.abs(s.lon - station.lon) < 0.000001
        );
        const apparatusCounts = originalStation ? prev.get(originalStation.id) || {} : {};
        console.log(`Station ${station.name} (new ID: ${index}) - preserved apparatus:`, apparatusCounts);
        newMap.set(index.toString(), apparatusCounts);
      });
      
      console.log('New apparatus counts map:', Array.from(newMap.entries()));
      return newMap;
    });
    
    setOriginalApparatusCounts(prev => {
      const newMap = new Map();
      stationsWithNewIds.forEach((station, index) => {
        // Find the original station before ID reassignment to preserve its apparatus counts
        const originalStation = stations.find(s => 
          s.name === station.name && 
          s.displayName === station.displayName &&
          Math.abs(s.lat - station.lat) < 0.000001 && 
          Math.abs(s.lon - station.lon) < 0.000001
        );
        const apparatusCounts = originalStation ? prev.get(originalStation.id) || {} : {};
        newMap.set(index.toString(), apparatusCounts);
      });
      return newMap;
    });

    // Update station apparatus map
    setStationApparatus(prev => {
      const newMap = new Map();
      stationsWithNewIds.forEach((station, index) => {
        // Find the original station before ID reassignment to preserve its apparatus
        const originalStation = stations.find(s => 
          s.name === station.name && 
          s.displayName === station.displayName &&
          Math.abs(s.lat - station.lat) < 0.000001 && 
          Math.abs(s.lon - station.lon) < 0.000001
        );
        const apparatus = originalStation ? prev.get(originalStation.id) || [] : [];
        newMap.set(index.toString(), apparatus);
      });
      return newMap;
    });
    
    // Close apparatus manager if the deleted station is selected
    if (selectedStationForApparatus?.id === stationId) {
      setApparatusManagerOpen(false);
      setSelectedStationForApparatus(null);
    }
    
    // Remove marker from map
    const marker = stationMarkers.get(stationId);
    if (marker && markerLayer) {
      markerLayer.removeLayer(marker);
      setStationMarkers(prev => {
        const newMap = new Map(prev);
        newMap.delete(stationId);
        return newMap;
      });
      console.log(`Removed marker for station ${stationId} from map`);
    } else {
      console.log(`No marker found for station ${stationId}`);
    }
    
    console.log(`Successfully deleted station with ID: ${stationId}`);
  }, [stations, stationMarkers, markerLayer, onStationsChange, reassignStationIds]);

  // Helper function to find which zone contains a point
  const findZoneContainingPoint = useCallback((latlng: L.LatLng): any => {
    if (!zoneGeometries) {
      console.log('No zone geometries available');
      return null;
    }
    
    let containingZone: any = null;
    let layerCount = 0;
    
    zoneGeometries.eachLayer((layer: any) => {
      layerCount++;
      if (layer.feature && layer.feature.geometry) {
        // Use Leaflet's built-in contains method for polygons
        if (layer.getBounds && layer.getBounds().contains(latlng)) {
          // More precise check using the actual geometry
          const point = L.latLng(latlng.lat, latlng.lng);
          
          // For MultiPolygon or Polygon
          if (layer.feature.geometry.type === 'Polygon' || layer.feature.geometry.type === 'MultiPolygon') {
            // Use leaflet-pip or manual point-in-polygon check
            // Simple bounds check for now, can be enhanced with proper point-in-polygon
            const coordinates = layer.feature.geometry.coordinates;
            if (isPointInGeoJSONPolygon(point, coordinates, layer.feature.geometry.type)) {
              containingZone = layer.feature;
              console.log('Found containing zone for point:', latlng, 'Zone properties:', layer.feature.properties);
            }
          }
        }
      }
    });
    
    console.log(`Checked ${layerCount} zone layers for point`, latlng);
    
    return containingZone;
  }, [zoneGeometries]);

  // Simple point-in-polygon check for GeoJSON coordinates
  const isPointInGeoJSONPolygon = (point: L.LatLng, coordinates: any, geometryType: string): boolean => {
    // For Polygon
    if (geometryType === 'Polygon') {
      return checkPointInRing(point, coordinates[0]); // Check outer ring
    }
    
    // For MultiPolygon
    if (geometryType === 'MultiPolygon') {
      for (const polygon of coordinates) {
        if (checkPointInRing(point, polygon[0])) {
          return true;
        }
      }
    }
    
    return false;
  };

  // Ray casting algorithm for point-in-polygon
  const checkPointInRing = (point: L.LatLng, ring: number[][]): boolean => {
    let inside = false;
    const x = point.lng;
    const y = point.lat;
    
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const xi = ring[i][0], yi = ring[i][1];
      const xj = ring[j][0], yj = ring[j][1];
      
      const intersect = ((yi > y) !== (yj > y))
        && (x < (xj - xi) * (y - yi) / (yj - yi) + xi);
      
      if (intersect) inside = !inside;
    }
    
    return inside;
  };

  // Handle adding a new station at the clicked location
  const handleAddNewStation = useCallback((lat: number, lng: number) => {
    if (selectedStationData !== 'custom_stations') {
      console.log('Add station only available for custom stations');
      return;
    }

    // Find the highest existing station number from all stations for naming purposes
    const existingStationNumbers = stations
      .map(station => {
        // Extract number from station names like "Station 1", "Station 2", etc.
        const match = station.name.match(/Station (\d+)/i) || station.displayName.match(/Station (\d+)/i);
        return match ? parseInt(match[1], 10) : 0;
      })
      .filter(num => !isNaN(num));
    
    const maxStationNumber = existingStationNumbers.length > 0 ? Math.max(...existingStationNumbers) : 0;
    const newStationNumber = maxStationNumber + 1;
    
    // Find which zone contains this point
    const latlng = L.latLng(lat, lng);
    console.log('Adding new station at:', latlng, 'Zone geometries available:', !!zoneGeometriesRef.current);
    const containingZone = findZoneContainingPoint(latlng);
    console.log('Containing zone found:', !!containingZone);
    
    if (!containingZone) {
      console.warn('Cannot add station - no zone found at this location. Make sure zones are loaded.');
      alert('Cannot add station at this location. No service zone found. Make sure you are clicking within a zone boundary.');
      return;
    }
    
    // Create new station object with temporary ID (will be reassigned)
    const newStation: ProcessedStation = {
      id: 'temp', // Temporary ID, will be reassigned by reassignStationIds
      name: `Station ${newStationNumber}`,
      displayName: `Station ${newStationNumber}`,
      lat: lat,
      lon: lng,
      address: `${lat.toFixed(6)} ${lng.toFixed(6)}`,
      serviceZone: 'Custom',
      stationNumber: newStationNumber,
      apparatus: [
        {
          id: `temp_engine_1`,
          type: 'Engine',
          name: `Engine ${newStationNumber}`,
          status: 'Available',
          crew: 4
        },
        {
          id: `temp_ambulance_1`,
          type: 'Ambulance',
          name: `Ambulance ${newStationNumber}`,
          status: 'Available',
          crew: 2
        }
      ]
    };

    // Add to stations array and reassign all IDs
    const updatedStations = [...stations, newStation];
    const stationsWithNewIds = reassignStationIds(updatedStations);
    onStationsChange(stationsWithNewIds);
    
    // Store the initial zone for this station (use temporary ID for now, will update after reassignment)
    if (containingZone) {
      setStationInitialZones(prev => {
        const newMap = new Map(prev);
        newMap.set('temp', containingZone);
        return newMap;
      });
      
      // Update with the correct ID after reassignment
      setTimeout(() => {
        const newStationFinalId = (updatedStations.length - 1).toString();
        setStationInitialZones(prev => {
          const newMap = new Map(prev);
          if (newMap.has('temp')) {
            newMap.set(newStationFinalId, newMap.get('temp'));
            newMap.delete('temp');
          }
          return newMap;
        });
      }, 100);
    }

    // Set default apparatus for the new station (will have the last ID after reassignment)
    const newStationFinalId = (updatedStations.length - 1).toString();
    const defaultApparatusCounts: ApparatusCounts = {
      Engine_ID: 1,
      Truck: 0,
      Rescue: 0,
      Hazard: 0,
      Squad: 0,
      FAST: 0,
      Medic: 1,
      Brush: 0,
      Boat: 0,
      UTV: 0,
      REACH: 0,
      Chief: 0
    };

    // Update apparatus counts for all stations with new IDs
    setStationApparatusCounts(prev => {
      const newMap = new Map();
      // Reassign all existing apparatus counts to new IDs
      stationsWithNewIds.forEach((station, index) => {
        const oldApparatusCounts = index < stations.length 
          ? prev.get(stations[index].id) || {}
          : defaultApparatusCounts; // Use default for the new station
        newMap.set(index.toString(), index === stationsWithNewIds.length - 1 ? defaultApparatusCounts : oldApparatusCounts);
      });
      return newMap;
    });

    setOriginalApparatusCounts(prev => {
      const newMap = new Map();
      // Reassign all existing original apparatus counts to new IDs
      stationsWithNewIds.forEach((station, index) => {
        const oldApparatusCounts = index < stations.length 
          ? prev.get(stations[index].id) || {}
          : { ...defaultApparatusCounts }; // Use default for the new station
        newMap.set(index.toString(), index === stationsWithNewIds.length - 1 ? { ...defaultApparatusCounts } : oldApparatusCounts);
      });
      return newMap;
    });

    console.log(`Created new station: ${newStation.name} at ${lat}, ${lng} with default apparatus`);
    
    // Exit add station mode
    setIsAddingStation(false);
  }, [selectedStationData, stations, onStationsChange, reassignStationIds, findZoneContainingPoint]);

  // Stabilize global delete handler: register once and reference latest via ref
  const deleteHandlerRef = useRef(handleStationDelete);
  useEffect(() => {
    deleteHandlerRef.current = handleStationDelete;
  }, [handleStationDelete]);
  useEffect(() => {
    setupGlobalDeleteHandler((stationId: string) => deleteHandlerRef.current(stationId));
    return () => {
      if (window.deleteStation) delete window.deleteStation;
    };
  }, []);

  // Handle clear layers callback
  useEffect(() => {
    if (onClearLayers) {
      const clearLayers = () => {
        // Reset map layer toggles
        if (gridsLayer && mapInstance) {
          mapInstance.removeLayer(gridsLayer);
          setShowGrids(false);
        }
        if (zonesLayer && mapInstance) {
          mapInstance.removeLayer(zonesLayer);
          setShowZones(false);
        }
        // Clear marker layers (stations and incidents)
        if (markerLayer) {
          markerLayer.clearLayers();
        }
        // Clear service zones
        if (serviceZoneLayer) {
          serviceZoneLayer.clearLayers();
        }
        // Clear incidents
        setIncidents([]);
        if (onIncidentsCountChange) onIncidentsCountChange(0);
        
        // Reset current station data so it can be reloaded
        setCurrentStationData('');
        
        // Reset layer toggle states
        setShowStations(true);
        setShowIncidents(true);
      };
      
      // Store the clear function so it can be called from parent
      (window as any).clearMapLayers = clearLayers;
    }
    
    return () => {
      if ((window as any).clearMapLayers) {
        delete (window as any).clearMapLayers;
      }
    };
  }, [onClearLayers, gridsLayer, zonesLayer, mapInstance, markerLayer, serviceZoneLayer, onIncidentsCountChange]);

  // Load service zones (GeoJSON polygons)
  useEffect(() => {
    const loadServiceZones = async () => {
      // Use default zone file if none is selected
      const zoneFile = selectedServiceZoneFile || 'beats_shpfile_merged.geojson';
      
      if (!zoneFile || !serviceZoneLayer) {
        // Clear service zones if no file selected
        if (serviceZoneLayer) {
          serviceZoneLayer.clearLayers();
          setZoneGeometries(null);
        }
        return;
      }

      try {
        console.log('Loading service zones from:', `/data/${zoneFile}`);
        const response = await fetch(`/data/${zoneFile}`);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const geoJsonData = await response.json();
        console.log('GeoJSON data loaded:', geoJsonData);

        // Clear existing service zone layers
        serviceZoneLayer.clearLayers();

        // Add GeoJSON to the service zone layer
        const geoJsonLayer = L.geoJSON(geoJsonData, {
          style: (feature) => {
            // Style for the polygons
            return {
              fillColor: '#3388ff',
              weight: 2,
              opacity: 1,
              color: '#3388ff',
              dashArray: '3',
              fillOpacity: 0.2
            };
          },
          onEachFeature: (feature, layer) => {
            // Add popup with zone information if available
            if (feature.properties) {
              const popupContent = Object.entries(feature.properties)
                .map(([key, value]) => `<strong>${key}:</strong> ${value}`)
                .join('<br>');
              layer.bindPopup(`<div>${popupContent}</div>`);
            }
          }
        });

        // Only add to map layer if in custom stations mode or if a zone file was explicitly selected
        if (selectedStationData === 'custom_stations' || selectedServiceZoneFile) {
          geoJsonLayer.addTo(serviceZoneLayer);
          console.log('Service zones added to map (visible)');
        } else {
          console.log('Service zones loaded but not displayed (zone assignment only)');
        }
        
        // Always store zone geometries for zone assignment (even if not visible)
        setZoneGeometries(geoJsonLayer);
        
        console.log('Service zones loaded');

      } catch (error) {
        console.error('Error loading service zones:', error);
      }
    };

    loadServiceZones();
  }, [selectedServiceZoneFile, serviceZoneLayer, selectedStationData]);

  // Helper function to filter incidents by date range
  const filterIncidentsByDateRange = useCallback((incidents: any[], startDate?: Date, endDate?: Date) => {
    if (!startDate && !endDate) {
      return incidents; // No date filtering
    }

    return incidents.filter(incident => {
      if (!incident.datetime) {
        return true; // Include incidents without datetime
      }

      const incidentDate = new Date(incident.datetime);
      
      // Check if the date is valid
      if (isNaN(incidentDate.getTime())) {
        return true; // Include incidents with invalid dates
      }

      // Filter by start date
      if (startDate && incidentDate < startDate) {
        return false;
      }

      // Filter by end date (include the entire end date)
      if (endDate) {
        const endOfDay = new Date(endDate);
        endOfDay.setHours(23, 59, 59, 999); // End of the selected day
        if (incidentDate > endOfDay) {
          return false;
        }
      }

      return true;
    });
  }, []);

  // Clear incidents when incident model changes or is unselected
  useEffect(() => {
    if (!selectedIncidentModel) {
      setIncidents([]);
      if (onIncidentsCountChange) onIncidentsCountChange(0);
      setIsLoadingIncidents(false);
    } else {
      // Clear incidents when changing to a different model to force manual loading
      setIncidents([]);
      if (onIncidentsCountChange) onIncidentsCountChange(0);
    }
  }, [selectedIncidentModel, onIncidentsCountChange]);

  useEffect(() => {
    const loadStations = async () => {
      if (!selectedStationFile) {
        // If no explicit selection, leave stations as-is (might be loaded from default config)
        return;
      }

      try {
        const stationsUrl = `/data/${selectedStationFile}`;
        console.log('Loading stations from explicit selection:', stationsUrl);
        const csvText = await fetchTextCached(stationsUrl);
        const parsedStations = parseCSV(csvText);

        const processedStations = parsedStations.slice(0, 100).map((row, index) => {
          const stationNumberMatch = row.Stations?.match(/(\d+)/) || row['Facility Name']?.match(/(\d+)/);
          const stationNumber = stationNumberMatch ? parseInt(stationNumberMatch[1]) : index + 1;

          const station: ProcessedStation = {
            id: row.StationID || row.id || `station-${index}`,
            name: row.Stations || row['Facility Name'] || `Station ${stationNumber}`,
            address: row.Address || 'Address not available',
            lat: parseFloat(row.lat),
            lon: parseFloat(row.lon),
            stationNumber: stationNumber,
            displayName: `Station ${stationNumber.toString().padStart(2, '0')}`,
            apparatus: []
          };

          if (selectedStationFile === 'stations.csv') {
            const apparatus = createApparatusFromCSV(row, station.id, stationNumber);
            setStationApparatus(prev => new Map(prev).set(station.id, apparatus));

            const apparatusCounts = extractApparatusCountsFromCSV(row);
            setStationApparatusCounts(prev => new Map(prev).set(station.id, apparatusCounts));
            setOriginalApparatusCounts(prev => new Map(prev).set(station.id, { ...apparatusCounts }));
          }

          return station;
        }).filter(station => !isNaN(station.lat) && !isNaN(station.lon));

        onStationsChange(processedStations);
      } catch (error) {
        console.error('Error loading stations:', error);
      }
    };

    loadStations();
  }, [selectedStationFile, fetchTextCached, parseCSV, createApparatusFromCSV, extractApparatusCountsFromCSV, setStationApparatus, onStationsChange]);

  useEffect(() => {
    console.log('Initializing map');
    const map = L.map('map').setView([config.map.defaultView.lat, config.map.defaultView.lng], config.map.defaultView.zoom);

    L.tileLayer(config.map.tileLayer.url, config.map.tileLayer.options).addTo(map);


    // console.log('Map initialized', map);

    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          const { latitude, longitude } = position.coords;
          map.setView([latitude, longitude], config.map.defaultView.zoom);
        },
        () => {
          // silently ignore geolocation errors
        }
      );
    }

    // Store map instance in state
    setMapInstance(map);

    // Notify parent component
    if (onMapInstanceChange) {
      onMapInstanceChange(map);
    }

    // Initialize service zone layer
    const newServiceZoneLayer = L.layerGroup().addTo(map);
    setServiceZoneLayer(newServiceZoneLayer);

    // Cleanup on unmount
    return () => {
      map.remove();
    };
  }, []);

  // Update map click handler when add station mode changes
  useEffect(() => {
    if (!mapInstance) return;

    // Remove existing click handlers
    mapInstance.off('click');

    // Add click handler for adding new stations
    mapInstance.on('click', (e: L.LeafletMouseEvent) => {
      // Handle custom station placement (works in both standard and counterfactual mode)
      if (isAddingStation && selectedStationData === 'custom_stations') {
        handleAddNewStation(e.latlng.lat, e.latlng.lng);
      }
    });

    return () => {
      mapInstance.off('click');
    };
  }, [mapInstance, isAddingStation, selectedStationData, handleAddNewStation]);

  // Automatically disable add station mode when switching away from custom stations
  useEffect(() => {
    if (selectedStationData !== 'custom_stations' && isAddingStation) {
      setIsAddingStation(false);
    }
  }, [selectedStationData, isAddingStation]);

  // Disable zone layer interactions when in add station mode by temporarily removing from map
  useEffect(() => {
    if (!serviceZoneLayer || !mapInstance) return;

    if (isAddingStation) {
      // Remove the service zone layer from the map to prevent interactions
      console.log('Removing service zone layer for add station mode');
      if (mapInstance.hasLayer(serviceZoneLayer)) {
        mapInstance.removeLayer(serviceZoneLayer);
      }
    } else {
      // Re-add the service zone layer to the map
      console.log('Re-adding service zone layer');
      if (!mapInstance.hasLayer(serviceZoneLayer)) {
        mapInstance.addLayer(serviceZoneLayer);
      }
    }
  }, [isAddingStation, serviceZoneLayer, mapInstance]);

  // Update map cursor style when add station mode changes
  useEffect(() => {
    const mapElement = document.getElementById('map');
    if (mapElement) {
      if (isAddingStation && selectedStationData === 'custom_stations') {
        mapElement.style.cursor = 'crosshair';
      } else {
        mapElement.style.cursor = '';
      }
    }
  }, [isAddingStation, selectedStationData]);

  useEffect(() => {
    if (!mapInstance) return;

    // Ensure marker layer is initialized
    if (!markerLayer) {
      const newMarkerLayer = L.layerGroup().addTo(mapInstance);
      setMarkerLayer(newMarkerLayer);
    }

    // Re-render markers when incidents or stations change
    if (markerLayer) {
        // Wait for zones to be loaded before rendering markers if zones are selected
        if (selectedServiceZoneFile && !zoneGeometries) {
          console.log('Waiting for zones to load before rendering station markers...');
          return;
        }
        markerLayer.clearLayers();
        setStationMarkers(new Map()); // Clear tracked markers

        // Add incident markers first (so they appear under stations) - only if incidents are enabled
        if (showIncidents) {
          incidents.forEach(incident => {
            // Use simple circle marker instead of complex HTML icon for better performance
            const marker = L.circleMarker([incident.lat, incident.lon], {
              radius: 6,
              fillColor: '#fbbf24', // Yellow color
              color: '#000000', // Black outline
              weight: 2,
              opacity: 1,
              fillOpacity: 0.8,
              interactive: false, // Make non-interactive for performance
              // @ts-ignore - Add custom property to identify incident markers
              isIncidentMarker: true
            });

            marker.addTo(markerLayer);
            // Don't bind popup for performance - incidents are non-interactive
            // marker.bindPopup(createIncidentPopup(incident));
          });
        }

        // Add station markers on top of incidents - only if stations are enabled
        if (showStations) {
          const newStationMarkers = new Map<string, L.Marker>();
          stations.forEach(station => {
          const iconHtml = createStationIcon(station);
          
          // Determine if stations should be draggable based on selected station data
          const isDraggable = selectedStationData === 'custom_stations';
          
          let marker: L.Marker;
          
          // Store initial zone for all stations if zones are loaded (not just custom stations)
          if (zoneGeometries && !stationInitialZones.has(station.id)) {
            const latlng = L.latLng(station.lat, station.lon);
            const containingZone = findZoneContainingPoint(latlng);
            console.log(`Station ${station.id} (${station.name}) initial zone:`, containingZone ? 'Found' : 'Not found', latlng);
            if (containingZone) {
              console.log(`Zone properties:`, containingZone.properties);
              setStationInitialZones(prev => {
                const newMap = new Map(prev);
                newMap.set(station.id, containingZone);
                console.log(`Stored initial zone for station ${station.id}. Total zones stored:`, newMap.size);
                return newMap;
              });
            }
          }
          
          if (isDraggable) {
            
            // Create custom drag handlers that update the shared state
            const customDragHandlers = {
              ...defaultDragHandlers,
              onDrag: (marker: L.Marker, station: ProcessedStation) => {
                // Check if new position is within the initial zone
                const newLatLng = marker.getLatLng();
                const initialZone = stationInitialZonesRef.current.get(station.id);
                
                console.log(`Dragging station ${station.id}, has initial zone:`, !!initialZone);
                
                if (initialZone) {
                  const isInZone = isPointInGeoJSONPolygon(
                    newLatLng,
                    initialZone.geometry.coordinates,
                    initialZone.geometry.type
                  );
                  
                  console.log(`Station ${station.id} is in zone:`, isInZone);
                  
                  if (!isInZone) {
                    console.log(`Reverting station ${station.id} to original position`);
                    // Revert to last valid position
                    marker.setLatLng([station.lat, station.lon]);
                  }
                }
                
                // Call original onDrag handler
                if (defaultDragHandlers.onDrag) {
                  defaultDragHandlers.onDrag(marker, station);
                }
              },
              onStationUpdate: (updatedStation: ProcessedStation) => {
                // Verify final position is within initial zone before updating
                const latlng = L.latLng(updatedStation.lat, updatedStation.lon);
                const initialZone = stationInitialZonesRef.current.get(updatedStation.id);
                
                if (initialZone) {
                  const isInZone = isPointInGeoJSONPolygon(
                    latlng,
                    initialZone.geometry.coordinates,
                    initialZone.geometry.type
                  );
                  
                  if (!isInZone) {
                    console.log(`Station ${updatedStation.id} cannot be moved outside its initial zone`);
                    return; // Don't update if outside zone
                  }
                }
                
                // Update the shared state - marker position is already updated by Leaflet
                const updatedStations = stations.map(s => 
                  s.id === updatedStation.id ? updatedStation : s
                );
                onStationsChange(updatedStations);
              }
            };
            
            marker = createDraggableStationMarker(station, iconHtml, customDragHandlers);
          } else {
            // Create static (non-draggable) marker for default stations
            marker = createStaticStationMarker(station, iconHtml);
          }

          marker.addTo(markerLayer);
          
          // Get zone information for this station
          const getZoneInfo = (stationId: string): string => {
            const zoneData = stationInitialZonesRef.current.get(stationId);
            if (!zoneData || !zoneData.properties) return '';
            
            // Extract useful zone properties
            const props = zoneData.properties;
            const zoneFields: string[] = [];
            
            // Common zone property names
            if (props.name) zoneFields.push(props.name);
            else if (props.NAME) zoneFields.push(props.NAME);
            else if (props.zone) zoneFields.push(props.zone);
            else if (props.ZONE) zoneFields.push(props.ZONE);
            else if (props.beat) zoneFields.push(`Beat ${props.beat}`);
            else if (props.BEAT) zoneFields.push(`Beat ${props.BEAT}`);
            else if (props.id) zoneFields.push(`Zone ${props.id}`);
            else if (props.ID) zoneFields.push(`Zone ${props.ID}`);
            
            return zoneFields.length > 0 ? zoneFields.join(' - ') : 'Zone detected';
          };
          
          // Bind the correct popup based on dispatch policy
          const zoneInfo = getZoneInfo(station.id);
          const popupContent = selectedDispatchPolicy === 'firebeats'
            ? createFirebeatsStationPopup(station, selectedStationData)
            : createDetailedStationPopup(station, undefined, selectedStationData, zoneInfo);
          
          marker.bindPopup(popupContent);

          // Refresh popup content when it opens to ensure it's up-to-date
          marker.on('popupopen', () => {
            const freshStationData = stations.find(s => s.id === station.id) || station;
            const freshZoneInfo = getZoneInfo(freshStationData.id);
            const freshPopupContent = selectedDispatchPolicy === 'firebeats'
              ? createFirebeatsStationPopup(freshStationData, selectedStationData)
              : createDetailedStationPopup(freshStationData, undefined, selectedStationData, freshZoneInfo);
            marker.setPopupContent(freshPopupContent);

            // Set the selected station (but don't auto-open apparatus manager)
            setSelectedStationForApparatus(freshStationData);
          });
          
          // Track the marker
          newStationMarkers.set(station.id, marker);
        });
        setStationMarkers(newStationMarkers);
        } else {
          // Clear station markers when stations are hidden
          setStationMarkers(new Map());
        }
      }
  }, [incidents, stations, markerLayer, selectedDispatchPolicy, onStationsChange, showStations, showIncidents, selectedStationData, zoneGeometries, stationInitialZones, findZoneContainingPoint, selectedServiceZoneFile]);

  // Debug logging removed to reduce noise during interactions

  return (
    <div className="h-full w-full bg-white relative">
      {/* Leaflet map container */}
      <div
        id="map"
        className="h-full w-full absolute inset-0"
      />
      
      {/* Counterfactual Mode Banner */}
      {isCounterfactualMode && (
        <div 
          className="absolute top-4 left-1/2 transform -translate-x-1/2 z-[1000] bg-blue-600 text-white px-4 py-2 rounded-lg shadow-lg flex items-center gap-2"
          style={{ pointerEvents: 'none' }}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2L2 7v10c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V7l-10-5z"/>
          </svg>
          <span className="font-semibold">Counterfactual Mode Active - Use Custom Stations to add test stations</span>
        </div>
      )}
      
      {/* Loading Overlay */}
      {(isLoadingIncidents || isLoadingStations) && (
        <div className="absolute inset-0 bg-black bg-opacity-30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-4 shadow-lg flex items-center space-x-3">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
            <span className="text-gray-700 font-medium">
              {isLoadingIncidents && isLoadingStations
                ? 'Loading incidents and stations...'
                : isLoadingIncidents
                ? 'Loading incidents...'
                : 'Loading stations...'
              }
            </span>
          </div>
        </div>
      )}

      {/* Add Station Mode Indicator */}
      {isAddingStation && selectedStationData === 'custom_stations' && (
        <div className="absolute top-20 left-1/2 transform -translate-x-1/2 bg-green-100 border border-green-500 rounded-lg px-4 py-2 shadow-lg" style={{zIndex: 10000}}>
          <div className="text-green-800 font-medium text-sm">
            📍 Click anywhere on the map to add a new station
          </div>
          <div className="text-green-600 text-xs mt-1">
            New stations come with 1 Engine + 1 Ambulance
          </div>
        </div>
      )}
      
      {/* Layer Controls */}
      <div className="absolute top-4 right-4 bg-white rounded-lg shadow-lg p-3 space-y-2" style={{zIndex: 10000}}>
        <div className="text-sm font-semibold text-gray-700 mb-2">Map Layers</div>
        
        {/* Station Layer Toggle */}
        <label className="flex items-center space-x-2 cursor-pointer">
          <input
            type="checkbox"
            checked={showStations}
            onChange={toggleStationsLayer}
            className="form-checkbox h-4 w-4 text-blue-600"
          />
          <span className="text-sm text-gray-700">Stations</span>
          <div className="w-3 h-3 bg-blue-600 border border-blue-700 rounded-sm"></div>
        </label>
        
        {/* Incidents Layer Toggle */}
        <label className="flex items-center space-x-2 cursor-pointer">
          <input
            type="checkbox"
            checked={showIncidents}
            onChange={toggleIncidentsLayer}
            className="form-checkbox h-4 w-4 text-yellow-600"
          />
          <span className="text-sm text-gray-700">Incidents</span>
          <div className="w-3 h-3 bg-yellow-400 border-2 border-black rounded-full"></div>
        </label>

        {/* Add Station Mode Toggle - Only show for custom stations */}
        {selectedStationData === 'custom_stations' && (
          <label className="flex items-center space-x-2 cursor-pointer">
            <input
              type="checkbox"
              checked={isAddingStation}
              onChange={(e) => setIsAddingStation(e.target.checked)}
              className="form-checkbox h-4 w-4 text-green-600"
            />
            <span className="text-sm text-gray-700">Add Station Mode</span>
            <div className="w-3 h-3 bg-green-500 border border-green-600 rounded-sm"></div>
          </label>
        )}
        
        {gridsUrlRef.current && (
          <label className="flex items-center space-x-2 cursor-pointer">
            <input
              type="checkbox"
              checked={showGrids}
              onChange={toggleGridsLayer}
              className="form-checkbox h-4 w-4 text-blue-600"
            />
            <span className="text-sm text-gray-700">Grids</span>
            <div className="w-3 h-3 bg-blue-500 border border-blue-600 rounded-sm"></div>
          </label>
        )}
        {zonesUrlRef.current && (
          <label className="flex items-center space-x-2 cursor-pointer">
            <input
              type="checkbox"
              checked={showZones}
              onChange={toggleZonesLayer}
              className="form-checkbox h-4 w-4 text-red-600"
            />
            <span className="text-sm text-gray-700">Zones</span>
            <div className="w-3 h-3 bg-red-500 border border-red-600 rounded-sm"></div>
          </label>
        )}
      </div>
      
      {/* Apparatus Manager Sidebar */}
      {apparatusManagerOpen && selectedStationForApparatus && (
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          bottom: 0,
          width: '320px',
          backgroundColor: 'white',
          borderRight: '1px solid #d1d5db',
          boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)',
          display: 'flex',
          flexDirection: 'column',
          zIndex: 1000
        }}>
          <div style={{
            padding: '1rem',
            flexShrink: 0,
            borderBottom: '1px solid #e5e7eb'
          }}>
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-semibold text-gray-900">
                {selectedStationForApparatus.displayName} - Apparatus
              </h3>
              <button
                onClick={() => setApparatusManagerOpen(false)}
                className="text-gray-500 hover:text-gray-700 text-xl font-bold"
              >
                ×
              </button>
            </div>
          </div>
          
          {/* Scrollable content area */}
          <div style={{
            flex: '1 1 0%',
            overflowY: 'auto',
            overflowX: 'hidden',
            minHeight: 0,
            padding: '0 1rem 1rem 1rem'
          }}>
            <div className="space-y-4">
              <div className="text-sm text-gray-600 mb-4">
                <p><strong>Address:</strong> {selectedStationForApparatus.address}</p>
                <p><strong>Service Zone:</strong> {selectedStationForApparatus.serviceZone || 'Not assigned'}</p>
              </div>
              
              <div>
                <h4 className="font-medium text-gray-900 mb-3">Apparatus Configuration</h4>
                <div className="space-y-3">
                  {APPARATUS_TYPES.map(apparatusType => {
                    const currentCounts = getApparatusCounts(selectedStationForApparatus.id);
                    const count = currentCounts[apparatusType.key] || 0;
                    const isActive = count > 0;
                    const isModified = isApparatusCountModified(selectedStationForApparatus.id, apparatusType.key);
                    
                    return (
                      <div 
                        key={apparatusType.key} 
                        className={`flex items-center justify-between p-3 border rounded-lg transition-all ${
                          isActive 
                            ? 'bg-blue-50 border-blue-200 shadow-sm' 
                            : 'bg-gray-100 border-gray-300'
                        }`}
                      >
                        <div className="flex items-center space-x-3">
                          <div 
                            className={`w-3 h-3 rounded-full ${
                              isModified ? 'bg-red-500' : (isActive ? 'bg-blue-500' : 'bg-gray-400')
                            }`}
                          />
                          <span className={`font-medium ${
                            isActive ? 'text-blue-900' : 'text-gray-700'
                          }`}>
                            {apparatusType.name}
                          </span>
                        </div>
                        <div className="flex items-center space-x-2">
                          <button
                            onClick={() => handleApparatusCountUpdate(selectedStationForApparatus.id, apparatusType.key, count - 1)}
                            disabled={count <= 0}
                            className="w-8 h-8 rounded-full bg-red-500 text-white hover:bg-red-600 disabled:bg-gray-300 disabled:text-gray-500 disabled:cursor-not-allowed flex items-center justify-center text-sm font-bold"
                          >
                            -
                          </button>
                          <span className="w-8 text-center font-semibold text-gray-900">
                            {count}
                          </span>
                          <button
                            onClick={() => handleApparatusCountUpdate(selectedStationForApparatus.id, apparatusType.key, count + 1)}
                            className="w-8 h-8 rounded-full bg-blue-500 text-white hover:bg-blue-600 flex items-center justify-center text-sm font-bold"
                          >
                            +
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
                
                <div className="mt-6 p-3 bg-gray-100 rounded-lg">
                  <h5 className="font-medium text-gray-900 mb-2">Total Apparatus</h5>
                  <p className="text-sm text-gray-600">
                    {Object.values(getApparatusCounts(selectedStationForApparatus.id)).reduce((sum, count) => sum + count, 0)} units configured
                  </p>
                </div>
                
                <div className="mt-4 p-2 bg-gray-50 rounded text-xs text-gray-600">
                  <div className="flex items-center justify-between">
                    <span>Status:</span>
                  </div>
                  <div className="flex items-center space-x-4 mt-1">
                    <div className="flex items-center space-x-1">
                      <div className="w-2 h-2 rounded-full bg-blue-500"></div>
                      <span>Active</span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <div className="w-2 h-2 rounded-full bg-gray-400"></div>
                      <span>Inactive</span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <div className="w-2 h-2 rounded-full bg-red-500"></div>
                      <span>Modified</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}