import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  LocationRisk,
  SourceHealth,
  SystemStatus,
  AlertRecord,
  BasemapId,
  AccumulationPeriod,
  WeatherMode,
} from './types';
import { api } from './api';
import { TopBar } from './components/TopBar';
import { LeftPanel } from './components/LeftPanel';
import { RightPanel } from './components/RightPanel';
import { BottomTimeline } from './components/BottomTimeline';
import { GlobalEarthGlobe } from './components/GlobalEarthGlobe';
import { VillageDetailDrawer } from './components/VillageDetailDrawer';
import { AlertCenter } from './components/AlertCenter';
import { ModelInfoModal } from './components/ModelInfoModal';
import { AboutModal } from './components/AboutModal';
import { SettingsModal } from './components/SettingsModal';
import { ManageSourcesModal } from './components/ManageSourcesModal';
import { TacticalMapView } from './components/TacticalMapView';
import { TropicalActivityModal } from './components/TropicalActivityModal';
import { HydrographModal } from './components/HydrographModal';

// Replay discrete timesteps
const REPLAY_TIMESTEPS = [
  '2026-07-14 00:00:00',
  '2026-07-14 06:00:00',
  '2026-07-14 12:00:00',
  '2026-07-14 18:00:00',
  '2026-07-15 00:00:00',
  '2026-07-15 06:00:00',
  '2026-07-15 10:00:00',
  '2026-07-15 12:00:00',
  '2026-07-16 00:00:00',
];

