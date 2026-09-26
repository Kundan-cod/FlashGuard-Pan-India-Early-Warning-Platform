import React from 'react';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  units: 'metric' | 'imperial';
  onUnitsChange: (units: 'metric' | 'imperial') => void;
  labelDensity: 'all' | 'medium' | 'minimal';
  onLabelDensityChange: (d: 'all' | 'medium' | 'minimal') => void;
  atmosphereGlow: boolean;
  onAtmosphereGlowChange: (val: boolean) => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({
  isOpen,
  onClose,
  units,
  onUnitsChange,
  labelDensity,
  onLabelDensityChange,
  atmosphereGlow,
  onAtmosphereGlowChange,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fg-modal-overlay" onClick={onClose}>
      <div
        className="fg-modal-box"
        style={{ width: '560px', maxWidth: '92vw' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="fg-modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="2">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
            <div>
              <h2 style={{ fontSize: '16px', fontWeight: 800, color: '#ffffff' }}>System & Display Preferences</h2>
              <p style={{ fontSize: '11px', color: '#94a3b8' }}>Configure visual rendering, units, and map behavior</p>
            </div>
          </div>
          <button className="drawer-close-btn" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="fg-modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Unit selection */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: '13px', fontWeight: 700, color: '#ffffff' }}>Measurement Units</div>
              <div style={{ fontSize: '11px', color: '#94a3b8' }}>Precipitation in mm/hr, elevation in meters</div>
            </div>
            <div style={{ display: 'flex', background: 'rgba(10, 22, 45, 0.7)', borderRadius: '6px', padding: '3px', border: '1px solid rgba(30, 60, 100, 0.5)' }}>
              <button
                className={`timeline-pill-btn ${units === 'metric' ? 'active' : ''}`}
                onClick={() => onUnitsChange('metric')}
              >
                Metric (mm, m)
              </button>
              <button
                className={`timeline-pill-btn ${units === 'imperial' ? 'active' : ''}`}
                onClick={() => onUnitsChange('imperial')}
              >
                Imperial (in, ft)
              </button>
            </div>
          </div>

          {/* Label Density */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: '13px', fontWeight: 700, color: '#ffffff' }}>Map Label Density</div>
              <div style={{ fontSize: '11px', color: '#94a3b8' }}>Controls countries, states, districts, and village markers</div>
            </div>
            <div style={{ display: 'flex', background: 'rgba(10, 22, 45, 0.7)', borderRadius: '6px', padding: '3px', border: '1px solid rgba(30, 60, 100, 0.5)' }}>
              <button
                className={`timeline-pill-btn ${labelDensity === 'all' ? 'active' : ''}`}
                onClick={() => onLabelDensityChange('all')}
              >
                Full (All)
              </button>
              <button
                className={`timeline-pill-btn ${labelDensity === 'medium' ? 'active' : ''}`}
                onClick={() => onLabelDensityChange('medium')}
              >
                Standard
              </button>
              <button
                className={`timeline-pill-btn ${labelDensity === 'minimal' ? 'active' : ''}`}
                onClick={() => onLabelDensityChange('minimal')}
              >
                Minimal
              </button>
            </div>
          </div>

          {/* Atmosphere Glow */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: '13px', fontWeight: 700, color: '#ffffff' }}>Atmospheric Horizon Shader</div>
              <div style={{ fontSize: '11px', color: '#94a3b8' }}>Photorealistic limb glow around the Earth's circumference</div>
            </div>
            <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={atmosphereGlow}
                onChange={(e) => onAtmosphereGlowChange(e.target.checked)}
                className="fg-checkbox"
              />
            </label>
          </div>

          {/* Hardware Acceleration Note */}
          <div style={{ background: 'rgba(15, 23, 42, 0.85)', borderRadius: '6px', padding: '10px 14px', border: '1px solid rgba(45, 80, 140, 0.4)' }}>
            <div style={{ fontSize: '10.5px', color: '#38bdf8', fontWeight: 700 }}>GRAPHICS ACCELERATION: ACTIVE</div>
            <div style={{ fontSize: '10px', color: '#94a3b8' }}>
              WebGL 2.0 with ACES Filmic Tone Mapping and Antialiasing is active. 3D Globe camera smoothly interpolates orientation.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
