import React, { useEffect, useState } from "react";
import { api } from "../api";
import type { ModelInfo, FeatureImportance } from "../types";

interface ModelInfoModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ModelInfoModal: React.FC<ModelInfoModalProps> = ({ isOpen, onClose }) => {
  const [info, setInfo] = useState<ModelInfo | null>(null);
  const [importance, setImportance] = useState<FeatureImportance | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    Promise.all([api.modelInfo(), api.featureImportance()])
      .then(([inf, imp]) => {
        setInfo(inf);
        setImportance(imp);
      })
      .catch((err) => console.error("Error fetching model info:", err))
      .finally(() => setLoading(false));
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="fg-modal-overlay" onClick={onClose}>
      <div
        className="fg-modal-box"
        style={{ width: "680px" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="fg-modal-header">
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span style={{ fontSize: "20px" }}>🧠</span>
            <div>
              <h2 style={{ fontSize: "16px", fontWeight: 700, color: "#ffffff" }}>
                Hazard Modeling &amp; Explainability
              </h2>
              <p style={{ fontSize: "11px", color: "#94a3b8" }}>
                SIH 2026 PS 26192 Transparent ML Architecture
              </p>
            </div>
          </div>
          <button className="fg-btn-icon" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="fg-modal-body">
          {loading ? (
            <div style={{ textAlign: "center", padding: "30px 0", color: "#94a3b8" }}>
              Querying model registry...
            </div>
          ) : info ? (
            <>
              {/* Active Pipeline Status */}
              <div className="fg-card">
                <div className="fg-card-title">
                  <span>Current Runtime Implementation</span>
                  <span
                    className="fg-pill"
                    style={{
                      background: info.use_trained_models
                        ? "rgba(16, 185, 129, 0.2)"
                        : "rgba(139, 92, 246, 0.2)",
                      color: info.use_trained_models ? "#34d399" : "#c084fc",
                    }}
                  >
                    {info.use_trained_models
                      ? "OPT-IN TRAINED GBT ACTIVE"
                      : "TRANSPARENT DEMO SCORER (DEFAULT)"}
                  </span>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
                  <div className="fg-kpi-card">
                    <span className="fg-kpi-label">Flood Model</span>
                    <span style={{ fontSize: "13px", fontWeight: 700, color: "#38bdf8" }}>
                      {info.hazards.flood.implementation}
                    </span>
                    <span style={{ fontSize: "10px", color: "#64748b", marginTop: "2px" }}>
                      v: {info.hazards.flood.version}
                    </span>
                  </div>

                  <div className="fg-kpi-card">
                    <span className="fg-kpi-label">Landslide Model</span>
                    <span style={{ fontSize: "13px", fontWeight: 700, color: "#f97316" }}>
                      {info.hazards.landslide.implementation}
                    </span>
                    <span style={{ fontSize: "10px", color: "#64748b", marginTop: "2px" }}>
                      v: {info.hazards.landslide.version}
                    </span>
                  </div>
                </div>
              </div>

              {/* Feature Importance / Weights */}
              {importance && (
                <div className="fg-card">
                  <div className="fg-card-title">
                    <span>Feature Importance &amp; Weight Architecture</span>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                    <div>
                      <div style={{ fontSize: "12px", fontWeight: 600, color: "#38bdf8", marginBottom: "4px" }}>
                        🌊 Flood Hazard Drivers
                      </div>
                      <div style={{ fontSize: "11px", color: "#94a3b8" }}>
                        {importance.flood.note || "Gradient-boosted decision tree gain importance"}
                      </div>
                      {importance.flood.features && (
                        <div style={{ display: "flex", flexDirection: "column", gap: "4px", marginTop: "6px" }}>
                          {Object.entries(importance.flood.features).map(([feat, weight]) => (
                            <div key={feat} style={{ display: "flex", justifyContent: "space-between", fontSize: "11.5px" }}>
                              <span style={{ color: "#cbd5e1" }}>{feat}</span>
                              <span style={{ fontFamily: "var(--font-mono)", color: "#38bdf8" }}>
                                {typeof weight === "number" ? weight.toFixed(4) : String(weight)}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    <div style={{ borderTop: "1px dashed rgba(255,255,255,0.08)", paddingTop: "8px" }}>
                      <div style={{ fontSize: "12px", fontWeight: 600, color: "#f97316", marginBottom: "4px" }}>
                        ⛰️ Landslide Hazard Drivers
                      </div>
                      <div style={{ fontSize: "11px", color: "#94a3b8" }}>
                        {importance.landslide.note || "Gradient-boosted decision tree gain importance"}
                      </div>
                      {importance.landslide.features && (
                        <div style={{ display: "flex", flexDirection: "column", gap: "4px", marginTop: "6px" }}>
                          {Object.entries(importance.landslide.features).map(([feat, weight]) => (
                            <div key={feat} style={{ display: "flex", justifyContent: "space-between", fontSize: "11.5px" }}>
                              <span style={{ color: "#cbd5e1" }}>{feat}</span>
                              <span style={{ fontFamily: "var(--font-mono)", color: "#f97316" }}>
                                {typeof weight === "number" ? weight.toFixed(4) : String(weight)}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Honesty Disclosure Box */}
              <div
                style={{
                  background: "rgba(234, 179, 8, 0.1)",
                  border: "1px solid rgba(234, 179, 8, 0.3)",
                  borderRadius: "8px",
                  padding: "10px 14px",
                  fontSize: "11.5px",
                  color: "#fef08a",
                  lineHeight: 1.45,
                }}
              >
                <strong>Scientific Integrity Disclosure:</strong> The trainable GBT models were
                evaluated against deterministic simulated hill-region datasets (Flood AUC ≈ 0.78,
                Landslide AUC ≈ 0.68). These benchmark figures reflect simulated held-out
                performance and are not presented as real-world operational accuracy.
              </div>
            </>
          ) : (
            <div>Unable to retrieve model information.</div>
          )}
        </div>
      </div>
    </div>
  );
};
