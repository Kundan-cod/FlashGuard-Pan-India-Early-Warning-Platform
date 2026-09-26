import React from 'react';
import { SourceHealth } from '../types';

interface ManageSourcesModalProps {
  isOpen: boolean;
  onClose: () => void;
  sources: SourceHealth[];
}

interface SourceConfigItem {
  name: string;
  provider: string;
  endpoint: string;
  category: string;
  protocol: string;
  updateFreq: string;
  status: 'LIVE' | 'DISCOVERY' | 'SIMULATED' | 'NOT CONFIGURED';
  statusColor: string;
}

const SOURCES_CONFIG: SourceConfigItem[] = [
  {
    name: 'NASA GPM IMERG',
    provider: 'NASA GES DISC / Earthdata CMR',
    endpoint: 'https://cmr.earthdata.nasa.gov/search/granules.umm_json?short_name=GPM_3IMERGHHL',
    category: 'Satellite Precipitation',
    protocol: 'HTTPS / HDF5 OPeNDAP',
    updateFreq: 'Every 30 min (NRT)',
    status: 'DISCOVERY',
    statusColor: '#00d4ff',
  },
  {
    name: 'NASA SMAP',
    provider: 'NASA NSIDC DAAC',
    endpoint: 'https://nsidc.org/data/smap/smap-data.html',
    category: 'Soil Moisture L3/L4',
    protocol: 'HTTPS / NetCDF4',
    updateFreq: 'Every 3 hours',
    status: 'NOT CONFIGURED',
    statusColor: '#94a3b8',
  },
  {
    name: 'IMD (India Meteorological Dept)',
    provider: 'Ministry of Earth Sciences (MoES)',
    endpoint: 'https://mausam.imd.gov.in/api/v1/forecast',
    category: 'NWP Radar / AWS Rain Gauges',
    protocol: 'REST / GeoJSON',
    updateFreq: 'Hourly',
    status: 'NOT CONFIGURED',
    statusColor: '#ef4444',
  },
  {
    name: 'MOSDAC (SAC / ISRO)',
    provider: 'Space Applications Centre, ISRO',
    endpoint: 'https://mosdac.gov.in/apios/datasets.json',
    category: 'INSAT-3DS Multi-Spectral Rainfall (IMR)',
    protocol: 'REST / HDF5 OpenSearch',
    updateFreq: 'Every 30 min (NRT)',
    status: 'LIVE',
    statusColor: '#10b981',
  },
  {
    name: 'Bhuvan (NRSC / ISRO)',
    provider: 'National Remote Sensing Centre',
    endpoint: 'https://bhuvan-app1.nrsc.gov.in/2dresources/wms',
    category: 'CartoDEM 30m / Terrain Slope',
    protocol: 'OGC WMS / GeoTIFF',
    updateFreq: 'Static Baseline',
    status: 'LIVE',
    statusColor: '#10b981',
  },
  {
    name: 'CWC (NWIC)',
    provider: 'Central Water Commission / NWIC',
    endpoint: 'https://indiawris.gov.in/wris/#/riverGauges',
    category: 'River Discharge & Gauge Levels',
    protocol: 'REST / Telemetry JSON',
    updateFreq: 'Hourly Telemetry',
    status: 'LIVE',
    statusColor: '#10b981',
  },
  {
    name: 'GSI (Bhusanket)',
    provider: 'Geological Survey of India',
    endpoint: 'https://bhusanket.gsi.gov.in/api/susceptibility',
    category: 'Landslide Susceptibility Macro-Zonation',
    protocol: 'WFS / Vector GeoJSON',
    updateFreq: 'Daily Evaluation',
    status: 'LIVE',
    statusColor: '#10b981',
  },
  {
    name: 'LGD (Local Government Directory)',
    provider: 'Ministry of Panchayati Raj',
    endpoint: 'https://lgdirectory.gov.in/service/villages',
    category: 'Administrative Hierarchies (State/Dist/Village)',
    protocol: 'REST / Census Mapping',
    updateFreq: 'Monthly Master',
    status: 'LIVE',
    statusColor: '#00d4ff',
  },
  {
    name: 'NDEM (Disaster Management)',
    provider: 'ISRO Disaster Management Support Programme',
    endpoint: 'https://ndem.nrsc.gov.in/disaster_events',
    category: 'Emergency Incident Bulletins & Inundation',
    protocol: 'CAP v1.2 XML / GeoJSON',
    updateFreq: 'Realtime Push',
    status: 'LIVE',
    statusColor: '#a855f7',
  },
  {
    name: 'IoT Ground Sensors (Local AWS)',
    provider: 'District Emergency Operation Centre (DEOC)',
    endpoint: 'mqtt://iot.flashguard.in:1883/telemetry/uttarakhand',
    category: 'In-Situ Tipping Buckets & Piezometers',
    protocol: 'MQTT / HTTP Ingestion',
    updateFreq: 'Every 60 sec (Simulated)',
    status: 'SIMULATED',
    statusColor: '#f59e0b',
  },
  {
    name: 'ThingSpeak Channel 3368421 (Public IoT)',
    provider: 'MathWorks / Community Public Stream',
    endpoint: 'https://api.thingspeak.com/channels/3368421/feeds.json',
    category: 'External Public Ground IoT (Water Level / Tilt)',
    protocol: 'Public REST JSON Feed',
    updateFreq: 'Every ~20 sec (Stale >120d)',
    status: 'LIVE',
    statusColor: '#10b981',
  },
];

