import React, { useState, useEffect } from 'react';
import { LocationRisk } from '../types';
import { api } from '../api';

interface VillageDetailDrawerProps {
  location: LocationRisk | null;
  onClose: () => void;
  onOpenMapLibreView?: () => void;
  onOpenAlertsForVillage?: (location: LocationRisk) => void;
}

type BriefingPersona = 'PUBLIC_ALERT' | 'PUBLIC_ALERT_HINDI' | 'NDRF_TACTICAL' | 'EXECUTIVE_SUMMARY';

export const VillageDetailDrawer: React.FC<VillageDetailDrawerProps> = ({
  location,
  onClose,
  onOpenAlertsForVillage,
}) => {
  const [persona, setPersona] = useState<BriefingPersona>('PUBLIC_ALERT');
  const [briefingText, setBriefingText] = useState<string>('');
  const [engineName, setEngineName] = useState<string>('Tier 2 AI Engine');
  const [isLiveLLM, setIsLiveLLM] = useState<boolean>(false);
  const [loadingBriefing, setLoadingBriefing] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);
  const [speaking, setSpeaking] = useState<boolean>(false);

  const locId = location ? (location.location_id ?? location.id) : undefined;

  useEffect(() => {
    if (!location) return;
    loadBriefing(persona);
  }, [locId, persona]);

  const loadBriefing = async (targetPersona: BriefingPersona) => {
    if (!location || locId === undefined) return;
    setLoadingBriefing(true);
    try {
      const res = await api.briefing(Number(locId), targetPersona);
      setBriefingText(res.briefing);
      setEngineName(res.engine);
      setIsLiveLLM(Boolean(res.is_live_llm));
    } catch {
      // Offline fallback generation if API network is interrupted
      const isHi = targetPersona === 'PUBLIC_ALERT_HINDI';
      const isNDRF = targetPersona === 'NDRF_TACTICAL';
      const isDM = targetPersona === 'EXECUTIVE_SUMMARY';
      
      if (isHi) {
        setBriefingText(
          `### 🚨 आपातकालीन जन-चेतावनी: ${location.name} (${location.district})\n\n` +
          `**खतरे की स्थिति:** **${location.risk_level} चेतावनी** | सुरक्षित निकासी समय: **${location.lead_time_hours} घंटे**\n\n` +
          `${location.name} क्षेत्र में भारी वर्षा (${location.current_rainfall_mm.toFixed(0)} मिमी/घंटा) एवं अत्यधिक मृदा नमी (${(location.soil_moisture_saturation * 100).toFixed(0)}%) के कारण अचानक बाढ़ (${(location.flood_probability * 100).toFixed(0)}%) तथा भूस्खलन (${(location.landslide_probability * 100).toFixed(0)}%) का गंभीर संकट उत्पन्न हो गया है।\n\n` +
          `**महत्वपूर्ण जीवन-रक्षा निर्देश:**\n` +
          `1. **ऊंचे स्थानों की ओर जाएं:** नदी घाटी एवं ${location.slope_degrees.toFixed(1)}° से अधिक ढलान वाले क्षेत्रों के निवासी तुरंत सुरक्षित पंचायत आश्रयों में जाएं।\n` +
          `2. **नालों व जलभराव से दूर रहें:** उफान पर चल रही नदियों और पुलियों को पार करने का प्रयास कतई न करें।\n` +
          `3. **आपातकालीन सहायता:** किसी भी आपात स्थिति में तुरंत जिला आपदा नियंत्रण कक्ष हेल्पलाइन नंबर **1077** अथवा **112** पर संपर्क करें।`
        );
      } else if (isNDRF) {
        setBriefingText(
          `### 🛡️ NDRF TACTICAL OPERATION BRIEFING: ${location.name.toUpperCase()}\n\n` +
          `**SEVERITY:** ${location.risk_level} PRIORITY | Response Window: ${location.lead_time_hours} Hours | Confidence: ${(location.confidence_score * 100).toFixed(0)}%\n\n` +
          `**1. PRIMARY DYNAMICS:**\n` +
          `Combined risk index elevated by antecedent soil saturation (${(location.soil_moisture_saturation * 100).toFixed(0)}%) coupled with intense precipitation pulse (${location.current_rainfall_mm.toFixed(0)} mm/h). Catchment runoff velocity indicates imminent debris flow across ${location.slope_degrees.toFixed(1)}° slope profile.\n\n` +
          `**2. EVACUATION CORRIDORS & ACCESS CHOKE POINTS:**\n` +
          `- Primary arterial route vulnerable to road blockage from toe-slope slumping within 30 minutes.\n` +
          `- River surge (+${location.river_level_rise_m.toFixed(1)}m) threatening low-lying causeways.\n\n` +
          `**3. TACTICAL DEPLOYMENT DIRECTIVES:**\n` +
          `- Pre-stage QRT (Quick Response Team) with hydraulic cutters and heavy earthmoving machinery.\n` +
          `- Equip rescue units with inflatable motorized boats, lifebuoys, and SAT-phone communication backups.`
        );
      } else if (isDM) {
        setBriefingText(
          `### 🏛️ DISTRICT MAGISTRATE EXECUTIVE SUMMARY: ${location.name.toUpperCase()}\n\n` +
          `**INCIDENT CLASSIFICATION:** ${location.risk_level} MULTI-HAZARD ESCALATION (${location.district})\n` +
          `Dual Hazard Probabilities: Flash Flood ${(location.flood_probability * 100).toFixed(0)}% | Landslide ${(location.landslide_probability * 100).toFixed(0)}%\n\n` +
          `**1. SITUATION APPRAISAL:**\n` +
          `Sensor telemetry detects dangerous hydro-meteorological convergence. Rainfall of ${location.current_rainfall_mm.toFixed(0)} mm/hr exceeding drainage absorption capacity. Population at risk requires proactive precautionary evacuation.\n\n` +
          `**2. INTER-AGENCY MOBILIZATION DIRECTIVE:**\n` +
          `- **Revenue & Panchayat:** Initiate orderly relocation of vulnerable households to pre-identified community halls.\n` +
          `- **Public Works Dept (PWD):** Standby JCBs along vulnerable hill road cuts to maintain emergency corridor clearance.\n` +
          `- **Health Dept:** Activate Primary Health Centre trauma bays and ensure clean drinking water tankers are positioned.\n\n` +
          `**3. STRATEGIC PRIORITIES (T+0 TO T+6 HOURS):**\n` +
          `Activate Emergency Operation Centre (EOC) Level-2 protocol; issue public broadcasting sirens; coordinate with SDRF/NDRF 5th Battalion for staging.`
        );
      } else {
        setBriefingText(
          `### 🚨 EMERGENCY ADVISORY: ${location.name.toUpperCase()} (${location.district})\n\n` +
          `**HAZARD STATUS:** **${location.risk_level} ALERT** | Evacuation Window: **${location.lead_time_hours} Hours**\n\n` +
          `Torrential rainfall (${location.current_rainfall_mm.toFixed(0)} mm/hr) and saturated hillsides (${(location.soil_moisture_saturation * 100).toFixed(0)}%) have triggered critical flash flood (${(location.flood_probability * 100).toFixed(0)}%) ` +
          `and landslide (${(location.landslide_probability * 100).toFixed(0)}%) thresholds in ${location.name}.\n\n` +
          `**IMMEDIATE LIFE-SAFETY ACTIONS:**\n` +
          `1. **MOVE TO HIGHER GROUND:** Families in river basin corridors and below ${location.slope_degrees.toFixed(1)}° slopes must immediately relocate to designated Panchayat shelter points.\n` +
          `2. **AVOID WATER CROSSINGS:** Do not attempt to cross culverts or riverbanks (river surge currently at +${location.river_level_rise_m.toFixed(1)}m above baseline).\n` +
          `3. **COMMUNICATION & ASSISTANCE:** Keep mobile phones charged, monitor community sirens, and contact District Emergency Control Room (1077 / 112) for immediate distress assistance.`
        );
      }
      setEngineName('FlashGuard Offline AI Synthesis');
      setIsLiveLLM(false);
    } finally {
      setLoadingBriefing(false);
    }
  };

  const handleCopy = () => {
    if (!briefingText) return;
    navigator.clipboard.writeText(briefingText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleToggleSpeak = () => {
    if (!('speechSynthesis' in window)) return;
    if (speaking) {
      window.speechSynthesis.cancel();
      setSpeaking(false);
      return;
    }
    const cleanText = briefingText.replace(/[#*`_]/g, '');
    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.rate = 1.0;
    utterance.lang = persona === 'PUBLIC_ALERT_HINDI' ? 'hi-IN' : 'en-IN';
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(utterance);
    setSpeaking(true);
  };

  if (!location) return null;

  const isCritical = location.risk_level === 'CRITICAL';
  const isHigh = location.risk_level === 'HIGH';
  const riskClass = isCritical ? 'critical' : isHigh ? 'high' : 'moderate';

  return (
    <div className="fg-drawer-backdrop" onClick={onClose}>
      <div className="fg-drawer-panel" onClick={(e) => e.stopPropagation()}>
        {/* Drawer Header */}
        <div className="fg-drawer-header">
          <div className="drawer-title-group">
            <div className="drawer-subtitle">
              {location.block} Block • {location.district} District • {location.state}
            </div>
            <h2 className="drawer-title">{location.name}</h2>
          </div>
          <button className="drawer-close-btn" onClick={onClose}>
            ×
          </button>
        </div>

        {/* Risk Banner */}
        <div className={`drawer-risk-banner banner-${riskClass}`}>
          <div className="banner-left">
            <span className="banner-tier-label">{location.risk_level} HAZARD LEVEL</span>
            <span className="banner-score">{(location.overall_risk * 100).toFixed(1)}% Combined Threat Index</span>
          </div>
          <div className="banner-right">
            <span className="banner-lead-time">Est. Lead Time: {location.lead_time_hours} Hours</span>
            <span className="banner-confidence">
              Model Confidence: {(location.confidence_score * 100).toFixed(0)}%
            </span>
          </div>
        </div>

        {/* AI MODEL INFERENCE & METADATA BLOCK */}
        <div style={{
          background: 'rgba(8, 18, 36, 0.85)',
          border: '1px solid rgba(56, 189, 248, 0.25)',
          borderRadius: '8px',
          padding: '10px 14px',
          margin: '0 16px 12px',
          display: 'flex',
          flexDirection: 'column',
          gap: '6px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '11px', fontWeight: 800, color: '#38bdf8', display: 'flex', alignItems: 'center', gap: '5px' }}>
              🤖 FLASHGUARD AI INFERENCE PIPELINE
            </span>
            <span style={{ fontSize: '9.5px', background: 'rgba(239, 68, 68, 0.18)', color: '#f87171', border: '1px solid rgba(239, 68, 68, 0.4)', borderRadius: '4px', padding: '1px 6px', fontWeight: 700 }}>
              NOT VALIDATED (DEMO)
            </span>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px', fontSize: '10px', color: '#94a3b8' }}>
            <div>• <strong style={{ color: '#e2e8f0' }}>Models:</strong> Dual GBT (Flood + Landslide)</div>
            <div>• <strong style={{ color: '#e2e8f0' }}>Calibration:</strong> Platt Sigmoid Scaling</div>
            <div>• <strong style={{ color: '#e2e8f0' }}>Decision Thresh:</strong> 0.25 (Flood) / 0.40 (Landslide)</div>
            <div>• <strong style={{ color: '#e2e8f0' }}>Confidence:</strong> Decoupled from Risk (Telemetry Quality)</div>
          </div>
        </div>

        {/* Hazard Probabilities Row */}
        <div className="drawer-prob-grid">
          <div className="drawer-prob-card">
            <div className="prob-label">Flash Flood Probability</div>
            <div className="prob-value text-blue">{(location.flood_probability * 100).toFixed(1)}%</div>
            <div className="prob-progress-bar">
              <div
                className="prob-fill bg-blue"
                style={{ width: `${location.flood_probability * 100}%` }}
              />
            </div>
          </div>

          <div className="drawer-prob-card">
            <div className="prob-label">Landslide Probability</div>
            <div className="prob-value text-amber">{(location.landslide_probability * 100).toFixed(1)}%</div>
            <div className="prob-progress-bar">
              <div
                className="prob-fill bg-amber"
                style={{ width: `${location.landslide_probability * 100}%` }}
              />
            </div>
          </div>
        </div>

        {/* CURRENT HAZARD CONDITIONS */}
        <div className="drawer-section">
          <h4 className="drawer-section-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span>⚠️</span>
            <span>CURRENT HAZARD CONDITIONS</span>
          </h4>
          <div className="drawer-telemetry-grid">
            <div className="telemetry-box">
              <span className="telemetry-label">🌧 Rainfall</span>
              <span className="telemetry-val text-cyan">
                {location.current_rainfall_mm.toFixed(0)} mm/hr
              </span>
            </div>
            <div className="telemetry-box">
              <span className="telemetry-label">💧 Soil Moisture</span>
              <span className="telemetry-val text-emerald">
                {(location.soil_moisture_saturation * 100).toFixed(0)}%
              </span>
            </div>
            <div className="telemetry-box">
              <span className="telemetry-label">🌊 River Level</span>
              <span className="telemetry-val text-amber">
                +{location.river_level_rise_m.toFixed(1)} m
              </span>
            </div>
            <div className="telemetry-box">
              <span className="telemetry-label">⛰ Slope Risk</span>
              <span className="telemetry-val text-amber">
                {location.slope_degrees > 30 ? 'HIGH' : 'MODERATE'} ({location.slope_degrees.toFixed(1)}°)
              </span>
            </div>
            <div className="telemetry-box" style={{ gridColumn: 'span 2' }}>
              <span className="telemetry-label">⚠ Combined Risk</span>
              <span
                className="telemetry-val"
                style={{ color: location.risk_level === 'CRITICAL' ? '#ef4444' : '#f97316', fontWeight: 800 }}
              >
                {location.risk_level} ({(location.overall_risk * 100).toFixed(0)}%)
              </span>
            </div>
          </div>
        </div>

        {/* WHY THIS RISK? Explainability Breakdown */}
        <div className="drawer-section">
          <h4 className="drawer-section-title">
            <span>WHY THIS RISK? (Feature Contributions)</span>
          </h4>
          <div className="feature-contrib-list">
            {[
              {
                name: 'Antecedent Soil Moisture & Rainfall',
                weight: location.soil_moisture_saturation * 0.38,
                desc: 'Ground saturation nearing 100% capacity accelerates surface runoff',
                color: '#38bdf8',
              },
              {
                name: 'Steep Catchment Slope Gradient',
                weight: Math.min(1, location.slope_degrees / 45) * 0.28,
                desc: 'High slope instability triggers accelerated debris flow velocity',
                color: '#f59e0b',
              },
              {
                name: 'Upstream River Inflow Surge',
                weight: Math.min(1, location.river_level_rise_m / 4.0) * 0.22,
                desc: 'Channel depth exceeding critical flood discharge stage',
                color: '#ef4444',
              },
              {
                name: 'GPM IMERG Extreme Precipitation Spike',
                weight: Math.min(1, location.current_rainfall_mm / 100) * 0.12,
                desc: 'Intense short-duration cloudburst over watershed crest',
                color: '#a855f7',
              },
            ].map((factor, i) => (
              <div key={i} className="feature-row">
                <div className="feature-row-top">
                  <span className="feature-name">{factor.name}</span>
                  <span className="feature-weight">+{(factor.weight * 100).toFixed(0)}% Impact</span>
                </div>
                <div className="feature-bar-wrap">
                  <div
                    className="feature-bar-fill"
                    style={{ width: `${factor.weight * 100}%`, backgroundColor: factor.color }}
                  />
                </div>
                <div className="feature-desc">{factor.desc}</div>
              </div>
            ))}
          </div>
        </div>

        {/* 🧠 AI INCIDENT COMMAND BRIEFING (Tier 2 LLM) */}
        <div className="drawer-section" style={{ border: '1px solid rgba(168, 85, 247, 0.35)', background: 'linear-gradient(180deg, rgba(168, 85, 247, 0.08) 0%, rgba(15, 23, 42, 0.6) 100%)', borderRadius: '10px', padding: '14px', marginTop: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
            <h4 style={{ margin: 0, fontSize: '13px', fontWeight: 800, color: '#d8b4fe', letterSpacing: '0.04em', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span>🧠</span>
              <span>AI INCIDENT COMMAND BRIEFING</span>
            </h4>
            <span style={{ fontSize: '10px', padding: '2px 7px', borderRadius: '4px', background: isLiveLLM ? 'rgba(34, 197, 94, 0.2)' : 'rgba(168, 85, 247, 0.2)', color: isLiveLLM ? '#4ade80' : '#c084fc', border: `1px solid ${isLiveLLM ? '#22c55e' : '#a855f7'}`, fontWeight: 700 }}>
              {isLiveLLM ? '⚡ LIVE GEMINI LLM' : '🛡️ OFFLINE AI ENGINE'}
            </span>
          </div>

          {/* Persona selector pills */}
          <div style={{ display: 'flex', gap: '6px', overflowX: 'auto', paddingBottom: '6px', marginBottom: '10px' }}>
            {[
              { id: 'PUBLIC_ALERT' as BriefingPersona, label: '📢 Public Alert (EN)' },
              { id: 'PUBLIC_ALERT_HINDI' as BriefingPersona, label: '🇮🇳 जन-चेतावनी (HI)' },
              { id: 'NDRF_TACTICAL' as BriefingPersona, label: '🛡️ NDRF Tactical' },
              { id: 'EXECUTIVE_SUMMARY' as BriefingPersona, label: '🏛️ DM Summary' },
            ].map((p) => (
              <button
                key={p.id}
                onClick={() => setPersona(p.id)}
                style={{
                  padding: '5px 9px',
                  borderRadius: '6px',
                  fontSize: '11px',
                  fontWeight: 700,
                  cursor: 'pointer',
                  border: persona === p.id ? '1px solid #c084fc' : '1px solid rgba(255, 255, 255, 0.1)',
                  background: persona === p.id ? 'rgba(168, 85, 247, 0.3)' : 'rgba(30, 41, 59, 0.6)',
                  color: persona === p.id ? '#ffffff' : '#94a3b8',
                  whiteSpace: 'nowrap',
                  transition: 'all 0.15s ease',
                }}
              >
                {p.label}
              </button>
            ))}
          </div>

          {/* Briefing text content box */}
          <div style={{ background: 'rgba(10, 15, 29, 0.85)', borderRadius: '8px', padding: '12px', border: '1px solid rgba(255, 255, 255, 0.08)', minHeight: '120px' }}>
            {loadingBriefing ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100px', color: '#a855f7', fontSize: '12px', gap: '8px' }}>
                <span className="animate-spin">⚡</span>
                <span>Synthesizing situational emergency briefing...</span>
              </div>
            ) : (
              <div style={{ fontSize: '12px', lineHeight: '1.55', color: '#e2e8f0', whiteSpace: 'pre-wrap' }}>
                {briefingText}
              </div>
            )}
          </div>

          {/* Bottom actions: Copy & Text-to-speech */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '10px' }}>
            <span style={{ fontSize: '10px', color: '#64748b' }}>
              Engine: {engineName}
            </span>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={handleToggleSpeak}
                style={{
                  background: speaking ? 'rgba(239, 68, 68, 0.25)' : 'rgba(255, 255, 255, 0.08)',
                  border: speaking ? '1px solid #ef4444' : '1px solid rgba(255, 255, 255, 0.15)',
                  color: speaking ? '#f87171' : '#cbd5e1',
                  borderRadius: '5px',
                  padding: '4px 8px',
                  fontSize: '11px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {speaking ? '⏹ Stop Audio' : '🔊 Read Aloud'}
              </button>
              <button
                onClick={handleCopy}
                style={{
                  background: copied ? 'rgba(34, 197, 94, 0.25)' : 'rgba(168, 85, 247, 0.25)',
                  border: copied ? '1px solid #22c55e' : '1px solid #a855f7',
                  color: copied ? '#4ade80' : '#e9d5ff',
                  borderRadius: '5px',
                  padding: '4px 10px',
                  fontSize: '11px',
                  fontWeight: 700,
                  cursor: 'pointer',
                }}
              >
                {copied ? '✓ Copied' : '📋 Copy Alert'}
              </button>
            </div>
          </div>

          {onOpenAlertsForVillage && (
            <button
              onClick={() => onOpenAlertsForVillage(location)}
              style={{
                width: '100%',
                marginTop: '12px',
                background: 'linear-gradient(135deg, #ef4444 0%, #b91c1c 100%)',
                border: 'none',
                borderRadius: '6px',
                padding: '10px 14px',
                color: '#ffffff',
                fontSize: '12px',
                fontWeight: 800,
                letterSpacing: '0.5px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                boxShadow: '0 4px 14px rgba(239, 68, 68, 0.4)',
              }}
            >
              <span>🚨</span>
              <span>ISSUE ACTIONABLE EVACUATION ALERT (SMS)</span>
            </button>
          )}
        </div>

        {/* Decision Support & Honesty Disclaimer */}
        <div className="drawer-disclaimer">
          <div className="disclaimer-badge">DECISION SUPPORT ONLY</div>
          <p>
            FlashGuard provides predictive risk guidance using AI/ML early warning models and historical
            replay data. Operational field evacuations and incident response must strictly follow official directives
            issued by the National Disaster Response Force (NDRF), State Disaster Management Authority (SDMA), and
            District Emergency Operation Centers.
          </p>
        </div>
      </div>
    </div>
  );
};
