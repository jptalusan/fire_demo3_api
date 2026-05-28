import React, { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { Badge } from './ui/badge';
import { AlertTriangle, CheckCircle, Clock, MapPin, TrendingUp, ArrowDown, ArrowUp, GitCompare } from 'lucide-react';
import { processStationReport, StationReport } from '../utils/dataProcessing';

// Comparative Metric Card Component
interface ComparativeMetricCardProps {
  title: string;
  icon: React.ReactNode;
  baselineValue: number;
  newValue: number;
  unit: string;
  format?: (value: number) => string;
  lowerIsBetter?: boolean;
}

function ComparativeMetricCard({ 
  title, 
  icon, 
  baselineValue, 
  newValue, 
  unit, 
  format = (v) => v.toFixed(2),
  lowerIsBetter = true
}: ComparativeMetricCardProps) {
  const delta = newValue - baselineValue;
  const percentChange = baselineValue !== 0 ? ((delta / baselineValue) * 100) : 0;
  
  // Determine if this is an improvement
  const isImprovement = lowerIsBetter ? delta < 0 : delta > 0;
  const isNeutral = Math.abs(delta) < 0.01;
  
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold mb-2">
          {format(newValue)} {unit}
        </div>
        {!isNeutral && (
          <div className={`flex items-center gap-1 text-sm font-medium ${
            isImprovement ? 'text-green-600' : 'text-red-600'
          }`}>
            {isImprovement ? (
              <ArrowDown className="w-4 h-4" />
            ) : (
              <ArrowUp className="w-4 h-4" />
            )}
            <span>
              {Math.abs(delta).toFixed(2)} {unit} ({Math.abs(percentChange).toFixed(1)}%)
            </span>
          </div>
        )}
        {isNeutral && (
          <div className="flex items-center gap-1 text-sm font-medium text-gray-500">
            <span>No change</span>
          </div>
        )}
        <div className="text-xs text-muted-foreground mt-1">
          Baseline: {format(baselineValue)} {unit}
        </div>
      </CardContent>
    </Card>
  );
}

interface StatisticsTabProps {
  simulationResults?: any;
  stations?: Array<{
    id: string;
    displayName?: string;
    name?: string;
    lat?: number;
    lon?: number;
    lng?: number;
  }>;
  incidentsCount?: number;
  stationApparatusCounts?: Map<string, Record<string, number>>;
  historicalIncidentStats?: any;
  historicalIncidentError?: string | null;
  isCounterfactualMode?: boolean;
  baselineResults?: any;
  baselineStations?: Array<{
    id: string;
    displayName?: string;
    name?: string;
    lat?: number;
    lon?: number;
    lng?: number;
  }>;
  baselineApparatusCounts?: Map<string, Record<string, number>>;
}

