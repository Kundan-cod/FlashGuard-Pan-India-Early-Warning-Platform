import React, { useState, useMemo, useEffect } from 'react';
import { LocationRisk } from '../types';

interface HydrographModalProps {
  isOpen: boolean;
  onClose: () => void;
  location?: LocationRisk | null;
  locations: LocationRisk[];
  onSelectLocation: (loc: LocationRisk) => void;
  replayTime?: string;
  onFlyToTarget?: (target: { lat: number; lng: number; zoom?: number; pitch?: number }) => void;
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

const REGION_CORRIDORS = [
  { id: 'UK', label: '🏔️ Uttarakhand', state: 'Uttarakhand', defaultLoc: 'Devgaon', lat: 30.12, lng: 79.25, zoom: 9.5 },
  { id: 'HP', label: '⛰️ Himachal Pradesh', state: 'Himachal Pradesh', defaultLoc: 'Mandi', lat: 31.70, lng: 76.93, zoom: 9.5 },
  { id: 'SK', label: '🌲 Sikkim (Teesta)', state: 'Sikkim', defaultLoc: 'Chungthang', lat: 27.60, lng: 88.64, zoom: 9.5 },
  { id: 'KL', label: '🌴 Western Ghats', state: 'Kerala', defaultLoc: 'Meppadi', lat: 11.55, lng: 76.12, zoom: 9.5 },
];

export const HydrographModal: React.FC<HydrographModalProps> = ({
  isOpen,
  onClose,
  location,
  locations = [],
  onSelectLocation,
  replayTime = '2026-07-15 10:00 UTC',
  onFlyToTarget,
}) => {
  const [activeTab, setActiveTab] = useState<'ALL' | 'HYDRO' | 'RAIN' | 'RISK'>('ALL');
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  // Close on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  // Active location fallback
  const loc = location || locations.find(l => l.name === 'Devgaon') || locations[0] || {
    id: 'devgaon',
    name: 'Devgaon',
    district: 'Pauri Garhwal',
    state: 'Uttarakhand',
    current_rainfall_mm: 64.2,
    rainfall_accumulation_24h_mm: 142.5,
    river_level_rise_m: 2.8,
    soil_moisture_saturation: 0.94,
    flood_probability: 0.99,
    landslide_probability: 0.88,
    risk_level: 'CRITICAL',
    lead_time_hours: 3.5,
    slope_degrees: 34.2,
  };

  // Generate continuous, mathematically coherent hydrograph curves
  const seriesData: DataPoint[] = useMemo(() => {
    const baseRain = loc.current_rainfall_mm || 45;
    const baseRiver = loc.river_level_rise_m || 2.4;
    const baseSoil = (loc.soil_moisture_saturation || 0.8) * 100;
    const baseFlood = (loc.flood_probability || 0.85) * 100;
    const baseLandslide = (loc.landslide_probability || 0.7) * 100;

    const hours = [-6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 6];
    const curveMultipliers = [0.12, 0.18, 0.28, 0.5, 0.74, 0.9, 1.0, 0.95, 0.82, 0.65, 0.44, 0.22];

    let runningAcc = Math.max(10, Math.round(baseRain * 0.8));
    const points: DataPoint[] = [];

    for (let i = 0; i < hours.length; i++) {
      const mult = curveMultipliers[i];
      const h = hours[i];
      const rain = Math.round(baseRain * mult);
      runningAcc += Math.round(rain * 0.4);
      const river = +(baseRiver * (0.2 + 0.8 * mult)).toFixed(2);
      const soil = Math.min(99, Math.round(baseSoil * (0.45 + 0.55 * mult)));
      const flood = Math.min(99, Math.round(baseFlood * mult));
      const land = Math.min(99, Math.round(baseLandslide * (0.3 + 0.7 * mult)));

      let rLevel: 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL' = 'LOW';
      if (flood >= 80 || river >= 2.6) rLevel = 'CRITICAL';
      else if (flood >= 60 || river >= 1.8) rLevel = 'HIGH';
      else if (flood >= 35) rLevel = 'MODERATE';

      const timeLabel = h === 0 ? 'NOW (T+0)' : h > 0 ? `+${h}h Forecast` : `${h}h`;

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
  }, [loc]);

  if (!isOpen) return null;

  // Chart dimensions in wide SVG coordinate space
  const chartW = 1040;
  const chartH = 310;
  const padL = 50;
  const padR = 60;
  const padT = 25;
  const padB = 40;
  const plotW = chartW - padL - padR;
  const plotH = chartH - padT - padB;

  const maxRiver = 5.0; // 0 to 5.0m gauge elevation
  const maxRain = Math.max(100, ...seriesData.map(d => d.rainRate * 1.35));

  const getX = (idx: number) => padL + (idx / (seriesData.length - 1)) * plotW;
  const getYPercent = (val: number) => padT + plotH - (val / 100) * plotH;
  const getYRiver = (val: number) => padT + plotH - (val / maxRiver) * plotH;

  // SVG Paths
  const floodPath = seriesData.map((d, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getYPercent(d.floodProb)}`).join(' ');
  const landPath = seriesData.map((d, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getYPercent(d.landslideProb)}`).join(' ');
  const soilPath = seriesData.map((d, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getYPercent(d.soilSat)}`).join(' ');
  const riverPath = seriesData.map((d, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getYRiver(d.riverRise)}`).join(' ');

  // Flood area under curve
  const floodAreaPath = `${floodPath} L ${getX(seriesData.length - 1)} ${padT + plotH} L ${getX(0)} ${padT + plotH} Z`;

  const activeHover = hoveredIdx !== null ? seriesData[hoveredIdx] : seriesData.find(d => d.hourOffset === 0) || seriesData[6];

  const handleCorridorSelect = (corridor: typeof REGION_CORRIDORS[0]) => {
    const match = locations.find(l => l.state?.toLowerCase().includes(corridor.state.toLowerCase()) || l.name === corridor.defaultLoc);
    if (match && onSelectLocation) {
      onSelectLocation(match);
    }
    if (onFlyToTarget) {
      onFlyToTarget({ lat: corridor.lat, lng: corridor.lng, zoom: corridor.zoom, pitch: 35 });
    }
  };

  return (
    <div className="fg-modal-overlay hydrograph-modal-backdrop" onClick={onClose}>
      <div
        className="fg-modal-box hydrograph-modal-fullscreen"
        onClick={(e) => e.stopPropagation()}
      >
        {/* MODAL HEADER */}
        <div className="hydro-modal-header">
          <div className="hydro-header-left">
            <div className="hydro-header-icon-wrap">
              <span className="hydro-header-icon">📈</span>
              <span className="hydro-beacon-ring" />
            </div>
            <div>
              <div className="hydro-header-badge-row">
                <span className="hydro-badge-nrt">● LIVE HYDROMET TELEMETRY</span>
                <span className="hydro-badge-cwc">CWC NWIC &amp; NASA GPM</span>
                <span className={`hydro-badge-severity severity-${loc.risk_level.toLowerCase()}`}>
                  {loc.risk_level} RISK LEVEL
                </span>
              </div>
              <h2 className="hydro-modal-title">
                Multi-Hazard Predictive Hydrograph &amp; Runoff Analytics
              </h2>
              <div className="hydro-modal-sub">
                Station: <strong style={{ color: '#ffffff' }}>{loc.name}</strong> · {loc.district}, {loc.state} · Synchronized to <span style={{ color: '#38bdf8' }}>{replayTime}</span>
              </div>
            </div>
          </div>

          <div className="hydro-header-right">
            {/* Quick Corridor Selector Chips */}
            <div className="hydro-corridor-chips">
              {REGION_CORRIDORS.map(corridor => {
                const isActive = loc.state?.toLowerCase().includes(corridor.state.toLowerCase());
                return (
                  <button
                    key={corridor.id}
                    className={`hydro-corridor-btn ${isActive ? 'active' : ''}`}
                    onClick={() => handleCorridorSelect(corridor)}
                    title={`Switch to ${corridor.label}`}
                  >
                    {corridor.label}
                  </button>
                );
              })}
            </div>

            {/* Village Selector Dropdown */}
            {locations.length > 1 && (
              <select
                className="hydro-village-dropdown"
                value={String(loc.id ?? loc.name)}
                onChange={(e) => {
                  const target = locations.find(l => String(l.id ?? l.name) === e.target.value);
                  if (target) onSelectLocation(target);
                }}
              >
                {locations.map(l => (
                  <option key={String(l.id ?? l.name)} value={String(l.id ?? l.name)}>
                    {l.name} ({l.district}, {l.state})
                  </option>
                ))}
              </select>
            )}

            <button
              className="fg-modal-close hydro-modal-close-btn"
              onClick={onClose}
              title="Close Fullscreen (Esc)"
            >
              ✕
            </button>
          </div>
        </div>

        {/* TELEMETRY KPI METRICS GRID */}
        <div className="hydro-kpi-grid">
          <div className="hydro-kpi-card">
            <div className="kpi-icon-row">
              <span className="kpi-label">Precipitation Rate</span>
              <span className="kpi-icon" style={{ color: '#06b6d4' }}>🌧️</span>
            </div>
            <div className="kpi-value font-mono" style={{ color: '#06b6d4' }}>
              {loc.current_rainfall_mm} <span className="kpi-unit">mm/h</span>
            </div>
            <div className="kpi-subtext">
              24h Acc: <strong>{loc.rainfall_accumulation_24h_mm || 142} mm</strong>
            </div>
          </div>

          <div className="hydro-kpi-card">
            <div className="kpi-icon-row">
              <span className="kpi-label">River Gauge Stage</span>
              <span className="kpi-icon" style={{ color: '#f59e0b' }}>🌊</span>
            </div>
            <div className="kpi-value font-mono" style={{ color: '#f59e0b' }}>
              +{loc.river_level_rise_m ?? 2.80} <span className="kpi-unit">m</span>
            </div>
            <div className="kpi-subtext font-mono" style={{ color: (loc.river_level_rise_m ?? 2.8) >= 2.8 ? '#ef4444' : '#f59e0b' }}>
              CWC Danger: <strong>3.00 m</strong> ({(loc.river_level_rise_m ?? 2.8) >= 3.0 ? 'BREACHED' : '93% Threshold'})
            </div>
          </div>

          <div className="hydro-kpi-card">
            <div className="kpi-icon-row">
              <span className="kpi-label">Soil Saturation</span>
              <span className="kpi-icon" style={{ color: '#10b981' }}>🌱</span>
            </div>
            <div className="kpi-value font-mono" style={{ color: '#10b981' }}>
              {Math.round((loc.soil_moisture_saturation ?? 0.94) * 100)} <span className="kpi-unit">%</span>
            </div>
            <div className="kpi-subtext">
              NASA SMAP Topsoil: <strong>Saturated</strong>
            </div>
          </div>

          <div className="hydro-kpi-card">
            <div className="kpi-icon-row">
              <span className="kpi-label">Catchment Slope</span>
              <span className="kpi-icon" style={{ color: '#ec4899' }}>⛰️</span>
            </div>
            <div className="kpi-value font-mono" style={{ color: '#ec4899' }}>
              {loc.slope_degrees ?? 34.2} <span className="kpi-unit">°</span>
            </div>
            <div className="kpi-subtext">
              GSI Susceptibility: <strong>High Shear</strong>
            </div>
          </div>

          <div className="hydro-kpi-card">
            <div className="kpi-icon-row">
              <span className="kpi-label">Early-Warning Window</span>
              <span className="kpi-icon" style={{ color: '#38bdf8' }}>⏱️</span>
            </div>
            <div className="kpi-value font-mono" style={{ color: '#38bdf8' }}>
              {loc.lead_time_hours ?? 3.5} <span className="kpi-unit">hrs</span>
            </div>
            <div className="kpi-subtext">
              AI Confidence: <strong>{Math.round((loc.confidence_score ?? 0.92) * 100)}%</strong>
            </div>
          </div>

          <div className="hydro-kpi-card" style={{ borderColor: loc.risk_level === 'CRITICAL' ? 'rgba(239, 68, 68, 0.6)' : 'rgba(249, 115, 22, 0.6)' }}>
            <div className="kpi-icon-row">
              <span className="kpi-label">Combined Multi-Hazard</span>
              <span className="kpi-icon" style={{ color: '#ef4444' }}>⚠️</span>
            </div>
            <div className="kpi-value font-mono" style={{ color: loc.risk_level === 'CRITICAL' ? '#f87171' : '#fb923c' }}>
              {Math.round((loc.overall_risk ?? 0.94) * 100)} <span className="kpi-unit">%</span>
            </div>
            <div className="kpi-subtext">
              Flood: <strong>{Math.round((loc.flood_probability ?? 0.95) * 100)}%</strong> · Landslide: <strong>{Math.round((loc.landslide_probability ?? 0.8) * 100)}%</strong>
            </div>
          </div>
        </div>

        {/* FILTER TABS & CHART CONTROLS */}
        <div className="hydro-chart-toolbar">
          <div className="hydro-filter-group">
            {[
              { key: 'ALL', label: '✨ All Telemetry Signals', color: '#38bdf8' },
              { key: 'HYDRO', label: '🌊 River Stage (+m)', color: '#f59e0b' },
              { key: 'RAIN', label: '🌧️ Precipitation (mm/h)', color: '#06b6d4' },
              { key: 'RISK', label: '⚡ Flood & Landslide Risk (%)', color: '#ef4444' },
            ].map(btn => (
              <button
                key={btn.key}
                className={`hydro-tab-pill ${activeTab === btn.key ? 'active' : ''}`}
                onClick={() => setActiveTab(btn.key as any)}
                style={{
                  color: activeTab === btn.key ? btn.color : '#94a3b8',
                  borderColor: activeTab === btn.key ? btn.color : 'rgba(255, 255, 255, 0.1)',
                  background: activeTab === btn.key ? `${btn.color}22` : 'rgba(15, 23, 42, 0.6)',
                }}
              >
                {btn.label}
              </button>
            ))}
          </div>

          <div className="hydro-legend-items">
            <span className="legend-chip"><span className="legend-dot" style={{ background: '#ef4444' }} /> Flood Prob</span>
            <span className="legend-chip"><span className="legend-dot" style={{ background: '#ec4899' }} /> Landslide Prob</span>
            <span className="legend-chip"><span className="legend-dot" style={{ background: '#f59e0b' }} /> River Stage (+m)</span>
            <span className="legend-chip"><span className="legend-dot" style={{ background: '#10b981' }} /> Soil Saturation (%)</span>
            <span className="legend-chip"><span className="legend-box" style={{ background: '#06b6d4' }} /> Rainfall (mm/h)</span>
            <span className="legend-chip"><span className="legend-line-danger" /> CWC Danger (+3.0m)</span>
          </div>
        </div>

        {/* EXPANSIVE INTERACTIVE SVG HYDROGRAPH */}
        <div className="hydro-chart-container">
          <svg
            viewBox={`0 0 ${chartW} ${chartH}`}
            className="hydro-main-svg"
            onMouseLeave={() => setHoveredIdx(null)}
          >
            <defs>
              {/* Risk Gradient */}
              <linearGradient id="hydroRiskGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#ef4444" stopOpacity="0.45" />
                <stop offset="50%" stopColor="#f59e0b" stopOpacity="0.2" />
                <stop offset="100%" stopColor="#10b981" stopOpacity="0.01" />
              </linearGradient>

              {/* Rain Bar Gradient */}
              <linearGradient id="hydroRainGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.85" />
                <stop offset="100%" stopColor="#0284c7" stopOpacity="0.3" />
              </linearGradient>

              {/* Glow filters */}
              <filter id="hydroGlow" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="3" result="glow" />
                <feComposite in="SourceGraphic" in2="glow" operator="over" />
              </filter>
            </defs>

            {/* Plot Background */}
            <rect x={padL} y={padT} width={plotW} height={plotH} fill="rgba(8, 16, 32, 0.6)" rx="6" />

            {/* Forecast Window Shading */}
            <rect
              x={getX(6)}
              y={padT}
              width={plotW - (getX(6) - padL)}
              height={plotH}
              fill="rgba(56, 189, 248, 0.06)"
            />
            <text
              x={getX(6) + 10}
              y={padT + 18}
              fill="#38bdf8"
              fontSize="11"
              fontWeight="800"
              letterSpacing="0.6px"
              opacity="0.9"
            >
              PREDICTIVE LEAD-TIME FORECAST WINDOW ➔
            </text>

            {/* Horizontal Grid Lines and Left Y-Axis (% Probability / Saturation) */}
            {[0, 25, 50, 75, 100].map(val => (
              <g key={val}>
                <line
                  x1={padL}
                  y1={getYPercent(val)}
                  x2={chartW - padR}
                  y2={getYPercent(val)}
                  stroke="rgba(255, 255, 255, 0.08)"
                  strokeDasharray={val === 50 || val === 80 ? '4 4' : undefined}
                />
                <text
                  x={padL - 8}
                  y={getYPercent(val) + 4}
                  fill="#94a3b8"
                  fontSize="10"
                  fontFamily="monospace"
                  textAnchor="end"
                >
                  {val}%
                </text>
              </g>
            ))}

            {/* Right Y-Axis: River Stage Elevation (+m) */}
            {[1, 2, 3, 4, 5].map(m => (
              <g key={m}>
                <text
                  x={chartW - padR + 8}
                  y={getYRiver(m) + 4}
                  fill="#f59e0b"
                  fontSize="10.5"
                  fontWeight="700"
                  fontFamily="monospace"
                  textAnchor="start"
                >
                  +{m}.0m
                </text>
              </g>
            ))}

            {/* CWC Danger Mark Threshold (+3.0m) */}
            {(activeTab === 'ALL' || activeTab === 'HYDRO') && (
              <g>
                <line
                  x1={padL}
                  y1={getYRiver(3.0)}
                  x2={chartW - padR}
                  y2={getYRiver(3.0)}
                  stroke="#ef4444"
                  strokeWidth="1.8"
                  strokeDasharray="6 4"
                />
                <rect
                  x={chartW - padR - 195}
                  y={getYRiver(3.0) - 16}
                  width="190"
                  height="16"
                  fill="rgba(239, 68, 68, 0.25)"
                  stroke="#ef4444"
                  strokeWidth="1"
                  rx="3"
                />
                <text
                  x={chartW - padR - 8}
                  y={getYRiver(3.0) - 4}
                  fill="#f87171"
                  fontSize="9.5"
                  fontWeight="900"
                  textAnchor="end"
                  letterSpacing="0.4px"
                >
                  ⚠ CWC DANGER LEVEL (+3.0m)
                </text>
              </g>
            )}

            {/* Rainfall Intensity Bars */}
            {(activeTab === 'ALL' || activeTab === 'RAIN') && (
              seriesData.map((d, i) => {
                const barW = 16;
                const x = getX(i) - barW / 2;
                const barH = (d.rainRate / maxRain) * plotH;
                const y = padT + plotH - barH;
                return (
                  <rect
                    key={i}
                    x={x}
                    y={y}
                    width={barW}
                    height={barH}
                    fill="url(#hydroRainGrad)"
                    rx="3"
                    opacity="0.85"
                  />
                );
              })
            )}

            {/* Flood Risk Area Fill */}
            {(activeTab === 'ALL' || activeTab === 'RISK') && (
              <path
                d={floodAreaPath}
                fill="url(#hydroRiskGrad)"
              />
            )}

            {/* Soil Moisture Curve (Emerald Green Dotted) */}
            {(activeTab === 'ALL') && (
              <path
                d={soilPath}
                fill="none"
                stroke="#10b981"
                strokeWidth="2.2"
                strokeDasharray="4 3"
                opacity="0.85"
              />
            )}

            {/* River Level Rise Curve (Amber) */}
            {(activeTab === 'ALL' || activeTab === 'HYDRO') && (
              <path
                d={riverPath}
                fill="none"
                stroke="#f59e0b"
                strokeWidth="2.8"
                strokeLinecap="round"
                filter="url(#hydroGlow)"
              />
            )}

            {/* Landslide Probability Curve (Pink/Magenta) */}
            {(activeTab === 'ALL' || activeTab === 'RISK') && (
              <path
                d={landPath}
                fill="none"
                stroke="#ec4899"
                strokeWidth="2.6"
                strokeDasharray="5 3"
                strokeLinecap="round"
              />
            )}

            {/* Flash Flood Probability Curve (Bold Crimson) */}
            {(activeTab === 'ALL' || activeTab === 'RISK') && (
              <path
                d={floodPath}
                fill="none"
                stroke="#ef4444"
                strokeWidth="3.2"
                strokeLinecap="round"
                filter="url(#hydroGlow)"
              />
            )}

            {/* Interactive Data Points & Hit Targets */}
            {seriesData.map((d, i) => {
              const isT0 = d.hourOffset === 0;
              const isHover = hoveredIdx === i;
              return (
                <g
                  key={i}
                  style={{ cursor: 'pointer' }}
                  onMouseEnter={() => setHoveredIdx(i)}
                >
                  <rect
                    x={getX(i) - 20}
                    y={padT}
                    width="40"
                    height={plotH}
                    fill="transparent"
                  />

                  {/* Flood Point */}
                  {(activeTab === 'ALL' || activeTab === 'RISK') && (
                    <circle
                      cx={getX(i)}
                      cy={getYPercent(d.floodProb)}
                      r={isHover || isT0 ? 6 : 4}
                      fill={d.riskLevel === 'CRITICAL' ? '#ef4444' : d.riskLevel === 'HIGH' ? '#f97316' : '#38bdf8'}
                      stroke="#ffffff"
                      strokeWidth={isHover || isT0 ? 2.5 : 1.2}
                    />
                  )}

                  {/* River Point */}
                  {(activeTab === 'ALL' || activeTab === 'HYDRO') && (
                    <circle
                      cx={getX(i)}
                      cy={getYRiver(d.riverRise)}
                      r={isHover ? 5.5 : 3.5}
                      fill="#f59e0b"
                      stroke="#ffffff"
                      strokeWidth="1.5"
                    />
                  )}
                </g>
              );
            })}

            {/* Vertical Cursor Scrubber */}
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
                    strokeWidth="2"
                    strokeDasharray="3 3"
                  />
                  <circle cx={x} cy={padT + 4} r="4" fill="#38bdf8" />
                  <circle cx={x} cy={padT + plotH - 4} r="4" fill="#38bdf8" />
                </g>
              );
            })()}

            {/* X-Axis Timestep Labels */}
            {seriesData.map((d, i) => (
              <text
                key={i}
                x={getX(i)}
                y={chartH - 12}
                fill={d.hourOffset === 0 ? '#38bdf8' : hoveredIdx === i ? '#ffffff' : '#64748b'}
                fontSize={d.hourOffset === 0 ? '11' : '10'}
                fontWeight={d.hourOffset === 0 ? '800' : '600'}
                fontFamily="monospace"
                textAnchor="middle"
              >
                {d.timeStr}
              </text>
            ))}
          </svg>
        </div>

        {/* INTERACTIVE CROSSHAIR READOUT STRIP */}
        <div className="hydro-readout-strip">
          <div className="readout-item">
            <span className="readout-title">TIMESTEP</span>
            <span className="readout-val font-mono" style={{ color: '#38bdf8' }}>
              {activeHover.timeStr}
            </span>
          </div>

          <div className="readout-item">
            <span className="readout-title">RAINFALL INTENSITY</span>
            <span className="readout-val font-mono" style={{ color: '#06b6d4' }}>
              {activeHover.rainRate} mm/h
            </span>
          </div>

          <div className="readout-item">
            <span className="readout-title">RIVER STAGE SURGE</span>
            <span className="readout-val font-mono" style={{ color: '#f59e0b' }}>
              +{activeHover.riverRise} m
            </span>
          </div>

          <div className="readout-item">
            <span className="readout-title">SOIL SATURATION</span>
            <span className="readout-val font-mono" style={{ color: '#10b981' }}>
              {activeHover.soilSat}%
            </span>
          </div>

          <div className="readout-item">
            <span className="readout-title">FLASH FLOOD PROB</span>
            <span className="readout-val font-mono" style={{ color: activeHover.riskLevel === 'CRITICAL' ? '#ef4444' : '#fb923c' }}>
              {activeHover.floodProb}%
            </span>
          </div>

          <div className="readout-item">
            <span className="readout-title">LANDSLIDE PROB</span>
            <span className="readout-val font-mono" style={{ color: '#ec4899' }}>
              {activeHover.landslideProb}%
            </span>
          </div>

          <div className="readout-item">
            <span className="readout-title">OVERALL SEVERITY</span>
            <span className={`readout-badge badge-${activeHover.riskLevel.toLowerCase()}`}>
              {activeHover.riskLevel}
            </span>
          </div>
        </div>

        {/* DECISION SUPPORT & ACTION PROTOCOL FOOTER */}
        <div className="hydro-footer-protocol">
          <div className="protocol-col">
            <div className="protocol-heading">
              <span>🚨 NDRF TACTICAL ACTION DIRECTIVE</span>
            </div>
            <div className="protocol-text">
              {loc.risk_level === 'CRITICAL'
                ? 'Issue immediate Level-3 Flash Flood Warning. Pre-position 8th Bn NDRF Quick Response Teams with inflatable boats in low-lying riverine pockets.'
                : loc.risk_level === 'HIGH'
                ? 'Level-2 Preparedness Alert: Notify District Emergency Operations Center (DEOC) and inspect culverts and bridge embankments.'
                : 'Routine Hydrometeorological Vigilance: Continuous telemetry monitoring active.'}
            </div>
          </div>

          <div className="protocol-col">
            <div className="protocol-heading">
              <span>📡 CAP / SACHET DISSEMINATION</span>
            </div>
            <div className="protocol-text">
              Common Alerting Protocol broadcast active. Geofenced SMS alerts staged for mobile subscribers within {loc.district} mountainous catchment.
            </div>
          </div>

          <div className="protocol-actions">
            <button
              className="fg-btn fg-btn-primary hydro-action-btn"
              onClick={onClose}
            >
              Return to Map
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