export const ManageSourcesModal: React.FC<ManageSourcesModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  return (
    <div className="fg-modal-overlay" onClick={onClose}>
      <div
        className="fg-modal-box"
        style={{ width: '840px', maxWidth: '94vw', maxHeight: '88vh' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="fg-modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="2">
              <rect x="3" y="3" width="7" height="7" />
              <rect x="14" y="3" width="7" height="7" />
              <rect x="14" y="14" width="7" height="7" />
              <rect x="3" y="14" width="7" height="7" />
            </svg>
            <div>
              <h2 style={{ fontSize: '16px', fontWeight: 800, color: '#ffffff' }}>
                Multi-Source Ingestion Architecture & Data Feeds
              </h2>
              <p style={{ fontSize: '11px', color: '#94a3b8' }}>
                Operational ingestion endpoints, providers, and real-time connectivity status
              </p>
            </div>
          </div>
          <button className="drawer-close-btn" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="fg-modal-body" style={{ padding: '16px 20px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {SOURCES_CONFIG.map((s, idx) => (
              <div
                key={idx}
                style={{
                  background: 'rgba(10, 22, 45, 0.7)',
                  border: '1px solid rgba(35, 70, 120, 0.55)',
                  borderRadius: '8px',
                  padding: '12px 16px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '12px',
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px', flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span
                      style={{
                        width: '8px',
                        height: '8px',
                        borderRadius: '50%',
                        backgroundColor: s.statusColor,
                        boxShadow: `0 0 8px ${s.statusColor}`,
                        flexShrink: 0,
                      }}
                    />
                    <span style={{ fontSize: '13px', fontWeight: 700, color: '#ffffff' }}>{s.name}</span>
                    <span
                      style={{
                        fontSize: '9.5px',
                        fontWeight: 700,
                        padding: '1px 6px',
                        borderRadius: '4px',
                        border: `1px solid ${s.statusColor}`,
                        color: s.statusColor,
                        background: 'rgba(0,0,0,0.3)',
                      }}
                    >
                      {s.status}
                    </span>
                  </div>

                  <div style={{ fontSize: '11px', color: '#38bdf8' }}>
                    {s.provider} • <span style={{ color: '#cbd5e1' }}>{s.category}</span>
                  </div>

                  <div style={{ fontSize: '10px', color: '#64748b', fontFamily: 'JetBrains Mono, monospace' }}>
                    Endpoint: {s.endpoint}
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '2px', flexShrink: 0 }}>
                  <span style={{ fontSize: '10.5px', color: '#94a3b8', fontWeight: 500 }}>{s.protocol}</span>
                  <span style={{ fontSize: '9.5px', color: '#64748b' }}>{s.updateFreq}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
