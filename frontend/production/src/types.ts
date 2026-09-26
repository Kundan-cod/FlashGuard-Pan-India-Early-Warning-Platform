// Domain types for FlashGuard Early Warning System (SIH 2026 PS 26192)

export type RiskLevel = "LOW" | "MODERATE" | "HIGH" | "CRITICAL" | "UNKNOWN";

export type WeatherMode = "live" | "replay";

export interface LiveWeatherObservation {
  location_id: number;
  name: string;
  district: string;
  state: string;
  latitude: number;
  longitude: number;
  elevation_m: number;
  slope_deg: number;
  rainfall_rate_mm_hr: number;
  rainfall_30m_mm: number;
  quality_flag: string;
  units: string;
  risk_level: RiskLevel;
  hazard_status: string;
  source: string;
  satellite: string;
  sensor: string;
  observed_at: string;
}

export interface LiveWeatherResponse {
  status: string;
  mode: string;
  source: string;
  agency: string;
  product: string;
  product_description: string;
  granule_id: string;
  observed_at: string;
  total_stations: number;
  observations: LiveWeatherObservation[];
  hybrid_info?: {
    live_mode_description: string;
    replay_mode_description: string;
  };
}

export type SourceStatus =
  | "LIVE"
  | "NRT"
  | "STALE"
  | "ERROR"
  | "SIMULATED"
  | "REPLAY"
  | "NOT_CONFIGURED"
  | "DISCOVERY_ONLY"
  | "online"
  | "offline";

export interface RiskFactor {
  factor: string;
  contribution: number;
  feature?: string;
  value?: number;
  unit?: string;
}

export interface LocationRisk {
  id: string | number;
  location_id?: number | string;
  name: string;
  state: string;
  district: string;
  block: string;
  latitude: number;
  longitude: number;
  overall_risk: number;
  flood_probability: number;
  landslide_probability: number;
  risk_level: RiskLevel;
  lead_time_hours: number;
  confidence_score: number;
  current_rainfall_mm: number;
  rainfall_accumulation_24h_mm: number;
  soil_moisture_saturation: number;
  river_level_rise_m: number;
  slope_degrees: number;
  elevation_m: number;
}

export interface Risk {
  location_id: number;
  name: string;
  level?: string;
  state?: string;
  district?: string;
  latitude: number;
  longitude: number;
  risk_level: RiskLevel;
  flood_probability: number | null;
  landslide_probability: number | null;
  confidence: number | null;
  data_completeness: number | null;
  lead_time_min_lo: number | null;
  lead_time_min_hi: number | null;
  top_factors: RiskFactor[];
  model_version: string;
  mode: string;
  is_synthetic: boolean;
  ts: string;
}

export interface SourceHealth {
  source: string;
  status: string;
  last_success_at?: string | null;
  last_attempt_at?: string | null;
  last_latency_ms?: number | null;
  last_error?: string | null;
  records_last_run?: number | null;
  updated_at?: string;
  category?: string;
  description?: string;
}

export interface SystemStatus {
  status: string;
  model_disclaimer: string;
  mode: string;
  locations: number;
  villages: number;
  sources: SourceHealth[];
}

export interface TerrainFeatures {
  location_id: number;
  elevation: number | null;
  slope: number | null;
  aspect: number | null;
  curvature: number | null;
  flow_accumulation: number | null;
  drainage_density: number | null;
  distance_to_drainage: number | null;
  relative_relief: number | null;
  is_synthetic: number;
  source: string;
}

export interface GeoJSONGeometry {
  type: string;
  coordinates: any;
}

export interface GeoJSONFeatureCollection {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: GeoJSONGeometry;
    properties: Record<string, any>;
  }>;
  meta?: Record<string, any>;
}

export interface LocationDetail {
  id: number;
  ext_code: string;
  name: string;
  level: "country" | "state" | "district" | "block" | "village";
  parent_id: number | null;
  state: string | null;
  district: string | null;
  block: string | null;
  village: string | null;
  latitude: number;
  longitude: number;
  is_synthetic: number;
  created_at: string;
  geometry?: GeoJSONGeometry;
  terrain?: TerrainFeatures;
}

