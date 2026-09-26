// Typed client for FlashGuard Early Warning System API
import type {
  Risk,
  SourceHealth,
  SystemStatus,
  LocationDetail,
  AlertRecord,
  ModelInfo,
  FeatureImportance,
  GeoJSONFeatureCollection,
  LiveWeatherResponse,
  EvacuationCentre,
  AlertRecipient,
  ActionableAlert,
  AlertSendRequest,
  AlertSendResponse,
} from "./types";

const BASE = (import.meta as any).env?.VITE_API_BASE ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path);
  if (!r.ok) {
    throw new Error(`HTTP ${r.status} on ${path}`);
  }
  return r.json() as Promise<T>;
}

async function post<T>(path: string, body: any): Promise<T> {
  const r = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    let detail = "";
    try {
      const err = await r.json();
      detail = err.detail ? JSON.stringify(err.detail) : "";
    } catch {}
    throw new Error(`HTTP ${r.status} on ${path}: ${detail}`);
  }
  return r.json() as Promise<T>;
}

export const api = {
  health: () => get<{ status: string; service: string; mode: string }>("/health"),
  systemStatus: () => get<SystemStatus>("/system/status"),
  sources: () => get<{ sources: SourceHealth[] }>("/data-sources/status"),
  riskMap: () => get<GeoJSONFeatureCollection>("/risk/map"),
  risks: () => get<{ risks: Risk[] }>("/risk"),
  risk: (id: number) => get<Risk>(`/risk/${id}`),
  locations: (level?: string, parentId?: number) => {
    const params = new URLSearchParams();
    if (level) params.append("level", level);
    if (parentId != null) params.append("parent_id", String(parentId));
    const qs = params.toString();
    return get<{ locations: LocationDetail[] }>(`/locations${qs ? `?${qs}` : ""}`);
  },
  location: (id: number) => get<LocationDetail>(`/locations/${id}`),
  rainfall: (locationId: number) =>
    get<{ series: { ts: string; rainfall_30m: number; rainfall_3h: number; rainfall_24h: number }[] }>(
      `/rainfall?location_id=${locationId}`
    ),
  riverLevel: (locationId: number) =>
    get<{ series: { ts: string; water_level: number; rate_of_rise: number }[] }>(
      `/river-level?location_id=${locationId}`
    ),
  history: (locationId: number) =>
    get<{ history: any[] }>(`/predictions/history?location_id=${locationId}`),
  liveWeather: () => get<LiveWeatherResponse>("/weather/live"),
  weatherMode: () =>
    get<{
      supported_modes: string[];
      live_source: string;
      granule_id: string;
      observed_at: string;
      total_stations: number;
    }>("/weather/mode"),
  alerts: () => get<{ alerts: AlertRecord[] }>("/alerts"),
  modelInfo: () => get<ModelInfo>("/model/info"),
  featureImportance: () => get<FeatureImportance>("/model/feature-importance"),
  runPrediction: (locationId?: number, mode: string = "simulation") =>
    post<any>("/prediction/run", { location_id: locationId, mode }),
  runReplay: (reseed: boolean = false) =>
    post<{ timesteps: string[]; villages: number[]; predictions_written: number }>(
      "/replay/run",
      { reseed }
    ),
  postIot: (payload: {
    sensor_id: string;
    ts: string;
    latitude: number;
    longitude: number;
    rainfall?: number;
    soil_moisture?: number;
    water_level?: number;
    temperature?: number;
  }) => post<{ stored: boolean; sensor_id: string }>("/iot/observations", payload),
  briefing: (locationId: number, persona: string = "PUBLIC_ALERT") =>
    get<{
      engine: string;
      persona: string;
      location_name: string;
      briefing: string;
      is_live_llm: boolean;
    }>(`/briefing/${locationId}?persona=${persona}`),
  thingspeakLatest: (channelId: string = "3368421") =>
    get<{
      channel_id: string;
      classification: string;
      is_simulated: number;
      raw_telemetry: any;
      canonical_observation: any;
    }>(`/iot/thingspeak/latest?channel_id=${channelId}`),
  thingspeakSync: (results: number = 5) =>
    post<{
      synced: boolean;
      received: number;
      stored: number;
      rejected: number;
      latest: any;
    }>("/iot/thingspeak/sync", { results }),
  generateAlert: (params: {
    location_id: number;
    village?: string;
    hazard_type?: string;
    risk_level?: string;
    probability?: number;
    risk_window?: string;
    language?: string;
  }) => post<ActionableAlert>("/alerts/generate", params),
  sendAlert: (params: AlertSendRequest) =>
    post<AlertSendResponse>("/alerts/send", params),
  evacuationCentres: (village?: string, district?: string) => {
    const p = new URLSearchParams();
    if (village) p.append("village", village);
    if (district) p.append("district", district);
    const qs = p.toString();
    return get<{ centres: EvacuationCentre[] }>(`/evacuation-centres${qs ? `?${qs}` : ""}`);
  },
  nearbyEvacuationCentres: (locationId?: number, lat?: number, lon?: number) => {
    const p = new URLSearchParams();
    if (locationId != null) p.append("location_id", String(locationId));
    if (lat != null) p.append("latitude", String(lat));
    if (lon != null) p.append("longitude", String(lon));
    return get<{ centres: EvacuationCentre[] }>(`/evacuation-centres/nearby?${p.toString()}`);
  },
  affectedRecipients: (village: string) =>
    get<{
      village: string;
      total_recipients: number;
      recipients?: AlertRecipient[];
      sample_masked_contacts?: Array<{ name: string; masked_phone: string; language: string }>;
      language_breakdown?: Record<string, number>;
    }>(`/recipients/affected?village=${encodeURIComponent(village)}`),
  alertById: (id: number) => get<AlertRecord>(`/alerts/${id}`),
};