// TODO: Hard coded minutes label performance here.
export function StatisticsTab({ 
  simulationResults, 
  stations = [], 
  incidentsCount = 0, 
  stationApparatusCounts, 
  historicalIncidentStats, 
  historicalIncidentError,
  isCounterfactualMode = false,
  baselineResults,
  baselineStations = [],
  baselineApparatusCounts
}: StatisticsTabProps) {
  // Process station report data if available - handle both regular and comparison results
  const resultsData = simulationResults?.newConfig || simulationResults;
  const stationReports: StationReport[] = resultsData?.station_report
    ? processStationReport(resultsData.station_report) 
    : [];
  
  // Helper function to format time in minutes and seconds
  const formatTravelTime = (seconds: number): string => {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.round(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  // Helper function to get performance status based on travel time
  const getPerformanceStatus = (travelTimeSeconds: number): { status: string; color: string } => {
    const minutes = travelTimeSeconds / 60;
    if (minutes <= 4) return { status: 'Excellent', color: 'text-green-600' };
    if (minutes <= 6) return { status: 'Good', color: 'text-yellow-600' };
    return { status: 'Needs Improvement', color: 'text-red-600' };
  };

  // Baseline pre-simulation station summary
  const stationCount = stations.length;

  // Calculate average apparatus per station
  const averageApparatusPerStation = useMemo(() => {
    if (!stationApparatusCounts || stationApparatusCounts.size === 0) return 0;
    
    let totalApparatus = 0;
    stationApparatusCounts.forEach(counts => {
      const stationTotal = Object.values(counts).reduce((sum, count) => sum + (count || 0), 0);
      totalApparatus += stationTotal;
    });
    
    return stationApparatusCounts.size > 0 ? (totalApparatus / stationApparatusCounts.size).toFixed(1) : '0';
  }, [stationApparatusCounts]);

  // Apparatus keys and display names (aligns with MapSection CSV columns)
  const apparatusColumns: { key: string; label: string }[] = [
    { key: 'Engine_ID', label: 'Engine' },
    { key: 'Truck', label: 'Truck' },
    { key: 'Rescue', label: 'Rescue' },
    { key: 'Medic', label: 'Medic' },
    { key: 'Chief', label: 'Chief' },
    { key: 'Hazard', label: 'Hazard' },
    { key: 'Squad', label: 'Squad' },
    { key: 'FAST', label: 'FAST' },
    { key: 'Brush', label: 'Brush' },
    { key: 'Boat', label: 'Boat' },
    { key: 'UTV', label: 'UTV' },
    { key: 'REACH', label: 'REACH' },
  ];

  // Compute totals and per-station rows
  const { totalsByType, stationRows } = React.useMemo(() => {
    const totals: Record<string, number> = {};
    const rows: Array<{ stationId: string; stationName: string; counts: Record<string, number> }> = [];
    if (!stationApparatusCounts) {
      return { totalsByType: totals, stationRows: rows };
    }
    // Initialize totals
    apparatusColumns.forEach(col => (totals[col.key] = 0));

    // Build rows
    stationApparatusCounts.forEach((counts, stationId) => {
      const station = stations.find(s => s.id === stationId);
      const stationName = station?.displayName || station?.name || stationId;
      const rowCounts: Record<string, number> = {};
      apparatusColumns.forEach(col => {
        const val = Number(counts[col.key] || 0);
        rowCounts[col.key] = val;
        totals[col.key] += val;
      });
      rows.push({ stationId, stationName, counts: rowCounts });
    });

    // Sort rows by station number if present in name
    rows.sort((a, b) => {
      const an = parseInt(a.stationName.match(/\d+/)?.[0] || '0', 10);
      const bn = parseInt(b.stationName.match(/\d+/)?.[0] || '0', 10);
      return an - bn;
    });

    return { totalsByType: totals, stationRows: rows };
  }, [stationApparatusCounts, stations]);

  return (
    <div className="h-full overflow-auto space-y-4 p-4">
      {/* Note: Comparative metrics moved to Simulation tab in counterfactual mode */}
      {/* Note: KPI cards removed from Statistics tab - only shown in Simulation Results tab */}
      
      {/* Station Configuration Section (always shown in standard mode) */}
      {!isCounterfactualMode && (
        <div className="space-y-4">
          {/* Original statistics content continues below */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <MapPin className="h-5 w-5 text-blue-600" />
                Station Configuration
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Total Stations</p>
                  <p className="text-2xl font-bold">{stationCount}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Avg Apparatus per Station</p>
                  <p className="text-2xl font-bold">{averageApparatusPerStation}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
      
      {/* Previous counterfactual comparative content removed - now in Simulation tab */}
      {isCounterfactualMode && baselineResults && simulationResults && (
        <div className="space-y-4">
          {/* Comparison tables and detailed analysis can stay here
              unit=""
              format={(v) => v.toString()}
              lowerIsBetter={false}
            />
          </div>

          {/* Network Changes Summary */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <GitCompare className="w-4 h-4" />
                Network Configuration Changes
              </CardTitle>
            </CardHeader>
            <CardContent>
              {(() => {
                // Get baseline station data from props
                const baseline = baselineStations || [];
                const newStations = stations || [];
                
                // Debug logging
                console.log('Network Changes - Baseline count:', baseline.length);
                console.log('Network Changes - New stations count:', newStations.length);
                if (baseline.length > 0) {
                  console.log('Baseline first station:', baseline[0]);
                }
                if (newStations.length > 0) {
                  console.log('New stations first station:', newStations[0]);
                }
                
                // Helper to get station name
                const getStationName = (station: any) => 
                  station.displayName || station.name || station.station_name || station.id || station.station_id;
                
                // Calculate changes based on station names
                const baselineStationNames = new Set(baseline.map((s: any) => getStationName(s)));
                const newStationNames = new Set(newStations.map(s => getStationName(s)));
                
                // New stations added
                const addedStations = newStations.filter(s => !baselineStationNames.has(getStationName(s)));
                
                // Stations removed
                const removedStations = baseline.filter((s: any) => !newStationNames.has(getStationName(s)));
                
                // Stations that exist in both (potential moves or apparatus changes)
                const commonStations = newStations.filter(s => baselineStationNames.has(getStationName(s)));
                
                // Check for moved stations (position changed)
                const movedStations = commonStations.filter(current => {
                  const currentName = getStationName(current);
                  const baselineStation = baseline.find((s: any) => getStationName(s) === currentName);
                  
                  if (!baselineStation) return false;
                  
                  const baseLat = baselineStation.lat;
                  const baseLon = baselineStation.lon || baselineStation.lng;
                  const currLat = current.lat;
                  const currLon = current.lon || current.lng;
                  
                  // Check if position changed (allowing for small floating point differences)
                  if (baseLat === undefined || currLat === undefined) return false;
                  const latChanged = Math.abs(baseLat - currLat) > 0.0001;
                  const lonChanged = Math.abs((baseLon ?? 0) - (currLon ?? 0)) > 0.0001;
                  return latChanged || lonChanged;
                });
                
                // Check for apparatus changes
                const apparatusChangedStations = commonStations.filter(current => {
                  const currentName = getStationName(current);
                  const baselineStation = baseline.find((s: any) => getStationName(s) === currentName);
                  
                  if (!baselineStation) return false;
                  
                  // Get baseline apparatus counts from the captured baseline
                  const baseApparatus = baselineApparatusCounts?.get(baselineStation.id);
                  const currApparatus = stationApparatusCounts?.get(current.id);
                  
                  // If either is missing, can't compare
                  if (!baseApparatus && !currApparatus) return false;
                  if (!baseApparatus || !currApparatus) return true; // One has apparatus, one doesn't
                  
                  // Compare total apparatus count
                  const baseTotal = Object.values(baseApparatus).reduce((sum, count) => sum + (count || 0), 0);
                  const currTotal = Object.values(currApparatus).reduce((sum, count) => sum + (count || 0), 0);
                  
                  return baseTotal !== currTotal;
                });
                
                return (
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
                        <div className="text-2xl font-bold text-green-700">{addedStations.length}</div>
                        <div className="text-sm text-green-600">New Stations Added</div>
                      </div>
                      
                      <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                        <div className="text-2xl font-bold text-red-700">{removedStations.length}</div>
                        <div className="text-sm text-red-600">Stations Removed</div>
                      </div>
                      
                      <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                        <div className="text-2xl font-bold text-blue-700">{movedStations.length}</div>
                        <div className="text-sm text-blue-600">Stations Relocated</div>
                      </div>
                      
                      <div className="p-3 bg-purple-50 border border-purple-200 rounded-lg">
                        <div className="text-2xl font-bold text-purple-700">{apparatusChangedStations.length}</div>
                        <div className="text-sm text-purple-600">Apparatus Modified</div>
                      </div>
                    </div>
                    
                    {/* Detailed Changes */}
                    <div className="space-y-2 text-sm">
                      {addedStations.length > 0 && (
                        <div className="flex items-start gap-2">
                          <CheckCircle className="w-4 h-4 text-green-600 mt-0.5" />
                          <div>
                            <strong className="text-green-700">Added:</strong>{' '}
                            {addedStations.map(s => getStationName(s)).join(', ')}
                          </div>
                        </div>
                      )}
                      
                      {removedStations.length > 0 && (
                        <div className="flex items-start gap-2">
                          <AlertTriangle className="w-4 h-4 text-red-600 mt-0.5" />
                          <div>
                            <strong className="text-red-700">Removed:</strong>{' '}
                            {removedStations.map((s: any) => getStationName(s)).join(', ')}
                          </div>
                        </div>
                      )}
                      
                      {movedStations.length > 0 && (
                        <div className="flex items-start gap-2">
                          <MapPin className="w-4 h-4 text-blue-600 mt-0.5 flex-shrink-0" />
                          <div>
                            <strong className="text-blue-700">Relocated:</strong>
                            <div className="mt-1 space-y-1">
                              {movedStations.map(current => {
                                const currentName = getStationName(current);
                                const baselineStation = baseline.find((s: any) => getStationName(s) === currentName);
                                
                                if (!baselineStation) return null;
                                
                                const baseLat = baselineStation.lat?.toFixed(4);
                                const baseLon = (baselineStation.lon || baselineStation.lng)?.toFixed(4);
                                const currLat = current.lat?.toFixed(4);
                                const currLon = (current.lon || current.lng)?.toFixed(4);
                                
                                return (
                                  <div key={current.id} className="text-xs">
                                    <span className="font-medium">{currentName}</span>
                                    {' '}({baseLat}, {baseLon}) → ({currLat}, {currLon})
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        </div>
                      )}
                      
                      {apparatusChangedStations.length > 0 && (
                        <div className="flex items-start gap-2">
                          <TrendingUp className="w-4 h-4 text-purple-600 mt-0.5 flex-shrink-0" />
                          <div>
                            <strong className="text-purple-700">Apparatus Changed:</strong>
                            <div className="mt-1 space-y-1">
                              {apparatusChangedStations.map(current => {
                                const currentName = getStationName(current);
                                const baselineStation = baseline.find((s: any) => getStationName(s) === currentName);
                                
                                if (!baselineStation) return null;
                                
                                // Get baseline and current apparatus counts
                                const baseApparatus = baselineApparatusCounts?.get(baselineStation.id) || {};
                                const currApparatus = stationApparatusCounts?.get(current.id) || {};
                                
                                // Calculate differences
                                const allApparatusTypes = new Set([
                                  ...Object.keys(baseApparatus),
                                  ...Object.keys(currApparatus)
                                ]);
                                
                                const changes: string[] = [];
                                allApparatusTypes.forEach(type => {
                                  const baseCount = baseApparatus[type] || 0;
                                  const currCount = currApparatus[type] || 0;
                                  const diff = currCount - baseCount;
                                  
                                  if (diff !== 0) {
                                    const sign = diff > 0 ? '+' : '';
                                    // Convert apparatus type to readable name
                                    const typeName = type.replace('_ID', '').replace('_', ' ');
                                    changes.push(`${sign}${diff} ${typeName}`);
                                  }
                                });
                                
                                if (changes.length === 0) return null;
                                
                                return (
                                  <div key={current.id} className="text-xs">
                                    <span className="font-medium">{currentName}</span>
                                    {' '}({changes.join(', ')})
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        </div>
                      )}
                      
                      {addedStations.length === 0 && removedStations.length === 0 && 
                       movedStations.length === 0 && apparatusChangedStations.length === 0 && (
                        <div className="text-gray-500 italic text-center py-2">
                          No network configuration changes detected
                        </div>
                      )}
                    </div>
                  </div>
                );
              })()}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Top-level simulation KPIs moved to Simulation Results tab */}
      {/* Performance Impact Summary moved to Simulation Results tab */}
      {/* Compact apparatus totals grid (aim ~6+ per row) */}
      <div className="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-6 xl:grid-cols-8 gap-2">
        {apparatusColumns.map(col => (
          <Card key={col.key} className="min-w-0">
            <CardHeader className="py-1 px-2">
              <CardTitle className="text-[10px] font-medium">{col.label}</CardTitle>
            </CardHeader>
            <CardContent className="py-1 px-2">
              <div className="text-[13px] leading-none font-semibold">{totalsByType?.[col.key] ?? 0}</div>
              <p className="text-[9px] leading-none mt-1 text-muted-foreground">Across all</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Stations Overview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <span>Total Stations</span>
              <Badge variant="secondary">{stationCount}</Badge>
            </div>
            <div className="flex items-center justify-between">
              <span>Average Apparatus per Station</span>
              <Badge variant="outline">{averageApparatusPerStation}</Badge>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Incidents Overview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between mb-3">
              <span className="font-medium">Total Incidents</span>
              <Badge variant="secondary">
                {historicalIncidentStats?.total_incidents || incidentsCount}
              </Badge>
            </div>
            
            {/* Error Message */}
            {historicalIncidentError && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-md">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 text-red-600" />
                  <span className="text-sm font-medium text-red-800">Error</span>
                </div>
                <p className="text-sm text-red-700 mt-1">{historicalIncidentError}</p>
              </div>
            )}
            
            {/* Historical Incident Statistics */}
            {historicalIncidentStats && !historicalIncidentError && (
              <div className="space-y-3">
                {/* Average time between incidents - with safe access */}
                {historicalIncidentStats.average_time_between_incidents_minutes !== undefined && 
                 historicalIncidentStats.average_time_between_incidents_minutes !== null && 
                 typeof historicalIncidentStats.average_time_between_incidents_minutes === 'number' && (
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">Avg Time Between Incidents</span>
                    <Badge variant="outline">
                      {historicalIncidentStats.average_time_between_incidents_minutes.toFixed(2)} min
                    </Badge>
                  </div>
                )}
                
                {/* Incident Type Breakdown */}
                {historicalIncidentStats.incident_counts && (
                  <div className="space-y-2">
                    <span className="text-sm font-medium text-muted-foreground">Incident Types:</span>
                    {Object.entries(historicalIncidentStats.incident_counts).map(([type, count]) => (
                      <div key={type} className="flex justify-between text-sm">
                        <span>{type}</span>
                        <span>{count as number}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Apparatus by Station Table */}
      <Card>
        <CardHeader>
          <CardTitle>Apparatus by Station</CardTitle>
        </CardHeader>
        <CardContent>
          {stationRows && stationRows.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Station</TableHead>
                  {apparatusColumns.map(col => (
                    <TableHead key={col.key}>{col.label}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {stationRows.map(row => (
                  <TableRow key={row.stationId}>
                    <TableCell className="font-medium">{row.stationName}</TableCell>
                    {apparatusColumns.map(col => (
                      <TableCell key={col.key} className="text-center">{row.counts[col.key] || 0}</TableCell>
                    ))}
                  </TableRow>
                ))}
                {/* Totals row */}
                <TableRow>
                  <TableCell className="font-bold">Total</TableCell>
                  {apparatusColumns.map(col => (
                    <TableCell key={col.key} className="font-bold text-center">{totalsByType?.[col.key] || 0}</TableCell>
                  ))}
                </TableRow>
              </TableBody>
            </Table>
          ) : (
            <div className="text-sm text-muted-foreground">No apparatus data available yet.</div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}