export interface EvacuationCentre {
  id: number;
  name: string;
  village?: string;
  district: string;
  state: string;
  latitude: number;
  longitude: number;
  capacity: number;
  elevation_m?: number;
  contact_name?: string;
  contact_phone?: string;
  amenities?: string;
  is_demo?: number | boolean;
  active?: number | boolean;
  distance_km?: number;
}

export interface AlertRecipient {
  id: number;
  village: string;
  district?: string;
  state?: string;
  name: string;
  phone: string;
  language: "en" | "hi" | "ta";
  role: string;
  active?: number | boolean;
}

export interface ActionableAlert {
  alert_id?: string | number;
  village: string;
  location_id?: number;
  hazard: string;
  hazard_type?: string;
  risk_level: RiskLevel;
  probability: number;
  lead_time_window: string;
  evacuation_centre_id?: number | null;
  evacuation_centre?: EvacuationCentre | null;
  evacuation_guidance: string;
  evacuation_route?: string;
  message: string;
  short_sms: string;
  language: string;
  fingerprint: string;
  translations?: Record<string, { full: string; sms: string }>;
  recipient_count?: number;
  sample_recipients?: Array<{ name: string; phone: string; language: string; role: string }>;
}

export interface AlertSendRequest {
  location_id: number;
  village?: string;
  hazard_type?: string;
  risk_level?: RiskLevel | string;
  probability?: number;
  risk_window?: string;
  language?: string;
  mock?: boolean;
}

export interface AlertSendResponse {
  alert_id: number;
  village: string;
  hazard_type: string;
  risk_level: string;
  dispatched: boolean;
  sms_status: string;
  push_status: string;
  recipient_count: number;
  is_mock: boolean;
  preview_message: string;
  short_sms: string;
  receipts: Array<{ phone: string; status: string; sent_at: string; chars: number; name?: string }>;
  evacuation_centre?: EvacuationCentre | null;
}

export interface AlertRecord {
  id: number;
  location_id: number;
  location_name?: string;
  village?: string;
  state?: string;
  district?: string;
  severity: "LOW" | "WATCH" | "WARNING" | "CRITICAL";
  hazard_type: "flood" | "landslide" | "multi_hazard" | string;
  message: string;
  status: "active" | "acknowledged" | "resolved" | "expired";
  mode: string;
  created_at: string;
  prediction_id?: number;
  confidence?: number;
  lead_time_window?: string;
  risk_level?: RiskLevel;
  risk_probability?: number;
  evacuation_centre_id?: number;
  evacuation_guidance?: string;
  recipient_count?: number;
  sms_status?: string;
  push_status?: string;
  fingerprint?: string;
  dispatched_at?: string;
}

export interface ModelInfo {
  use_trained_models: boolean;
  hazards: {
    flood: {
      version: string;
      validated: boolean;
      is_demo: boolean;
      implementation: string;
      card?: {
        validation_metrics?: Record<string, any>;
        feature_count?: number;
        dataset_summary?: string;
      };
    };
    landslide: {
      version: string;
      validated: boolean;
      is_demo: boolean;
      implementation: string;
      card?: {
        validation_metrics?: Record<string, any>;
        feature_count?: number;
        dataset_summary?: string;
      };
    };
  };
}

export interface FeatureImportance {
  flood: {
    type: string;
    features?: Record<string, number>;
    note?: string;
  };
  landslide: {
    type: string;
    features?: Record<string, number>;
    note?: string;
  };
}

export interface MapLayerConfig {
  boundaries: boolean;
  floodRisk: boolean;
  landslideRisk: boolean;
  rainfallIntensity: boolean;
  rainfallAccumulation: boolean;
  soilMoisture: boolean;
  riverGauges: boolean;
  terrainSlope: boolean;
  alerts: boolean;
  iotSensors: boolean;
}

export type BasemapId = "satellite" | "terrain" | "dark" | "light" | "carto-dark" | "esri-satellite" | "esri-topo" | "osm-standard" | "streets";

export type AccumulationPeriod = "30m" | "3h" | "24h" | "3d" | "7d";
