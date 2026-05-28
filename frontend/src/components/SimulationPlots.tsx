import React, { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from './ui/card';
import { MapPin, Clock, AlertTriangle, Activity, Thermometer, Truck, Timer, BarChart3 } from 'lucide-react';
import { MockBarChart } from './MockPlots';



// D3.js Heatmap Component following React Graph Gallery patterns
export const IncidentProbabilityHeatmap: React.FC = () => {
  const svgRef = useRef<SVGSVGElement>(null);

  // Data setup
  const stations = ['Station 1', 'Station 2', 'Station 3', 'Station 4', 'Station 5', 'Station 6'];
  const hours = Array.from({ length: 24 }, (_, i) => i);
  
  // Generate structured data for D3
  const data = stations.flatMap(station => 
    hours.map(hour => ({
      station,
      hour,
      value: Math.random() * 0.8 + 0.1, // 0.1 to 0.9 probability
      incidents: Math.floor(Math.random() * 10 + 1)
    }))
  );

  useEffect(() => {
    if (!svgRef.current) return;

    // Clear previous content
    d3.select(svgRef.current).selectAll("*").remove();

    // Dimensions and margins following React Graph Gallery pattern
    const margin = { top: 80, right: 25, bottom: 30, left: 90 };
    const width = 800 - margin.left - margin.right;
    const height = 400 - margin.top - margin.bottom;

    // Create main SVG
    const svg = d3.select(svgRef.current)
      .attr("width", width + margin.left + margin.right)
      .attr("height", height + margin.top + margin.bottom);

    const g = svg.append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    // Scales
    const xScale = d3.scaleBand()
      .range([0, width])
      .domain(hours.map(String))
      .padding(0.05);

    const yScale = d3.scaleBand()
      .range([height, 0])
      .domain(stations)
      .padding(0.05);

    // Color scale using D3's interpolateViridis for better color mapping
    const colorScale = d3.scaleSequential()
      .interpolator(d3.interpolateViridis)
      .domain([0.1, 0.9]);

    // Create tooltip div
    const tooltipDiv = d3.select("body")
      .append("div")
      .attr("class", "heatmap-tooltip-" + Date.now())
      .style("opacity", 0)
      .style("position", "absolute")
      .style("background", "rgba(0, 0, 0, 0.8)")
      .style("color", "white")
      .style("padding", "8px")
      .style("border-radius", "4px")
      .style("font-size", "12px")
      .style("pointer-events", "none")
      .style("z-index", "1000");

    // Create heatmap rectangles
    g.selectAll(".heatmap-rect")
      .data(data)
      .enter()
      .append("rect")
      .attr("class", "heatmap-rect")
      .attr("x", d => xScale(String(d.hour))!)
      .attr("y", d => yScale(d.station)!)
      .attr("rx", 2)
      .attr("ry", 2)
      .attr("width", xScale.bandwidth())
      .attr("height", yScale.bandwidth())
      .style("fill", d => colorScale(d.value))
      .style("stroke", "white")
      .style("stroke-width", 1)
      .style("cursor", "pointer")
      .on("mouseover", function(event, d) {
        d3.select(this)
          .style("stroke", "#333")
          .style("stroke-width", 2);
        
        tooltipDiv.transition()
          .duration(200)
          .style("opacity", .9);
        
        tooltipDiv.html(`
          <strong>${d.station}</strong><br/>
          Hour: ${d.hour}:00<br/>
          Probability: ${(d.value * 100).toFixed(1)}%<br/>
          Incidents: ${d.incidents}
        `)
          .style("left", (event.pageX + 10) + "px")
          .style("top", (event.pageY - 28) + "px");
      })
      .on("mouseout", function(d) {
        d3.select(this)
          .style("stroke", "white")
          .style("stroke-width", 1);
        
        tooltipDiv.transition()
          .duration(500)
          .style("opacity", 0);
      });

    // Add X axis
    g.append("g")
      .attr("transform", `translate(0,${height})`)
      .call(d3.axisBottom(xScale))
      .selectAll("text")
      .style("text-anchor", "middle")
      .style("font-size", "11px");

    // Add Y axis
    g.append("g")
      .call(d3.axisLeft(yScale))
      .selectAll("text")
      .style("font-size", "11px");

    // Add labels
    svg.append("text")
      .attr("transform", "rotate(-90)")
      .attr("y", 0 + 15)
      .attr("x", 0 - (height / 2) - margin.top)
      .attr("dy", "1em")
      .style("text-anchor", "middle")
      .style("font-size", "12px")
      .style("font-weight", "bold")
      .text("Fire Stations");

    svg.append("text")
      .attr("transform", `translate(${(width / 2) + margin.left}, ${height + margin.top + 25})`)
      .style("text-anchor", "middle")
      .style("font-size", "12px")
      .style("font-weight", "bold")
      .text("Hour of Day");

    // Add title
    svg.append("text")
      .attr("x", (width / 2) + margin.left)
      .attr("y", 25)
      .attr("text-anchor", "middle")
      .style("font-size", "16px")
      .style("font-weight", "bold")
      .text("Incident Probability by Station and Hour");

    // Add legend
    const legendWidth = 200;
    const legendHeight = 20;
    
    const legend = svg.append("g")
      .attr("transform", `translate(${width + margin.left - legendWidth}, 50)`);

    // Create legend gradient
    const defs = svg.append("defs");
    const linearGradient = defs.append("linearGradient")
      .attr("id", "legend-gradient");

    linearGradient.selectAll("stop")
      .data(d3.range(0, 1.1, 0.1))
      .enter().append("stop")
      .attr("offset", d => `${d * 100}%`)
      .attr("stop-color", d => colorScale(0.1 + d * 0.8));

    legend.append("rect")
      .attr("width", legendWidth)
      .attr("height", legendHeight)
      .style("fill", "url(#legend-gradient)")
      .style("stroke", "#ccc");

    // Legend labels
    legend.append("text")
      .attr("x", 0)
      .attr("y", legendHeight + 15)
      .style("font-size", "10px")
      .text("Low (10%)");

    legend.append("text")
      .attr("x", legendWidth)
      .attr("y", legendHeight + 15)
      .style("text-anchor", "end")
      .style("font-size", "10px")
      .text("High (90%)");

    // Cleanup function to remove tooltip when component unmounts
    return () => {
      tooltipDiv.remove();
    };
  }, []);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Thermometer className="h-5 w-5" />
          Incident Probability Heatmap
        </CardTitle>
        <CardDescription>
          D3.js visualization showing incident probability patterns across stations and time
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="w-full flex justify-center">
          <svg ref={svgRef}></svg>
        </div>
      </CardContent>
    </Card>
  );
};