const BASE_LOCATIONS: LocationRisk[] = [
  // 1. UTTARAKHAND (Mandakini / Alaknanda / Garhwal Corridor)
  {
    id: 'loc-devgaon',
    name: 'Devgaon',
    state: 'Uttarakhand',
    district: 'Pauri Garhwal',
    block: 'Kot',
    latitude: 30.12,
    longitude: 79.25,
    overall_risk: 0.94,
    flood_probability: 0.99,
    landslide_probability: 0.88,
    risk_level: 'CRITICAL',
    lead_time_hours: 3.5,
    confidence_score: 0.92,
    current_rainfall_mm: 64.2,
    rainfall_accumulation_24h_mm: 142.5,
    soil_moisture_saturation: 0.94,
    river_level_rise_m: 2.8,
    slope_degrees: 34.2,
    elevation_m: 1420,
  },
  {
    id: 'loc-talli',
    name: 'Talli',
    state: 'Uttarakhand',
    district: 'Nainital',
    block: 'Bhimtal',
    latitude: 30.08,
    longitude: 79.31,
    overall_risk: 0.78,
    flood_probability: 0.65,
    landslide_probability: 0.78,
    risk_level: 'HIGH',
    lead_time_hours: 4.2,
    confidence_score: 0.88,
    current_rainfall_mm: 42.0,
    rainfall_accumulation_24h_mm: 96.0,
    soil_moisture_saturation: 0.82,
    river_level_rise_m: 1.4,
    slope_degrees: 38.5,
    elevation_m: 1680,
  },
  {
    id: 'loc-malla',
    name: 'Malla',
    state: 'Uttarakhand',
    district: 'Pauri Garhwal',
    block: 'Kot',
    latitude: 30.15,
    longitude: 79.2,
    overall_risk: 0.45,
    flood_probability: 0.48,
    landslide_probability: 0.38,
    risk_level: 'MODERATE',
    lead_time_hours: 6.0,
    confidence_score: 0.85,
    current_rainfall_mm: 18.5,
    rainfall_accumulation_24h_mm: 45.2,
    soil_moisture_saturation: 0.58,
    river_level_rise_m: 0.6,
    slope_degrees: 22.0,
    elevation_m: 1250,
  },
  {
    id: 'loc-bhairav',
    name: 'Bhairav Garhi',
    state: 'Uttarakhand',
    district: 'Pauri Garhwal',
    block: 'Lansdowne',
    latitude: 30.05,
    longitude: 79.35,
    overall_risk: 0.22,
    flood_probability: 0.18,
    landslide_probability: 0.25,
    risk_level: 'LOW',
    lead_time_hours: 12.0,
    confidence_score: 0.94,
    current_rainfall_mm: 4.2,
    rainfall_accumulation_24h_mm: 12.0,
    soil_moisture_saturation: 0.32,
    river_level_rise_m: 0.1,
    slope_degrees: 15.0,
    elevation_m: 1890,
  },
  {
    id: 'loc-joshimath',
    name: 'Joshimath (MB)',
    state: 'Uttarakhand',
    district: 'Chamoli',
    block: 'Joshimath',
    latitude: 30.5564,
    longitude: 79.5630,
    overall_risk: 0.32,
    flood_probability: 0.02,
    landslide_probability: 0.32,
    risk_level: 'MODERATE',
    lead_time_hours: 4.0,
    confidence_score: 0.39,
    current_rainfall_mm: 0.48, // Live NASA GPM IMERG observation
    rainfall_accumulation_24h_mm: 0.48,
    soil_moisture_saturation: 0.45,
    river_level_rise_m: 0.2,
    slope_degrees: 38.5,
    elevation_m: 1875,
  },
  {
    id: 'loc-mana',
    name: 'Mana Village',
    state: 'Uttarakhand',
    district: 'Chamoli',
    block: 'Joshimath',
    latitude: 30.7710,
    longitude: 79.4950,
    overall_risk: 0.37,
    flood_probability: 0.02,
    landslide_probability: 0.37,
    risk_level: 'MODERATE',
    lead_time_hours: 4.0,
    confidence_score: 0.35,
    current_rainfall_mm: 0.01, // Live NASA GPM IMERG observation
    rainfall_accumulation_24h_mm: 0.01,
    soil_moisture_saturation: 0.40,
    river_level_rise_m: 0.1,
    slope_degrees: 44.0,
    elevation_m: 3200,
  },

  // 2. HIMACHAL PRADESH (Beas Basin & Kullu-Mandi Corridor)
  {
    id: 'loc-pandoh',
    name: 'Pandoh',
    state: 'Himachal Pradesh',
    district: 'Mandi',
    block: 'Sadar Mandi',
    latitude: 31.67,
    longitude: 77.01,
    overall_risk: 0.84,
    flood_probability: 0.88,
    landslide_probability: 0.72,
    risk_level: 'HIGH',
    lead_time_hours: 2.8,
    confidence_score: 0.89,
    current_rainfall_mm: 56.4,
    rainfall_accumulation_24h_mm: 128.0,
    soil_moisture_saturation: 0.88,
    river_level_rise_m: 2.3,
    slope_degrees: 36.0,
    elevation_m: 880,
  },
  {
    id: 'loc-aut-larji',
    name: 'Aut-Larji',
    state: 'Himachal Pradesh',
    district: 'Mandi',
    block: 'Banjar Valley',
    latitude: 31.75,
    longitude: 77.20,
    overall_risk: 0.72,
    flood_probability: 0.75,
    landslide_probability: 0.68,
    risk_level: 'HIGH',
    lead_time_hours: 3.2,
    confidence_score: 0.86,
    current_rainfall_mm: 48.0,
    rainfall_accumulation_24h_mm: 110.0,
    soil_moisture_saturation: 0.81,
    river_level_rise_m: 1.9,
    slope_degrees: 39.5,
    elevation_m: 960,
  },
  {
    id: 'loc-manali-vashisht',
    name: 'Manali-Vashisht',
    state: 'Himachal Pradesh',
    district: 'Kullu',
    block: 'Naggar',
    latitude: 32.24,
    longitude: 77.19,
    overall_risk: 0.62,
    flood_probability: 0.58,
    landslide_probability: 0.66,
    risk_level: 'MODERATE',
    lead_time_hours: 4.5,
    confidence_score: 0.84,
    current_rainfall_mm: 36.5,
    rainfall_accumulation_24h_mm: 84.0,
    soil_moisture_saturation: 0.74,
    river_level_rise_m: 1.2,
    slope_degrees: 42.0,
    elevation_m: 2050,
  },
  {
    id: 'loc-dharamshala-bhagsu',
    name: 'Dharamshala-Bhagsunag',
    state: 'Himachal Pradesh',
    district: 'Kangra',
    block: 'Dharamshala',
    latitude: 32.25,
    longitude: 76.35,
    overall_risk: 0.55,
    flood_probability: 0.52,
    landslide_probability: 0.61,
    risk_level: 'MODERATE',
    lead_time_hours: 5.0,
    confidence_score: 0.82,
    current_rainfall_mm: 32.0,
    rainfall_accumulation_24h_mm: 72.0,
    soil_moisture_saturation: 0.68,
    river_level_rise_m: 0.9,
    slope_degrees: 35.0,
    elevation_m: 1750,
  },

  // 3. SIKKIM (Teesta River Basin & Glacial Lake Outburst / GLOF Corridor)
  {
    id: 'loc-chungthang',
    name: 'Chungthang',
    state: 'Sikkim',
    district: 'North Sikkim',
    block: 'Chungthang Sub-Division',
    latitude: 27.60,
    longitude: 88.65,
    overall_risk: 0.96,
    flood_probability: 0.98,
    landslide_probability: 0.91,
    risk_level: 'CRITICAL',
    lead_time_hours: 1.8,
    confidence_score: 0.94,
    current_rainfall_mm: 72.5,
    rainfall_accumulation_24h_mm: 165.0,
    soil_moisture_saturation: 0.96,
    river_level_rise_m: 3.4,
    slope_degrees: 44.0,
    elevation_m: 1790,
  },
  {
    id: 'loc-mangan-singhik',
    name: 'Mangan-Singhik',
    state: 'Sikkim',
    district: 'North Sikkim',
    block: 'Mangan',
    latitude: 27.50,
    longitude: 88.53,
    overall_risk: 0.86,
    flood_probability: 0.82,
    landslide_probability: 0.89,
    risk_level: 'CRITICAL',
    lead_time_hours: 2.4,
    confidence_score: 0.90,
    current_rainfall_mm: 58.0,
    rainfall_accumulation_24h_mm: 135.0,
    soil_moisture_saturation: 0.90,
    river_level_rise_m: 2.2,
    slope_degrees: 38.0,
    elevation_m: 1450,
  },
  {
    id: 'loc-dikchu',
    name: 'Dikchu',
    state: 'Sikkim',
    district: 'East Sikkim',
    block: 'Gangtok Rural',
    latitude: 27.39,
    longitude: 88.52,
    overall_risk: 0.65,
    flood_probability: 0.68,
    landslide_probability: 0.58,
    risk_level: 'HIGH',
    lead_time_hours: 3.8,
    confidence_score: 0.85,
    current_rainfall_mm: 38.0,
    rainfall_accumulation_24h_mm: 88.0,
    soil_moisture_saturation: 0.76,
    river_level_rise_m: 1.5,
    slope_degrees: 31.0,
    elevation_m: 920,
  },
  {
    id: 'loc-rangpo',
    name: 'Rangpo',
    state: 'Sikkim',
    district: 'Pakyong',
    block: 'Rangpo Basin',
    latitude: 27.18,
    longitude: 88.53,
    overall_risk: 0.38,
    flood_probability: 0.42,
    landslide_probability: 0.28,
    risk_level: 'MODERATE',
    lead_time_hours: 7.0,
    confidence_score: 0.88,
    current_rainfall_mm: 16.0,
    rainfall_accumulation_24h_mm: 42.0,
    soil_moisture_saturation: 0.52,
    river_level_rise_m: 0.5,
    slope_degrees: 24.0,
    elevation_m: 450,
  },

  // 4. WESTERN GHATS / KERALA (Wayanad & Idukki Slope / Debris Flow Corridor)
  {
    id: 'loc-meppadi-chooralmala',
    name: 'Meppadi-Chooralmala',
    state: 'Western Ghats / Kerala',
    district: 'Wayanad',
    block: 'Vythiri Taluk',
    latitude: 11.55,
    longitude: 76.13,
    overall_risk: 0.95,
    flood_probability: 0.94,
    landslide_probability: 0.96,
    risk_level: 'CRITICAL',
    lead_time_hours: 2.0,
    confidence_score: 0.93,
    current_rainfall_mm: 82.0,
    rainfall_accumulation_24h_mm: 195.0,
    soil_moisture_saturation: 0.98,
    river_level_rise_m: 2.9,
    slope_degrees: 41.0,
    elevation_m: 980,
  },
  {
    id: 'loc-mundakkai',
    name: 'Mundakkai',
    state: 'Western Ghats / Kerala',
    district: 'Wayanad',
    block: 'Vythiri Taluk',
    latitude: 11.53,
    longitude: 76.15,
    overall_risk: 0.92,
    flood_probability: 0.91,
    landslide_probability: 0.95,
    risk_level: 'CRITICAL',
    lead_time_hours: 2.2,
    confidence_score: 0.91,
    current_rainfall_mm: 78.0,
    rainfall_accumulation_24h_mm: 182.0,
    soil_moisture_saturation: 0.97,
    river_level_rise_m: 2.6,
    slope_degrees: 43.0,
    elevation_m: 1050,
  },
  {
    id: 'loc-munnar-pettimudi',
    name: 'Munnar-Pettimudi',
    state: 'Western Ghats / Kerala',
    district: 'Idukki',
    block: 'Devikulam',
    latitude: 10.15,
    longitude: 77.02,
    overall_risk: 0.82,
    flood_probability: 0.78,
    landslide_probability: 0.88,
    risk_level: 'HIGH',
    lead_time_hours: 3.0,
    confidence_score: 0.89,
    current_rainfall_mm: 52.0,
    rainfall_accumulation_24h_mm: 125.0,
    soil_moisture_saturation: 0.86,
    river_level_rise_m: 1.8,
    slope_degrees: 45.0,
    elevation_m: 1620,
  },
  {
    id: 'loc-cheruthoni',
    name: 'Cheruthoni',
    state: 'Western Ghats / Kerala',
    district: 'Idukki',
    block: 'Idukki Dam Catchment',
    latitude: 9.85,
    longitude: 76.97,
    overall_risk: 0.42,
    flood_probability: 0.45,
    landslide_probability: 0.35,
    risk_level: 'MODERATE',
    lead_time_hours: 6.5,
    confidence_score: 0.87,
    current_rainfall_mm: 22.0,
    rainfall_accumulation_24h_mm: 55.0,
    soil_moisture_saturation: 0.62,
    river_level_rise_m: 0.8,
    slope_degrees: 28.0,
    elevation_m: 720,
  },
  {
    id: 'loc-munnar-gp',
    name: 'Munnar Grama Panchayat',
    state: 'Western Ghats / Kerala',
    district: 'Idukki',
    block: 'Devikulam',
    latitude: 10.0889,
    longitude: 77.0595,
    overall_risk: 0.33,
    flood_probability: 0.02,
    landslide_probability: 0.33,
    risk_level: 'MODERATE',
    lead_time_hours: 4.0,
    confidence_score: 0.39,
    current_rainfall_mm: 0.99, // Live NASA GPM / ISRO observation
    rainfall_accumulation_24h_mm: 1.5,
    soil_moisture_saturation: 0.65,
    river_level_rise_m: 0.4,
    slope_degrees: 42.0,
    elevation_m: 1532,
  },
];

