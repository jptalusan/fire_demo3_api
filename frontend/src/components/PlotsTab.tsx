import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from './ui/collapsible';
import { ChevronDown, ChevronRight, Maximize2, X } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell, ReferenceLine } from 'recharts';
import { processStationReport, processStationTravelTimes, StationReport, StationTravelTimes } from '../utils/dataProcessing';
import { BoxPlotChart } from './BoxPlotChart';
import { MockPlotsContainer, IncidentTypesPieChart, MockBoxPlot } from './MockPlots';

interface PlotsTabProps {
  simulationResults?: any;
  historicalIncidentStats?: any;
  incidents?: any[];
  isCounterfactualMode?: boolean;
}

export function PlotsTab({ simulationResults, historicalIncidentStats, incidents = [] }: PlotsTabProps) {
  console.log('PlotsTab simulationResults:', simulationResults);
  console.log('PlotsTab has comparison:', !!simulationResults?.comparison);
  console.log('PlotsTab has newConfig:', !!simulationResults?.newConfig);
  console.log('PlotsTab has baseline:', !!simulationResults?.baseline);
  
  const [advancedAnalyticsOpen, setAdvancedAnalyticsOpen] = useState(false);
  const [fullscreenChart, setFullscreenChart] = useState<{
    title: string;
    content: React.ReactNode;
  } | null>(null);

  // Build response time chart data from simulation station_report
  // Handle both regular results and counterfactual comparison results
  const resultsData = simulationResults?.newConfig || simulationResults;
  console.log('PlotsTab resultsData:', resultsData);
  console.log('PlotsTab resultsData.station_report:', resultsData?.station_report);
  
  let stationReports: StationReport[] = [];
  let stationTravelTimes: StationTravelTimes[] = [];
  
  try {
    stationReports = resultsData?.station_report
      ? processStationReport(resultsData.station_report)
      : [];
    
    stationTravelTimes = resultsData?.station_report
      ? processStationTravelTimes(resultsData.station_report)
      : [];
  } catch (error) {
    console.error('Error processing station data:', error);
    stationReports = [];
    stationTravelTimes = [];
  }

  console.log('Processed station reports:', stationReports);
  console.log('Processed station travel times:', stationTravelTimes);

  // TODO: 5 is hard coded, put it in some config.
  const targetMinutes: number = resultsData?.target_response_minutes ?? 5;

  const responseTimeData = stationReports
    .slice()
    .sort((a, b) => {
      // Extract station numbers for sorting
      const aNum = parseFloat(a.stationName.replace(/\D/g, '')) || 0;
      const bNum = parseFloat(b.stationName.replace(/\D/g, '')) || 0;
      return aNum - bNum;
    })
    .map((r) => {
      // Extract just the number from "Station XX" format
      const match = r.stationName.match(/\d+/);
      const stationNum = match ? match[0] : r.stationName;
      return {
        station: stationNum,
        avgTime: Number((r.travelTimeMean / 60).toFixed(2)), // seconds -> minutes
        target: targetMinutes,
        incidents: r.incidentCount,
      };
    });

  const incidentTypeData = [
    { type: 'Medical Emergency', count: 580, color: '#4ECDC4' },
    { type: 'Structure Fire', count: 204, color: '#FF6B6B' },
    { type: 'Vehicle Accident', count: 304, color: '#4DABF7' },
    { type: 'Hazmat', count: 50, color: '#69DB7C' },
    { type: 'Other', count: 109, color: '#FFD43B' }
  ];

  const coverageData = [
    { area: 'Downtown', covered: 85, uncovered: 15 },
    { area: 'Midtown', covered: 78, uncovered: 22 },
    { area: 'Uptown', covered: 92, uncovered: 8 },
    { area: 'Brooklyn', covered: 71, uncovered: 29 }
  ];

  // Generate mock data for the box plot with proper quartile relationships
  const mockStationTravelTimes = ['station_01', 'station_02', 'station_03', 'station_04', 'station_05', 'station_06'].map(station => {
    const min = Math.round((Math.random() * 2 + 1) * 100) / 100; // 1-3 minutes
    const q1 = min + Math.round((Math.random() * 3 + 2) * 100) / 100; // Q1 > min
    const median = q1 + Math.round((Math.random() * 2 + 1) * 100) / 100; // median > Q1
    const q3 = median + Math.round((Math.random() * 2 + 1) * 100) / 100; // Q3 > median
    const max = q3 + Math.round((Math.random() * 3 + 2) * 100) / 100; // max > Q3
    const mean = (min + q1 + median + q3 + max) / 5; // Calculate mean
    
    return {
      stationName: station,
      min,
      q1,
      median,
      q3,
      max,
      mean: Math.round(mean * 100) / 100
    };
  });

  // Check for evaluation data
  const hasEvaluation = simulationResults?.evaluation !== undefined;
  const engineEvaluation = simulationResults?.evaluation?.engine_evaluation;
  const medicEvaluation = simulationResults?.evaluation?.medic_evaluation;

  // Prepare station data for comparison charts
  const prepareStationData = (evaluation: any) => {
    if (!evaluation?.per_station_metrics?.station_comparison) return [];
    
    return evaluation.per_station_metrics.station_comparison
      .filter((station: any) => station.travel_mean_sim !== null && station.travel_mean_gt !== null)
      .map((station: any) => ({
        station: station.StationID.replace('Station ', 'S'),
        simMean: station.travel_mean_sim / 60, // Convert to minutes
        gtMean: station.travel_mean_gt / 60,
        simP90: station.travel_p90_sim / 60,
        gtP90: station.travel_p90_gt / 60,
        simCount: station.count_sim,
        gtCount: station.count_gt,
      }));
  };

  const engineStationData = engineEvaluation ? prepareStationData(engineEvaluation) : [];
  const medicStationData = medicEvaluation ? prepareStationData(medicEvaluation) : [];

  const [evaluationChartsOpen, setEvaluationChartsOpen] = useState(true);

  return (
    <div className="h-full overflow-auto space-y-4 p-4">
      {/* Evaluation Comparison Charts - Simulation vs Historical */}
      {hasEvaluation && (engineEvaluation || medicEvaluation) && (
        <Collapsible open={evaluationChartsOpen} onOpenChange={setEvaluationChartsOpen}>
          <Card className="border-2 border-blue-200 bg-gradient-to-r from-blue-50 to-purple-50">
            <CollapsibleTrigger className="w-full">
              <CardHeader className="cursor-pointer hover:bg-white/50 transition-colors">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    {evaluationChartsOpen ? (
                      <ChevronDown className="h-5 w-5 text-blue-600" />
                    ) : (
                      <ChevronRight className="h-5 w-5 text-blue-600" />
                    )}
                    <CardTitle className="text-lg">
                      Simulation vs Ground Truth Comparison
                    </CardTitle>
                    <Badge variant="secondary" className="bg-blue-100 text-blue-900">
                      Evaluation Mode
                    </Badge>
                  </div>
                </div>
                <CardDescription className="text-left ml-8">
                  Station-level performance comparison between simulation results and historical ground truth data
                </CardDescription>
              </CardHeader>
            </CollapsibleTrigger>
            
            <CollapsibleContent>
              <CardContent className="space-y-6 pt-4">
                {/* Fire Engine Charts */}
                {engineEvaluation && engineStationData.length > 0 && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary" className="text-sm bg-blue-100 text-blue-900">
                        Fire Engine
                      </Badge>
                      <span className="text-sm text-muted-foreground">
                        {engineStationData.length} stations
                      </span>
                    </div>

                    {/* Engine: Avg Travel Time Comparison */}
                    <Card>
                      <CardHeader>
                        <div className="flex items-center justify-between">
                          <div>
                            <CardTitle className="text-base">Average Travel Time by Station</CardTitle>
                            <CardDescription>
                              Comparison of simulation vs historical data (minutes)
                            </CardDescription>
                          </div>
                          <Button 
                            variant="ghost" 
                            size="sm"
                            onClick={() => setFullscreenChart({
                              title: "Engine: Average Travel Time by Station",
                              content: (
                                <ResponsiveContainer width="100%" height={600}>
                                  <BarChart 
                                    data={engineStationData}
                                    margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
                                  >
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis 
                                      dataKey="station" 
                                      angle={-45}
                                      textAnchor="end"
                                      height={80}
                                      label={{ value: 'Station', position: 'insideBottom', offset: -20 }}
                                    />
                                    <YAxis domain={['auto', 'auto']} label={{ value: 'Avg Travel Time (min)', angle: -90, position: 'center', offset: 20 }} />
                                    <Tooltip formatter={(value: any) => `${Number(value).toFixed(2)} min`} />
                                    <Legend verticalAlign="top" align="right" wrapperStyle={{ paddingBottom: '20px' }} />
                                    <Bar dataKey="simMean" fill="#3b82f6" name="Simulation" />
                                    <Bar dataKey="gtMean" fill="#f97316" name="Historical" />
                                  </BarChart>
                                </ResponsiveContainer>
                              )
                            })}
                            className="hover:bg-gray-100"
                          >
                            <Maximize2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <ResponsiveContainer width="100%" height={400}>
                          <BarChart 
                            data={engineStationData}
                            margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis 
                              dataKey="station" 
                              angle={-45}
                              textAnchor="end"
                              height={80}
                              label={{ value: 'Station', position: 'insideBottom', offset: -20 }}
                            />
                            <YAxis label={{ value: 'Avg Travel Time (min)', angle: -90, position: 'center', offset: 10 }} />
                            <Tooltip formatter={(value: any) => `${Number(value).toFixed(2)} min`} />
                            <Legend verticalAlign="top" align="right" wrapperStyle={{ paddingBottom: '20px' }} />
                            <Bar dataKey="simMean" fill="#3b82f6" name="Simulation" />
                            <Bar dataKey="gtMean" fill="#f97316" name="Historical" />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>

                    {/* Engine: P90 Travel Time Comparison */}
                    <Card>
                      <CardHeader>
                        <div className="flex items-center justify-between">
                          <div>
                            <CardTitle className="text-base">P90 Travel Time by Station</CardTitle>
                            <CardDescription>
                              90th percentile comparison of simulation vs historical data (minutes)
                            </CardDescription>
                          </div>
                          <Button 
                            variant="ghost" 
                            size="sm"
                            onClick={() => setFullscreenChart({
                              title: "Engine: P90 Travel Time by Station",
                              content: (
                                <ResponsiveContainer width="100%" height={600}>
                                  <BarChart 
                                    data={engineStationData}
                                    margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
                                  >
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis 
                                      dataKey="station" 
                                      angle={-45}
                                      textAnchor="end"
                                      height={80}
                                      label={{ value: 'Station', position: 'insideBottom', offset: -20 }}
                                    />
                                    <YAxis domain={['auto', 'auto']} label={{ value: 'P90 Travel Time (min)', angle: -90, position: 'center', offset: 20 }} />
                                    <Tooltip formatter={(value: any) => `${Number(value).toFixed(2)} min`} />
                                    <Legend verticalAlign="top" align="right" wrapperStyle={{ paddingBottom: '20px' }} />
                                    <Bar dataKey="simP90" fill="#3b82f6" name="Simulation" />
                                    <Bar dataKey="gtP90" fill="#f97316" name="Historical" />
                                  </BarChart>
                                </ResponsiveContainer>
                              )
                            })}
                            className="hover:bg-gray-100"
                          >
                            <Maximize2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <ResponsiveContainer width="100%" height={400}>
                          <BarChart 
                            data={engineStationData}
                            margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis 
                              dataKey="station" 
                              angle={-45}
                              textAnchor="end"
                              height={80}
                              label={{ value: 'Station', position: 'insideBottom', offset: -20 }}
                            />
                            <YAxis label={{ value: 'P90 Travel Time (min)', angle: -90, position: 'center', offset: 10 }} />
                            <Tooltip formatter={(value: any) => `${Number(value).toFixed(2)} min`} />
                            <Legend verticalAlign="top" align="right" wrapperStyle={{ paddingBottom: '20px' }} />
                            <Bar dataKey="simP90" fill="#3b82f6" name="Simulation" />
                            <Bar dataKey="gtP90" fill="#f97316" name="Historical" />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>

                    {/* Engine: Incident Count Comparison */}
                    <Card>
                      <CardHeader>
                        <div className="flex items-center justify-between">
                          <div>
                            <CardTitle className="text-base">Incident Count by Station</CardTitle>
                            <CardDescription>
                              Number of incidents handled: simulation vs historical data
                            </CardDescription>
                          </div>
                          <Button 
                            variant="ghost" 
                            size="sm"
                            onClick={() => setFullscreenChart({
                              title: "Engine: Incident Count by Station",
                              content: (
                                <ResponsiveContainer width="100%" height={600}>
                                  <BarChart 
                                    data={engineStationData}
                                    margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
                                  >
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis 
                                      dataKey="station" 
                                      angle={-45}
                                      textAnchor="end"
                                      height={80}
                                      label={{ value: 'Station', position: 'insideBottom', offset: -20 }}
                                    />
                                    <YAxis domain={['auto', 'auto']} label={{ value: 'Incident Count', angle: -90, position: 'center', offset: 20 }} />
                                    <Tooltip />
                                    <Legend verticalAlign="top" align="right" wrapperStyle={{ paddingBottom: '20px' }} />
                                    <Bar dataKey="simCount" fill="#3b82f6" name="Simulation" />
                                    <Bar dataKey="gtCount" fill="#f97316" name="Historical" />
                                  </BarChart>
                                </ResponsiveContainer>
                              )
                            })}
                            className="hover:bg-gray-100"
                          >
                            <Maximize2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <ResponsiveContainer width="100%" height={400}>
                          <BarChart 
                            data={engineStationData}
                            margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis 
                              dataKey="station" 
                              angle={-45}
                              textAnchor="end"
                              height={80}
                              label={{ value: 'Station', position: 'insideBottom', offset: -20 }}
                            />
                            <YAxis label={{ value: 'Incident Count', angle: -90, position: 'center', offset: 10 }} />
                            <Tooltip />
                            <Legend verticalAlign="top" align="right" wrapperStyle={{ paddingBottom: '20px' }} />
                            <Bar dataKey="simCount" fill="#3b82f6" name="Simulation" />
                            <Bar dataKey="gtCount" fill="#f97316" name="Historical" />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  </div>
                )}

                {/* Medic Unit Charts */}
                {medicEvaluation && medicStationData.length > 0 && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 mt-6">
                      <Badge variant="secondary" className="text-sm bg-purple-100 text-purple-900">
                        Medic Units
                      </Badge>
                      <span className="text-sm text-muted-foreground">
                        {medicStationData.length} stations
                      </span>
                    </div>

                    {/* Medic: Avg Travel Time Comparison */}
                    <Card>
                      <CardHeader>
                        <div className="flex items-center justify-between">
                          <div>
                            <CardTitle className="text-base">Average Travel Time by Station</CardTitle>
                            <CardDescription>
                              Comparison of simulation vs historical data (minutes)
                            </CardDescription>
                          </div>
                          <Button 
                            variant="ghost" 
                            size="sm"
                            onClick={() => setFullscreenChart({
                              title: "Medic: Average Travel Time by Station",
                              content: (
                                <ResponsiveContainer width="100%" height={600}>
                                  <BarChart 
                                    data={medicStationData}
                                    margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
                                  >
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis 
                                      dataKey="station" 
                                      angle={-45}
                                      textAnchor="end"
                                      height={80}
                                      label={{ value: 'Station', position: 'insideBottom', offset: -20 }}
                                    />
                                    <YAxis domain={['auto', 'auto']} label={{ value: 'Avg Travel Time (min)', angle: -90, position: 'center', offset: 20 }} />
                                    <Tooltip formatter={(value: any) => `${Number(value).toFixed(2)} min`} />
                                    <Legend verticalAlign="top" align="right" wrapperStyle={{ paddingBottom: '20px' }} />
                                    <Bar dataKey="simMean" fill="#3b82f6" name="Simulation" />
                                    <Bar dataKey="gtMean" fill="#f97316" name="Historical" />
                                  </BarChart>
                                </ResponsiveContainer>
                              )
                            })}
                            className="hover:bg-gray-100"
                          >
                            <Maximize2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <ResponsiveContainer width="100%" height={400}>
                          <BarChart 
                            data={medicStationData}
                            margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis 
                              dataKey="station" 
                              angle={-45}
                              textAnchor="end"
                              height={80}
                              label={{ value: 'Station', position: 'insideBottom', offset: -20 }}
                            />
                            <YAxis domain={['auto', 'auto']} label={{ value: 'Avg Travel Time (min)', angle: -90, position: 'center', offset: 20 }} />
                            <Tooltip formatter={(value: any) => `${Number(value).toFixed(2)} min`} />
                            <Legend verticalAlign="top" align="right" wrapperStyle={{ paddingBottom: '20px' }} />
                            <Bar dataKey="simMean" fill="#3b82f6" name="Simulation" />
                            <Bar dataKey="gtMean" fill="#f97316" name="Historical" />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>

                    {/* Medic: P90 Travel Time Comparison */}
                    <Card>
                      <CardHeader>
                        <div className="flex items-center justify-between">
                          <div>
                            <CardTitle className="text-base">P90 Travel Time by Station</CardTitle>
                            <CardDescription>
                              90th percentile comparison of simulation vs historical data (minutes)
                            </CardDescription>
                          </div>
                          <Button 
                            variant="ghost" 
                            size="sm"
                            onClick={() => setFullscreenChart({
                              title: "Medic: P90 Travel Time by Station",
                              content: (
                                <ResponsiveContainer width="100%" height={600}>
                                  <BarChart 
                                    data={medicStationData}
                                    margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
                                  >
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis 
                                      dataKey="station" 
                                      angle={-45}
                                      textAnchor="end"
                                      height={80}
                                      label={{ value: 'Station', position: 'insideBottom', offset: -20 }}
                                    />
                                    <YAxis domain={['auto', 'auto']} label={{ value: 'P90 Travel Time (min)', angle: -90, position: 'center', offset: 20 }} />
                                    <Tooltip formatter={(value: any) => `${Number(value).toFixed(2)} min`} />
                                    <Legend verticalAlign="top" align="right" wrapperStyle={{ paddingBottom: '20px' }} />
                                    <Bar dataKey="simP90" fill="#3b82f6" name="Simulation" />
                                    <Bar dataKey="gtP90" fill="#f97316" name="Historical" />
                                  </BarChart>
                                </ResponsiveContainer>
                              )
                            })}
                            className="hover:bg-gray-100"
                          >
                            <Maximize2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <ResponsiveContainer width="100%" height={400}>
                          <BarChart 
                            data={medicStationData}
                            margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis 
                              dataKey="station" 
                              angle={-45}
                              textAnchor="end"
                              height={80}
                              label={{ value: 'Station', position: 'insideBottom', offset: -20 }}
                            />
                            <YAxis domain={['auto', 'auto']} label={{ value: 'P90 Travel Time (min)', angle: -90, position: 'center', offset: 20 }} />
                            <Tooltip formatter={(value: any) => `${Number(value).toFixed(2)} min`} />
                            <Legend verticalAlign="top" align="right" wrapperStyle={{ paddingBottom: '20px' }} />
                            <Bar dataKey="simP90" fill="#3b82f6" name="Simulation" />
                            <Bar dataKey="gtP90" fill="#f97316" name="Historical" />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>

                    {/* Medic: Incident Count Comparison */}
                    <Card>
                      <CardHeader>
                        <div className="flex items-center justify-between">
                          <div>
                            <CardTitle className="text-base">Incident Count by Station</CardTitle>
                            <CardDescription>
                              Number of incidents handled: simulation vs historical data
                            </CardDescription>
                          </div>
                          <Button 
                            variant="ghost" 
                            size="sm"
                            onClick={() => setFullscreenChart({
                              title: "Medic: Incident Count by Station",
                              content: (
                                <ResponsiveContainer width="100%" height={600}>
                                  <BarChart 
                                    data={medicStationData}
                                    margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
                                  >
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis 
                                      dataKey="station" 
                                      angle={-45}
                                      textAnchor="end"
                                      height={80}
                                      label={{ value: 'Station', position: 'insideBottom', offset: -20 }}
                                    />
                                    <YAxis domain={['auto', 'auto']} label={{ value: 'Incident Count', angle: -90, position: 'center', offset: 20 }} />
                                    <Tooltip />
                                    <Legend verticalAlign="top" align="right" wrapperStyle={{ paddingBottom: '20px' }} />
                                    <Bar dataKey="simCount" fill="#3b82f6" name="Simulation" />
                                    <Bar dataKey="gtCount" fill="#f97316" name="Historical" />
                                  </BarChart>
                                </ResponsiveContainer>
                              )
                            })}
                            className="hover:bg-gray-100"
                          >
                            <Maximize2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </CardHeader>
                      <CardContent>
                        <ResponsiveContainer width="100%" height={400}>
                          <BarChart 
                            data={medicStationData}
                            margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis 
                              dataKey="station" 
                              angle={-45}
                              textAnchor="end"
                              height={80}
                              label={{ value: 'Station', position: 'insideBottom', offset: -20 }}
                            />
                            <YAxis domain={['auto', 'auto']} label={{ value: 'Incident Count', angle: -90, position: 'center', offset: 20 }} />
                            <Tooltip />
                            <Legend verticalAlign="top" align="right" wrapperStyle={{ paddingBottom: '20px' }} />
                            <Bar dataKey="simCount" fill="#3b82f6" name="Simulation" />
                            <Bar dataKey="gtCount" fill="#f97316" name="Historical" />
                          </BarChart>
                        </ResponsiveContainer>
                      </CardContent>
                    </Card>
                  </div>
                )}
              </CardContent>
            </CollapsibleContent>
          </Card>
        </Collapsible>
      )}

      {/* Comparison Charts for Changed Stations (Counterfactual Mode) */}
      {(() => {
        // Check if we have both baseline and newConfig data
        if (!simulationResults?.baseline?.station_report || !simulationResults?.newConfig?.station_report) {
          return null;
        }

        // Process baseline and newConfig station reports
        const baselineReports = processStationReport(simulationResults.baseline.station_report);
        const newConfigReports = processStationReport(simulationResults.newConfig.station_report);
        
        console.log('Baseline station reports:', baselineReports);
        console.log('New config station reports:', newConfigReports);

        // Create a map of baseline data for easy lookup
        const baselineMap = new Map(baselineReports.map(r => [r.stationName, r]));
        const newConfigMap = new Map(newConfigReports.map(r => [r.stationName, r]));

        // Get all station names from both datasets
        const allStationNames = new Set([...baselineMap.keys(), ...newConfigMap.keys()]);

        // Build comparison data - include all stations that exist in either baseline or newConfig
        const stationsWithComparison = Array.from(allStationNames)
          .map(stationName => {
            const baseline = baselineMap.get(stationName);
            const newConfig = newConfigMap.get(stationName);
            
            // Determine if this is a new station or existing
            const isNewStation = !baseline && !!newConfig;
            
            return {
              station_name: stationName,
              status: isNewStation ? 'new_station' : 'existing_station',
              average_travel_time: {
                baseline: baseline?.travelTimeMean || 0,
                new: newConfig?.travelTimeMean || 0,
                difference: (newConfig?.travelTimeMean || 0) - (baseline?.travelTimeMean || 0)
              },
              p90_travel_time: {
                baseline: baseline?.travelTimeP90 || 0,
                new: newConfig?.travelTimeP90 || 0,
                difference: (newConfig?.travelTimeP90 || 0) - (baseline?.travelTimeP90 || 0)
              },
              total_incidents: {
                baseline: baseline?.incidentCount || 0,
                new: newConfig?.incidentCount || 0,
                difference: (newConfig?.incidentCount || 0) - (baseline?.incidentCount || 0)
              }
            };
          })
          .filter(station => {
            // Include stations that have data in at least one configuration
            return station.average_travel_time.baseline > 0 || station.average_travel_time.new > 0;
          });

        console.log('Stations with comparison data:', stationsWithComparison);

        if (stationsWithComparison.length === 0) {
          console.log('No stations with comparison data found');
          return null;
        }

        return (
          <div className="space-y-4 mb-6">
            <div className="flex items-center gap-2 mb-4">
              <Badge variant="secondary" className="text-sm">
                Counterfactual Analysis
              </Badge>
              <span className="text-sm text-muted-foreground">
                Comparing {stationsWithComparison.filter(s => s.status === 'existing_station').length} existing stations
                {stationsWithComparison.some(s => s.status === 'new_station') && 
                  ` + ${stationsWithComparison.filter(s => s.status === 'new_station').length} new station(s)`}
              </span>
            </div>

            {/* Average Response Time Comparison */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Average Response Time: Baseline vs New Configuration</CardTitle>
                    <CardDescription>
                      Comparison of average response times for existing stations with changes (minutes)
                    </CardDescription>
                  </div>
                  <Button 
                    variant="ghost" 
                    size="sm"
                    onClick={() => setFullscreenChart({
                      title: "Average Response Time: Baseline vs New Configuration",
                      content: (
                        <ResponsiveContainer width="100%" height={600}>
                          <BarChart 
                            data={stationsWithComparison.map((station: any) => ({
                              station: station.station_name.replace('Station ', ''),
                              baseline: Number((station.average_travel_time.baseline / 60).toFixed(2)),
                              newConfig: Number((station.average_travel_time.new / 60).toFixed(2))
                            }))}
                            margin={{ top: 20, right: 30, left: 5, bottom: 100 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis 
                              dataKey="station" 
                              angle={-45}
                              textAnchor="end"
                              height={100}
                              tickMargin={15}
                              fontSize={11}
                              label={{ value: 'Stations', position: 'insideBottom', offset: -5, style: { textAnchor: 'middle' } }}
                            />
                            <YAxis 
                              label={{ value: 'Response Time (minutes)', angle: -90, position: 'center', offset: 10 }} 
                              width={80}
                            />
                            <Tooltip formatter={(value: any) => `${value} min`} />
                            <Legend />
                            <Bar dataKey="baseline" fill="#8884d8" name="Baseline" />
                            <Bar dataKey="newConfig" fill="#82ca9d" name="New Configuration" />
                          </BarChart>
                        </ResponsiveContainer>
                      )
                    })}
                    className="hover:bg-gray-100"
                  >
                    <Maximize2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={450}>
                  <BarChart 
                    data={stationsWithComparison.map((station: any) => ({
                      station: station.station_name.replace('Station ', ''),
                      baseline: Number((station.average_travel_time.baseline / 60).toFixed(2)),
                      newConfig: Number((station.average_travel_time.new / 60).toFixed(2))
                    }))}
                    margin={{ top: 20, right: 30, left: 5, bottom: 80 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="station" 
                      angle={-45}
                      textAnchor="end"
                      height={80}
                      tickMargin={10}
                      fontSize={11}
                    />
                    <YAxis 
                      label={{ value: 'Response Time (minutes)', angle: -90, position: 'center' }} 
                      width={100}
                    />
                    <Tooltip formatter={(value: any) => `${value} min`} />
                    <Legend />
                    <Bar dataKey="baseline" fill="#8884d8" name="Baseline" />
                    <Bar dataKey="newConfig" fill="#82ca9d" name="New Configuration" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* P90 Response Time Comparison */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>P90 Response Time: Baseline vs New Configuration</CardTitle>
                    <CardDescription>
                      Comparison of 90th percentile response times for existing stations with changes (minutes)
                    </CardDescription>
                  </div>
                  <Button 
                    variant="ghost" 
                    size="sm"
                    onClick={() => setFullscreenChart({
                      title: "P90 Response Time: Baseline vs New Configuration",
                      content: (
                        <ResponsiveContainer width="100%" height={600}>
                          <BarChart 
                            data={stationsWithComparison.map((station: any) => ({
                              station: station.station_name.replace('Station ', ''),
                              baseline: Number((station.p90_travel_time.baseline / 60).toFixed(2)),
                              newConfig: Number((station.p90_travel_time.new / 60).toFixed(2))
                            }))}
                            margin={{ top: 20, right: 30, left: 5, bottom: 100 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis 
                              dataKey="station" 
                              angle={-45}
                              textAnchor="end"
                              height={100}
                              tickMargin={15}
                              fontSize={11}
                            />
                            <YAxis 
                              label={{ value: 'P90 Response Time (minutes)', angle: -90, position: 'center' }} 
                              width={100}
                            />
                            <Tooltip formatter={(value: any) => `${value} min`} />
                            <Legend />
                            <Bar dataKey="baseline" fill="#8884d8" name="Baseline" />
                            <Bar dataKey="newConfig" fill="#82ca9d" name="New Configuration" />
                          </BarChart>
                        </ResponsiveContainer>
                      )
                    })}
                    className="hover:bg-gray-100"
                  >
                    <Maximize2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={450}>
                  <BarChart 
                    data={stationsWithComparison.map((station: any) => ({
                      station: station.station_name.replace('Station ', ''),
                      baseline: Number((station.p90_travel_time.baseline / 60).toFixed(2)),
                      newConfig: Number((station.p90_travel_time.new / 60).toFixed(2))
                    }))}
                    margin={{ top: 20, right: 30, left: 5, bottom: 80 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="station" 
                      angle={-45}
                      textAnchor="end"
                      height={80}
                      tickMargin={10}
                      fontSize={11}
                    />
                    <YAxis 
                      label={{ value: 'P90 Response Time (minutes)', angle: -90, position: 'center' }} 
                      width={100}
                    />
                    <Tooltip formatter={(value: any) => `${value} min`} />
                    <Legend />
                    <Bar dataKey="baseline" fill="#8884d8" name="Baseline" />
                    <Bar dataKey="newConfig" fill="#82ca9d" name="New Configuration" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            {/* Incident Count Comparison */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>Incidents Handled: Baseline vs New Configuration</CardTitle>
                    <CardDescription>
                      Comparison of incident counts for existing stations with changes
                    </CardDescription>
                  </div>
                  <Button 
                    variant="ghost" 
                    size="sm"
                    onClick={() => setFullscreenChart({
                      title: "Incidents Handled: Baseline vs New Configuration",
                      content: (
                        <ResponsiveContainer width="100%" height={600}>
                          <BarChart 
                            data={stationsWithComparison.map((station: any) => ({
                              station: station.station_name.replace('Station ', ''),
                              baseline: station.total_incidents.baseline,
                              newConfig: station.total_incidents.new
                            }))}
                            margin={{ top: 20, right: 30, left: 5, bottom: 100 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" />
                            <XAxis 
                              dataKey="station" 
                              angle={-45}
                              textAnchor="end"
                              height={100}
                              tickMargin={15}
                              fontSize={11}
                            />
                            <YAxis 
                              label={{ value: 'Incident Count', angle: -90, position: 'center' }} 
                              width={100}
                            />
                            <Tooltip />
                            <Legend />
                            <Bar dataKey="baseline" fill="#8884d8" name="Baseline" />
                            <Bar dataKey="newConfig" fill="#82ca9d" name="New Configuration" />
                          </BarChart>
                        </ResponsiveContainer>
                      )
                    })}
                    className="hover:bg-gray-100"
                  >
                    <Maximize2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={450}>
                  <BarChart 
                    data={stationsWithComparison.map((station: any) => ({
                      station: station.station_name.replace('Station ', ''),
                      baseline: station.total_incidents.baseline,
                      newConfig: station.total_incidents.new
                    }))}
                    margin={{ top: 20, right: 30, left: 5, bottom: 80 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis 
                      dataKey="station" 
                      angle={-45}
                      textAnchor="end"
                      height={80}
                      tickMargin={10}
                      fontSize={11}
                    />
                    <YAxis 
                      label={{ value: 'Incident Count', angle: -90, position: 'center' }} 
                      width={100}
                    />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="baseline" fill="#8884d8" name="Baseline" />
                    <Bar dataKey="newConfig" fill="#82ca9d" name="New Configuration" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>
        );
      })()}

      {/* Travel Times Box Plot - Full Width */}
      {/* Travel Times Box Plot - Compact Layout */}
      <Card>
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-lg">Travel Time Distribution by Station</CardTitle>
              <CardDescription className="text-sm mt-1">
                Distribution of travel times for different scenarios
              </CardDescription>
            </div>
            <Button 
              variant="ghost" 
              size="sm"
              onClick={() => setFullscreenChart({
                title: "Travel Time Distribution by Station",
                content: resultsData && stationTravelTimes.length > 0 ? (
                  <BoxPlotChart data={stationTravelTimes} yAxisLabel="Travel Time (minutes)" height={600} />
                ) : (
                  <div className="text-sm text-muted-foreground p-4 text-center">
                    Run a simulation to see travel time distribution.
                  </div>
                )
              })}
              className="hover:bg-gray-100"
            >
              <Maximize2 className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="pt-2 pb-2">
          {resultsData && stationTravelTimes.length > 0 ? (
            <div className="w-full" style={{ height: '280px' }}>
              <BoxPlotChart data={stationTravelTimes} yAxisLabel="Travel Time (minutes)" height={280} />
            </div>
          ) : (
            <div className="text-sm text-muted-foreground py-4 text-center">
              Run a simulation to see travel time distribution.
            </div>
          )}
        </CardContent>
      </Card>

      {/* P90 Response Times by Station */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>P90 Response Times by Station</CardTitle>
              <CardDescription>
                90th percentile response times (minutes) - 90% of incidents are handled within this time
              </CardDescription>
            </div>
            <Button 
              variant="ghost" 
              size="sm"
              onClick={() => setFullscreenChart({
                title: "P90 Response Times by Station",
                content: resultsData && resultsData.station_report && responseTimeData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={600}>
                    <BarChart 
                      data={stationReports
                        .slice()
                        .sort((a, b) => {
                          const aNum = parseFloat(a.stationName.replace(/\D/g, '')) || 0;
                          const bNum = parseFloat(b.stationName.replace(/\D/g, '')) || 0;
                          return aNum - bNum;
                        })
                        .map((r) => {
                          const match = r.stationName.match(/\d+/);
                          const stationNum = match ? match[0] : r.stationName;
                          return {
                            station: stationNum,
                            p90Time: Number((r.travelTimeP90 / 60).toFixed(2)),
                            incidents: r.incidentCount,
                          };
                        })
                      }
                      margin={{ top: 20, right: 30, left: 5, bottom: 100 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" />
                      <XAxis 
                        dataKey="station" 
                        interval={0} 
                        angle={-45} 
                        textAnchor="end" 
                        height={100} 
                        tickMargin={15}
                        fontSize={11}
                        label={{ value: 'Stations', position: 'insideBottom', offset: -5, style: { textAnchor: 'middle' } }}
                      />
                      <YAxis 
                        label={{ value: 'Response Time (minutes)', angle: -90, position: 'center' }} 
                        width={100}
                      />
                      <Tooltip formatter={(value: any) => [`${value} min`, 'P90 Time']} />
                      <Bar dataKey="p90Time" fill="#82ca9d" name="P90 Time (min)" />
                      <ReferenceLine y={targetMinutes} stroke="red" strokeDasharray="5 5" label={`Target ${targetMinutes}m`} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="text-sm text-muted-foreground p-4 text-center">
                    Run a simulation to see P90 data.
                  </div>
                )
              })}
              className="hover:bg-gray-100"
            >
              <Maximize2 className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {resultsData && resultsData.station_report && stationReports.length > 0 ? (
            <ResponsiveContainer width="100%" height={450}>
              <BarChart 
                data={stationReports
                  .slice()
                  .sort((a, b) => {
                    const aNum = parseFloat(a.stationName.replace(/\D/g, '')) || 0;
                    const bNum = parseFloat(b.stationName.replace(/\D/g, '')) || 0;
                    return aNum - bNum;
                  })
                  .map((r) => {
                    const match = r.stationName.match(/\d+/);
                    const stationNum = match ? match[0] : r.stationName;
                    return {
                      station: stationNum,
                      p90Time: Number((r.travelTimeP90 / 60).toFixed(2)),
                      incidents: r.incidentCount,
                    };
                  })
                }
                margin={{ top: 20, right: 30, left: 5, bottom: 100 }}
              >
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis 
                  dataKey="station" 
                  interval={0} 
                  angle={-45} 
                  textAnchor="end" 
                  height={100} 
                  tickMargin={15}
                  fontSize={11}
                  label={{ value: 'Stations', position: 'insideBottom', offset: -5, style: { textAnchor: 'middle' } }}
                />
                <YAxis 
                  label={{ value: 'Response Time (minutes)', angle: -90, position: 'center' }} 
                  width={100}
                />
                <Tooltip formatter={(value: any) => [`${value} min`, 'P90 Time']} />
                <Bar dataKey="p90Time" fill="#82ca9d" name="P90 Time (min)" />
                <ReferenceLine y={targetMinutes} stroke="red" strokeDasharray="5 5" label={`Target ${targetMinutes}m`} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="text-sm text-muted-foreground p-4 text-center">
              Run a simulation to see P90 data.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Response Time and Incidents Charts - Full Width Layout */}
      <div className="space-y-4">
        {/* Response Time Chart (from actual simulation results) */}
        {/* Average Response Times by Station */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Average Response Times by Station</CardTitle>
                <CardDescription>
                  Response time (minutes) per station from simulation
                </CardDescription>
              </div>
              <Button 
                variant="ghost" 
                size="sm"
                  onClick={() => setFullscreenChart({
                    title: "Average Response Times by Station",
                    content: resultsData && resultsData.station_report && responseTimeData.length > 0 ? (
                    <div style={{ width: '100%', height: '700px' }}>
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={responseTimeData} margin={{ top: 20, right: 30, left: 5, bottom: 120 }}>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis 
                            dataKey="station" 
                            interval={0} 
                            angle={-45} 
                            textAnchor="end" 
                            height={120} 
                            tickMargin={20}
                            fontSize={14}
                            label={{ value: 'Stations', position: 'insideBottom', offset: -10, style: { textAnchor: 'middle', fontSize: '16px' } }}
                          />
                          <YAxis 
                            label={{ value: 'Response Time (minutes)', angle: -90, position: 'center' }}
                            fontSize={14}
                            width={100}
                          />
                          <Tooltip 
                            formatter={(value: any, name: any) => [`${value} min`, name === 'avgTime' ? 'Response Time' : name]}
                            labelStyle={{ fontSize: '14px' }}
                            contentStyle={{ fontSize: '14px' }}
                          />
                          <Bar dataKey="avgTime" fill="#8884d8" name="Response Time (min)" />
                          <ReferenceLine y={targetMinutes} stroke="red" strokeDasharray="5 5" />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <div className="text-sm text-muted-foreground p-4 text-center">
                      Run a simulation to see response times.
                    </div>
                  )
                })}
                className="hover:bg-gray-100"
              >
                <Maximize2 className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {resultsData && resultsData.station_report && responseTimeData.length > 0 ? (
              <ResponsiveContainer width="100%" height={450}>
                <BarChart data={responseTimeData} margin={{ top: 20, right: 30, left: 5, bottom: 100 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="station" 
                    interval={0} 
                    angle={-45} 
                    textAnchor="end" 
                    height={100} 
                    tickMargin={15}
                    fontSize={11}
                    label={{ value: 'Stations', position: 'insideBottom', offset: -5, style: { textAnchor: 'middle' } }}
                  />
                  <YAxis 
                    label={{ value: 'Minutes', angle: -90, position: 'center' }} 
                    width={100}
                  />
                  <Tooltip formatter={(value: any, name: any) => [value, name === 'avgTime' ? 'Avg Time (min)' : name === 'target' ? 'Target (min)' : name]} />
                  <Bar dataKey="avgTime" fill="#8884d8" name="Avg Time (min)" />
                  <ReferenceLine y={targetMinutes} stroke="#82ca9d" strokeDasharray="4 4" label={`Target ${targetMinutes}m`} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-sm text-muted-foreground p-4 text-center">
                Run a simulation to see response time data.
              </div>
            )}
          </CardContent>
        </Card>

        {/* Incidents per Station */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Incidents Handled by Station</CardTitle>
                <CardDescription>
                  Number of incidents handled by each station
                </CardDescription>
              </div>
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => setFullscreenChart({
                  title: "Incidents Handled by Station",
                  content: resultsData && resultsData.station_report && responseTimeData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={600}>
                      <BarChart data={responseTimeData} margin={{ top: 20, right: 30, left: 5, bottom: 100 }}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis 
                          dataKey="station" 
                          interval={0} 
                          angle={-45} 
                          textAnchor="end" 
                          height={100} 
                          tickMargin={15}
                          fontSize={11}
                          label={{ value: 'Stations', position: 'insideBottom', offset: -5, style: { textAnchor: 'middle' } }}
                        />
                        <YAxis 
                          label={{ value: 'Incidents', angle: -90, position: 'center' }} 
                          width={100}
                        />
                        <Tooltip formatter={(value: any, name: any) => [value, name === 'incidents' ? 'Incidents' : name]} />
                        <Bar dataKey="incidents" fill="#4ECDC4" name="Incidents" />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="text-sm text-muted-foreground p-4 text-center">
                      Run a simulation to see incident distribution.
                    </div>
                  )
                })}
                className="hover:bg-gray-100"
              >
                <Maximize2 className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {resultsData && resultsData.station_report && responseTimeData.length > 0 ? (
              <ResponsiveContainer width="100%" height={450}>
                <BarChart data={responseTimeData} margin={{ top: 20, right: 30, left: 5, bottom: 100 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="station" 
                    interval={0} 
                    angle={-45} 
                    textAnchor="end" 
                    height={100} 
                    tickMargin={15}
                    fontSize={11}
                    label={{ value: 'Stations', position: 'insideBottom', offset: -5, style: { textAnchor: 'middle' } }}
                  />
                  <YAxis 
                    label={{ value: 'Incidents', angle: -90, position: 'center' }} 
                    width={100}
                  />
                  <Tooltip formatter={(value: any, name: any) => [value, name === 'incidents' ? 'Incidents' : name]} />
                  <Bar dataKey="incidents" fill="#4ECDC4" name="Incidents" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-sm text-muted-foreground p-4 text-center">
                Run a simulation to see incident distribution.
              </div>
            )}
          </CardContent>
        </Card>

        {/* Average Service Time per Station */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Average Service Time by Station</CardTitle>
                <CardDescription>
                  Average time spent at incident scenes by each station (in minutes)
                </CardDescription>
              </div>
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => setFullscreenChart({
                  title: "Average Service Time by Station",
                  content: resultsData && resultsData.station_report && stationReports.length > 0 ? (
                    <ResponsiveContainer width="100%" height={600}>
                      <BarChart 
                        data={stationReports
                          .slice()
                          .sort((a, b) => {
                            const aNum = parseFloat(a.stationName.replace(/\D/g, '')) || 0;
                            const bNum = parseFloat(b.stationName.replace(/\D/g, '')) || 0;
                            return aNum - bNum;
                          })
                          .map((report) => {
                            const match = report.stationName.match(/\d+/);
                            const stationNum = match ? match[0] : report.stationName;
                            const stationData = resultsData.station_report.find((item: any) => 
                              Object.keys(item)[0] === `Station ${stationNum.padStart(2, '0')}`
                            );
                            const stationMetrics = stationData ? (Object.values(stationData)[0] as any) : null;
                            const serviceTime = stationMetrics ? 
                              ((stationMetrics['average_service_time'] || stationMetrics['average service time']) / 60) : 0;
                            return {
                              station: stationNum,
                              serviceTime: Number(serviceTime.toFixed(2))
                            };
                          })
                        } 
                        margin={{ top: 20, right: 30, left: 5, bottom: 100 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis 
                          dataKey="station" 
                          interval={0} 
                          angle={-45} 
                          textAnchor="end" 
                          height={100} 
                          tickMargin={15}
                          fontSize={11}
                          label={{ value: 'Stations', position: 'insideBottom', offset: -5, style: { textAnchor: 'middle' } }}
                        />
                        <YAxis 
                          label={{ value: 'Service Time (minutes)', angle: -90, position: 'center' }} 
                          width={100}
                        />
                        <Tooltip formatter={(value: any, name: any) => [`${value} min`, 'Service Time']} />
                        <Bar dataKey="serviceTime" fill="#9B59B6" name="Service Time (min)" />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="text-sm text-muted-foreground p-4 text-center">
                      Run a simulation to see service time data.
                    </div>
                  )
                })}
                className="hover:bg-gray-100"
              >
                <Maximize2 className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {resultsData && resultsData.station_report && stationReports.length > 0 ? (
              <ResponsiveContainer width="100%" height={450}>
                <BarChart 
                  data={stationReports
                    .slice()
                    .sort((a, b) => {
                      // Extract station numbers for sorting
                      const aNum = parseFloat(a.stationName.replace(/\D/g, '')) || 0;
                      const bNum = parseFloat(b.stationName.replace(/\D/g, '')) || 0;
                      return aNum - bNum;
                    })
                    .map((report) => {
                      // Extract just the number from "Station XX" format
                      const match = report.stationName.match(/\d+/);
                      const stationNum = match ? match[0] : report.stationName;
                      
                      // Get service time from simulation results
                      const stationData = resultsData.station_report.find((item: any) => 
                        Object.keys(item)[0] === `Station ${stationNum.padStart(2, '0')}`
                      );
                      const stationMetrics = stationData ? (Object.values(stationData)[0] as any) : null;
                      const serviceTime = stationMetrics ? 
                        ((stationMetrics['average_service_time'] || stationMetrics['average service time']) / 60) : 0; // Convert seconds to minutes
                      
                      return {
                        station: stationNum,
                        serviceTime: Number(serviceTime.toFixed(2))
                      };
                    })
                  } 
                  margin={{ top: 20, right: 30, left: 5, bottom: 100 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis 
                    dataKey="station" 
                    interval={0} 
                    angle={-45} 
                    textAnchor="end" 
                    height={100} 
                    tickMargin={15}
                    fontSize={11}
                    label={{ value: 'Stations', position: 'insideBottom', offset: -5, style: { textAnchor: 'middle' } }}
                  />
                  <YAxis 
                    label={{ value: 'Service Time (minutes)', angle: -90, position: 'center' }} 
                    width={100}
                  />
                  <Tooltip formatter={(value: any, name: any) => [`${value} min`, 'Service Time']} />
                  <Bar dataKey="serviceTime" fill="#9B59B6" name="Service Time (min)" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-sm text-muted-foreground p-4 text-center">
                Run a simulation to see service time data.
              </div>
            )}
          </CardContent>
        </Card>

      </div>

      {/* Enhanced Analytics with Real Data */}
      <div className="mt-8">
        <Collapsible open={advancedAnalyticsOpen} onOpenChange={setAdvancedAnalyticsOpen}>
          <CollapsibleTrigger asChild>
            <Card className="cursor-pointer hover:bg-gray-50 transition-colors">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-xl">Advanced Analytics</CardTitle>
                    <CardDescription className="mt-2">
                      {incidents.length > 0 || (resultsData && resultsData.station_report)
                        ? "Performance metrics using real data from loaded incidents and simulation results"
                        : "Detailed performance metrics and station-specific analysis with sample data"
                      }
                    </CardDescription>

                  </div>
                  <Button variant="ghost" size="sm">
                    {advancedAnalyticsOpen ? (
                      <ChevronDown className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </CardHeader>
            </Card>
          </CollapsibleTrigger>
          
          <CollapsibleContent>
            <div className="mt-4">
              <MockPlotsContainer 
                historicalIncidentStats={historicalIncidentStats} 
                simulationResults={simulationResults}
                stationReports={stationReports}
                incidents={incidents}
              />
            </div>
          </CollapsibleContent>
        </Collapsible>
      </div>

      {/* Fullscreen Modal - Rendered as Portal */}
      {fullscreenChart && createPortal(
        <div 
          className="fixed inset-0 bg-black bg-opacity-75 flex items-center justify-center p-8" 
          style={{ 
            zIndex: 10000,
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0
          }}
        >
          <div 
            className="bg-white rounded-lg shadow-2xl flex flex-col"
            style={{
              width: '90vw',
              height: '85vh',
              maxWidth: '1600px',
              maxHeight: '1000px'
            }}
          >
            <div className="flex items-center justify-between p-4 border-b bg-gray-50 flex-shrink-0">
              <h2 className="text-xl font-bold text-gray-800">{fullscreenChart.title}</h2>
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => setFullscreenChart(null)}
                className="hover:bg-gray-200"
              >
                <X className="h-5 w-5" />
              </Button>
            </div>
            <div className="flex-1 overflow-y-auto overflow-x-hidden bg-white">
              <div className="p-6">
                {fullscreenChart.content}
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}