import React, { useState } from "react";

export const MapLegend: React.FC = () => {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="fg-floating-legend">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          cursor: "pointer",
        }}
        onClick={() => setCollapsed(!collapsed)}
      >
        <span className="fg-legend-title" style={{ margin: 0 }}>
          🗺️ Legend &amp; Scales
        </span>
        <span style={{ fontSize: "10px", color: "#94a3b8" }}>
          {collapsed ? "▲" : "▼"}
        </span>
      </div>

      {!collapsed && (
        <div style={{ marginTop: "10px", display: "flex", flexDirection: "column", gap: "10px" }}>
          {/* Risk Level Color Palette */}
          <div>
            <div className="fg-legend-title">Hazard Threat Tier</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span style={{ width: "10px", height: "10px", borderRadius: "2px", background: "#ef4444" }} />
                <span style={{ color: "#fca5a5", fontSize: "10px" }}>CRITICAL</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span style={{ width: "10px", height: "10px", borderRadius: "2px", background: "#f97316" }} />
                <span style={{ color: "#fdba74", fontSize: "10px" }}>HIGH</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span style={{ width: "10px", height: "10px", borderRadius: "2px", background: "#eab308" }} />
                <span style={{ color: "#fde047", fontSize: "10px" }}>MODERATE</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span style={{ width: "10px", height: "10px", borderRadius: "2px", background: "#10b981" }} />
                <span style={{ color: "#6ee7b7", fontSize: "10px" }}>LOW</span>
              </div>
            </div>
          </div>

          {/* Precipitation Intensity Scale */}
          <div>
            <div className="fg-legend-title">GPM Rain Rate (mm/hr)</div>
            <div
              className="fg-legend-gradient"
              style={{
                background: "linear-gradient(90deg, #1e3a8a 0%, #0284c7 30%, #eab308 65%, #ef4444 100%)",
              }}
            />
            <div className="fg-legend-labels">
              <span>0</span>
              <span>10</span>
              <span>25</span>
              <span>50+</span>
            </div>
          </div>

          {/* Soil Saturation Scale */}
          <div>
            <div className="fg-legend-title">Soil Moisture Saturation (%)</div>
            <div
              className="fg-legend-gradient"
              style={{
                background: "linear-gradient(90deg, #fef08a 0%, #ca8a04 40%, #15803d 80%, #064e3b 100%)",
              }}
            />
            <div className="fg-legend-labels">
              <span>0% Dry</span>
              <span>50%</span>
              <span>85% Alert</span>
              <span>100% Sat</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
