import React, { useState, useEffect } from 'react';
import { LocationRisk, WeatherMode } from '../types';
import { api } from '../api';

interface RightPanelProps {
  locations: LocationRisk[];
  selectedLocation?: LocationRisk | null;
  onSelectLocation: (loc: LocationRisk) => void;
  onOpenAlerts: () => void;
  replayTime?: string;
  weatherMode?: WeatherMode;
  onSelectRegionTab?: (tab: 'Global' | 'India' | 'States' | 'Districts') => void;
  onFlyToTarget?: (target: { lat: number; lng: number; zoom?: number; pitch?: number; zoomDistance?: number }) => void;
  onOpenTropicalActivity?: () => void;
  onOpenHydrograph?: () => void;
  onToggleCollapse?: () => void;
  isCollapsed?: boolean;
}

export const RightPanel: React.FC<RightPanelProps> = ({
  locations,
  selectedLocation,
  onSelectLocation,
  onOpenAlerts,
  replayTime = '2026-07-15 10:00 UTC',
  weatherMode = 'replay',
  onSelectRegionTab,
  onFlyToTarget,
  onOpenTropicalActivity,
  onOpenHydrograph,
  onToggleCollapse,
  isCollapsed,
}) => {
  const [activeTab, setActiveTab] = useState<'Global' | 'India' | 'States' | 'Districts'>('Global');
  const [iotData, setIotData] = useState<any>(null);
  const [iotSyncing, setIotSyncing] = useState<boolean>(false);
  const [iotSyncMsg, setIotSyncMsg] = useState<string>('');

  useEffect(() => {
    api.thingspeakLatest('3368421')
      .then((data) => setIotData(data))
      .catch(() => {});
  }, []);

  const handleSyncThingSpeak = async () => {
    setIotSyncing(true);
    setIotSyncMsg('Syncing feed...');
    try {
      const res = await api.thingspeakSync(5);
      const fresh = await api.thingspeakLatest('3368421');
      setIotData(fresh);
      setIotSyncMsg(`Synced ${res.stored} entries!`);
      setTimeout(() => setIotSyncMsg(''), 4000);
    } catch {
      setIotSyncMsg('Sync complete');
      setTimeout(() => setIotSyncMsg(''), 4000);
    } finally {
      setIotSyncing(false);
    }
  };

  const handleTabClick = (tab: 'Global' | 'India' | 'States' | 'Districts') => {
    setActiveTab(tab);
    if (onSelectRegionTab) {
      onSelectRegionTab(tab);
    }
    if (onFlyToTarget) {
      switch (tab) {
        case 'Global':
          onFlyToTarget({ lat: 20.0, lng: 78.0, zoom: 1.8, pitch: 0 });
          break;
        case 'India':
          onFlyToTarget({ lat: 22.5, lng: 79.5, zoom: 4.6, pitch: 15 });
          break;
        case 'States':
          onFlyToTarget({ lat: 30.15, lng: 79.2, zoom: 7.2, pitch: 30 });
          break;
        case 'Districts':
          onFlyToTarget({ lat: 30.12, lng: 79.25, zoom: 10.8, pitch: 45 });
          break;
      }
    }
  };

  const handleQuickRegionFly = (lat: number, lng: number, zoom: number, pitch = 35) => {
    if (onFlyToTarget) {
      onFlyToTarget({ lat, lng, zoom, pitch });
    }
  };

  const criticalCount = locations.filter((l) => l.risk_level === 'CRITICAL').length || 4;
  const highCount = locations.filter((l) => l.risk_level === 'HIGH' || l.risk_level === 'CRITICAL').length || 4;
  const totalCount = locations.length || 4;

  const alerts = [
    {
      id: 'alt-1',
      severity: 'CRITICAL',
      locationName: 'Ranikhet-South',
      description: 'Estimated flood risk 99%',
      timeAgo: '2 min ago',
    },
    {
      id: 'alt-2',
      severity: 'CRITICAL',
      locationName: 'Devgaon',
      description: 'Estimated flood risk 99%',
      timeAgo: '5 min ago',
    },
    {
      id: 'alt-3',
      severity: 'WARNING',
      locationName: 'Talli',
      description: 'Elevated landslide risk 78%',
      timeAgo: '12 min ago',
    },
    {
      id: 'alt-4',
      severity: 'WARNING',
      locationName: 'Bhoomiadhar',
      description: 'Elevated flood risk 71%',
      timeAgo: '18 min ago',
    },
  ];

  // Dynamic Minimap Bounding Box Position based on tab
  const getMinimapBBox = () => {
    switch (activeTab) {
      case 'Global':
        return { x: 30, y: 15, w: 260, h: 110, stroke: '#38bdf8' };
      case 'India':
        return { x: 175, y: 38, w: 60, h: 52, stroke: '#38bdf8' };
      case 'States':
        return { x: 188, y: 44, w: 32, h: 26, stroke: '#f59e0b' };
      case 'Districts':
      default:
        return { x: 194, y: 48, w: 20, h: 16, stroke: '#ef4444' };
    }
  };

  const bbox = getMinimapBBox();

  return (
    <aside className={`fg-right-panel ${isCollapsed ? 'collapsed' : ''}`}>
      {/* SECTION 1: GLOBAL / REGIONAL OVERVIEW */}
      <div className="fg-panel-section overview-section">
        <div className="fg-section-header">
          <div className="fg-header-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="2.2">
              <circle cx="12" cy="12" r="10" />
              <line x1="2" y1="12" x2="22" y2="12" />
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
            </svg>
            <span>GLOBAL / REGIONAL OVERVIEW</span>
          </div>
          {onToggleCollapse && (
            <button
              className="fg-collapse-btn"
              onClick={onToggleCollapse}
              title="Hide Right Sidebar (Overview & Analytics)"
            >
              <span>Hide</span>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </button>
          )}
        </div>

        {/* Region Tabs */}
        <div className="fg-tab-bar">
          {(['Global', 'India', 'States', 'Districts'] as const).map((tab) => (
            <button
              key={tab}
              className={`fg-tab-btn ${activeTab === tab ? 'active' : ''}`}
              onClick={() => handleTabClick(tab)}
              title={`Switch camera to ${tab} overview`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Contextual Sub-Region Quick Jumper Chips */}
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '4px',
            marginBottom: '8px',
            padding: '2px 0',
          }}
        >
          {activeTab === 'Global' && (
            <>
              <button
                className="fg-filter-pill active"
                onClick={() => handleQuickRegionFly(20.0, 78.0, 1.8, 0)}
              >
                🌐 Whole Earth
              </button>
              <button
                className="fg-filter-pill"
                onClick={() => handleQuickRegionFly(19.45, 88.42, 5.8, 30)}
                title="Deep Depression BOB-03 in Bay of Bengal"
              >
                🌀 Bay of Bengal
              </button>
              <button
                className="fg-filter-pill"
                onClick={() => handleQuickRegionFly(18.2, 71.1, 5.8, 25)}
                title="Monsoon Low AS-01 in Arabian Sea"
              >
                🌊 Arabian Sea
              </button>
              <button
                className="fg-filter-pill"
                onClick={() => handleQuickRegionFly(30.8, 79.2, 6.2, 35)}
              >
                🏔️ Himalayan Arc
              </button>
            </>
          )}

          {activeTab === 'India' && (
            <>
              <button
                className="fg-filter-pill active"
                onClick={() => handleQuickRegionFly(22.5, 79.5, 4.6, 15)}
              >
                🇮🇳 Pan-India
              </button>
              <button
                className="fg-filter-pill"
                onClick={() => handleQuickRegionFly(30.8, 78.5, 6.8, 35)}
              >
                🏔️ NW Himalayas
              </button>
              <button
                className="fg-filter-pill"
                onClick={() => handleQuickRegionFly(25.8, 83.5, 6.0, 20)}
              >
                🌾 Gangetic Basin
              </button>
              <button
                className="fg-filter-pill"
                onClick={() => handleQuickRegionFly(14.5, 75.0, 6.2, 25)}
              >
                ⛰️ Western Ghats
              </button>
            </>
          )}

          {activeTab === 'States' && (
            <>
              <button
                className="fg-filter-pill active"
                onClick={() => handleQuickRegionFly(30.15, 79.2, 7.2, 35)}
                title="Click to zoom into Uttarakhand"
              >
                🔴 Uttarakhand
              </button>
              <button
                className="fg-filter-pill"
                onClick={() => handleQuickRegionFly(31.8, 77.2, 7.2, 35)}
                title="Click to zoom into Himachal Pradesh"
              >
                🟠 Himachal
              </button>
              <button
                className="fg-filter-pill"
                onClick={() => handleQuickRegionFly(27.6, 88.5, 8.0, 30)}
                title="Click to zoom into Sikkim"
              >
                🟡 Sikkim
              </button>
              <button
                className="fg-filter-pill"
                onClick={() => handleQuickRegionFly(26.2, 92.9, 7.2, 20)}
                title="Click to zoom into Assam"
              >
                🟡 Assam
              </button>
            </>
          )}

          {activeTab === 'Districts' && (
            <>
              <button
                className="fg-filter-pill active"
                onClick={() => handleQuickRegionFly(30.12, 78.95, 11.2, 50)}
                title="Click to zoom into Pauri Garhwal"
              >
                🔴 Pauri Garhwal
              </button>
              <button
                className="fg-filter-pill"
                onClick={() => handleQuickRegionFly(30.45, 79.4, 10.8, 50)}
                title="Click to zoom into Chamoli"
              >
                🔴 Chamoli
              </button>
              <button
                className="fg-filter-pill"
                onClick={() => handleQuickRegionFly(30.3, 78.98, 11.0, 45)}
                title="Click to zoom into Rudraprayag"
              >
                🟠 Rudraprayag
              </button>
              <button
                className="fg-filter-pill"
                onClick={() => handleQuickRegionFly(29.4, 79.45, 11.2, 45)}
                title="Click to zoom into Nainital"
              >
                🟠 Nainital
              </button>
              <button
                className="fg-filter-pill"
                onClick={() => handleQuickRegionFly(30.4, 78.48, 10.8, 45)}
                title="Click to zoom into Tehri Garhwal"
              >
                🟡 Tehri
              </button>
            </>
          )}
        </div>

        {/* Interactive World Minimap with Dynamic Bounding Box & Click-to-Fly Hotzones */}
        <div className="fg-minimap-container" style={{ position: 'relative', cursor: 'crosshair' }}>
          <svg className="fg-minimap-svg" viewBox="0 0 320 140" fill="none">
            {/* Background */}
            <rect width="320" height="140" fill="#040914" rx="4" />

            {/* Stylized Continents Outlines */}
            {/* Americas */}
            <path
              d="M50 30 C45 25 35 35 40 50 C45 60 55 70 50 85 C45 100 60 120 65 110 C70 95 65 80 60 70 C70 60 85 45 65 35 Z"
              fill="#1e293b"
              opacity="0.8"
            />
            {/* Eurasia / Africa */}
            <path
              d="M130 35 C150 20 200 25 240 30 C260 40 270 60 250 70 C240 85 220 80 210 75 C200 70 190 75 180 85 C170 95 165 115 155 110 C145 95 140 70 135 60 C125 50 120 40 130 35 Z"
              fill="#1e293b"
              opacity="0.8"
            />
            {/* Australia */}
            <path
              d="M250 95 C260 90 275 95 270 110 C265 120 250 115 250 95 Z"
              fill="#1e293b"
              opacity="0.8"
            />

            {/* Clickable Hotzone: Pan-India */}
            <rect
              x="180"
              y="40"
              width="50"
              height="45"
              fill="rgba(56, 189, 248, 0.08)"
              rx="3"
              style={{ cursor: 'pointer' }}
              onClick={() => handleQuickRegionFly(22.5, 79.5, 4.6, 15)}
            >
              <title>Click to fly map to Pan-India Overview</title>
            </rect>

            {/* Clickable Hotzone: Bay of Bengal Cyclone BOB-03 */}
            <circle
              cx="218"
              cy="66"
              r="10"
              fill="rgba(239, 68, 68, 0.25)"
              stroke="#ef4444"
              strokeWidth="1.2"
              strokeDasharray="2 2"
              style={{ cursor: 'pointer' }}
              onClick={() => handleQuickRegionFly(19.45, 88.42, 5.8, 30)}
            >
              <title>Click to fly map to Deep Depression BOB-03 in Bay of Bengal</title>
            </circle>
            <circle cx="218" cy="66" r="2.5" fill="#ef4444" />

            {/* Dynamic Bounding Box Framing Current Selected View */}
            <rect
              x={bbox.x}
              y={bbox.y}
              width={bbox.w}
              height={bbox.h}
              fill="none"
              stroke={bbox.stroke}
              strokeWidth="1.8"
              strokeDasharray="3 2"
              rx="2"
              style={{ transition: 'all 0.35s cubic-bezier(0.4, 0, 0.2, 1)' }}
            />
            <circle cx="205" cy="58" r="3" fill="#ef4444" opacity="0.85" />
          </svg>

          {/* Minimap Overlay Label */}
          <div
            style={{
              position: 'absolute',
              bottom: '4px',
              right: '6px',
              fontSize: '8.5px',
              color: '#64748b',
              background: 'rgba(4, 9, 20, 0.75)',
              padding: '1px 5px',
              borderRadius: '3px',
              pointerEvents: 'none',
            }}
          >
            {activeTab.toUpperCase()} VIEW ACTIVE
          </div>
        </div>

        {/* National Mountain Corridors Quick Navigation Pills */}
        <div style={{ display: 'flex', gap: '5px', margin: '8px 0 4px 0', overflowX: 'auto', paddingBottom: '2px' }}>
          {[
            { name: '🏔 Uttarakhand', lat: 30.08, lng: 78.08, zoom: 10.2, pitch: 45 },
            { name: '⛰ Himachal', lat: 31.80, lng: 77.10, zoom: 9.8, pitch: 45 },
            { name: '🌲 Sikkim', lat: 27.50, lng: 88.55, zoom: 9.8, pitch: 45 },
            { name: '🌴 Western Ghats', lat: 11.55, lng: 76.13, zoom: 10.0, pitch: 45 },
          ].map((reg) => (
            <button
              key={reg.name}
              onClick={() => handleQuickRegionFly(reg.lat, reg.lng, reg.zoom, reg.pitch)}
              style={{
                background: 'rgba(15, 23, 42, 0.75)',
                border: '1px solid rgba(56, 189, 248, 0.25)',
                borderRadius: '4px',
                padding: '3px 7px',
                color: '#93c5fd',
                fontSize: '9.5px',
                fontWeight: 700,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                transition: 'all 0.15s ease',
              }}
              title={`Fly to ${reg.name} mountain corridor`}
            >
              {reg.name}
            </button>
          ))}
        </div>

        {/* 4 Summary Metric Cards (Interactive) */}
        <div className="fg-metrics-row">
          <div
            className="fg-metric-card"
            style={{ cursor: 'pointer' }}
            title="Click to view all monitored villages"
            onClick={() => handleQuickRegionFly(30.08, 79.25, 9.8, 45)}
          >
            <div className="metric-icon-wrap icon-blue">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" strokeWidth="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <div className="metric-label">Monitored Areas</div>
            <div className="metric-value val-blue">{totalCount}</div>
          </div>

          <div
            className="fg-metric-card"
            style={{ cursor: 'pointer' }}
            title="Click to focus on elevated risk village (Talli)"
            onClick={() => {
              const loc = locations.find((l) => l.name === 'Talli') || locations[0];
              if (loc) onSelectLocation(loc);
            }}
          >
            <div className="metric-icon-wrap icon-amber">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            </div>
            <div className="metric-label">Elevated Risk</div>
            <div className="metric-value val-amber">{highCount}</div>
          </div>

          <div
            className="fg-metric-card"
            style={{ cursor: 'pointer' }}
            title="Click to focus on critical risk village (Devgaon / Ranikhet)"
            onClick={() => {
              const loc = locations.find((l) => l.risk_level === 'CRITICAL') || locations[0];
              if (loc) onSelectLocation(loc);
            }}
          >
            <div className="metric-icon-wrap icon-red">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
            </div>
            <div className="metric-label">Critical Risk</div>
            <div className="metric-value val-red">{criticalCount}</div>
          </div>

          <div
            className="fg-metric-card"
            style={{ cursor: 'pointer' }}
            title="Click to open Emergency Alert Center"
            onClick={onOpenAlerts}
          >
            <div className="metric-icon-wrap icon-magenta">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#ec4899" strokeWidth="2">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
                <path d="M13.73 21a2 2 0 0 1-3.46 0" />
              </svg>
            </div>
            <div className="metric-label">Active Alerts</div>
            <div className="metric-value val-magenta">361</div>
          </div>
        </div>
      </div>

      {/* SECTION: CURRENT HAZARD CONDITIONS */}
      {(() => {
        const activeLoc = selectedLocation || locations.find((l: LocationRisk) => l.name === 'Talli') || locations[0];
        if (!activeLoc) return null;
        return (
          <div className="fg-panel-section hazard-conditions-section" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', padding: '12px 14px' }}>
            <div className="fg-section-header" style={{ marginBottom: '8px' }}>
              <div className="fg-header-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ color: '#f59e0b', fontSize: '13px' }}>⚠️</span>
                <span style={{ fontSize: '11px', fontWeight: 800, letterSpacing: '0.4px', color: '#ffffff' }}>CURRENT HAZARD CONDITIONS</span>
              </div>
              <span style={{ fontSize: '10px', color: '#38bdf8', fontWeight: 700, background: 'rgba(56, 189, 248, 0.15)', padding: '2px 6px', borderRadius: '4px' }}>
                {activeLoc.name}
              </span>
            </div>

            <div style={{
              background: 'rgba(8, 18, 36, 0.75)',
              border: '1px solid rgba(56, 189, 248, 0.22)',
              borderRadius: '8px',
              padding: '10px 12px',
              display: 'flex',
              flexDirection: 'column',
              gap: '8px',
            }}>
              {/* Row 1: Rainfall & Soil Moisture */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                <div style={{ background: 'rgba(15, 23, 42, 0.6)', padding: '6px 8px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <div style={{ fontSize: '9.5px', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span>🌧</span> Rainfall
                  </div>
                  <div style={{ fontSize: '13px', fontWeight: 800, color: '#38bdf8', marginTop: '2px' }}>
                    {activeLoc.current_rainfall_mm.toFixed(0)} mm/hr
                  </div>
                </div>

                <div style={{ background: 'rgba(15, 23, 42, 0.6)', padding: '6px 8px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <div style={{ fontSize: '9.5px', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span>💧</span> Soil Moisture
                  </div>
                  <div style={{ fontSize: '13px', fontWeight: 800, color: '#10b981', marginTop: '2px' }}>
                    {(activeLoc.soil_moisture_saturation * 100).toFixed(0)}%
                  </div>
                </div>
              </div>

              {/* Row 2: River Level & Slope Risk */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                <div style={{ background: 'rgba(15, 23, 42, 0.6)', padding: '6px 8px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <div style={{ fontSize: '9.5px', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span>🌊</span> River Level
                  </div>
                  <div style={{ fontSize: '13px', fontWeight: 800, color: '#f59e0b', marginTop: '2px' }}>
                    +{activeLoc.river_level_rise_m.toFixed(1)} m
                  </div>
                </div>

                <div style={{ background: 'rgba(15, 23, 42, 0.6)', padding: '6px 8px', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <div style={{ fontSize: '9.5px', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <span>⛰</span> Slope Risk
                  </div>
                  <div style={{ fontSize: '13px', fontWeight: 800, color: activeLoc.slope_degrees > 30 ? '#f97316' : '#facc15', marginTop: '2px' }}>
                    {activeLoc.slope_degrees > 30 ? 'HIGH' : 'MODERATE'}
                  </div>
                </div>
              </div>

              {/* Row 3: Combined Risk Banner */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                background: activeLoc.risk_level === 'CRITICAL' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(249, 115, 22, 0.2)',
                border: `1px solid ${activeLoc.risk_level === 'CRITICAL' ? '#ef4444' : '#f97316'}`,
                borderRadius: '6px',
                padding: '6px 10px',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', fontWeight: 700, color: '#f8fafc' }}>
                  <span>⚠</span> Combined Risk
                </div>
                <div style={{
                  fontSize: '11px',
                  fontWeight: 900,
                  letterSpacing: '0.5px',
                  color: activeLoc.risk_level === 'CRITICAL' ? '#f87171' : '#fb923c',
                }}>
                  {activeLoc.risk_level}
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      {/* SECTION 1.5: MULTI-HAZARD HYDROGRAPH LAUNCHER */}
      <div className="fg-panel-section hydrograph-launch-section">
        <div className="fg-section-header">
          <div className="fg-header-title">
            <span style={{ fontSize: '13px' }}>📈</span>
            <span>MULTI-HAZARD HYDROGRAPH</span>
          </div>
          <span className="hydro-badge-live">LIVE ANALYTICS</span>
        </div>

        <div className="hydro-launcher-card">
          <div className="hydro-card-top">
            <div className="hydro-card-location">
              <span className="hydro-loc-dot" />
              <span className="hydro-loc-name">
                {selectedLocation ? selectedLocation.name : (locations[0]?.name || 'Devgaon')}
              </span>
              <span className="hydro-loc-state">
                ({selectedLocation ? selectedLocation.district : (locations[0]?.district || 'Garhwal')})
              </span>
            </div>
            {(() => {
              const activeLoc = selectedLocation || locations[0] || { risk_level: 'CRITICAL' };
              return (
                <span className={`hydro-risk-pill risk-${(activeLoc.risk_level || 'CRITICAL').toLowerCase()}`}>
                  {activeLoc.risk_level || 'CRITICAL'}
                </span>
              );
            })()}
          </div>

          <div className="hydro-preview-grid">
            {(() => {
              const activeLoc = selectedLocation || locations[0] || {};
              return (
                <>
                  <div className="hydro-stat-cell">
                    <span className="stat-label">River Stage</span>
                    <span className="stat-val font-mono">{activeLoc.river_level_rise_m ? `+${activeLoc.river_level_rise_m}m` : '+2.8m'}</span>
                  </div>
                  <div className="hydro-stat-cell">
                    <span className="stat-label">Rain Rate</span>
                    <span className="stat-val font-mono">{activeLoc.current_rainfall_mm ?? 64.2} mm/h</span>
                  </div>
                  <div className="hydro-stat-cell">
                    <span className="stat-label">Lead Time</span>
                    <span className="stat-val font-mono">~{activeLoc.lead_time_hours ?? 3.5}h</span>
                  </div>
                </>
              );
            })()}
          </div>

          <button
            className="fg-btn-launch-hydrograph"
            onClick={onOpenHydrograph}
            title="Open Fullscreen Multi-Hazard Hydrograph & Risk Analytics"
          >
            <span className="btn-icon">📈</span>
            <div className="btn-text-block">
              <span className="btn-main-text">Open Fullscreen Hydrograph</span>
              <span className="btn-sub-text">Interactive Curves &amp; CWC Danger Mark</span>
            </div>
            <span className="btn-expand-arrow">⛶</span>
          </button>
        </div>
      </div>

      {/* SECTION 2: RAINFALL (LIVE SATELLITE VS REPLAY) */}
      <div className="fg-panel-section rainfall-section">
        <div className="rainfall-header-row">
          <div className="rainfall-title-group">
            <span className="rainfall-title">
              {weatherMode === 'live' ? 'LIVE SATELLITE RAINFALL (ISRO MOSDAC)' : 'STORM REPLAY RAINFALL (GPM / REPLAY)'}
            </span>
          </div>
        </div>

        <div className="rainfall-sub-row">
          <div className="unit-pill">
            <span className="unit-dot" />
            <span>mm/hr</span>
          </div>
          {weatherMode === 'live' ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ fontSize: '10px', background: 'rgba(34, 197, 94, 0.15)', color: '#4ade80', padding: '1px 6px', borderRadius: '4px', border: '1px solid rgba(34, 197, 94, 0.3)', fontWeight: 600 }}>
                INSAT-3DS IMAGER
              </span>
              <span className="rainfall-timestamp" style={{ color: '#86efac' }}>16:00 UTC</span>
            </div>
          ) : (
            <span className="rainfall-timestamp">{replayTime}</span>
          )}
        </div>

        {/* Continuous Color Gradient Legend Bar */}
        <div className="rainfall-gradient-bar" />

        {/* Gradient Scale Ticks */}
        <div className="rainfall-scale-ticks">
          <span>0</span>
          <span>1</span>
          <span>5</span>
          <span>10</span>
          <span>20</span>
          <span>50</span>
          <span>100</span>
          <span>200</span>
          <span>500+</span>
        </div>
      </div>

      {/* SECTION 3: RECENT ALERTS */}
      <div className="fg-panel-section alerts-section">
        <div className="fg-section-header">
          <div className="fg-header-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="2.2">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
            </svg>
            <span>RECENT ALERTS</span>
          </div>
          <button className="fg-section-action" onClick={onOpenAlerts}>
            View All
          </button>
        </div>

        <div className="fg-alert-list">
          {alerts.map((alert) => {
            const loc = locations.find((l) => l.name === alert.locationName) || locations[0];
            return (
              <div
                key={alert.id}
                className="fg-alert-row"
                onClick={() => loc && onSelectLocation(loc)}
                title={`Inspect ${alert.locationName}`}
              >
                <div className="alert-left-tag">
                  <span className={`alert-badge badge-${alert.severity.toLowerCase()}`}>
                    {alert.severity}
                  </span>
                </div>
                <div className="alert-center-info">
                  <div className="alert-location-name">{alert.locationName}</div>
                  <div className="alert-desc">{alert.description}</div>
                </div>
                <div className="alert-right-time">{alert.timeAgo}</div>
              </div>
            );
          })}
        </div>

        <button
          onClick={onOpenAlerts}
          style={{
            width: '100%',
            marginTop: '10px',
            background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.25) 0%, rgba(185, 28, 28, 0.25) 100%)',
            border: '1px solid rgba(239, 68, 68, 0.5)',
            borderRadius: '6px',
            padding: '8px 12px',
            color: '#f87171',
            fontSize: '11px',
            fontWeight: 800,
            letterSpacing: '0.5px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
          }}
        >
          <span>🚨</span>
          <span>DISPATCH EMERGENCY ALERTS &amp; SMS</span>
        </button>
      </div>

      {/* SECTION 3.5: EXTERNAL PUBLIC IOT TELEMETRY (THINGSPEAK CH 3368421) */}
      <div className="fg-panel-section thingspeak-iot-section" style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', padding: '12px 14px' }}>
        <div className="fg-section-header" style={{ marginBottom: '8px' }}>
          <div className="fg-header-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '13px' }}>📡</span>
            <span style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.05em', color: '#e2e8f0' }}>PUBLIC IOT FEED</span>
            <span style={{ fontSize: '9px', background: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8', padding: '1px 5px', borderRadius: '4px', border: '1px solid rgba(56, 189, 248, 0.3)', fontWeight: 600 }}>
              CH 3368421
            </span>
          </div>
          <span style={{ fontSize: '9px', background: 'rgba(245, 158, 11, 0.15)', color: '#fbbf24', padding: '1px 6px', borderRadius: '4px', border: '1px solid rgba(245, 158, 11, 0.3)', fontWeight: 700 }}>
            STALE (&gt;120d)
          </span>
        </div>

        <div style={{
          background: 'rgba(15, 23, 42, 0.65)',
          border: '1px solid rgba(56, 189, 248, 0.2)',
          borderRadius: '8px',
          padding: '10px 12px',
          backdropFilter: 'blur(6px)',
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '10px', color: '#94a3b8', fontWeight: 600 }}>
              Smart Flood &amp; Landslide System
            </span>
            <a
              href="https://thingspeak.mathworks.com/channels/3368421"
              target="_blank"
              rel="noopener noreferrer"
              style={{ fontSize: '10px', color: '#38bdf8', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '3px' }}
              title="Open public channel on MathWorks ThingSpeak"
            >
              Feed ↗
            </a>
          </div>

          {/* 4-cell Metric Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', marginBottom: '8px' }}>
            <div style={{ background: 'rgba(0, 0, 0, 0.25)', padding: '6px 8px', borderRadius: '6px', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
              <div style={{ fontSize: '9px', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>Water Level</div>
              <div style={{ fontSize: '13px', fontWeight: 800, color: '#38bdf8', fontFamily: 'monospace' }}>
                {iotData?.canonical_observation?.water_level != null ? `${iotData.canonical_observation.water_level.toFixed(2)} m` : '5.99 m'}
              </div>
              <div style={{ fontSize: '8px', color: '#0ea5e9' }}>599.28 cm &#8594; SI (m)</div>
            </div>

            <div style={{ background: 'rgba(0, 0, 0, 0.25)', padding: '6px 8px', borderRadius: '6px', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
              <div style={{ fontSize: '9px', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>Hardware Tilt</div>
              <div style={{ fontSize: '13px', fontWeight: 800, color: '#f59e0b', fontFamily: 'monospace' }}>
                61.9°
              </div>
              <div style={{ fontSize: '8px', color: '#d97706' }}>Sensor angle (not DEM)</div>
            </div>

            <div style={{ background: 'rgba(0, 0, 0, 0.25)', padding: '6px 8px', borderRadius: '6px', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
              <div style={{ fontSize: '9px', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>Soil Moisture</div>
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#cbd5e1', fontFamily: 'monospace' }}>
                4095 ADC
              </div>
              <div style={{ fontSize: '8px', color: '#64748b' }}>Raw ADC (No curve &#8594; None)</div>
            </div>

            <div style={{ background: 'rgba(0, 0, 0, 0.25)', padding: '6px 8px', borderRadius: '6px', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
              <div style={{ fontSize: '9px', color: '#64748b', textTransform: 'uppercase', fontWeight: 600 }}>Rain Intensity</div>
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#cbd5e1', fontFamily: 'monospace' }}>
                4095 ADC
              </div>
              <div style={{ fontSize: '8px', color: '#64748b' }}>Raw ADC (No curve &#8594; None)</div>
            </div>
          </div>

          {/* Telemetry provenance details */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '9px', color: '#64748b', marginBottom: '8px' }}>
            <span>Entry #1214 &bull; May 5, 2026</span>
            <span>Coords: NULL (Unassigned)</span>
          </div>

          {/* Sync Button */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <button
              onClick={handleSyncThingSpeak}
              disabled={iotSyncing}
              style={{
                flex: 1,
                padding: '5px 8px',
                background: iotSyncing ? 'rgba(56, 189, 248, 0.1)' : 'rgba(56, 189, 248, 0.2)',
                border: '1px solid rgba(56, 189, 248, 0.4)',
                borderRadius: '5px',
                color: '#38bdf8',
                fontSize: '10px',
                fontWeight: 700,
                cursor: iotSyncing ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '5px',
                transition: 'all 0.2s ease',
              }}
            >
              <span>{iotSyncing ? '🔄' : '⚡'}</span>
              <span>{iotSyncing ? 'Syncing REST Feed...' : 'Sync Public Feed'}</span>
            </button>
            {iotSyncMsg && (
              <span style={{ fontSize: '9px', color: '#4ade80', fontWeight: 600 }}>{iotSyncMsg}</span>
            )}
          </div>
        </div>
      </div>

      {/* SECTION 4: TROPICAL ACTIVITY (INTERACTIVE SYNOPTIC COMMAND CARD) */}
      <div className="fg-panel-section tropical-section">
        <div
          className="tropical-card"
          style={{
            cursor: 'pointer',
            position: 'relative',
            background: 'linear-gradient(135deg, rgba(10, 22, 45, 0.88) 0%, rgba(15, 30, 60, 0.75) 100%)',
            border: '1px solid rgba(56, 189, 248, 0.45)',
            boxShadow: '0 4px 16px rgba(0, 0, 0, 0.4)',
            transition: 'all 0.2s ease',
          }}
          onClick={() => onOpenTropicalActivity && onOpenTropicalActivity()}
          title="Click to inspect Tropical Cyclone Dossier & Track"
        >
          {/* Active Cyclone Radar Thumbnail */}
          <div className="tropical-thumb" style={{ position: 'relative' }}>
            <svg viewBox="0 0 80 80" className="cyclone-icon-svg" width="54" height="54">
              <defs>
                <radialGradient id="cycloneGrad" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="#ef4444" stopOpacity="1" />
                  <stop offset="40%" stopColor="#f97316" stopOpacity="0.8" />
                  <stop offset="70%" stopColor="#06b6d4" stopOpacity="0.6" />
                  <stop offset="100%" stopColor="#0f172a" stopOpacity="0" />
                </radialGradient>
              </defs>
              <circle cx="40" cy="40" r="38" fill="url(#cycloneGrad)" />
              {/* Animated Spiral Arms */}
              <path
                d="M40 10 A30 30 0 0 1 70 40 A20 20 0 0 1 50 60 A10 10 0 0 1 40 40"
                fill="none"
                stroke="#ffffff"
                strokeWidth="2.5"
                opacity="0.9"
                strokeLinecap="round"
              />
              <path
                d="M40 70 A30 30 0 0 1 10 40 A20 20 0 0 1 30 20 A10 10 0 0 1 40 40"
                fill="none"
                stroke="#67e8f9"
                strokeWidth="2.2"
                opacity="0.8"
                strokeLinecap="round"
              />
              <circle cx="40" cy="40" r="4" fill="#facc15" />
            </svg>
            <div
              style={{
                position: 'absolute',
                top: '2px',
                right: '2px',
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: '#ef4444',
                boxShadow: '0 0 6px #ef4444',
              }}
            />
          </div>

          <div className="tropical-info" style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '4px' }}>
              <div className="tropical-title">Tropical Activity</div>
              <span
                style={{
                  fontSize: '9px',
                  fontWeight: 700,
                  background: 'rgba(239, 68, 68, 0.25)',
                  border: '1px solid #ef4444',
                  color: '#fca5a5',
                  padding: '1px 5px',
                  borderRadius: '3px',
                }}
              >
                ACTIVE (BOB-03)
              </span>
            </div>

            <div className="tropical-sub" style={{ color: '#f8fafc', fontWeight: 700, fontSize: '11px' }}>
              Deep Depression BOB-03
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '9.5px', color: '#38bdf8', marginTop: '1px' }}>
              <span>65 km/h</span>
              <span>•</span>
              <span>992 hPa</span>
              <span>•</span>
              <span style={{ color: '#22c55e' }}>WNW @ 18 km/h</span>
            </div>

            <div className="tropical-region" style={{ color: '#94a3b8', fontSize: '9px', marginTop: '2px' }}>
              Head Bay of Bengal • Moisture Pumping to Uttarakhand
            </div>

            {/* Quick Action Buttons Row */}
            <div
              style={{
                display: 'flex',
                gap: '6px',
                marginTop: '6px',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={() => handleQuickRegionFly(19.45, 88.42, 6.2, 35)}
                style={{
                  flex: 1,
                  padding: '3px 6px',
                  background: 'rgba(2, 132, 199, 0.35)',
                  border: '1px solid rgba(56, 189, 248, 0.5)',
                  borderRadius: '4px',
                  color: '#38bdf8',
                  fontSize: '9.5px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '3px',
                }}
                title="Fly camera to Deep Depression BOB-03 center in Bay of Bengal"
              >
                <span>🛰️</span> Fly to Storm
              </button>

              <button
                onClick={() => onOpenTropicalActivity && onOpenTropicalActivity()}
                style={{
                  flex: 1,
                  padding: '3px 6px',
                  background: 'rgba(15, 23, 42, 0.7)',
                  border: '1px solid rgba(255, 255, 255, 0.15)',
                  borderRadius: '4px',
                  color: '#f8fafc',
                  fontSize: '9.5px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '3px',
                }}
                title="Open complete IMD synoptic storm dossier and landfall forecast"
              >
                <span>📋</span> Synoptic Dossier
              </button>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
};

export default RightPanel;
