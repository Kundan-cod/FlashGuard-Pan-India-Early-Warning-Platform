import React, { useState } from 'react';
import { LocationRisk, WeatherMode } from '../types';

interface TopBarProps {
  locations: LocationRisk[];
  onSelectLocation: (loc: LocationRisk) => void;
  onSelectSearchTarget?: (target: { name: string; lat: number; lng: number; zoomDistance: number }) => void;
  onOpenAlerts: () => void;
  onOpenModelInfo: () => void;
  onOpenAbout: () => void;
  onOpenSettings?: () => void;
  onOpenSources?: () => void;
  activeAlertCount?: number;
  criticalAlertCount?: number;
  activeSourceCount?: number;
  totalSourceCount?: number;
  weatherMode?: WeatherMode;
  onToggleWeatherMode?: () => void;
}

const REGIONAL_SEARCH_TARGETS = [
  { name: 'India (Country View)', lat: 21.5, lng: 78.9, zoomDistance: 8.5, type: 'Country' },
  { name: 'Uttarakhand (State)', lat: 30.15, lng: 79.20, zoomDistance: 6.8, type: 'State' },
  { name: 'Himachal Pradesh (State)', lat: 31.9, lng: 77.1, zoomDistance: 6.8, type: 'State' },
  { name: 'Jammu & Kashmir (UT)', lat: 33.7, lng: 75.3, zoomDistance: 6.8, type: 'State' },
  { name: 'Pauri Garhwal (District)', lat: 30.15, lng: 78.78, zoomDistance: 5.8, type: 'District' },
  { name: 'Nainital (District)', lat: 29.38, lng: 79.46, zoomDistance: 5.8, type: 'District' },
  { name: 'Dehradun (Capital City)', lat: 30.31, lng: 78.03, zoomDistance: 5.8, type: 'City' },
  { name: 'Chamoli (District)', lat: 30.40, lng: 79.33, zoomDistance: 5.8, type: 'District' },
  { name: 'Rudraprayag (District)', lat: 30.28, lng: 78.98, zoomDistance: 5.8, type: 'District' },
  { name: 'Tehri Garhwal (District)', lat: 30.38, lng: 78.48, zoomDistance: 5.8, type: 'District' },
  { name: 'Almora (District)', lat: 29.60, lng: 79.66, zoomDistance: 5.8, type: 'District' },
  { name: 'Pithoragarh (District)', lat: 29.58, lng: 80.22, zoomDistance: 5.8, type: 'District' },
  { name: 'Haridwar (City)', lat: 29.94, lng: 78.16, zoomDistance: 5.8, type: 'City' },
  { name: 'Rishikesh (City)', lat: 30.08, lng: 78.26, zoomDistance: 5.8, type: 'City' },
  { name: 'Srinagar (Garhwal)', lat: 30.22, lng: 78.78, zoomDistance: 5.8, type: 'City' },
  { name: 'Joshimath (Town)', lat: 30.55, lng: 79.56, zoomDistance: 5.8, type: 'City' },
  { name: 'Ranikhet (Town)', lat: 29.64, lng: 79.43, zoomDistance: 5.8, type: 'City' },
  { name: 'Kedarnath (Sanctuary)', lat: 30.73, lng: 79.06, zoomDistance: 5.5, type: 'Town' },
  { name: 'Badrinath (Town)', lat: 30.74, lng: 79.49, zoomDistance: 5.5, type: 'Town' },
  { name: 'New Delhi (Capital)', lat: 28.61, lng: 77.21, zoomDistance: 6.0, type: 'City' },
];

