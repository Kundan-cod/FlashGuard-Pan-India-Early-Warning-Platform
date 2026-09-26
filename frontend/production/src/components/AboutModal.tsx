import React from "react";
import type { SourceHealth } from "../types";

interface AboutModalProps {
  isOpen: boolean;
  onClose: () => void;
  sources: SourceHealth[];
}

export const AboutModal: React.FC<AboutModalProps> = ({ isOpen, onClose, sources }) => {
  if (!isOpen) return null;

  return (
    <div className="fg-modal-overlay" onClick={onClose}>
      <div
        className="fg-modal-box"
        style={{ width: "720px" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="fg-modal-header">
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span style={{ fontSize: "20px" }}>ℹ️</span>
            <div>
              <h2 style={{ fontSize: "16px", fontWeight: 700, color: "#ffffff" }}>
                About FlashGuard · SIH 2026 PS 26192
              </h2>
              <p style={{ fontSize: "11px", color: "#94a3b8" }}>
                Flash Flood &amp; Landslide Prediction System for Hilly Regions using Multi-Source Data
              </p>
            </div>
          </div>
          <button className="fg-btn-icon" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="fg-modal-body">
          {/* Mission & Problem Statement */}
          <div className="fg-card">
            <div className="fg-card-title">
              <span>System Objective</span>
            </div>
            <p style={{ fontSize: "12px", color: "#cbd5e1", lineHeight: 1.5 }}>
              FlashGuard is built to solve <strong>SIH 2026 Problem Statement 26192</strong>.
              Hilly terrains in India (e.g. Uttarakhand, Himachal Pradesh) suffer from sudden
              cloudburst-triggered flash floods and slope failures with extremely short lead times.
              FlashGuard fuses spaceborne precipitation radar (NASA GPM), soil moisture (SMAP),
              geological susceptibility (GSI), river telemetry (CWC), and high-resolution terrain
              (ISRO Bhuvan) to provide automated, village-level early warning alerts with
              estimated 15–45 minute lead times.
            </p>
          </div>

          {/* Real Data Honesty Framework */}
          <div
            style={{
              background: "rgba(239, 68, 68, 0.1)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: "8px",
              padding: "12px 14px",
              fontSize: "12px",
              color: "#fecaca",
              lineHeight: 1.5,
            }}
          >
            <strong>🛡️ Real Data Honesty Posture:</strong>
            <p style={{ marginTop: "4px" }}>
              In compliance with SIH scientific evaluation protocols, FlashGuard never fabricates
              credentials or labels simulated/replay feeds as LIVE. Every data source reports its
              actual operational status:
            </p>
            <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "8px" }}>
              <span className="fg-status-tag live">LIVE</span>
              <span className="fg-status-tag nrt">NRT</span>
              <span className="fg-status-tag replay">REPLAY</span>
              <span className="fg-status-tag simulated">SIMULATED</span>
              <span className="fg-status-tag discovery">DISCOVERY_ONLY</span>
              <span className="fg-status-tag not-config">NOT_CONFIGURED</span>
            </div>
          </div>

          {/* Data Sources Architecture Grid */}
          <div className="fg-card">
            <div className="fg-card-title">
              <span>11-Source Multi-Sensor Registry ({sources.length} Cataloged)</span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "6px" }}>
              {sources.map((s) => (
                <div
                  key={s.source}
                  style={{
                    background: "rgba(10, 16, 26, 0.6)",
                    border: "1px solid var(--border-dim)",
                    borderRadius: "6px",
                    padding: "6px 8px",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    fontSize: "11px",
                  }}
                >
                  <span style={{ fontWeight: 600, color: "#ffffff" }}>{s.source.toUpperCase()}</span>
                  <span
                    style={{
                      fontSize: "9.5px",
                      fontFamily: "var(--font-mono)",
                      color:
                        s.status.toLowerCase() === "live" || s.status.toLowerCase() === "online"
                          ? "#34d399"
                          : s.status.toLowerCase() === "replay"
                          ? "#c084fc"
                          : "#94a3b8",
                    }}
                  >
                    {s.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
