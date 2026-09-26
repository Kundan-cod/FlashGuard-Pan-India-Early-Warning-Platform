import React from 'react';
import { AccumulationPeriod, WeatherMode } from '../types';

interface BottomTimelineProps {
  currentStepIndex: number;
  totalSteps: number;
  currentTimeStr: string;
  isPlaying: boolean;
  onTogglePlay: () => void;
  onStepChange: (index: number) => void;
  playbackSpeed: number;
  onSpeedChange: (speed: number) => void;
  accumulationPeriod: AccumulationPeriod;
  onPeriodChange: (period: AccumulationPeriod) => void;
  weatherMode?: WeatherMode;
  onToggleWeatherMode?: () => void;
  onRefreshLive?: () => Promise<void> | void;
}

export const BottomTimeline: React.FC<BottomTimelineProps> = ({
  currentStepIndex,
  totalSteps,
  currentTimeStr = '2026-07-15 10:00:00',
  isPlaying,
  onTogglePlay,
  onStepChange,
  playbackSpeed,
  onSpeedChange,
  accumulationPeriod,
  onPeriodChange,
  weatherMode = 'replay',
  onToggleWeatherMode,
  onRefreshLive,
}) => {
  const [isSyncing, setIsSyncing] = React.useState(false);
  const [syncFeedback, setSyncFeedback] = React.useState<string | null>(null);

  const handleManualSync = async () => {
    if (isSyncing) return;
    setIsSyncing(true);
    setSyncFeedback('Querying ISRO MOSDAC...');
    try {
      if (onRefreshLive) {
        await onRefreshLive();
      }
      setSyncFeedback('Synced with INSAT-3DS');
      setTimeout(() => setSyncFeedback(null), 3500);
    } catch {
      setSyncFeedback('Sync failed');
      setTimeout(() => setSyncFeedback(null), 2500);
    } finally {
      setIsSyncing(false);
    }
  };
  const speeds = [0.5, 1, 2, 4];
  const periods: AccumulationPeriod[] = ['30m', '3h', '24h', '3d', '7d'];
  const periodLabels: Record<AccumulationPeriod, string> = {
    '30m': '30 min',
    '3h': '3 hr',
    '24h': '24 hr',
    '3d': '3 day',
    '7d': '7 day',
  };

  const handlePrev = () => {
    if (currentStepIndex > 0) {
      onStepChange(currentStepIndex - 1);
    }
  };

  const handleNext = () => {
    if (currentStepIndex < totalSteps - 1) {
      onStepChange(currentStepIndex + 1);
    }
  };

  // Timeline track tick markers
  const timelineMarkers = [
    { label: '07-14 00:00', percent: 0, color: undefined },
    { label: '07-14 12:00', percent: 25, color: '#f59e0b' }, // yellow
    { label: '07-15 00:00', percent: 50, color: '#ef4444' }, // red
    { label: '07-15 12:00', percent: 75, color: '#f59e0b' }, // yellow
    { label: '07-16 00:00', percent: 100, color: '#f59e0b' }, // yellow
  ];

  const currentPercent = (currentStepIndex / Math.max(1, totalSteps - 1)) * 100;

  return (
    <div className="fg-bottom-timeline">
      {/* Top Row: Transport & Settings */}
      <div className="timeline-top-row">
        {/* Left: Time Label & Date */}
        <div className="timeline-time-info">
          <span className="timeline-label" style={{ color: weatherMode === 'live' ? '#4ade80' : undefined }}>
            {weatherMode === 'live' ? 'LIVE SATELLITE (UTC)' : 'TIME CONTROL (UTC)'}
          </span>
          <div
            className="timeline-datetime-badge"
            style={weatherMode === 'live' ? { borderColor: 'rgba(74, 222, 128, 0.4)', background: 'rgba(74, 222, 128, 0.08)' } : undefined}
          >
            {weatherMode === 'live' ? (
              <div style={{ width: 7, height: 7, borderRadius: '50%', backgroundColor: '#4ade80', animation: 'pulse 1.8s infinite' }} />
            ) : (
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" strokeWidth="2">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            )}
            <span className="datetime-text" style={weatherMode === 'live' ? { color: '#4ade80' } : undefined}>
              {weatherMode === 'live' ? '2026-09-07 16:00:00 UTC' : currentTimeStr}
            </span>
          </div>
        </div>

        {/* Center: Playback Transport or Live Status */}
        {weatherMode === 'live' ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                background: 'rgba(34, 197, 94, 0.12)',
                border: '1px solid rgba(34, 197, 94, 0.35)',
                padding: '6px 12px',
                borderRadius: '8px',
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
              <span style={{ fontSize: '11px', color: '#4ade80', fontWeight: 600, letterSpacing: '0.03em' }}>
                LIVE FEED: SAC-ISRO INSAT-3DS (16:00 UTC)
              </span>
            </div>

            {/* Manual Sync / Auto-Poll Button */}
            <button
              onClick={handleManualSync}
              disabled={isSyncing}
              style={{
                background: isSyncing ? 'rgba(56, 189, 248, 0.2)' : 'rgba(34, 197, 94, 0.16)',
                border: isSyncing ? '1px solid rgba(56, 189, 248, 0.5)' : '1px solid rgba(34, 197, 94, 0.45)',
                color: isSyncing ? '#38bdf8' : '#4ade80',
                borderRadius: '8px',
                padding: '6px 12px',
                fontSize: '11px',
                fontWeight: 700,
                cursor: isSyncing ? 'wait' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                transition: 'all 0.2s ease',
              }}
              title="Poll SAC-ISRO MOSDAC servers for latest satellite granule pass"
            >
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                style={{
                  transformOrigin: 'center',
                  animation: isSyncing ? 'spin 0.8s linear infinite' : undefined,
                }}
              >
                <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
              </svg>
              <span>{syncFeedback || 'Auto-Sync: Active (30s)'}</span>
            </button>

            {onToggleWeatherMode && (
              <button
                onClick={onToggleWeatherMode}
                style={{
                  background: 'rgba(245, 158, 11, 0.18)',
                  border: '1px solid rgba(245, 158, 11, 0.45)',
                  color: '#fbbf24',
                  borderRadius: '8px',
                  padding: '6px 12px',
                  fontSize: '11px',
                  fontWeight: 700,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}
                title="Switch to Storm Replay Mode to test cloudburst warning escalation"
              >
                <span>Test Storm Replay</span>
                <span style={{ fontSize: '12px' }}>▶</span>
              </button>
            )}
          </div>
        ) : (
          <div className="timeline-transport">
            <button
              className="transport-step-btn"
              onClick={handlePrev}
              disabled={currentStepIndex === 0}
              title="Previous Timestep"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="19 20 9 12 19 4 19 20" />
                <line x1="5" y1="19" x2="5" y2="5" stroke="currentColor" strokeWidth="2.5" />
              </svg>
            </button>

            <button
              className={`transport-play-btn ${isPlaying ? 'playing' : ''}`}
              onClick={onTogglePlay}
              title={isPlaying ? 'Pause Replay' : 'Play Replay'}
            >
              {isPlaying ? (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                  <rect x="6" y="4" width="4" height="16" rx="1" />
                  <rect x="14" y="4" width="4" height="16" rx="1" />
                </svg>
              ) : (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style={{ marginLeft: 2 }}>
                  <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
              )}
            </button>

            <button
              className="transport-step-btn"
              onClick={handleNext}
              disabled={currentStepIndex === totalSteps - 1}
              title="Next Timestep"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <polygon points="5 4 15 12 5 20 5 4" />
                <line x1="19" y1="5" x2="19" y2="19" stroke="currentColor" strokeWidth="2.5" />
              </svg>
            </button>
          </div>
        )}

        {/* Right Controls: Speed & Accumulation */}
        <div className="timeline-settings">
          {/* Speed Pills */}
          <div className="timeline-pill-group">
            {speeds.map((s) => (
              <button
                key={s}
                className={`timeline-pill-btn ${playbackSpeed === s ? 'active' : ''}`}
                onClick={() => onSpeedChange(s)}
              >
                {s}x
              </button>
            ))}
          </div>

          <div className="timeline-divider" />

          {/* Accumulation Period Pills */}
          <div className="timeline-accumulation-group">
            <span className="accumulation-label">Accumulation Period</span>
            <div className="timeline-pill-group">
              {periods.map((p) => (
                <button
                  key={p}
                  className={`timeline-pill-btn ${accumulationPeriod === p ? 'active' : ''}`}
                  onClick={() => onPeriodChange(p)}
                >
                  {periodLabels[p]}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Row: Scrubber Track with Event Markers */}
      <div className="timeline-track-container">
        {weatherMode === 'live' ? (
          <>
            <div className="timeline-track" style={{ cursor: 'default' }}>
              {/* Progress fill indicating real-time live synchronization */}
              <div
                className="timeline-fill"
                style={{
                  width: '100%',
                  background: 'linear-gradient(90deg, rgba(34, 197, 94, 0.2) 0%, rgba(34, 197, 94, 0.6) 75%, #4ade80 100%)',
                  boxShadow: '0 0 12px rgba(74, 222, 128, 0.4)',
                }}
              />
              {/* Live Satellite Orbit Markers */}
              {[
                { label: '14:30 UTC', percent: 0 },
                { label: '15:00 UTC', percent: 33 },
                { label: '15:30 UTC', percent: 66 },
                { label: '16:00 UTC (CURRENT PASS)', percent: 100, color: '#4ade80' },
              ].map((m, idx) => (
                <div key={idx} className="timeline-marker" style={{ left: `${m.percent}%` }}>
                  <div
                    className="marker-dot"
                    style={{
                      backgroundColor: m.color || 'rgba(74, 222, 128, 0.6)',
                      boxShadow: m.color ? `0 0 8px ${m.color}` : undefined,
                    }}
                  />
                </div>
              ))}
              {/* Live Active Scrubber Handle */}
              <div
                className="timeline-handle"
                style={{
                  left: '100%',
                  backgroundColor: '#4ade80',
                  boxShadow: '0 0 12px #4ade80',
                  transform: 'translateX(-50%)',
                }}
              />
            </div>
            {/* Timestamp Labels below track */}
            <div className="timeline-labels-row">
              {[
                { label: '14:30 UTC · Pre-Pass', percent: 0 },
                { label: '15:00 UTC · Scan T-60m', percent: 33 },
                { label: '15:30 UTC · Scan T-30m', percent: 66 },
                { label: '16:00 UTC · ACTIVE PASS (3SIMG_07SEP2026_1600)', percent: 100 },
              ].map((m, idx) => (
                <span
                  key={idx}
                  className="timeline-tick-label"
                  style={{
                    left: `${m.percent}%`,
                    color: idx === 3 ? '#4ade80' : 'rgba(255, 255, 255, 0.5)',
                    fontWeight: idx === 3 ? 700 : 500,
                  }}
                >
                  {m.label}
                </span>
              ))}
            </div>
          </>
        ) : (
          <>
            <div
              className="timeline-track"
              onClick={(e) => {
                const rect = e.currentTarget.getBoundingClientRect();
                const clickPercent = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
                const newIndex = Math.round(clickPercent * (totalSteps - 1));
                onStepChange(newIndex);
              }}
            >
              {/* Progress fill */}
              <div className="timeline-fill" style={{ width: `${currentPercent}%` }} />

              {/* Markers along track */}
              {timelineMarkers.map((m, idx) => (
                <div
                  key={idx}
                  className="timeline-marker"
                  style={{ left: `${m.percent}%` }}
                >
                  {m.color && (
                    <div
                      className="marker-dot"
                      style={{ backgroundColor: m.color, boxShadow: `0 0 6px ${m.color}` }}
                    />
                  )}
                </div>
              ))}

              {/* Current Active Scrubber Handle */}
              <div
                className="timeline-handle"
                style={{ left: `${currentPercent}%` }}
              />
            </div>

            {/* Timestamp Labels below track */}
            <div className="timeline-labels-row">
              {timelineMarkers.map((m, idx) => (
                <span key={idx} className="timeline-tick-label" style={{ left: `${m.percent}%` }}>
                  {m.label}
                </span>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
};
