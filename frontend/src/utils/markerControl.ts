import L from 'leaflet';
import { ProcessedStation } from './dataProcessing';

/**
 * Configuration options for draggable markers
 */
export interface DraggableMarkerOptions {
  onDragStart?: (marker: L.Marker, station: ProcessedStation) => void;
  onDrag?: (marker: L.Marker, station: ProcessedStation) => void;
  onDragEnd?: (marker: L.Marker, station: ProcessedStation, newLatLng: L.LatLng) => void;
  onDelete?: (stationId: string, marker: L.Marker) => void; // Added delete callback
  onStationUpdate?: (updatedStation: ProcessedStation) => void; // Added station update callback
}

/**
 * Makes a station marker draggable with event handlers
 * @param marker - The Leaflet marker to make draggable
 * @param station - The station data associated with the marker
 * @param options - Configuration options for drag events
 */
export function makeDraggableMarker(
  marker: L.Marker, 
  station: ProcessedStation, 
  options: DraggableMarkerOptions = {}
): L.Marker {
  // Enable dragging on the marker
  marker.dragging?.enable();
  
  // Set up drag event handlers
  marker.on('dragstart', (e: L.LeafletEvent) => {
    if (options.onDragStart) {
      options.onDragStart(marker, station);
    }
  });

  marker.on('drag', (e: L.LeafletEvent) => {
    if (options.onDrag) {
      options.onDrag(marker, station);
    }
  });

  marker.on('dragend', (e: L.DragEndEvent) => {
    const newLatLng = marker.getLatLng();
    
    // Update the station's coordinates
    station.lat = newLatLng.lat;
    station.lon = newLatLng.lng;
    
    // Call the station update callback if provided
    if (options.onStationUpdate) {
      options.onStationUpdate(station);
    }
    
    if (options.onDragEnd) {
      options.onDragEnd(marker, station, newLatLng);
    }
  });

  return marker;
}

/**
 * Creates a non-draggable station marker for default/read-only stations
 * @param station - The station data
 * @param iconHtml - The HTML content for the marker icon
 * @returns A configured non-draggable marker
 */
export function createStaticStationMarker(
  station: ProcessedStation,
  iconHtml: string
): L.Marker {
  const marker = L.marker([station.lat, station.lon], {
    icon: L.divIcon({
      className: 'custom-marker station-marker static-marker',
      html: iconHtml,
      iconSize: [32, 32],
      iconAnchor: [16, 16]
    }),
    draggable: false // Explicitly disable dragging
  });

  return marker;
}

/**
 * Creates a draggable station marker with custom styling for draggable state
 * @param station - The station data
 * @param iconHtml - The HTML content for the marker icon
 * @param options - Draggable marker options
 * @returns A configured draggable marker
 */
export function createDraggableStationMarker(
  station: ProcessedStation,
  iconHtml: string,
  options: DraggableMarkerOptions = {}
): L.Marker {
  const marker = L.marker([station.lat, station.lon], {
    icon: L.divIcon({
      className: 'custom-marker station-marker draggable-marker',
      html: iconHtml,
      iconSize: [32, 32], // Updated to match new station icon size
      iconAnchor: [16, 16] // Center the anchor for the new size
    }),
    draggable: true // Enable dragging
  });

  return makeDraggableMarker(marker, station, options);
}

/**
 * Default drag event handlers
 */
export const defaultDragHandlers: DraggableMarkerOptions = {
  onDragStart: (marker: L.Marker, station: ProcessedStation) => {
    // Add visual feedback when dragging starts
    const element = marker.getElement();
    if (element) {
      element.style.cursor = 'grabbing';
      element.style.zIndex = '1000';
    }
  },
  
  onDrag: (marker: L.Marker, station: ProcessedStation) => {
    // Optional: Add any real-time feedback during dragging
  },
  
  onDragEnd: (marker: L.Marker, station: ProcessedStation, newLatLng: L.LatLng) => {
    // Reset visual feedback when dragging ends
    const element = marker.getElement();
    if (element) {
      element.style.cursor = 'grab';
      element.style.zIndex = '';
    }
  }
};

/**
 * Sets up the global delete handler for station markers
 * @param onDelete - Function to call when a station is deleted
 */
export function setupGlobalDeleteHandler(onDelete: (stationId: string) => void): void {
  (window as any).deleteStation = (stationId: string) => {
    if (confirm('Are you sure you want to delete this station?')) {
      onDelete(stationId);
    }
  };
}