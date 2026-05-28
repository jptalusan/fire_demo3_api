import React from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { Badge } from './ui/badge';
import { AlertTriangle, CheckCircle, Clock, MapPin, AlertTriangle as Triangle, BarChart3, TrendingUp, GitCompare, ArrowDown, ArrowUp } from 'lucide-react';
import { SimulationPlotsContainer } from './SimulationPlots';
import { processStationReport, StationReport } from '../utils/dataProcessing';

interface SimulationTabProps {
  hasResults: boolean;
  simulationResults: any;
  incidentsCount?: number;
  isCounterfactualMode?: boolean;
  baselineResults?: any;
}

// Ground Truth Metric Card Component
interface GroundTruthMetricCardProps {
  title: string;
  icon: React.ReactNode;
  simulationValue: number;
  groundTruthValue: number;
  unit: string;
  format?: (value: number) => string;
  lowerIsBetter?: boolean;
}

function GroundTruthMetricCard({ 
  title, 
  icon, 
  simulationValue, 
  groundTruthValue, 
  unit, 
  format = (v) => v.toFixed(2),
  lowerIsBetter = true
}: GroundTruthMetricCardProps) {
  const delta = simulationValue - groundTruthValue;
  const percentChange = groundTruthValue !== 0 ? ((delta / groundTruthValue) * 100) : 0;
  
  // Determine if this is better or worse
  const isBetter = lowerIsBetter ? delta < 0 : delta > 0;
  const isNeutral = Math.abs(delta) < 0.01;
  
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold mb-1">
          {format(simulationValue)} {unit}
        </div>
        {!isNeutral && (
          <div className={`flex items-center gap-1 text-sm font-medium ${
            isBetter ? 'text-green-600' : 'text-red-600'
          }`}>
            {delta > 0 ? (
              <ArrowUp className="w-4 h-4" />
            ) : (
              <ArrowDown className="w-4 h-4" />
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
          Historical: {format(groundTruthValue)} {unit}
        </div>
      </CardContent>
    </Card>
  );
}

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
            {delta > 0 ? (
              <ArrowUp className="w-4 h-4" />
            ) : (
              <ArrowDown className="w-4 h-4" />
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

export function SimulationTab({ hasResults, simulationResults, incidentsCount, isCounterfactualMode = false, baselineResults }: SimulationTabProps) {
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

  // Process station report data if available - handle both regular and comparison results
  const resultsData = simulationResults?.newConfig || simulationResults;
  const stationReports: StationReport[] = resultsData?.station_report 
    ? processStationReport(resultsData.station_report)
    : [];
  
  // Check if evaluation data exists (ground truth comparison)
  const hasEvaluation = simulationResults?.evaluation !== undefined;
  const overallSummary = simulationResults?.evaluation?.overall_summary;
  const engineEvaluation = simulationResults?.evaluation?.engine_evaluation;
  const medicEvaluation = simulationResults?.evaluation?.medic_evaluation;

  return (
    <div className="h-full overflow-auto space-y-4 p-4">
      {hasResults ? (
        <div className="space-y-4">
          {/* Counterfactual Mode: Comparative Analysis */}
          {isCounterfactualMode && baselineResults && simulationResults ? (
            <div className="space-y-4">
              {/* Comparative Metrics Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <ComparativeMetricCard
                  title="Avg Response Time"
                  icon={<Clock className="h-4 w-4 text-muted-foreground" />}
                  baselineValue={Number(baselineResults.average_response_time) || 0}
                  newValue={Number(resultsData.average_response_time) || 0}
                  unit="sec"
                  lowerIsBetter={true}
                />
                
                <ComparativeMetricCard
                  title="P90 Response Time"
                  icon={<Clock className="h-4 w-4 text-muted-foreground" />}
                  baselineValue={Number(baselineResults.P90_continuous) || 0}
                  newValue={Number(resultsData.P90_continuous) || 0}
                  unit="sec"
                  lowerIsBetter={true}
                />
                
                <ComparativeMetricCard
                  title="On-Time Rate"
                  icon={<MapPin className="h-4 w-4 text-muted-foreground" />}
                  baselineValue={parseFloat(String(baselineResults.coverage_percent).replace('%', '')) || 0}
                  newValue={parseFloat(String(resultsData.coverage_percent).replace('%', '')) || 0}
                  unit="%"
                  lowerIsBetter={false}
                />
              </div>
            </div>
          ) : hasEvaluation && overallSummary ? (
            /* Regular Mode: KPI Cards with Ground Truth Comparison */
            <div className="grid grid-cols-3 gap-3">
              <GroundTruthMetricCard
                title="Avg Response Time"
                icon={<Clock className="h-4 w-4 text-muted-foreground" />}
                simulationValue={Number(resultsData?.average_response_time) || 0}
                groundTruthValue={overallSummary.ground_truth_travel_time_mean || 0}
                unit="sec"
                lowerIsBetter={true}
              />
              <GroundTruthMetricCard
                title="P90 Response Time"
                icon={<Clock className="h-4 w-4 text-muted-foreground" />}
                simulationValue={Number(resultsData?.P90_continuous) || 0}
                groundTruthValue={overallSummary.ground_truth_P90_continuous || 0}
                unit="sec"
                lowerIsBetter={true}
              />
              <GroundTruthMetricCard
                title="On-Time Response Rate"
                icon={<MapPin className="h-4 w-4 text-muted-foreground" />}
                simulationValue={parseFloat(String(resultsData?.coverage_percent || 0).replace('%', ''))}
                groundTruthValue={overallSummary.ground_truth_coverage_percent || 0}
                unit="%"
                lowerIsBetter={false}
              />
            </div>
          ) : (
            /* Regular Mode: KPI Cards without Ground Truth */
            <div className="grid grid-cols-3 gap-3">
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-1.5">
                  <CardTitle className="text-sm">Avg Response Time</CardTitle>
                  <Clock className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-xl">{resultsData?.average_response_time ? Number(resultsData.average_response_time).toFixed(2) : '-'} sec</div>
                  <p className="text-[11px] text-green-600">Mean travel time</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-1.5">
                  <CardTitle className="text-sm">P90 Response Time</CardTitle>
                  <Clock className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-xl">{resultsData?.P90_continuous ? Number(resultsData.P90_continuous).toFixed(2) : '-'} sec</div>
                  <p className="text-[11px] text-blue-600">90th percentile</p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-1.5">
                  <CardTitle className="text-sm">On-Time Response Rate</CardTitle>
                  <MapPin className="h-4 w-4 text-muted-foreground" />
                </CardHeader>
                <CardContent>
                  <div className="text-xl">{resultsData?.coverage_percent ? 
                    (typeof simulationResults.coverage_percent === 'string' && simulationResults.coverage_percent.includes('%') 
                      ? simulationResults.coverage_percent 
                      : Number(simulationResults.coverage_percent).toFixed(2) + '%') 
                    : '87%'}
                  </div>
                  <p className="text-[11px] text-muted-foreground">Within 5-minute response</p>
                </CardContent>
              </Card>
            </div>
          )}

          {/* Performance Analytics Section */}
          <div className="mt-8">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5 text-blue-600" />
                  Performance Analytics
                </CardTitle>
                <CardDescription>
                  Detailed performance metrics and operational insights from simulation
                </CardDescription>
              </CardHeader>
              <CardContent>
                <SimulationPlotsContainer 
                  simulationResults={simulationResults}
                  historicalIncidentStats={undefined}
                  incidentsCount={incidentsCount}
                />
              </CardContent>
            </Card>
          </div>

          {/* Station Performance Report - Show only if simulation has run and we have station report data */}
          {simulationResults && simulationResults.station_report && stationReports.length > 0 && (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold">Station Performance Report</h2>
                <Badge variant="secondary">{stationReports.length} stations</Badge>
                <Badge variant="outline" className="text-xs">From Simulation</Badge>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {stationReports
                  .sort((a, b) => parseFloat(a.stationName) - parseFloat(b.stationName))
                  .map((report) => {
                    const performance = getPerformanceStatus(report.travelTimeMean);
                    return (
                      <Card key={report.stationName} className="hover:shadow-md transition-shadow">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                          <CardTitle className="text-sm">
                            Station {report.stationName.padStart(2, '0')}
                          </CardTitle>
                          <TrendingUp className={`h-4 w-4 ${performance.color.replace('text-', 'text-')}`} />
                        </CardHeader>
                        <CardContent className="space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium">Avg Travel Time</span>
                            <span className={`text-sm font-bold ${performance.color}`}>
                              {formatTravelTime(report.travelTimeMean)}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium">P90 Travel Time</span>
                            <span className="text-sm font-bold text-blue-600">
                              {formatTravelTime(report.travelTimeP90)}
                            </span>
                          </div>
                          <div className="flex items-center justify-between">
                            <span className="text-sm font-medium">Incidents Handled</span>
                            <Badge variant="outline">{report.incidentCount}</Badge>
                          </div>
                          <div className="pt-1">
                            <span className={`text-xs font-medium ${performance.color}`}>
                              {performance.status}
                            </span>
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
              </div>
            </div>
          )}
        </div>
      ) : (
        <Card className="h-full">
          <CardContent className="flex items-center justify-center h-full">
            <div className="text-center text-muted-foreground">
              <AlertTriangle className="h-8 w-8 mx-auto mb-2" />
              <p>No simulation results available</p>
              <p className="text-sm">Run a simulation to see results here</p>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}