// Helper to compute dynamic step-based risk for the replay simulation
function getStepLocations(stepIndex: number): LocationRisk[] {
  const intensityMap: Record<number, number> = {
    0: 0.18,
    1: 0.25,
    2: 0.42,
    3: 0.65,
    4: 0.85,
    5: 0.95,
    6: 1.0,
    7: 0.82,
    8: 0.3,
  };
  const factor = intensityMap[stepIndex] ?? 0.8;

  return BASE_LOCATIONS.map((loc) => {
    const rain = Math.round(loc.current_rainfall_mm * factor * 10) / 10;
    const overallRisk = Math.min(0.99, Math.round(loc.overall_risk * factor * 100) / 100);
    let risk_level: LocationRisk['risk_level'] = 'LOW';
    if (overallRisk >= 0.85) risk_level = 'CRITICAL';
    else if (overallRisk >= 0.65) risk_level = 'HIGH';
    else if (overallRisk >= 0.35) risk_level = 'MODERATE';

    return {
      ...loc,
      current_rainfall_mm: rain,
      overall_risk: overallRisk,
      flood_probability: Math.min(0.99, Math.round(loc.flood_probability * factor * 100) / 100),
      landslide_probability: Math.min(0.99, Math.round(loc.landslide_probability * factor * 100) / 100),
      risk_level,
    };
  });
}

