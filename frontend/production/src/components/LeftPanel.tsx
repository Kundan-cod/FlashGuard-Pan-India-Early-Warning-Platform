import React from 'react';
import { SourceHealth } from '../types';

interface LeftPanelProps {
  layers: Record<string, boolean>;
  onToggleLayer: (layerKey: string) => void;
  onResetLayers: () => void;
  onOpenManageSources?: () => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
  sources?: SourceHealth[];
}

interface SourceItem {
  id: string;
  name: string;
  dataType: string;
  status: 'LIVE' | 'DISCOVERY' | 'SIMULATED' | 'NOT CONFIGURED' | 'NRT';
  lastUpdate?: string;
  dotColor: string;
}

const DATA_SOURCES: SourceItem[] = [
  {
    id: 'gpm',
    name: 'NASA GPM IMERG',
    dataType: 'Precipitation (mm/hr)',
    status: 'DISCOVERY',
    lastUpdate: '12 min ago',
    dotColor: '#10b981', // green
  },
  {
    id: 'smap',
    name: 'NASA SMAP',
    dataType: 'Soil Moisture',
    status: 'NOT CONFIGURED',
    dotColor: '#64748b', // gray
  },
  {
    id: 'imd',
    name: 'IMD',
    dataType: 'Weather / Forecast',
    status: 'NOT CONFIGURED',
    dotColor: '#ef4444', // red
  },
  {
    id: 'mosdac',
    name: 'MOSDAC (ISRO)',
    dataType: 'Satellite Products',
    status: 'LIVE',
    lastUpdate: '10 min ago',
    dotColor: '#10b981', // green
  },
  {
    id: 'bhuvan',
    name: 'Bhuvan (NRSC)',
    dataType: 'Terrain / DEM',
    status: 'LIVE',
    lastUpdate: '5 min ago',
    dotColor: '#10b981', // green
  },
  {
    id: 'cwc',
    name: 'CWC (NWIC)',
    dataType: 'River Gauges',
    status: 'LIVE',
    lastUpdate: '8 min ago',
    dotColor: '#10b981', // green
  },
  {
    id: 'gsi',
    name: 'GSI (Bhusanket)',
    dataType: 'Landslide Susceptibility',
    status: 'LIVE',
    lastUpdate: '15 min ago',
    dotColor: '#10b981', // green
  },
  {
    id: 'lgd',
    name: 'LGD',
    dataType: 'Administrative Boundaries',
    status: 'LIVE',
    lastUpdate: '1 hour ago',
    dotColor: '#00d4ff', // cyan
  },
  {
    id: 'ndem',
    name: 'NDEM',
    dataType: 'Disaster Events',
    status: 'LIVE',
    lastUpdate: '2 hours ago',
    dotColor: '#a855f7', // purple
  },
  {
    id: 'iot',
    name: 'IoT Sensors',
    dataType: 'Ground Observations',
    status: 'SIMULATED',
    lastUpdate: 'realtime',
    dotColor: '#f59e0b', // orange
  },
  {
    id: 'thingspeak-3368421',
    name: 'ThingSpeak (Ch 3368421)',
    dataType: 'External Public IoT',
    status: 'LIVE',
    lastUpdate: 'realtime',
    dotColor: '#10b981', // green
  },
];

interface LayerDef {
  id: string;
  name: string;
  icon: React.ReactNode;
}

const LAYER_DEFS: LayerDef[] = [
  {
    id: 'precipitation',
    name: 'Precipitation',
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="2">
        <path d="M20 16.58A5 5 0 0 0 18 7h-1.26A8 8 0 1 0 4 15.25" />
        <line x1="8" y1="19" x2="8" y2="23" />
        <line x1="12" y1="17" x2="12" y2="21" />
        <line x1="16" y1="19" x2="16" y2="23" />
      </svg>
    ),
  },
  {
    id: 'rainfall_accumulation',
    name: 'Rainfall Accumulation',
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" strokeWidth="2">
        <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z" />
        <line x1="11" y1="20" x2="11" y2="23" />
        <line x1="15" y1="20" x2="15" y2="23" />
      </svg>
    ),
  },
  {
    id: 'soil_moisture',
    name: 'Soil Moisture',
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2">
        <path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z" />
      </svg>
    ),
  },
  {
    id: 'flood_risk',
    name: 'Flood Risk',
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#ef4444" strokeWidth="2">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
        <line x1="12" y1="9" x2="12" y2="13" />
        <line x1="12" y1="17" x2="12.01" y2="17" />
      </svg>
    ),
  },
  {
    id: 'landslide_risk',
    name: 'Landslide Risk',
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2">
        <path d="M21 21H3L12 3l9 18z" />
        <path d="M12 9v4" />
        <path d="M12 17h.01" />
      </svg>
    ),
  },
  {
    id: 'terrain_slope',
    name: 'Terrain / Slope',
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2">
        <path d="m8 3 4 8 5-5 5 15H2L8 3z" />
      </svg>
    ),
  },
  {
    id: 'rivers_gauges',
    name: 'Rivers / Gauges',
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" strokeWidth="2">
        <path d="M2 6c.6.5 1.2 1 2.5 1C7 7 7 5 9.5 5c2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1" />
        <path d="M2 12c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1" />
        <path d="M2 18c.6.5 1.2 1 2.5 1 2.5 0 2.5-2 5-2 2.6 0 2.4 2 5 2 2.5 0 2.5-2 5-2 1.3 0 1.9.5 2.5 1" />
      </svg>
    ),
  },
  {
    id: 'admin_boundaries',
    name: 'Administrative Boundaries',
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="2">
        <polygon points="12 2 2 7 12 12 22 7 12 2" />
        <polyline points="2 17 12 22 22 17" />
        <polyline points="2 12 12 17 22 12" />
      </svg>
    ),
  },
  {
    id: 'iot_sensors',
    name: 'IoT Sensors',
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2">
        <path d="M12 2v4" />
        <path d="M12 18v4" />
        <path d="M4.93 4.93l2.83 2.83" />
        <path d="M16.24 16.24l2.83 2.83" />
        <path d="M2 12h4" />
        <path d="M18 12h4" />
        <circle cx="12" cy="12" r="3" />
      </svg>
    ),
  },
  {
    id: 'historical_events',
    name: 'Historical Events',
    icon: (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#a855f7" strokeWidth="2">
        <circle cx="12" cy="12" r="10" />
        <polyline points="12 6 12 12 16 14" />
      </svg>
    ),
  },
];

