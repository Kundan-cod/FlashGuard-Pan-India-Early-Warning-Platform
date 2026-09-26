import React, { useState } from 'react';

export interface TropicalSystem {
  id: string;
  name: string;
  category: string;
  basin: string;
  coordinates: { lat: number; lng: number };
  maxWindsKmh: number;
  gustsKmh: number;
  centralPressureHpa: number;
  movementDirection: string;
  movementSpeedKmh: number;
  status: 'ACTIVE' | 'WATCH' | 'MONSOON LOW';
  teleconnectionAlert: string;
  satelliteDescription: string;
  forecastTrack: Array<{
    period: string;
    validTime: string;
    coordinates: string;
    lat: number;
    lng: number;
    intensity: string;
    windKmh: number;
    pressureHpa: number;
  }>;
}

export const TROPICAL_SYSTEMS: TropicalSystem[] = [
  {
    id: 'BOB-03',
    name: 'Deep Depression BOB-03',
    category: 'Deep Depression (IMD T2.0 / 3-min Sustained)',
    basin: 'North Indian Ocean • Head Bay of Bengal',
    coordinates: { lat: 19.45, lng: 88.42 },
    maxWindsKmh: 65,
    gustsKmh: 85,
    centralPressureHpa: 992,
    movementDirection: 'WNW',
    movementSpeedKmh: 18,
    status: 'ACTIVE',
    satelliteDescription:
      'GPM IMERG Microwave radar & INSAT-3D IR imagery shows intense convective cloud clusters organizing over Northwest Bay of Bengal with well-defined curved bands wrapping into the low-level cyclonic center.',
    teleconnectionAlert:
      'CRITICAL HIMALAYAN TELECONNECTION: The cyclonic circulation of BOB-03 is drawing an intense maritime low-level moisture jet across the Gangetic trough directly into Uttarakhand and Himachal Pradesh. Orographic lifting over the Garhwal ridges is precipitating extreme cloudbursts (>75 mm/hr) and flash floods.',
    forecastTrack: [
      {
        period: '+00h (Observed)',
        validTime: '2026-07-15 10:00 UTC',
        coordinates: '19.5°N, 88.4°E',
        lat: 19.45,
        lng: 88.42,
        intensity: 'Deep Depression',
        windKmh: 65,
        pressureHpa: 992,
      },
      {
        period: '+06h',
        validTime: '2026-07-15 16:00 UTC',
        coordinates: '19.9°N, 87.5°E',
        lat: 19.9,
        lng: 87.5,
        intensity: 'Deep Depression',
        windKmh: 65,
        pressureHpa: 992,
      },
      {
        period: '+12h (Landfall)',
        validTime: '2026-07-15 22:00 UTC',
        coordinates: '20.4°N, 86.7°E',
        lat: 20.4,
        lng: 86.7,
        intensity: 'Deep Depression (Chandbali Coast)',
        windKmh: 60,
        pressureHpa: 994,
      },
      {
        period: '+24h',
        validTime: '2026-07-16 10:00 UTC',
        coordinates: '21.3°N, 85.0°E',
        lat: 21.3,
        lng: 85.0,
        intensity: 'Depression (Inland Odisha/Jharkhand)',
        windKmh: 50,
        pressureHpa: 997,
      },
      {
        period: '+48h',
        validTime: '2026-07-17 10:00 UTC',
        coordinates: '23.4°N, 81.6°E',
        lat: 23.4,
        lng: 81.6,
        intensity: 'Well-Marked Low (Merged into Monsoon Trough)',
        windKmh: 40,
        pressureHpa: 1000,
      },
    ],
  },
  {
    id: 'AS-01',
    name: 'Monsoon Low Pressure AS-01',
    category: 'Well-Marked Low Pressure System (IMD T1.5)',
    basin: 'East-Central Arabian Sea',
    coordinates: { lat: 18.2, lng: 71.1 },
    maxWindsKmh: 45,
    gustsKmh: 60,
    centralPressureHpa: 1002,
    movementDirection: 'NNW',
    movementSpeedKmh: 14,
    status: 'WATCH',
    satelliteDescription:
      'Broad cyclonic vortex centered off the Konkan-Goa coast with strong southwesterly cross-equatorial monsoon surge feeding moisture into Maharashtra and Gujarat.',
    teleconnectionAlert:
      'Secondary moisture feed into Northern India: Offshore trough along Western Ghats induces secondary convergence along the Aravalli range, funneling supplementary precipitable water vapor toward Uttarakhand.',
    forecastTrack: [
      {
        period: '+00h (Observed)',
        validTime: '2026-07-15 10:00 UTC',
        coordinates: '18.2°N, 71.1°E',
        lat: 18.2,
        lng: 71.1,
        intensity: 'Monsoon Low',
        windKmh: 45,
        pressureHpa: 1002,
      },
      {
        period: '+12h',
        validTime: '2026-07-15 22:00 UTC',
        coordinates: '19.4°N, 70.3°E',
        lat: 19.4,
        lng: 70.3,
        intensity: 'Monsoon Low',
        windKmh: 45,
        pressureHpa: 1002,
      },
      {
        period: '+24h',
        validTime: '2026-07-16 10:00 UTC',
        coordinates: '20.6°N, 69.7°E',
        lat: 20.6,
        lng: 69.7,
        intensity: 'Depression',
        windKmh: 50,
        pressureHpa: 1000,
      },
    ],
  },
];

