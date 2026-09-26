import React, { useState, useMemo } from 'react';
import { LocationRisk } from '../types';

interface TimeSeriesVisualizerProps {
  location?: LocationRisk | null;
  locations?: LocationRisk[];
  onSelectLocation?: (loc: LocationRisk) => void;
  replayTime?: string;
  onClose?: () => void;
}

interface DataPoint {
  timeStr: string;
  hourOffset: number;
  rainRate: number; // mm/h
  rainAcc: number;  // mm 24h
  riverRise: number; // +m
  soilSat: number;  // 0-100%
  floodProb: number; // 0-100%
  landslideProb: number; // 0-100%
  riskLevel: 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL';
}

export const TimeSeriesVisualizer: React.FC<TimeSeriesVisualizerProps> = ({
  location,
  locations = [],
  onSelectLocation,
  replayTime = '2026-07-15 10:00:00',
  onClose,
}) => {
  const [activeTab, setActiveTab] = useState<'ALL' | 'RAIN' | 'HYDRO' | 'RISK'>('ALL');
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  // Fallback to active location or first available
  const loc = location || locations[0] || {
    name: 'Devgaon',
    district: 'Garhwal',
    state: 'Uttarakhand',
    current_rainfall_mm: 52,
    rainfall_accumulation_24h_mm: 145,
    river_level_rise_m: 2.8,
    soil_moisture_saturation: 0.88,
    flood_probability: 0.87,
    landslide_probability: 0.74,
    risk_level: 'CRITICAL',
    lead_time_hours: 1.5,
  };

  // Generate realistic 12-hour progressive time-series tailored to the location's current telemetry
  const seriesData: DataPoint[] = useMemo(() => {
    const baseRain = loc.current_rainfall_mm || 40;
    const baseRiver = loc.river_level_rise_m || 2.2;
    const baseSoil = (loc.soil_moisture_saturation || 0.75) * 100;
    const baseFlood = (loc.flood_probability || 0.7) * 100;
    const baseLandslide = (loc.landslide_probability || 0.6) * 100;

    const points: DataPoint[] = [];
    const hours = [-6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 6];
    
    // Relative progression multipliers from quiet baseline to storm peak and projected recession
    const curveMultipliers = [0.12, 0.18, 0.28, 0.48, 0.72, 0.88, 1.0, 0.95, 0.82, 0.65, 0.45, 0.25];

    let runningAcc = 15;

    for (let i = 0; i < hours.length; i++) {
      const mult = curveMultipliers[i];
      const h = hours[i];
      const rain = Math.round(baseRain * mult);
      runningAcc += Math.round(rain * 0.5);
      const river = +(baseRiver * (0.2 + 0.8 * mult)).toFixed(2);
      const soil = Math.min(99, Math.round(baseSoil * (0.5 + 0.5 * mult)));
      const flood = Math.min(99, Math.round(baseFlood * mult));
      const land = Math.min(99, Math.round(baseLandslide * (0.3 + 0.7 * mult)));

      let rLevel: 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL' = 'LOW';
      if (flood >= 80 || land >= 80) rLevel = 'CRITICAL';
      else if (flood >= 60 || land >= 60) rLevel = 'HIGH';
      else if (flood >= 35 || land >= 35) rLevel = 'MODERATE';

      const timeLabel = h === 0 ? 'NOW (T+0)' : h > 0 ? `+${h}h Lead` : `${h}h`;

      points.push({
        timeStr: timeLabel,
        hourOffset: h,
        rainRate: rain,
        rainAcc: runningAcc,
        riverRise: river,
        soilSat: soil,
        floodProb: flood,
        landslideProb: land,
        riskLevel: rLevel,
      });
    }
    return points;
  }, [loc.name, loc.current_rainfall_mm, loc.river_level_rise_m, loc.soil_moisture_saturation]);

  // Chart dimensions & scaling
  const chartW = 540;
  const chartH = 200;
  const padL = 40;
  const padR = 40;
  const padT = 20;
  const padB = 30;
  const plotW = chartW - padL - padR;
  const plotH = chartH - padT - padB;

  const maxRain = Math.max(100, ...seriesData.map(d => d.rainRate * 1.3));
  const maxRiver = 5.0; // 0 to 5m

  const getX = (idx: number) => padL + (idx / (seriesData.length - 1)) * plotW;
  const getYPercent = (val: number) => padT + plotH - (val / 100) * plotH;
  const getYRiver = (val: number) => padT + plotH - (val / maxRiver) * plotH;

  // Build SVG path strings
  const floodPath = seriesData.map((d, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getYPercent(d.floodProb)}`).join(' ');
  const landPath = seriesData.map((d, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getYPercent(d.landslideProb)}`).join(' ');
  const soilPath = seriesData.map((d, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getYPercent(d.soilSat)}`).join(' ');
  const riverPath = seriesData.map((d, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getYRiver(d.riverRise)}`).join(' ');

  const activeHover = hoveredIdx !== null ? seriesData[hoveredIdx] : seriesData.find(d => d.hourOffset === 0) || seriesData[6];

  return (
    <div style={{
      background: 'linear-gradient(180deg, rgba(8, 18, 36, 0.96) 0%, rgba(4, 9, 20, 0.98) 100%)',
      border: '1px solid rgba(56, 189, 248, 0.35)',
      borderRadius: '10px',
      padding: '14px 16px',
      color: '#f8fafc',
      fontFamily: 'Inter, system-ui, sans-serif',
      boxShadow: '0 8px 32px rgba(0, 0, 0, 0.6)',
      position: 'relative',
    }}>
      {/* Header with Title and Region selector */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '15px' }}>📈</span>
            <span style={{ fontSize: '13px', fontWeight: 800, letterSpacing: '0.5px', color: '#38bdf8' }}>
              MULTI-HAZARD TIME-SERIES & HYDROGRAPH
            </span>
            <span style={{
              fontSize: '10px',
              padding: '2px 8px',
              borderRadius: '4px',
              background: activeHover.riskLevel === 'CRITICAL' ? 'rgba(239, 68, 68, 0.25)' : 'rgba(245, 158, 11, 0.25)',
              color: activeHover.riskLevel === 'CRITICAL' ? '#f87171' : '#fbbf24',
              border: `1px solid ${activeHover.riskLevel === 'CRITICAL' ? '#ef4444' : '#f59e0b'}`,
              fontWeight: 800,
            }}>
              {activeHover.riskLevel} PEAK
            </span>
          </div>
          <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>{loc.name} · {loc.district}, {loc.state} · Telemetry ({replayTime})</span>
            {locations.length > 1 && onSelectLocation && (
              <select
                value={String(loc.id ?? loc.name)}
                onChange={(e) => {
                  const found = locations.find(l => String(l.id ?? l.name) === e.target.value);
                  if (found) onSelectLocation(found);
                }}
                style={{
                  background: 'rgba(15, 23, 42, 0.8)',
                  border: '1px solid rgba(56, 189, 248, 0.3)',
                  color: '#38bdf8',
                  fontSize: '10px',
                  borderRadius: '3px',
                  padding: '1px 4px',
                  cursor: 'pointer',
                }}
              >
                {locations.map(l => (
                  <option key={String(l.id ?? l.name)} value={String(l.id ?? l.name)}>
                    {l.name} ({l.district})
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>

        {onClose && (
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#94a3b8',
              cursor: 'pointer',
              fontSize: '18px',
              padding: '2px 6px',
            }}
          >
            ✕
          </button>
        )}
      </div>

      {/* Layer Filter Pills */}
      <div style={{ display: 'flex', gap: '6px', marginBottom: '10px', flexWrap: 'wrap' }}>
        {[
          { key: 'ALL', label: 'All Telemetry', color: '#38bdf8' },
          { key: 'RISK', label: 'Flood & Landslide Risk (%)', color: '#ef4444' },
          { key: 'HYDRO', label: 'River Stage (+m)', color: '#f59e0b' },
          { key: 'RAIN', label: 'Rainfall Intensity (mm/h)', color: '#06b6d4' },
        ].map(btn => (
          <button
            key={btn.key}
            onClick={() => setActiveTab(btn.key as any)}
            style={{
              background: activeTab === btn.key ? `${btn.color}22` : 'rgba(15, 23, 42, 0.6)',
              border: `1px solid ${activeTab === btn.key ? btn.color : 'rgba(255, 255, 255, 0.1)'}`,
              color: activeTab === btn.key ? btn.color : '#94a3b8',
              fontSize: '10.5px',
              fontWeight: 700,
              padding: '3px 9px',
              borderRadius: '5px',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            {btn.label}
          </button>
        ))}
      </div>

      {/* Main SVG Plot */}
      <div style={{ position: 'relative', width: '100%', overflowX: 'auto' }}>
        <svg
          viewBox={`0 0 ${chartW} ${chartH}`}
          style={{ width: '100%', height: 'auto', display: 'block' }}
          onMouseLeave={() => setHoveredIdx(null)}
        >
          <defs>
            {/* Grid & Fills */}
            <linearGradient id="riskGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ef4444" stopOpacity="0.4" />
              <stop offset="60%" stopColor="#f59e0b" stopOpacity="0.2" />
              <stop offset="100%" stopColor="#10b981" stopOpacity="0.02" />
            </linearGradient>
            <linearGradient id="rainBarGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.8" />
              <stop offset="100%" stopColor="#0284c7" stopOpacity="0.3" />
            </linearGradient>
          </defs>

          {/* Background & T+0 Forecast Boundary */}
          <rect x={padL} y={padT} width={plotW} height={plotH} fill="rgba(15, 23, 42, 0.45)" />
          {/* Lead-Time Forecast Area shading */}
          <rect
            x={getX(6)}
            y={padT}
            width={plotW - (getX(6) - padL)}
            height={plotH}
            fill="rgba(56, 189, 248, 0.05)"
          />
          <text
            x={getX(6) + 6}
            y={padT + 12}
            fill="#38bdf8"
            fontSize="9"
            fontWeight="700"
            opacity="0.85"
          >
            FORECAST WINDOW →
          </text>

          {/* Horizontal Grid lines */}
          {[0, 25, 50, 75, 100].map(val => (
            <g key={val}>
              <line
                x1={padL}
                y1={getYPercent(val)}
                x2={chartW - padR}
                y2={getYPercent(val)}
                stroke="rgba(255, 255, 255, 0.08)"
                strokeDasharray={val === 50 || val === 80 ? '3 3' : undefined}
              />
              <text
                x={padL - 6}
                y={getYPercent(val) + 3}
                fill="#64748b"
                fontSize="8.5"
                textAnchor="end"
              >
                {val}%
              </text>
            </g>
          ))}

          {/* Right Y-Axis: River Stage (+m) */}
          {[1, 2, 3, 4].map(m => (
            <text
              key={m}
              x={chartW - padR + 6}
              y={getYRiver(m) + 3}
              fill="#f59e0b"
              fontSize="8.5"
              textAnchor="start"
            >
              +{m}m
            </text>
          ))}

          {/* CWC Danger Level Reference Line (+3.0m) */}
          {(activeTab === 'ALL' || activeTab === 'HYDRO') && (
            <g>
              <line
                x1={padL}
                y1={getYRiver(3.0)}
                x2={chartW - padR}
                y2={getYRiver(3.0)}
                stroke="#ef4444"
                strokeWidth="1.2"
                strokeDasharray="4 3"
              />
              <text
                x={chartW - padR - 4}
                y={getYRiver(3.0) - 3}
                fill="#ef4444"
                fontSize="8"
                fontWeight="800"
                textAnchor="end"
              >
                CWC DANGER MARK (+3.0m)
              </text>
            </g>
          )}

          {/* Rainfall Intensity Bars */}
          {(activeTab === 'ALL' || activeTab === 'RAIN') && (
            seriesData.map((d, i) => {
              const x = getX(i) - 6;
              const barH = (d.rainRate / maxRain) * plotH;
              const y = padT + plotH - barH;
              return (
                <rect
                  key={i}
                  x={x}
                  y={y}
                  width="12"
                  height={barH}
                  fill="url(#rainBarGrad)"
                  rx="2"
                  opacity="0.85"
                />
              );
            })
          )}

          {/* Soil Moisture Curve (Green Area) */}
          {(activeTab === 'ALL') && (
            <path
              d={soilPath}
              fill="none"
              stroke="#10b981"
              strokeWidth="1.8"
              strokeDasharray="2 2"
              opacity="0.8"
            />
          )}

          {/* River Level Curve (Amber) */}
          {(activeTab === 'ALL' || activeTab === 'HYDRO') && (
            <path
              d={riverPath}
              fill="none"
              stroke="#f59e0b"
              strokeWidth="2.2"
              strokeLinecap="round"
            />
          )}

          {/* Landslide Risk Curve (Purple/Orange) */}
          {(activeTab === 'ALL' || activeTab === 'RISK') && (
            <path
              d={landPath}
              fill="none"
              stroke="#ec4899"
              strokeWidth="2.2"
              strokeDasharray="3 2"
            />
          )}

          {/* Flash Flood Risk Curve (Bold Red) */}
          {(activeTab === 'ALL' || activeTab === 'RISK') && (
            <path
              d={floodPath}
              fill="none"
              stroke="#ef4444"
              strokeWidth="2.8"
              strokeLinecap="round"
            />
          )}

          {/* Data Points on Curves */}
          {seriesData.map((d, i) => {
            const isT0 = d.hourOffset === 0;
            const isHover = hoveredIdx === i;
            return (
              <g
                key={i}
                style={{ cursor: 'pointer' }}
                onMouseEnter={() => setHoveredIdx(i)}
              >
                {/* Hit zone */}
                <rect
                  x={getX(i) - 15}
                  y={padT}
                  width="30"
                  height={plotH}
                  fill="transparent"
                />

                {/* Flood Risk Point */}
                {(activeTab === 'ALL' || activeTab === 'RISK') && (
                  <circle
                    cx={getX(i)}
                    cy={getYPercent(d.floodProb)}
                    r={isHover || isT0 ? 5 : 3}
                    fill={d.riskLevel === 'CRITICAL' ? '#ef4444' : d.riskLevel === 'HIGH' ? '#f97316' : '#38bdf8'}
                    stroke="#ffffff"
                    strokeWidth={isHover || isT0 ? 2 : 1}
                  />
                )}

                {/* River Rise Point */}
                {(activeTab === 'ALL' || activeTab === 'HYDRO') && (
                  <circle
                    cx={getX(i)}
                    cy={getYRiver(d.riverRise)}
                    r={isHover ? 4.5 : 2.8}
                    fill="#f59e0b"
                    stroke="#ffffff"
                    strokeWidth="1"
                  />
                )}
              </g>
            );
          })}

          {/* Vertical Time Scrubber Line on Active/Hovered Point */}
          {(() => {
            const targetIdx = hoveredIdx !== null ? hoveredIdx : 6;
            const x = getX(targetIdx);
            return (
              <g pointerEvents="none">
                <line
                  x1={x}
                  y1={padT}
                  x2={x}
                  y2={padT + plotH}
                  stroke="#38bdf8"
                  strokeWidth="1.5"
                  strokeDasharray="2 2"
                />
                <circle cx={x} cy={padT} r="3" fill="#38bdf8" />
              </g>
            );
          })()}

          {/* X-Axis Labels */}
          {seriesData.map((d, i) => (
            <text
              key={i}
              x={getX(i)}
              y={chartH - 8}
              fill={d.hourOffset === 0 ? '#38bdf8' : hoveredIdx === i ? '#ffffff' : '#64748b'}
              fontSize={d.hourOffset === 0 ? '9.5' : '8.5'}
              fontWeight={d.hourOffset === 0 ? '800' : '500'}
              textAnchor="middle"
            >
              {d.timeStr}
            </text>
          ))}
        </svg>
      </div>

      {/* Interactive Telemetry Inspector Strip */}
      <div style={{
        marginTop: '10px',
        padding: '8px 12px',
        background: 'rgba(15, 23, 42, 0.75)',
        border: '1px solid rgba(56, 189, 248, 0.2)',
        borderRadius: '6px',
        display: 'grid',
        gridTemplateColumns: 'repeat(5, 1fr)',
        gap: '8px',
        textAlign: 'center',
      }}>
        <div>
          <div style={{ fontSize: '9px', color: '#94a3b8' }}>TIMESTEP</div>
          <div style={{ fontSize: '11px', fontWeight: 800, color: '#38bdf8', marginTop: '1px' }}>
            {activeHover.timeStr}
          </div>
        </div>

        <div>
          <div style={{ fontSize: '9px', color: '#94a3b8' }}>RAIN RATE</div>
          <div style={{ fontSize: '11px', fontWeight: 800, color: '#06b6d4', marginTop: '1px' }}>
            {activeHover.rainRate} mm/h
          </div>
        </div>

        <div>
          <div style={{ fontSize: '9px', color: '#94a3b8' }}>RIVER SURGE</div>
          <div style={{ fontSize: '11px', fontWeight: 800, color: '#f59e0b', marginTop: '1px' }}>
            +{activeHover.riverRise} m
          </div>
        </div>

        <div>
          <div style={{ fontSize: '9px', color: '#94a3b8' }}>SOIL SATURATION</div>
          <div style={{ fontSize: '11px', fontWeight: 800, color: '#10b981', marginTop: '1px' }}>
            {activeHover.soilSat}%
          </div>
        </div>

        <div>
          <div style={{ fontSize: '9px', color: '#94a3b8' }}>FLOOD / LANDSLIDE</div>
          <div style={{ fontSize: '11px', fontWeight: 900, color: activeHover.riskLevel === 'CRITICAL' ? '#f87171' : '#fb923c', marginTop: '1px' }}>
            {activeHover.floodProb}% / {activeHover.landslideProb}%
          </div>
        </div>
      </div>

      {/* Legend Footnote */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginTop: '8px',
        fontSize: '9px',
        color: '#64748b',
        padding: '0 4px',
      }}>
        <div style={{ display: 'flex', gap: '12px' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '8px', height: '8px', background: '#ef4444', borderRadius: '50%' }} /> Flood Prob
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '8px', height: '8px', background: '#ec4899', borderRadius: '50%' }} /> Landslide Prob
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '8px', height: '8px', background: '#f59e0b', borderRadius: '50%' }} /> River Surge (+m)
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <span style={{ width: '8px', height: '8px', background: '#38bdf8', borderRadius: '2px' }} /> Rainfall
          </span>
        </div>
        <div>Hover cursor scrubs timeline · Projections show estimated risk windows</div>
      </div>
    </div>
  );
};