export const App: React.FC = () => {
  // Core domain data
  const [locations, setLocations] = useState<LocationRisk[]>(() => getStepLocations(6));
  const [selectedLocation, setSelectedLocation] = useState<LocationRisk | null>(null);
  const [_systemStatus, setSystemStatus] = useState<SystemStatus | null>(null);
  const [sources, setSources] = useState<SourceHealth[]>([]);
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);

  // Modals state
  const [isAlertCenterOpen, setIsAlertCenterOpen] = useState(false);
  const [alertCenterVillage, setAlertCenterVillage] = useState<string | undefined>(undefined);
  const [isModelInfoOpen, setIsModelInfoOpen] = useState(false);
  const [isAboutOpen, setIsAboutOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isManageSourcesOpen, setIsManageSourcesOpen] = useState(false);
  const [isTropicalActivityOpen, setIsTropicalActivityOpen] = useState(false);
  const [isHydrographOpen, setIsHydrographOpen] = useState(false);

  // Sidebar collapse states
  const [isLeftCollapsed, setIsLeftCollapsed] = useState(false);
  const [isRightCollapsed, setIsRightCollapsed] = useState(false);

  // View mode and 3D globe focus target
  const [viewMode, setViewMode] = useState<'3d-globe' | 'tactical-map'>('3d-globe');
  const [focusTarget, setFocusTarget] = useState<{ lat: number; lng: number; zoomDistance?: number; zoom?: number; pitch?: number } | null>(null);

  // Settings
  const [units, setUnits] = useState<'metric' | 'imperial'>('metric');
  const [labelDensity, setLabelDensity] = useState<'all' | 'medium' | 'minimal'>('all');
  const [atmosphereGlow, setAtmosphereGlow] = useState(true);

  // Visualization settings
  const [basemap, setBasemap] = useState<BasemapId>('satellite');
  const [layers, setLayers] = useState<Record<string, boolean>>({
    precipitation: true,
    rainfall_accumulation: true,
    soil_moisture: false,
    flood_risk: true,
    landslide_risk: true,
    terrain_slope: false,
    rivers_gauges: false,
    admin_boundaries: true,
    iot_sensors: false,
    historical_events: false,
  });

  // Weather Hybrid Mode (Live Satellite stream vs Calibrated Storm Replay)
  const [weatherMode, setWeatherMode] = useState<WeatherMode>('replay');

  // Replay timeline state
  const [currentStepIndex, setCurrentStepIndex] = useState(6); // Default to 2026-07-15 10:00:00
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [accumulationPeriod, setAccumulationPeriod] = useState<AccumulationPeriod>('30m');

  const playTimerRef = useRef<number | null>(null);

  // Fetch live satellite weather helper
  const fetchLiveSatelliteWeather = useCallback(async () => {
    try {
      const live = await api.liveWeather();
      if (live && live.observations && live.observations.length > 0) {
        const obsMap = new Map(live.observations.map((o) => [o.name, o]));
        setLocations((prev) =>
          prev.map((loc) => {
            const o = obsMap.get(loc.name);
            if (!o) return loc;
            const rain = o.rainfall_rate_mm_hr;
            let rLevel: LocationRisk['risk_level'] = o.risk_level || 'LOW';
            let overallRisk = 0.08;
            let floodP = 0.05;
            let landP = 0.06;

            if (rain >= 50) {
              rLevel = 'CRITICAL';
              overallRisk = 0.92;
              floodP = 0.94;
              landP = 0.88;
            } else if (rain >= 20) {
              rLevel = 'HIGH';
              overallRisk = 0.72;
              floodP = 0.75;
              landP = 0.68;
            } else if (rain >= 5) {
              rLevel = 'MODERATE';
              overallRisk = 0.45;
              floodP = 0.42;
              landP = 0.48;
            } else if (rain > 0) {
              rLevel = 'LOW';
              overallRisk = 0.22;
              floodP = 0.18;
              landP = 0.25;
            }

            return {
              ...loc,
              current_rainfall_mm: rain,
              risk_level: rLevel,
              overall_risk: overallRisk,
              flood_probability: floodP,
              landslide_probability: landP,
            };
          })
        );
      }
    } catch (err) {
      console.error('Failed to fetch live satellite weather:', err);
    }
  }, []);

  // Auto-polling interval for live satellite feed (every 30s)
  useEffect(() => {
    if (weatherMode === 'live') {
      const pollTimer = window.setInterval(() => {
        fetchLiveSatelliteWeather();
      }, 30000);
      return () => window.clearInterval(pollTimer);
    }
  }, [weatherMode, fetchLiveSatelliteWeather]);

  // Hybrid Mode toggle handler
  const handleToggleWeatherMode = useCallback(async () => {
    if (weatherMode === 'replay') {
      setWeatherMode('live');
      setIsPlaying(false);
      await fetchLiveSatelliteWeather();
    } else {
      setWeatherMode('replay');
      const dynamicLocs = getStepLocations(currentStepIndex);
      setLocations(dynamicLocs);
    }
  }, [weatherMode, currentStepIndex, fetchLiveSatelliteWeather]);

  // Layer toggle handler
  const handleToggleLayer = (layerKey: string) => {
    setLayers((prev) => ({
      ...prev,
      [layerKey]: !prev[layerKey],
    }));
  };

  const handleResetLayers = () => {
    setLayers({
      precipitation: true,
      rainfall_accumulation: true,
      soil_moisture: false,
      flood_risk: true,
      landslide_risk: true,
      terrain_slope: false,
      rivers_gauges: false,
      admin_boundaries: true,
      iot_sensors: false,
      historical_events: false,
    });
  };

  // Initial Data Fetching
  const loadInitialData = useCallback(async () => {
    try {
      const [statusRes, srcRes, alertsRes] = await Promise.all([
        api.systemStatus().catch(() => null),
        api.sources().catch(() => null),
        api.alerts().catch(() => null),
      ]);

      if (statusRes) setSystemStatus(statusRes);
      if (srcRes && srcRes.sources) setSources(srcRes.sources);
      if (alertsRes && alertsRes.alerts) setAlerts(alertsRes.alerts);
    } catch {
      // Fallback cleanly
    }
  }, []);

  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  // Replay Timestep scrubber handler
  const handleStepChange = useCallback((stepIndex: number) => {
    setCurrentStepIndex(stepIndex);
    if (weatherMode === 'replay') {
      const dynamicLocs = getStepLocations(stepIndex);
      setLocations(dynamicLocs);

      // If a location is currently selected, update its reference
      setSelectedLocation((prev) => {
        if (!prev) return null;
        return dynamicLocs.find((l) => l.id === prev.id) || prev;
      });
    }
  }, [weatherMode]);

  // Replay Transport Playback Timer
  useEffect(() => {
    if (isPlaying) {
      const intervalMs = Math.round(2500 / playbackSpeed);
      playTimerRef.current = window.setInterval(() => {
        setCurrentStepIndex((prev) => {
          const next = prev + 1 >= REPLAY_TIMESTEPS.length ? 0 : prev + 1;
          handleStepChange(next);
          return next;
        });
      }, intervalMs);
    } else {
      if (playTimerRef.current) {
        clearInterval(playTimerRef.current);
        playTimerRef.current = null;
      }
    }
    return () => {
      if (playTimerRef.current) clearInterval(playTimerRef.current);
    };
  }, [isPlaying, playbackSpeed, handleStepChange]);

  const handleTogglePlay = () => {
    setIsPlaying(!isPlaying);
  };

  const handleSelectLocation = (loc: LocationRisk) => {
    setSelectedLocation(loc);
    setFocusTarget({ lat: loc.latitude, lng: loc.longitude, zoomDistance: 4.8 });
  };

  const handleSelectAlert = (alert: AlertRecord) => {
    const loc = locations.find((l) => l.name === alert.location_name) || locations[0];
    if (loc) {
      setSelectedLocation(loc);
      setFocusTarget({ lat: loc.latitude, lng: loc.longitude, zoomDistance: 4.8 });
      setIsAlertCenterOpen(false);
    }
  };

  const handleSelectSearchTarget = (target: { name: string; lat: number; lng: number; zoomDistance: number }) => {
    setFocusTarget({ lat: target.lat, lng: target.lng, zoomDistance: target.zoomDistance });
  };

  const handleFlyToTarget = (target: { lat: number; lng: number; zoom?: number; pitch?: number; zoomDistance?: number }) => {
    setFocusTarget(target);
  };

  const handleSelectRegionTab = (tab: 'Global' | 'India' | 'States' | 'Districts') => {
    switch (tab) {
      case 'Global':
        setFocusTarget({ lat: 20.0, lng: 78.0, zoom: 1.8, pitch: 0 });
        break;
      case 'India':
        setFocusTarget({ lat: 22.5, lng: 79.5, zoom: 4.6, pitch: 15 });
        break;
      case 'States':
        setFocusTarget({ lat: 30.15, lng: 79.2, zoom: 7.2, pitch: 30 });
        break;
      case 'Districts':
        setFocusTarget({ lat: 30.12, lng: 79.25, zoom: 10.8, pitch: 45 });
        break;
    }
  };

  return (
    <div className="fg-command-center">
      {/* 1. TOP BAR */}
      <TopBar
        locations={locations}
        onSelectLocation={handleSelectLocation}
        onSelectSearchTarget={handleSelectSearchTarget}
        onOpenAlerts={() => setIsAlertCenterOpen(true)}
        onOpenModelInfo={() => setIsModelInfoOpen(true)}
        onOpenAbout={() => setIsAboutOpen(true)}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onOpenSources={() => setIsManageSourcesOpen(true)}
        activeAlertCount={361}
        criticalAlertCount={4}
        activeSourceCount={7}
        totalSourceCount={11}
        weatherMode={weatherMode}
        onToggleWeatherMode={handleToggleWeatherMode}
      />

      {/* 2. MAIN VIEWPORT */}
      <main className="fg-main-viewport">
        {/* LEFT CONTROL PANEL */}
        <LeftPanel
          layers={layers}
          onToggleLayer={handleToggleLayer}
          onResetLayers={handleResetLayers}
          onOpenManageSources={() => setIsManageSourcesOpen(true)}
          isCollapsed={isLeftCollapsed}
          onToggleCollapse={() => setIsLeftCollapsed(!isLeftCollapsed)}
          sources={sources}
        />

        {/* CENTER 3D GLOBAL EARTH / TACTICAL MAP & INTEGRATED TIMELINE */}
        <div className="fg-center-region" style={{ position: 'relative' }}>
          {/* Floating Expand Button for Left Sidebar */}
          {isLeftCollapsed && (
            <button
              className="fg-sidebar-floating-toggle fg-toggle-left"
              onClick={() => setIsLeftCollapsed(false)}
              title="Show Left Sidebar (Layers & Sources)"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="9 18 15 12 9 6" />
              </svg>
              <span>Layers</span>
            </button>
          )}

          {/* Floating Expand Button for Right Sidebar */}
          {isRightCollapsed && (
            <button
              className="fg-sidebar-floating-toggle fg-toggle-right"
              onClick={() => setIsRightCollapsed(false)}
              title="Show Right Sidebar (Overview & Analytics)"
            >
              <span>Overview</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>
          )}

          {/* Dual View Mode Switcher */}
          <div
            style={{
              position: 'absolute',
              top: '16px',
              left: isLeftCollapsed ? '120px' : '16px',
              transition: 'left 0.28s cubic-bezier(0.4, 0, 0.2, 1)',
              zIndex: 40,
              display: 'flex',
              gap: '6px',
              background: 'rgba(10, 16, 26, 0.85)',
              padding: '4px',
              borderRadius: '24px',
              border: '1px solid rgba(255, 255, 255, 0.12)',
              backdropFilter: 'blur(10px)',
              boxShadow: '0 4px 16px rgba(0, 0, 0, 0.5)',
            }}
          >
            <button
              className={`fg-btn ${viewMode === '3d-globe' ? 'fg-btn-primary' : 'fg-btn-secondary'}`}
              onClick={() => setViewMode('3d-globe')}
              style={{
                fontSize: '11px',
                fontWeight: 600,
                padding: '5px 13px',
                borderRadius: '18px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                background: viewMode === '3d-globe' ? '#0284c7' : 'transparent',
                borderColor: viewMode === '3d-globe' ? '#38bdf8' : 'transparent',
                color: '#fff',
                cursor: 'pointer',
              }}
            >
              <span>🌍</span> 3D Earth Globe
            </button>
            <button
              className={`fg-btn ${viewMode === 'tactical-map' ? 'fg-btn-primary' : 'fg-btn-secondary'}`}
              onClick={() => setViewMode('tactical-map')}
              style={{
                fontSize: '11px',
                fontWeight: 600,
                padding: '5px 13px',
                borderRadius: '18px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                background: viewMode === 'tactical-map' ? '#0284c7' : 'transparent',
                borderColor: viewMode === 'tactical-map' ? '#38bdf8' : 'transparent',
                color: '#fff',
                cursor: 'pointer',
              }}
            >
              <span>🗺️</span> Tactical GIS Map
            </button>
          </div>

          {viewMode === '3d-globe' ? (
            <GlobalEarthGlobe
              locations={locations}
              selectedLocation={selectedLocation}
              onSelectLocation={handleSelectLocation}
              basemap={basemap}
              onBasemapChange={setBasemap}
              layers={layers}
              replayTime={REPLAY_TIMESTEPS[currentStepIndex]}
              focusTarget={focusTarget}
              onOpenTropicalActivity={() => setIsTropicalActivityOpen(true)}
            />
          ) : (
            <TacticalMapView
              locations={locations}
              selectedLocation={selectedLocation}
              onSelectLocation={handleSelectLocation}
              basemap={basemap}
              layers={layers}
            />
          )}

          {/* FLOATING BOTTOM TIMELINE (Docked within center map area) */}
          <BottomTimeline
            currentStepIndex={currentStepIndex}
            totalSteps={REPLAY_TIMESTEPS.length}
            currentTimeStr={REPLAY_TIMESTEPS[currentStepIndex]}
            isPlaying={isPlaying}
            onTogglePlay={handleTogglePlay}
            onStepChange={handleStepChange}
            playbackSpeed={playbackSpeed}
            onSpeedChange={setPlaybackSpeed}
            accumulationPeriod={accumulationPeriod}
            onPeriodChange={setAccumulationPeriod}
            weatherMode={weatherMode}
            onToggleWeatherMode={handleToggleWeatherMode}
            onRefreshLive={fetchLiveSatelliteWeather}
          />
        </div>

        {/* RIGHT OVERVIEW & LEGENDS PANEL */}
        <RightPanel
          locations={locations}
          selectedLocation={selectedLocation}
          onSelectLocation={handleSelectLocation}
          onOpenAlerts={() => setIsAlertCenterOpen(true)}
          onSelectRegionTab={handleSelectRegionTab}
          onFlyToTarget={handleFlyToTarget}
          onOpenTropicalActivity={() => setIsTropicalActivityOpen(true)}
          onOpenHydrograph={() => setIsHydrographOpen(true)}
          replayTime={`${REPLAY_TIMESTEPS[currentStepIndex].replace(' ', 'T').slice(0, 16)} UTC`}
          weatherMode={weatherMode}
          isCollapsed={isRightCollapsed}
          onToggleCollapse={() => setIsRightCollapsed(!isRightCollapsed)}
        />
      </main>

      {/* 3. VILLAGE DETAIL DRAWER (Explainability & In-Situ Sensor Dossier) */}
      <VillageDetailDrawer
        location={selectedLocation}
        onClose={() => setSelectedLocation(null)}
        onOpenAlertsForVillage={(loc) => {
          setSelectedLocation(loc);
          setAlertCenterVillage(loc.name);
          setIsAlertCenterOpen(true);
        }}
      />

      {/* 4. EMERGENCY ALERT CENTER MODAL */}
      <AlertCenter
        isOpen={isAlertCenterOpen}
        onClose={() => {
          setIsAlertCenterOpen(false);
          setAlertCenterVillage(undefined);
        }}
        alerts={alerts}
        onSelectAlert={handleSelectAlert}
        locations={locations}
        selectedLocation={selectedLocation}
        onAlertDispatched={loadInitialData}
        initialVillage={alertCenterVillage}
      />

      {/* 5. MODEL INFO & EXPLAINABILITY MODAL */}
      <ModelInfoModal
        isOpen={isModelInfoOpen}
        onClose={() => setIsModelInfoOpen(false)}
      />

      {/* 6. MANAGE SOURCES MODAL */}
      <ManageSourcesModal
        isOpen={isManageSourcesOpen}
        onClose={() => setIsManageSourcesOpen(false)}
        sources={sources}
      />

      {/* 7. SETTINGS MODAL */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        units={units}
        onUnitsChange={setUnits}
        labelDensity={labelDensity}
        onLabelDensityChange={setLabelDensity}
        atmosphereGlow={atmosphereGlow}
        onAtmosphereGlowChange={setAtmosphereGlow}
      />

      {/* 8. ABOUT FLASHGUARD MODAL */}
      <AboutModal
        isOpen={isAboutOpen}
        onClose={() => setIsAboutOpen(false)}
        sources={sources}
      />

      {/* 9. TROPICAL ACTIVITY & SYNOPTIC TRACKER MODAL */}
      <TropicalActivityModal
        isOpen={isTropicalActivityOpen}
        onClose={() => setIsTropicalActivityOpen(false)}
        onFlyToStorm={handleFlyToTarget}
      />

      {/* 10. FULLSCREEN MULTI-HAZARD HYDROGRAPH & RUNOFF MODAL */}
      <HydrographModal
        isOpen={isHydrographOpen}
        onClose={() => setIsHydrographOpen(false)}
        location={selectedLocation || locations[0]}
        locations={locations}
        onSelectLocation={handleSelectLocation}
        replayTime={`${REPLAY_TIMESTEPS[currentStepIndex].replace(' ', 'T').slice(0, 16)} UTC`}
        onFlyToTarget={handleFlyToTarget}
      />
    </div>
  );
};

export default App;