function resolveSourceStatus(item: SourceItem, liveList?: SourceHealth[]): { status: string; dotColor: string; lastUpdate?: string } {
  if (!liveList || liveList.length === 0) {
    return { status: item.status, dotColor: item.dotColor, lastUpdate: item.lastUpdate };
  }
  const match = liveList.find((s) => s.source.toLowerCase() === item.id.toLowerCase());
  if (!match) {
    return { status: item.status, dotColor: item.dotColor, lastUpdate: item.lastUpdate };
  }

  const rawStatus = (match.status || '').toUpperCase();
  let status = item.status;
  let dotColor = item.dotColor;

  if (rawStatus === 'LIVE' || rawStatus === 'ONLINE' || rawStatus === 'NRT') {
    status = 'LIVE';
    dotColor = '#10b981'; // green
  } else if (rawStatus === 'DISCOVERY' || rawStatus === 'DISCOVERY_ONLY') {
    status = 'DISCOVERY';
    dotColor = '#00d4ff'; // cyan
  } else if (rawStatus === 'SIMULATED') {
    status = 'SIMULATED';
    dotColor = '#f59e0b'; // orange
  } else if (rawStatus === 'NOT_CONFIGURED') {
    status = 'NOT CONFIGURED';
    dotColor = '#ef4444'; // red
  }

  let lastUpdate = item.lastUpdate;
  if (match.last_success_at) {
    const diffMs = Date.now() - new Date(match.last_success_at).getTime();
    const diffMin = Math.round(diffMs / 60000);
    lastUpdate = diffMin < 1 ? 'just now' : diffMin < 60 ? `${diffMin} min ago` : `${Math.round(diffMin / 60)}h ago`;
  }

  return { status, dotColor, lastUpdate };
}

export const LeftPanel: React.FC<LeftPanelProps> = ({
  layers,
  onToggleLayer,
  onResetLayers,
  onOpenManageSources,
  isCollapsed,
  onToggleCollapse,
  sources,
}) => {
  return (
    <aside className={`fg-left-panel ${isCollapsed ? 'collapsed' : ''}`}>
      {/* SECTION 1: DATA SOURCES */}
      <div className="fg-panel-section">
        <div className="fg-section-header">
          <div className="fg-header-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="2.2">
              <rect x="3" y="3" width="7" height="7" />
              <rect x="14" y="3" width="7" height="7" />
              <rect x="14" y="14" width="7" height="7" />
              <rect x="3" y="14" width="7" height="7" />
            </svg>
            <span>DATA SOURCES</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <button className="fg-section-action" onClick={onOpenManageSources}>
              Manage
            </button>
            {onToggleCollapse && (
              <button
                className="fg-collapse-btn"
                onClick={onToggleCollapse}
                title="Hide Left Sidebar (Layers & Sources)"
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="15 18 9 12 15 6" />
                </svg>
                <span>Hide</span>
              </button>
            )}
          </div>
        </div>

        <div className="fg-source-list">
          {DATA_SOURCES.map((source) => {
            const resolved = resolveSourceStatus(source, sources);
            return (
              <div
                key={source.id}
                className="fg-source-row"
                style={{ cursor: 'pointer' }}
                onClick={onOpenManageSources}
                title={`Click to inspect ${source.name} configuration and endpoints`}
              >
                <div className="fg-source-left">
                  <div className="fg-source-dot" style={{ backgroundColor: resolved.dotColor }} />
                  <div className="fg-source-meta">
                    <div className="fg-source-name">{source.name}</div>
                    <div className="fg-source-type">{source.dataType}</div>
                  </div>
                </div>

                <div className="fg-source-right">
                  <span className={`fg-source-tag tag-${resolved.status.toLowerCase().replace(/\s+/g, '-')}`}>
                    {resolved.status}
                  </span>
                  {resolved.lastUpdate && (
                    <span className="fg-source-time">{resolved.lastUpdate}</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* SECTION 2: MAP LAYERS */}
      <div className="fg-panel-section map-layers-section">
        <div className="fg-section-header">
          <div className="fg-header-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="2.2">
              <polygon points="12 2 2 7 12 12 22 7 12 2" />
              <polyline points="2 17 12 22 22 17" />
              <polyline points="2 12 12 17 22 12" />
            </svg>
            <span>MAP LAYERS</span>
          </div>
          <button className="fg-section-action" onClick={onResetLayers}>
            Reset
          </button>
        </div>

        <div className="fg-layer-list">
          {LAYER_DEFS.map((layer) => {
            const isChecked = layers[layer.id] !== false;
            return (
              <label key={layer.id} className="fg-layer-row">
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={() => onToggleLayer(layer.id)}
                  className="fg-checkbox"
                />
                <span className="fg-layer-icon">{layer.icon}</span>
                <span className="fg-layer-name">{layer.name}</span>
              </label>
            );
          })}
        </div>
      </div>
    </aside>
  );
};
