import React, { useState } from 'react';
import { ResponsiveContainer, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts';

interface BoxPlotData {
  stationName: string;
  min: number;
  q1: number;
  median: number;
  q3: number;
  max: number;
  mean: number;
}

interface BoxPlotChartProps {
  data: BoxPlotData[];
  width?: string | number;
  height?: number;
  yAxisLabel?: string;
}

export function BoxPlotChart({ data, width = "100%", height = 500, yAxisLabel = "Value" }: BoxPlotChartProps) {
  const [hoveredStation, setHoveredStation] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<{ x: number; y: number; data: BoxPlotData } | null>(null);

  // Calculate chart dimensions based on data
  const margin = { top: 10, right: 30, bottom: 40, left: 40 };
  const boxWidth = 30;
  const spacing = 8;
  const minWidth = data.length * (boxWidth + spacing) + margin.left + margin.right;
  const chartWidth = Math.max(800, minWidth);
  
  // Calculate domain with some padding
  const allValues = data.flatMap(d => [d.min, d.q1, d.median, d.q3, d.max, d.mean]);
  const dataMin = Math.min(...allValues);
  const dataMax = Math.max(...allValues);
  const padding = (dataMax - dataMin) * 0.1;
  const yDomain = [Math.max(0, dataMin - padding), dataMax + padding];
  const [yMin, yMax] = yDomain;
  const whiskerWidth = 20;

  return (
    <div className="w-full h-full overflow-hidden relative">
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${chartWidth} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        style={{ display: 'block', margin: '0 auto' }}
      >
        {/* Background grid */}
        <defs>
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#e0e0e0" strokeWidth="1" strokeDasharray="2,2"/>
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill="url(#grid)" />
        
        {/* Y-axis */}
        <line x1={margin.left} y1={margin.top} x2={margin.left} y2={height - margin.bottom} stroke="#666" strokeWidth="1"/>
        
        {/* X-axis */}
        <line x1={margin.left} y1={height - margin.bottom} x2={chartWidth - margin.right} y2={height - margin.bottom} stroke="#666" strokeWidth="1"/>
        
        {/* Y-axis label */}
        <text x="20" y={height / 2} textAnchor="middle" transform={`rotate(-90, 20, ${height / 2})`} 
              fontSize="14" fill="#666" fontWeight="500">
          {yAxisLabel}
        </text>
        
        {/* X-axis label */}
        <text x={chartWidth / 2} y={height - 5} textAnchor="middle" 
              fontSize="14" fill="#666" fontWeight="600">
          Stations
        </text>
        
        {/* Box plots */}
        {data.map((item, index) => {
          const x = margin.left + (boxWidth / 2) + index * (boxWidth + spacing); // Proper spacing between stations
          
          // Scale values to fit the chart
          const scaleY = (value: number) => {
            const ratio = (value - yMin) / (yMax - yMin);
            return height - margin.bottom - ratio * (height - margin.top - margin.bottom);
          };
          
          const minY = scaleY(item.min);
          const q1Y = scaleY(item.q1);
          const medianY = scaleY(item.median);
          const q3Y = scaleY(item.q3);
          const maxY = scaleY(item.max);
          const meanY = scaleY(item.mean);
          
          const isHovered = hoveredStation === item.stationName;
          
          return (
            <g key={item.stationName}>
              {/* Interactive area for hover detection */}
              <rect 
                x={x - boxWidth/2 - 10} 
                y={maxY - 10} 
                width={boxWidth + 20} 
                height={minY - maxY + 20} 
                fill="transparent"
                style={{ cursor: 'pointer' }}
                onMouseEnter={(e) => {
                  setHoveredStation(item.stationName);
                  const svgRect = (e.target as SVGRectElement).ownerSVGElement?.getBoundingClientRect();
                  if (svgRect) {
                    setTooltip({
                      x: e.clientX - svgRect.left,
                      y: e.clientY - svgRect.top,
                      data: item
                    });
                  }
                }}
                onMouseMove={(e) => {
                  const svgRect = (e.target as SVGRectElement).ownerSVGElement?.getBoundingClientRect();
                  if (svgRect) {
                    setTooltip(prev => prev ? {
                      ...prev,
                      x: e.clientX - svgRect.left,
                      y: e.clientY - svgRect.top
                    } : null);
                  }
                }}
                onMouseLeave={() => {
                  setHoveredStation(null);
                  setTooltip(null);
                }}
              />
              
              {/* Upper whisker */}
              <line x1={x} y1={maxY} x2={x} y2={q3Y} stroke={isHovered ? "#2196F3" : "#333"} strokeWidth={isHovered ? "3" : "2"}/>
              <line x1={x - whiskerWidth/2} y1={maxY} x2={x + whiskerWidth/2} y2={maxY} stroke={isHovered ? "#2196F3" : "#333"} strokeWidth={isHovered ? "3" : "2"}/>
              
              {/* Box */}
              <rect 
                x={x - boxWidth/2} 
                y={q3Y} 
                width={boxWidth} 
                height={q1Y - q3Y} 
                fill={isHovered ? "#2196F3" : "#4ECDC4"} 
                fillOpacity={isHovered ? "0.8" : "0.7"}
                stroke={isHovered ? "#1976D2" : "#333"} 
                strokeWidth={isHovered ? "3" : "2"}
              />
              
              {/* Median line */}
              <line x1={x - boxWidth/2} y1={medianY} x2={x + boxWidth/2} y2={medianY} stroke={isHovered ? "#1976D2" : "#333"} strokeWidth={isHovered ? "4" : "3"}/>
              
              {/* Mean point */}
              <circle cx={x} cy={meanY} r={isHovered ? "6" : "4"} fill="#FF6B6B" stroke={isHovered ? "#D32F2F" : "#333"} strokeWidth={isHovered ? "2" : "1"}/>
              
              {/* Lower whisker */}
              <line x1={x} y1={q1Y} x2={x} y2={minY} stroke={isHovered ? "#2196F3" : "#333"} strokeWidth={isHovered ? "3" : "2"}/>
              <line x1={x - whiskerWidth/2} y1={minY} x2={x + whiskerWidth/2} y2={minY} stroke={isHovered ? "#2196F3" : "#333"} strokeWidth={isHovered ? "3" : "2"}/>
              
              {/* Station label */}
              <text x={x} y={height - margin.bottom + 12} textAnchor="middle" fontSize={isHovered ? "9" : "7"} fill={isHovered ? "#1976D2" : "#666"} fontWeight={isHovered ? "600" : "500"}>
                {item.stationName.startsWith('station_') 
                  ? item.stationName.replace('station_', '')
                  : item.stationName.replace('Station ', '')
                }
              </text>
            </g>
          );
        })}
        
        {/* Y-axis ticks and labels */}
        {Array.from({ length: 6 }, (_, i) => {
          const value = yMin + (yMax - yMin) * i / 5;
          const y = height - margin.bottom - (i / 5) * (height - margin.top - margin.bottom);
          return (
            <g key={i}>
              <line x1={margin.left - 5} y1={y} x2={margin.left + 5} y2={y} stroke="#666" strokeWidth="1"/>
              <text x={margin.left - 10} y={y + 4} textAnchor="end" fontSize="12" fill="#666">
                {value.toFixed(1)}
              </text>
            </g>
          );
        })}
        
        {/* Legend - positioned at the end */}
        <g transform={`translate(${chartWidth - 220}, 60)`}>
          <text x="0" y="0" fontSize="16" fontWeight="bold" fill="#333">Legend:</text>
          
          {/* Box */}
          <rect x="15" y="20" width="25" height="20" fill="#4ECDC4" fillOpacity="0.7" stroke="#333" strokeWidth="2"/>
          <text x="50" y="35" fontSize="14" fill="#666">Q1-Q3 (IQR)</text>
          
          {/* Median line */}
          <line x1="15" y1="55" x2="40" y2="55" stroke="#333" strokeWidth="3"/>
          <text x="50" y="60" fontSize="14" fill="#666">Median</text>
          
          {/* Mean point */}
          <circle cx="27.5" cy="75" r="4" fill="#FF6B6B" stroke="#333" strokeWidth="2"/>
          <text x="50" y="80" fontSize="14" fill="#666">Mean</text>
          
          {/* Whiskers */}
          <line x1="27.5" y1="95" x2="27.5" y2="110" stroke="#333" strokeWidth="2"/>
          <line x1="20" y1="95" x2="35" y2="95" stroke="#333" strokeWidth="2"/>
          <line x1="20" y1="110" x2="35" y2="110" stroke="#333" strokeWidth="2"/>
          <text x="50" y="105" fontSize="14" fill="#666">Min/Max</text>
        </g>
      </svg>
      
      {/* Tooltip */}
      {tooltip && tooltip.data && (() => {
        const tooltipWidth = 220;
        const tooltipHeight = 250;
        const containerWidth = chartWidth;
        const containerHeight = height;
        
        // Determine if tooltip should appear on left or right of cursor
        const showOnLeft = tooltip.x + tooltipWidth + 30 > containerWidth;
        const showAbove = tooltip.y + tooltipHeight / 2 > containerHeight;
        
        let leftPos = showOnLeft ? tooltip.x - tooltipWidth - 15 : tooltip.x + 15;
        let topPos = tooltip.y;
        
        // Clamp to container bounds
        leftPos = Math.max(10, Math.min(leftPos, containerWidth - tooltipWidth - 10));
        topPos = Math.max(10, Math.min(topPos, containerHeight - 10));
        
        return (
          <div 
            className="absolute bg-white border-2 border-gray-300 p-3 rounded-lg shadow-xl pointer-events-none"
            style={{
              left: `${leftPos}px`,
              top: `${topPos}px`,
              transform: showAbove ? 'translateY(-100%)' : 'translateY(-50%)',
              zIndex: 99999,
              minWidth: '200px',
              maxWidth: '250px'
            }}
          >
          <div className="font-bold text-base mb-3 text-blue-600 border-b border-gray-200 pb-2">
            {tooltip.data.stationName?.startsWith('station_') 
              ? `Station ${tooltip.data.stationName.replace('station_', '')}`
              : tooltip.data.stationName?.replace('Station ', '') || 'Station'
            }
          </div>
          <div className="text-sm space-y-2">
            <div className="flex justify-between items-center bg-red-50 px-2 py-1 rounded">
              <span className="font-medium text-gray-700">Min:</span> 
              <span className="font-mono font-bold text-red-600">{typeof tooltip.data.min === 'number' ? tooltip.data.min.toFixed(2) : 'N/A'} min</span>
            </div>
            <div className="flex justify-between items-center bg-orange-50 px-2 py-1 rounded">
              <span className="font-medium text-gray-700">Q1:</span> 
              <span className="font-mono font-bold text-orange-600">{typeof tooltip.data.q1 === 'number' ? tooltip.data.q1.toFixed(2) : 'N/A'} min</span>
            </div>
            <div className="flex justify-between items-center bg-yellow-50 px-2 py-1 rounded">
              <span className="font-medium text-gray-700">Median:</span> 
              <span className="font-mono font-bold text-yellow-700">{typeof tooltip.data.median === 'number' ? tooltip.data.median.toFixed(2) : 'N/A'} min</span>
            </div>
            <div className="flex justify-between items-center bg-purple-50 px-2 py-1 rounded">
              <span className="font-medium text-gray-700">Mean:</span> 
              <span className="font-mono font-bold text-purple-600">{typeof tooltip.data.mean === 'number' ? tooltip.data.mean.toFixed(2) : 'N/A'} min</span>
            </div>
            <div className="flex justify-between items-center bg-blue-50 px-2 py-1 rounded">
              <span className="font-medium text-gray-700">Q3:</span> 
              <span className="font-mono font-bold text-blue-600">{typeof tooltip.data.q3 === 'number' ? tooltip.data.q3.toFixed(2) : 'N/A'} min</span>
            </div>
            <div className="flex justify-between items-center bg-green-50 px-2 py-1 rounded">
              <span className="font-medium text-gray-700">Max:</span> 
              <span className="font-mono font-bold text-green-600">{typeof tooltip.data.max === 'number' ? tooltip.data.max.toFixed(2) : 'N/A'} min</span>
            </div>
          </div>
          </div>
        );
      })()}
    </div>
  );
}