export const TopBar: React.FC<TopBarProps> = ({
  locations,
  onSelectLocation,
  onSelectSearchTarget,
  onOpenAlerts,
  onOpenModelInfo,
  onOpenAbout,
  onOpenSettings,
  onOpenSources,
  activeAlertCount = 361,
  criticalAlertCount = 4,
  activeSourceCount = 7,
  totalSourceCount = 11,
  weatherMode = 'replay',
  onToggleWeatherMode,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const matchedVillages = searchQuery.trim()
    ? locations.filter((loc: LocationRisk) =>
        loc.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        loc.district.toLowerCase().includes(searchQuery.toLowerCase()) ||
        loc.state.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : [];

  const matchedRegions = searchQuery.trim()
    ? REGIONAL_SEARCH_TARGETS.filter((r) =>
        r.name.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : [];

  const handleToggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().then(() => setIsFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullscreen(false)).catch(() => {});
    }
  };

  return (
    <header className="fg-topbar">
      {/* Brand Identity */}
      <div className="fg-brand-group">
        <div className="fg-brand-icon">
          <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
            <path
              d="M16 2L3 9V23L16 30L29 23V9L16 2Z"
              stroke="#00d4ff"
              strokeWidth="2.2"
              fill="rgba(0, 162, 232, 0.15)"
            />
            <path
              d="M16 6L7 11.5V20.5L16 26L25 20.5V11.5L16 6Z"
              stroke="#00f2fe"
              strokeWidth="1.6"
              fill="rgba(0, 242, 254, 0.25)"
            />
            <circle cx="16" cy="16" r="3.5" fill="#ffffff" />
          </svg>
        </div>
        <div className="fg-brand-text">
          <div className="fg-title">FLASHGUARD</div>
          <div className="fg-subtitle">Pan-India Flash Flood & Landslide Early Warning System</div>
          <div className="fg-meta">SIH 2026 • PS 26192</div>
        </div>
      </div>

      {/* Center Search Input */}
      <div className="fg-search-container">
        <div className="fg-search-bar">
          <svg className="fg-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            type="text"
            className="fg-search-input"
            placeholder="Search location (e.g. India, Uttarakhand, Dehradun, Devgaon...)"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setIsSearchOpen(true);
            }}
            onFocus={() => setIsSearchOpen(true)}
            onBlur={() => setTimeout(() => setIsSearchOpen(false), 200)}
          />
          {searchQuery && (
            <button className="fg-search-clear" onClick={() => setSearchQuery('')}>
              ×
            </button>
          )}
        </div>

        {/* Search Results Dropdown */}
        {isSearchOpen && (matchedVillages.length > 0 || matchedRegions.length > 0) && (
          <div className="fg-search-dropdown">
            {matchedRegions.map((region, idx) => (
              <div
                key={`reg-${idx}`}
                className="fg-search-item"
                onMouseDown={() => {
                  if (onSelectSearchTarget) {
                    onSelectSearchTarget(region);
                  }
                  setSearchQuery(region.name);
                  setIsSearchOpen(false);
                }}
              >
                <div className="fg-search-item-info">
                  <span className="fg-search-item-name">{region.name}</span>
                  <span className="fg-search-item-meta">Geographic View • {region.type}</span>
                </div>
                <span className="fg-search-badge" style={{ background: 'rgba(0, 212, 255, 0.2)', color: '#38bdf8', border: '1px solid rgba(0, 212, 255, 0.4)' }}>
                  FLY TO
                </span>
              </div>
            ))}

            {matchedVillages.map((loc: LocationRisk) => (
              <div
                key={loc.id}
                className="fg-search-item"
                onMouseDown={() => {
                  onSelectLocation(loc);
                  setSearchQuery(loc.name);
                  setIsSearchOpen(false);
                }}
              >
                <div className="fg-search-item-info">
                  <span className="fg-search-item-name">{loc.name}</span>
                  <span className="fg-search-item-meta">
                    {loc.block}, {loc.district}, {loc.state}
                  </span>
                </div>
                <span className={`fg-search-badge ${loc.risk_level.toLowerCase()}`}>
                  {loc.risk_level} ({(loc.overall_risk * 100).toFixed(0)}%)
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Right Telemetry & Badges */}
      <div className="fg-telemetry-group">
        {/* Weather Mode Badge - Hybrid Live Satellite vs Replay */}
        {weatherMode === 'live' ? (
          <div
            className="fg-status-pill live-satellite-pill"
            title="Operational LIVE SATELLITE MODE: streaming real-time INSAT-3DS rainfall from SAC-ISRO. Click to switch to Storm Replay."
            onClick={onToggleWeatherMode}
            style={{
              cursor: 'pointer',
              borderColor: 'rgba(34, 197, 94, 0.5)',
              background: 'linear-gradient(135deg, rgba(34, 197, 94, 0.15), rgba(16, 185, 129, 0.05))',
              boxShadow: '0 0 16px rgba(34, 197, 94, 0.25)',
            }}
          >
            <div
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                backgroundColor: '#4ade80',
                boxShadow: '0 0 8px #4ade80',
                animation: 'pulse 1.8s infinite',
              }}
            />
            <div className="pill-text">
              <span className="pill-title" style={{ color: '#4ade80', display: 'flex', alignItems: 'center', gap: 4 }}>
                LIVE SATELLITE
                <span style={{ fontSize: '8px', background: 'rgba(74, 222, 128, 0.2)', padding: '1px 4px', borderRadius: '3px', fontWeight: 700 }}>
                  ISRO
                </span>
              </span>
              <span className="pill-sub" style={{ color: '#86efac' }}>INSAT-3DS · NRT</span>
            </div>
          </div>
        ) : (
          <div
            className="fg-status-pill replay-pill"
            title="Operating under July 2026 calibrated storm replay. Click to switch to Live ISRO Satellite Feed."
            onClick={onToggleWeatherMode}
            style={{
              cursor: 'pointer',
              borderColor: 'rgba(245, 158, 11, 0.45)',
              background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.12), rgba(217, 119, 6, 0.04))',
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fbbf24" strokeWidth="2.5">
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
            <div className="pill-text">
              <span className="pill-title" style={{ color: '#fbbf24', display: 'flex', alignItems: 'center', gap: 4 }}>
                STORM REPLAY
                <span style={{ fontSize: '8px', background: 'rgba(245, 158, 11, 0.2)', padding: '1px 4px', borderRadius: '3px', fontWeight: 700 }}>
                  EVENT
                </span>
              </span>
              <span className="pill-sub" style={{ color: '#fcd34d' }}>July 2026 Cloudburst</span>
            </div>
          </div>
        )}

        {/* Demo Model Badge */}
        <div
          className="fg-status-pill model-pill"
          title="Demo model architecture - click to inspect explainability"
          onClick={onOpenModelInfo}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          <div className="pill-text">
            <span className="pill-title">DEMO MODEL</span>
            <span className="pill-sub">Not Validated</span>
          </div>
        </div>

        {/* Alerts Pill */}
        <div
          className="fg-status-pill alerts-pill"
          title="Click to open Emergency Alert Center"
          onClick={onOpenAlerts}
        >
          <div className="alert-dot" />
          <div className="pill-text">
            <span className="pill-title">{activeAlertCount} Alerts</span>
            <span className="pill-sub red-sub">{criticalAlertCount} Critical</span>
          </div>
        </div>

        {/* Sources Health Pill */}
        <div
          className="fg-status-pill sources-pill"
          title="Click to manage Data Feed Sources"
          onClick={onOpenSources}
        >
          <div className="source-dot" />
          <div className="pill-text">
            <span className="pill-title">Sources {activeSourceCount}/{totalSourceCount}</span>
            <span className="pill-sub green-sub">Active</span>
          </div>
        </div>

        {/* Action Controls */}
        <button
          className="fg-header-btn"
          title={isFullscreen ? 'Exit Fullscreen' : 'Enter Fullscreen'}
          onClick={handleToggleFullscreen}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
          </svg>
          <span>Fullscreen</span>
        </button>

        <button
          className="fg-header-btn"
          title="Settings & Preferences"
          onClick={onOpenSettings || onOpenModelInfo}
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
          <span>Settings</span>
        </button>

        <button className="fg-header-btn" title="System Architecture & Integrity" onClick={onOpenAbout}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          <span>About</span>
        </button>
      </div>
    </header>
  );
};