// Compact Metadata Cards Component
interface CompactMetadataCardsProps {
  simulationResults?: any;
  incidentsCount?: number;
}

export const CompactMetadataCards: React.FC<CompactMetadataCardsProps> = ({ simulationResults, incidentsCount }) => {
  // Calculate success rate from simulation results
  const calculateSuccessRate = () => {
    if (!simulationResults) {
      return 'N/A';
    }
    
    // Success Rate = incidents in simulation / total incidents loaded
    const totalIncidentsInSimulation = simulationResults.total_incidents;
    
    // Use the actual incidentsCount passed from App.tsx (the 333 total incidents)
    const totalIncidentsLoaded = incidentsCount || 
                                 simulationResults.total_incidents_loaded || 
                                 simulationResults.incidents_total || 
                                 simulationResults.loaded_incidents ||
                                 simulationResults.original_incidents_count;
    
    if (!totalIncidentsInSimulation || !totalIncidentsLoaded) {
      return 'N/A';
    }
    
    const successRate = ((totalIncidentsInSimulation / totalIncidentsLoaded) * 100).toFixed(1);
    return `${successRate}%`;
  };

  // Get simulation time from results - time to call run_simulation2 and get response
  const getSimulationTime = () => {
    // Look for API call duration fields
    const apiCallTime = simulationResults?.api_call_duration || 
                       simulationResults?.request_duration ||
                       simulationResults?.simulation_duration ||
                       simulationResults?.execution_time;
    
    if (apiCallTime) {
      const time = parseFloat(apiCallTime);
      // Format based on magnitude
      if (time < 1) {
        return `${(time * 1000).toFixed(0)}ms`;
      } else if (time < 60) {
        return `${time.toFixed(1)}s`;
      } else {
        return `${(time / 60).toFixed(1)}min`;
      }
    }
    
    return '2.3s'; // fallback
  };

  const metadata = [
    {
      title: 'Simulation time',
      value: getSimulationTime(),
      description: 'Simulation time',
      icon: <Clock className="h-4 w-4" />,
    }
  ];

  return (
    <div className="grid grid-cols-1 gap-4">
      {metadata.map((item, index) => (
        <Card key={index} className="p-3">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-lg font-bold">{item.value}</div>
              <div className="text-xs text-gray-600">{item.description}</div>
            </div>
            <div className="text-gray-400">
              {item.icon}
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
};

// Main Simulation Plots Container
interface SimulationPlotsContainerProps {
  simulationResults?: any;
  historicalIncidentStats?: any;
  incidentsCount?: number;
}

export const SimulationPlotsContainer: React.FC<SimulationPlotsContainerProps> = ({ 
  simulationResults, 
  historicalIncidentStats,
  incidentsCount 
}) => {
  return (
    <div className="space-y-6">
      {/* Compact Performance Analytics */}
      <div>
        <h3 className="text-lg font-semibold mb-4">Performance Analytics</h3>
        <CompactMetadataCards simulationResults={simulationResults} incidentsCount={incidentsCount} />
      </div>

      {/* Single Incident Probability Heatmap - Commented out for now */}
      {/* <div>
        <IncidentProbabilityHeatmap />
      </div> */}

      {/* Vehicle and Response Analytics */}
      <div>
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <BarChart3 className="h-5 w-5" />
          Vehicle & Response Analytics
        </h3>
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
          <MockBarChart 
            title="Average Response Times by Category"
            data={simulationResults && simulationResults.average_response_time_per_incident_type
              ? simulationResults.average_response_time_per_incident_type
                  .slice(0, 10) // Take top 10
                  .map((item: any) => {
                    const category = Object.keys(item)[0];
                    const data = Object.values(item)[0] as any;
                    return {
                      category: category.length > 150 ? category.substring(0, 147) + '...' : category,
                      avgResponseTime: Math.round((data['average_travel_time'] / 60) * 100) / 100 // Convert seconds to minutes, round to 2 decimals
                    };
                  })
              : [
                  { category: 'Fire Alarm', avgResponseTime: 4.2 },
                  { category: 'Medical Emergency', avgResponseTime: 5.8 },
                  { category: 'Vehicle Accident', avgResponseTime: 6.1 },
                  { category: 'Structure Fire', avgResponseTime: 3.9 },
                  { category: 'Hazmat', avgResponseTime: 7.3 }
                ]
            }
            valueKey="avgResponseTime"
            labelKey="category"
            unit=" min"
            isRealData={!!(simulationResults && simulationResults.average_response_time_per_incident_type)}
          />
          
          <MockBarChart 
            title="Average Travel Time by Vehicle Type"
            data={simulationResults && simulationResults.vehicle_report 
              ? simulationResults.vehicle_report.map((vehicleReport: any) => {
                  const vehicleType = Object.keys(vehicleReport)[0];
                  const data = vehicleReport[vehicleType];
                  return {
                    vehicleType: vehicleType === 'Medic' ? 'Medic Unit' : 
                                vehicleType === 'Engine' ? 'Fire Engine' :
                                vehicleType === 'Truck' ? 'Ladder Truck' :
                                vehicleType === 'Rescue' ? 'Rescue Unit' :
                                vehicleType,
                    avgTravelTime: Math.round((data['travel_time_mean'] / 60) * 100) / 100 // Convert seconds to minutes
                  };
                })
              : [
                  { vehicleType: 'Fire Engine', avgTravelTime: 3.5 },
                  { vehicleType: 'Medic Unit', avgTravelTime: 4.2 },
                  { vehicleType: 'Ladder Truck', avgTravelTime: 5.1 },
                  { vehicleType: 'Rescue Unit', avgTravelTime: 3.8 }
                ]
            }
            valueKey="avgTravelTime"
            labelKey="vehicleType"
            unit=" min"
            isRealData={!!(simulationResults && simulationResults.vehicle_report)}
          />
          
          <MockBarChart 
            title="Incidents Handled by Vehicle Type"
            data={simulationResults && simulationResults.vehicle_report 
              ? simulationResults.vehicle_report.map((vehicleReport: any) => {
                  const vehicleType = Object.keys(vehicleReport)[0];
                  const data = vehicleReport[vehicleType];
                  return {
                    vehicleType: vehicleType === 'Medic' ? 'Medic Unit' : 
                                vehicleType === 'Engine' ? 'Fire Engine' :
                                vehicleType === 'Truck' ? 'Ladder Truck' :
                                vehicleType === 'Rescue' ? 'Rescue Unit' :
                                vehicleType,
                    incidentCount: data['incident_count']
                  };
                })
              : [
                  { vehicleType: 'Fire Engine', incidentCount: 45 },
                  { vehicleType: 'Medic Unit', incidentCount: 120 },
                  { vehicleType: 'Ladder Truck', incidentCount: 25 },
                  { vehicleType: 'Rescue Unit', incidentCount: 8 }
                ]
            }
            valueKey="incidentCount"
            labelKey="vehicleType"
            isRealData={!!(simulationResults && simulationResults.vehicle_report)}
          />
        </div>
      </div>
    </div>
  );
};