interface TropicalActivityModalProps {
  isOpen: boolean;
  onClose: () => void;
  onFlyToStorm: (coords: { lat: number; lng: number; zoom?: number; pitch?: number }) => void;
}

export const TropicalActivityModal: React.FC<TropicalActivityModalProps> = ({
  isOpen,
  onClose,
  onFlyToStorm,
}) => {
  const [selectedSystemId, setSelectedSystemId] = useState<string>('BOB-03');

  if (!isOpen) return null;

  const currentSystem = TROPICAL_SYSTEMS.find((s) => s.id === selectedSystemId) || TROPICAL_SYSTEMS[0];

  const handleFly = (lat: number, lng: number) => {
    onFlyToStorm({ lat, lng, zoom: 6.2, pitch: 40 });
    onClose();
  };

  return (
    <div className="fg-modal-overlay" onClick={onClose}>
      <div
        className="fg-modal-box"
        style={{ width: '740px', maxHeight: '88vh', overflowY: 'auto' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="fg-modal-header" style={{ borderBottom: '1px solid rgba(56, 189, 248, 0.25)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <span style={{ fontSize: '24px' }}>🌀</span>
            <div>
              <h2 style={{ fontSize: '16px', fontWeight: 800, color: '#ffffff', letterSpacing: '0.5px' }}>
                Tropical Activity &amp; Synoptic Cyclonic Tracker
              </h2>
              <div style={{ fontSize: '11px', color: '#38bdf8', fontWeight: 600 }}>
                IMD • NASA GPM IMERG Microwave Sounder • Pan-India Monsoon Teleconnection
              </div>
            </div>
          </div>
          <button className="fg-modal-close" onClick={onClose}>
            ✕
          </button>
        </div>

        {/* System Selector Tabs */}
        <div
          style={{
            display: 'flex',
            gap: '8px',
            padding: '12px 18px 0',
            background: 'rgba(7, 16, 32, 0.6)',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          }}
        >
          {TROPICAL_SYSTEMS.map((sys) => {
            const isActive = sys.id === currentSystem.id;
            return (
              <button
                key={sys.id}
                onClick={() => setSelectedSystemId(sys.id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '8px 14px',
                  background: isActive ? 'rgba(56, 189, 248, 0.16)' : 'rgba(15, 23, 42, 0.6)',
                  border: `1px solid ${isActive ? '#38bdf8' : 'rgba(255,255,255,0.08)'}`,
                  borderBottom: isActive ? '2px solid #38bdf8' : 'none',
                  borderRadius: '6px 6px 0 0',
                  color: isActive ? '#ffffff' : '#94a3b8',
                  cursor: 'pointer',
                  fontSize: '12px',
                  fontWeight: isActive ? 700 : 500,
                  transition: 'all 0.15s ease',
                }}
              >
                <span>{sys.status === 'ACTIVE' ? '🔴' : '🟡'}</span>
                <span>{sys.name}</span>
                <span
                  style={{
                    fontSize: '9.5px',
                    padding: '2px 5px',
                    borderRadius: '4px',
                    background: sys.status === 'ACTIVE' ? 'rgba(239, 68, 68, 0.3)' : 'rgba(245, 158, 11, 0.3)',
                    color: sys.status === 'ACTIVE' ? '#f87171' : '#fbbf24',
                  }}
                >
                  {sys.status}
                </span>
              </button>
            );
          })}
        </div>

        {/* Content Body */}
        <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Key Synoptic Metrics Grid */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(4, 1fr)',
              gap: '10px',
            }}
          >
            <div
              style={{
                background: 'rgba(12, 26, 52, 0.75)',
                border: '1px solid rgba(56, 189, 248, 0.2)',
                borderRadius: '8px',
                padding: '10px',
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Max Sustained Winds
              </div>
              <div style={{ fontSize: '18px', fontWeight: 800, color: '#38bdf8', marginTop: '2px' }}>
                {currentSystem.maxWindsKmh} <span style={{ fontSize: '11px', fontWeight: 500 }}>km/h</span>
              </div>
              <div style={{ fontSize: '9.5px', color: '#f59e0b', marginTop: '2px' }}>
                Gusts to {currentSystem.gustsKmh} km/h
              </div>
            </div>

            <div
              style={{
                background: 'rgba(12, 26, 52, 0.75)',
                border: '1px solid rgba(56, 189, 248, 0.2)',
                borderRadius: '8px',
                padding: '10px',
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Central Pressure
              </div>
              <div style={{ fontSize: '18px', fontWeight: 800, color: '#a855f7', marginTop: '2px' }}>
                {currentSystem.centralPressureHpa} <span style={{ fontSize: '11px', fontWeight: 500 }}>hPa</span>
              </div>
              <div style={{ fontSize: '9.5px', color: '#94a3b8', marginTop: '2px' }}>Deficit: -8 hPa</div>
            </div>

            <div
              style={{
                background: 'rgba(12, 26, 52, 0.75)',
                border: '1px solid rgba(56, 189, 248, 0.2)',
                borderRadius: '8px',
                padding: '10px',
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Forward Motion
              </div>
              <div style={{ fontSize: '18px', fontWeight: 800, color: '#22c55e', marginTop: '2px' }}>
                {currentSystem.movementDirection} <span style={{ fontSize: '11px', fontWeight: 500 }}>@ {currentSystem.movementSpeedKmh} km/h</span>
              </div>
              <div style={{ fontSize: '9.5px', color: '#94a3b8', marginTop: '2px' }}>Bearing: 295°</div>
            </div>

            <div
              style={{
                background: 'rgba(12, 26, 52, 0.75)',
                border: '1px solid rgba(56, 189, 248, 0.2)',
                borderRadius: '8px',
                padding: '10px',
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: '10px', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                Coordinates
              </div>
              <div style={{ fontSize: '16px', fontWeight: 800, color: '#f8fafc', marginTop: '4px' }}>
                {currentSystem.coordinates.lat}°N, {currentSystem.coordinates.lng}°E
              </div>
              <div style={{ fontSize: '9.5px', color: '#38bdf8', marginTop: '2px' }}>{currentSystem.basin.split('•')[1] || currentSystem.basin}</div>
            </div>
          </div>

          {/* Orographic Teleconnection Alert Banner */}
          <div
            style={{
              background: 'linear-gradient(90deg, rgba(239, 68, 68, 0.15) 0%, rgba(245, 158, 11, 0.1) 100%)',
              borderLeft: '4px solid #ef4444',
              borderRadius: '0 8px 8px 0',
              padding: '12px 16px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
              <span style={{ fontSize: '14px' }}>⚡</span>
              <span style={{ fontSize: '12px', fontWeight: 800, color: '#f87171', letterSpacing: '0.4px' }}>
                HIMALAYAN FLASH FLOOD TELECONNECTION NOTICE
              </span>
            </div>
            <p style={{ margin: 0, fontSize: '11.5px', lineHeight: '1.5', color: '#e2e8f0' }}>
              {currentSystem.teleconnectionAlert}
            </p>
          </div>

          {/* Satellite Imagery Analysis Note */}
          <div
            style={{
              background: 'rgba(10, 20, 38, 0.6)',
              border: '1px solid rgba(255, 255, 255, 0.08)',
              borderRadius: '8px',
              padding: '12px 16px',
            }}
          >
            <div style={{ fontSize: '11px', fontWeight: 700, color: '#38bdf8', marginBottom: '4px' }}>
              🛰️ GPM Radar &amp; INSAT-3D Synoptic Analysis
            </div>
            <p style={{ margin: 0, fontSize: '11px', color: '#94a3b8', lineHeight: '1.5' }}>
              {currentSystem.satelliteDescription}
            </p>
          </div>

          {/* Forecast Landfall Track Table */}
          <div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '8px',
              }}
            >
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#f8fafc' }}>
                Official Projected Track &amp; Cone of Uncertainty
              </div>
              <div style={{ fontSize: '10px', color: '#64748b' }}>Updated Every 6 Hours</div>
            </div>

            <div
              style={{
                background: 'rgba(6, 14, 28, 0.8)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderRadius: '8px',
                overflow: 'hidden',
              }}
            >
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
                <thead>
                  <tr style={{ background: 'rgba(15, 23, 42, 0.9)', color: '#94a3b8', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                    <th style={{ padding: '8px 12px', textAlign: 'left' }}>Time (UTC)</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left' }}>Position</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left' }}>Intensity Stage</th>
                    <th style={{ padding: '8px 12px', textAlign: 'center' }}>Winds (km/h)</th>
                    <th style={{ padding: '8px 12px', textAlign: 'center' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {currentSystem.forecastTrack.map((pt, idx) => (
                    <tr
                      key={idx}
                      style={{
                        borderBottom: '1px solid rgba(255,255,255,0.04)',
                        background: idx === 0 ? 'rgba(56, 189, 248, 0.05)' : 'transparent',
                      }}
                    >
                      <td style={{ padding: '8px 12px', color: '#f8fafc', fontWeight: idx === 0 ? 700 : 400 }}>
                        {pt.period} <span style={{ fontSize: '9.5px', color: '#64748b' }}>({pt.validTime.split(' ')[1]})</span>
                      </td>
                      <td style={{ padding: '8px 12px', color: '#38bdf8' }}>{pt.coordinates}</td>
                      <td style={{ padding: '8px 12px', color: '#e2e8f0' }}>{pt.intensity}</td>
                      <td style={{ padding: '8px 12px', textAlign: 'center', color: '#f59e0b', fontWeight: 600 }}>
                        {pt.windKmh}
                      </td>
                      <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                        <button
                          onClick={() => handleFly(pt.lat, pt.lng)}
                          style={{
                            padding: '3px 8px',
                            background: 'rgba(2, 132, 199, 0.4)',
                            border: '1px solid rgba(56, 189, 248, 0.5)',
                            borderRadius: '4px',
                            color: '#38bdf8',
                            fontSize: '9.5px',
                            cursor: 'pointer',
                          }}
                        >
                          Fly Here
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Footer Actions */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '14px 20px',
            background: 'rgba(7, 16, 32, 0.95)',
            borderTop: '1px solid rgba(255, 255, 255, 0.08)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', color: '#94a3b8' }}>
            <span>🌀</span>
            <span>Current Center: {currentSystem.coordinates.lat}°N, {currentSystem.coordinates.lng}°E</span>
          </div>

          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              onClick={() => handleFly(currentSystem.coordinates.lat, currentSystem.coordinates.lng)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 16px',
                background: 'linear-gradient(135deg, #0284c7 0%, #0369a1 100%)',
                border: '1px solid #38bdf8',
                borderRadius: '6px',
                color: '#ffffff',
                fontSize: '12px',
                fontWeight: 700,
                cursor: 'pointer',
                boxShadow: '0 2px 10px rgba(2, 132, 199, 0.4)',
              }}
            >
              <span>🛰️</span>
              <span>Fly 3D Globe to Storm Center</span>
            </button>

            <button
              onClick={onClose}
              style={{
                padding: '8px 16px',
                background: 'rgba(15, 23, 42, 0.8)',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                borderRadius: '6px',
                color: '#94a3b8',
                fontSize: '12px',
                cursor: 'pointer',
              }}
            >
              Close Dossier
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default TropicalActivityModal;
