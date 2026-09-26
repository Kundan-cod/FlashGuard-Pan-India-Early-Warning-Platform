import React, { useEffect, useRef, useState, useCallback } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { LocationRisk, BasemapId } from '../types';

interface GlobalEarthGlobeProps {
  locations: LocationRisk[];
  selectedLocation: LocationRisk | null;
  onSelectLocation: (loc: LocationRisk) => void;
  basemap: BasemapId;
  onBasemapChange: (basemap: BasemapId) => void;
  layers: Record<string, boolean>;
  replayTime: string;
  focusTarget?: { lat: number; lng: number; zoomDistance?: number; zoom?: number; pitch?: number } | null;
  onOpenTropicalActivity?: () => void;
}

// 1. Procedural High-Resolution GPM Doppler Weather Precipitation Radar
function createPrecipitationRadarDataUrl(): string {
  const canvas = document.createElement('canvas');
  canvas.width = 1024;
  canvas.height = 1024;
  const ctx = canvas.getContext('2d');
  if (!ctx) return '';

  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const drawStormCell = (cx: number, cy: number, r: number, intensity: number) => {
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    grad.addColorStop(0, `rgba(217, 70, 239, ${0.90 * intensity})`); // Magenta core (>75 mm/hr)
    grad.addColorStop(0.2, `rgba(239, 68, 68, ${0.85 * intensity})`);  // Red core (50 mm/hr)
    grad.addColorStop(0.4, `rgba(249, 115, 22, ${0.80 * intensity})`); // Orange (30 mm/hr)
    grad.addColorStop(0.6, `rgba(234, 179, 8, ${0.70 * intensity})`);  // Yellow (15 mm/hr)
    grad.addColorStop(0.78, `rgba(34, 197, 94, ${0.55 * intensity})`); // Green (5 mm/hr)
    grad.addColorStop(0.92, `rgba(6, 182, 212, ${0.40 * intensity})`); // Cyan (1 mm/hr)
    grad.addColorStop(1, 'rgba(6, 182, 212, 0)');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();
  };

  // Convert coords in bounds: lng [68..98], lat [8..36]
  const toX = (lng: number) => ((lng - 68) / (98 - 68)) * canvas.width;
  const toY = (lat: number) => ((36 - lat) / (36 - 8)) * canvas.height;

  // Deep Depression BOB-03 Core & Rainbands in Bay of Bengal
  drawStormCell(toX(88.42), toY(19.45), 135, 0.98);
  drawStormCell(toX(87.20), toY(20.40), 95, 0.82);
  drawStormCell(toX(89.60), toY(18.50), 90, 0.80);

  // Monsoon Low AS-01 in Arabian Sea
  drawStormCell(toX(71.10), toY(18.20), 100, 0.75);

  // Major storm cluster centered over Uttarakhand Himalayas
  drawStormCell(toX(79.25), toY(30.12), 110, 0.98); // Core Pauri / Chamoli storm
  drawStormCell(toX(78.50), toY(30.50), 95, 0.88);  // Tehri / Dehradun
  drawStormCell(toX(79.80), toY(29.70), 85, 0.92);  // Kumaon / Nainital
  drawStormCell(toX(77.60), toY(31.40), 75, 0.80);  // Himachal Pradesh
  drawStormCell(toX(81.20), toY(29.20), 90, 0.85);  // Western Nepal

  // Monsoon trough stream across Northern Gangetic Plain
  drawStormCell(toX(82.50), toY(26.80), 90, 0.70);
  drawStormCell(toX(85.80), toY(25.60), 105, 0.75);

  return canvas.toDataURL('image/png');
}

// 2. Layer: Rainfall Accumulation (24h) GeoJSON
const RAINFALL_ACCUMULATION_GEOJSON: any = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: { level: '200mm+', color: '#8b5cf6' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [79.05, 30.25], [79.45, 30.25], [79.40, 29.95], [79.00, 29.95], [79.05, 30.25],
          ],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { level: '120mm+', color: '#0284c7' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [78.60, 30.55], [79.80, 30.55], [79.70, 29.65], [78.50, 29.65], [78.60, 30.55],
          ],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { level: '60mm+', color: '#0d9488' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [78.10, 30.95], [80.20, 30.95], [80.10, 29.20], [78.00, 29.20], [78.10, 30.95],
          ],
        ],
      },
    },
  ],
};

// 3. Layer: Soil Moisture Saturation GeoJSON (SMAP / L-Band)
const SOIL_MOISTURE_GEOJSON: any = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: { saturation: '94% (Waterlogged)', location: 'Alaknanda Catchment' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [78.85, 30.30], [79.40, 30.30], [79.35, 30.08], [78.80, 30.08], [78.85, 30.30],
          ],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { saturation: '88% (High Moisture)', location: 'Kumaon Foothills' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [79.35, 29.60], [79.70, 29.60], [79.65, 29.35], [79.30, 29.35], [79.35, 29.60],
          ],
        ],
      },
    },
  ],
};

// 4. Layer: Flash Flood Hazard Index GeoJSON
const FLOOD_HAZARD_GEOJSON: any = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: { hazard: 'EXTREME FLOOD INUNDATION', zone: 'Devprayag-Kot Gorge' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [78.58, 30.17], [78.68, 30.17], [78.80, 30.12], [78.70, 30.08], [78.58, 30.17],
          ],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { hazard: 'HIGH RIVER OVERFLOW', zone: 'Srinagar Plain' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [78.74, 30.24], [78.85, 30.24], [78.83, 30.20], [78.72, 30.20], [78.74, 30.24],
          ],
        ],
      },
    },
  ],
};

// 5. Layer: Landslide Susceptibility GeoJSON (GSI Bhusanket)
const LANDSLIDE_HAZARD_GEOJSON: any = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: { hazard: 'ACTIVE DEBRIS FLOW', highway: 'NH-58 Rishikesh-Badrinath' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [79.10, 30.35], [79.25, 30.35], [79.23, 30.28], [79.08, 30.28], [79.10, 30.35],
          ],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { hazard: 'ROCKFALL CORRIDOR', highway: 'Kot-Lansdowne Cut' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [79.20, 30.14], [79.35, 30.14], [79.33, 30.07], [79.18, 30.07], [79.20, 30.14],
          ],
        ],
      },
    },
  ],
};

// 6. Layer: Terrain Slope > 30° GeoJSON (SRTM 30m)
const TERRAIN_SLOPE_GEOJSON: any = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: { slope: '38° - 46° Critical Slope', risk: 'HIGH' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [79.00, 30.45], [79.35, 30.45], [79.30, 30.30], [78.95, 30.30], [79.00, 30.45],
          ],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { slope: '34° - 42° Steep Valley Facet', risk: 'HIGH' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [79.22, 30.16], [79.38, 30.16], [79.35, 30.05], [79.19, 30.05], [79.22, 30.16],
          ],
        ],
      },
    },
  ],
};

// 7. Layer: Himalayan Rivers GeoJSON
const HIMALAYAN_RIVERS_GEOJSON: any = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: { name: 'Alaknanda River' },
      geometry: {
        type: 'LineString',
        coordinates: [
          [79.56, 30.55], [79.45, 30.40], [79.33, 30.28], [78.98, 30.26], [78.78, 30.22], [78.60, 30.15],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { name: 'Ganga River' },
      geometry: {
        type: 'LineString',
        coordinates: [
          [78.60, 30.15], [78.45, 30.12], [78.26, 30.08], [78.16, 29.94], [78.10, 29.75], [78.30, 29.30],
          [79.00, 28.50], [80.35, 26.45], [81.85, 25.43], [83.00, 25.32], [85.14, 25.61], [88.36, 22.57],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { name: 'Yamuna River' },
      geometry: {
        type: 'LineString',
        coordinates: [
          [78.46, 31.01], [78.15, 30.55], [77.70, 30.40], [77.21, 28.61], [77.67, 27.50], [78.01, 27.18], [81.85, 25.43],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { name: 'Mandakini River' },
      geometry: {
        type: 'LineString',
        coordinates: [
          [79.06, 30.73], [79.03, 30.55], [78.98, 30.26],
        ],
      },
    },
  ],
};

// 7b. CWC Gauge Stations
const CWC_GAUGES = [
  { name: 'Srinagar Gauge (Alaknanda)', lng: 78.78, lat: 30.22, currentLvl: '536.8m', dangerLvl: '536.0m', status: 'CRITICAL OVER-TOPPING', color: '#ef4444' },
  { name: 'Devprayag Gauge (Confluence)', lng: 78.60, lat: 30.15, currentLvl: '460.1m', dangerLvl: '463.0m', status: 'ELEVATED WARNING', color: '#f59e0b' },
  { name: 'Rishikesh Gauge (Ganga)', lng: 78.26, lat: 30.08, currentLvl: '338.2m', dangerLvl: '340.0m', status: 'NORMAL', color: '#10b981' },
  { name: 'Haridwar Gauge (Ganga)', lng: 78.16, lat: 29.94, currentLvl: '293.4m', dangerLvl: '294.0m', status: 'WARNING', color: '#f59e0b' },
];

// 8. Layer: Administrative Boundaries (LGD) GeoJSON
const ADMIN_BOUNDARIES_GEOJSON: any = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: { name: 'Uttarakhand State', type: 'state' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [77.58, 30.35], [78.10, 31.45], [78.95, 31.35], [79.85, 31.05], [80.45, 30.85],
            [81.05, 30.25], [80.55, 29.85], [80.10, 28.75], [79.45, 28.95], [78.75, 29.45],
            [77.95, 29.95], [77.58, 30.35],
          ],
        ],
      },
    },
    // District internal borders
    {
      type: 'Feature',
      properties: { name: 'Pauri Garhwal District', type: 'district' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [78.45, 30.25], [79.25, 30.30], [79.40, 29.75], [78.60, 29.75], [78.45, 30.25],
          ],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { name: 'Chamoli District', type: 'district' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [79.20, 31.10], [80.05, 31.00], [79.95, 30.25], [79.20, 30.25], [79.20, 31.10],
          ],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { name: 'Nainital District', type: 'district' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [79.15, 29.65], [79.85, 29.65], [79.80, 28.95], [79.10, 28.95], [79.15, 29.65],
          ],
        ],
      },
    },
  ],
};

// 9. Layer: In-Situ IoT Hydrological Sensors
const IOT_SENSORS = [
  { id: 'IOT-01', name: 'Ultrasonic Stream Gauge', loc: 'Devgaon (Alaknanda)', lng: 79.25, lat: 30.12, telemetry: '+2.8m Rise', color: '#00d4ff' },
  { id: 'IOT-02', name: 'Tipping-Bucket Rain Gauge', loc: 'Kot Hillside', lng: 79.22, lat: 30.15, telemetry: '64.2 mm/hr', color: '#38bdf8' },
  { id: 'IOT-03', name: 'Piezometer Pore Pressure', loc: 'Talli Ridge', lng: 79.31, lat: 30.08, telemetry: '44.2 kPa', color: '#a855f7' },
  { id: 'IOT-04', name: 'Soil Moisture TDR Probe', loc: 'Ranikhet South', lng: 79.41, lat: 29.61, telemetry: '88% Saturation', color: '#10b981' },
  { id: 'IOT-05', name: 'Debris Flow Detector', loc: 'Joshimath Gorge', lng: 79.56, lat: 30.55, telemetry: 'Stable (0.02g)', color: '#f59e0b' },
];

// 10. Layer: Historical Disaster Footprints GeoJSON & Pins (NDEM)
const HISTORICAL_EVENTS_GEOJSON: any = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: { event: '2013 Kedarnath Disaster Footprint', fatalities: '5,700+' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [78.95, 30.78], [79.15, 30.78], [79.12, 30.65], [78.92, 30.65], [78.95, 30.78],
          ],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { event: '2021 Chamoli Glacial Flash Flood', fatalities: '200+' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [79.60, 30.52], [79.80, 30.52], [79.75, 30.40], [79.58, 30.40], [79.60, 30.52],
          ],
        ],
      },
    },
  ],
};

// 11. Layer: Tropical Cyclone BOB-03 Track, Cone of Uncertainty, and Teleconnection Moisture Conveyor
const TROPICAL_TRACK_GEOJSON: any = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: { type: 'cone', name: 'BOB-03 48h Cone of Uncertainty' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [
            [88.42, 19.45],
            [89.20, 20.80],
            [87.50, 22.40],
            [83.80, 24.20],
            [80.50, 24.60],
            [79.80, 22.80],
            [83.50, 20.20],
            [85.80, 18.90],
            [88.42, 19.45],
          ],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { type: 'track', name: 'BOB-03 Track Line' },
      geometry: {
        type: 'LineString',
        coordinates: [
          [91.50, 16.80],
          [90.10, 17.90],
          [88.42, 19.45],
          [87.50, 19.90],
          [86.70, 20.40],
          [85.00, 21.30],
          [81.60, 23.40],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { type: 'moisture_feed', name: 'Low-Level Moisture Jet to Himalayas' },
      geometry: {
        type: 'LineString',
        coordinates: [
          [88.42, 19.45],
          [85.80, 23.20],
          [82.50, 26.50],
          [80.10, 28.80],
          [79.25, 30.12],
        ],
      },
    },
  ],
};

const HISTORICAL_DISASTER_PINS = [
  { name: '2013 Kedarnath Cloudburst & Flood', lng: 79.06, lat: 30.73, summary: 'Rainfall 375mm/24h • Chorabari Lake Breach' },
  { name: '2021 Chamoli Glacial Outburst', lng: 79.70, lat: 30.48, summary: 'Rongtong Avalanche • Tapovan Dam Damage' },
  { name: '1998 Malpa Landslide', lng: 80.35, lat: 29.90, summary: 'Massive rockfall on Kailash Mansarovar route' },
  { name: '1991 Uttarkashi Earthquake & Landslides', lng: 78.43, lat: 30.73, summary: 'Landslide damming of Bhagirathi river' },
];

// National Early-Warning Hazard Corridors (LOD Cluster Hubs for Zoom < 6.0)
const NATIONAL_CORRIDORS = [
  {
    id: 'corridor-uttarakhand',
    name: 'Uttarakhand',
    basin: 'Alaknanda & Kumaon Basin',
    icon: '🏔️',
    lat: 30.05,
    lng: 79.30,
    zoomTarget: 9.8,
    pitchTarget: 52,
    matchState: 'uttarakhand',
  },
  {
    id: 'corridor-himachal',
    name: 'Himachal Pradesh',
    basin: 'Kangra & Beas Basin',
    icon: '🏔️',
    lat: 31.88,
    lng: 76.95,
    zoomTarget: 9.8,
    pitchTarget: 52,
    matchState: 'himachal',
  },
  {
    id: 'corridor-sikkim',
    name: 'Sikkim',
    basin: 'Teesta River Basin',
    icon: '⛰️',
    lat: 27.32,
    lng: 88.52,
    zoomTarget: 10.2,
    pitchTarget: 50,
    matchState: 'sikkim',
  },
  {
    id: 'corridor-wghats',
    name: 'Western Ghats',
    basin: 'Idukki & Wayanad (Periyar)',
    icon: '🌿',
    lat: 10.70,
    lng: 76.60,
    zoomTarget: 9.2,
    pitchTarget: 48,
    matchState: 'western',
  },
];

// Monitored River Watershed Basins GeoJSON
const WATERSHED_BASINS_GEOJSON: any = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: { name: 'Alaknanda-Ganga Basin (Uttarakhand)', color: '#00d4ff' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [[78.5, 30.9], [79.9, 31.1], [80.2, 30.2], [79.8, 29.3], [78.9, 29.4], [78.5, 30.9]],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { name: 'Beas-Sutlej Basin (Himachal)', color: '#38bdf8' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [[75.8, 32.5], [77.6, 32.6], [77.8, 31.1], [76.8, 31.0], [75.8, 32.5]],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { name: 'Teesta River Basin (Sikkim)', color: '#10b981' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [[88.0, 28.1], [88.9, 28.0], [88.8, 26.9], [88.1, 27.0], [88.0, 28.1]],
        ],
      },
    },
    {
      type: 'Feature',
      properties: { name: 'Periyar-Idukki Catchment (Western Ghats)', color: '#f59e0b' },
      geometry: {
        type: 'Polygon',
        coordinates: [
          [[76.4, 11.8], [76.9, 11.9], [77.3, 10.3], [77.2, 9.4], [76.6, 9.5], [76.4, 11.8]],
        ],
      },
    },
  ],
};

export const GlobalEarthGlobe: React.FC<GlobalEarthGlobeProps> = ({
  locations,
  selectedLocation,
  onSelectLocation,
  basemap,
  onBasemapChange,
  layers,
  replayTime,
  focusTarget,
  onOpenTropicalActivity,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  // Markers refs
  const villageMarkersRef = useRef<maplibregl.Marker[]>([]);
  const corridorMarkersRef = useRef<maplibregl.Marker[]>([]);
  const activePopupRef = useRef<maplibregl.Popup | null>(null);
  const cwcMarkersRef = useRef<maplibregl.Marker[]>([]);
  const iotMarkersRef = useRef<maplibregl.Marker[]>([]);
  const historicalMarkersRef = useRef<maplibregl.Marker[]>([]);
  const cycloneMarkersRef = useRef<maplibregl.Marker[]>([]);

  const [compassAngle, setCompassAngle] = useState(0);
  const [is3DActive, setIs3DActive] = useState(true);
  const [currentZoom, setCurrentZoom] = useState(3.8);

  // Helper to add all 10 custom GIS layers idempotently
  const addAllCustomLayers = useCallback((map: maplibregl.Map) => {
    // 1. Precipitation Doppler Radar Image Layer
    if (!map.getSource('precipitation-radar-source')) {
      try {
        map.addSource('precipitation-radar-source', {
          type: 'image',
          url: createPrecipitationRadarDataUrl(),
          coordinates: [
            [68.0, 36.0],
            [98.0, 36.0],
            [98.0, 8.0],
            [68.0, 8.0],
          ],
        });

        map.addLayer({
          id: 'precipitation-radar-layer',
          type: 'raster',
          source: 'precipitation-radar-source',
          paint: {
            'raster-opacity': 0.72,
            'raster-fade-duration': 200,
          },
        });
      } catch {
        // Safe fallback
      }
    }

    // 2. Rainfall Accumulation Layer
    if (!map.getSource('rainfall-accum-source')) {
      map.addSource('rainfall-accum-source', {
        type: 'geojson',
        data: RAINFALL_ACCUMULATION_GEOJSON,
      });

      map.addLayer({
        id: 'rainfall-accum-fill',
        type: 'fill',
        source: 'rainfall-accum-source',
        paint: {
          'fill-color': ['get', 'color'],
          'fill-opacity': 0.35,
        },
      });

      map.addLayer({
        id: 'rainfall-accum-line',
        type: 'line',
        source: 'rainfall-accum-source',
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 2.5,
          'line-dasharray': [3, 2],
        },
      });
    }

    // 3. Soil Moisture Saturation Layer
    if (!map.getSource('soil-moisture-source')) {
      map.addSource('soil-moisture-source', {
        type: 'geojson',
        data: SOIL_MOISTURE_GEOJSON,
      });

      map.addLayer({
        id: 'soil-moisture-fill',
        type: 'fill',
        source: 'soil-moisture-source',
        paint: {
          'fill-color': '#06b6d4',
          'fill-opacity': 0.32,
        },
      });

      map.addLayer({
        id: 'soil-moisture-line',
        type: 'line',
        source: 'soil-moisture-source',
        paint: {
          'line-color': '#0891b2',
          'line-width': 2.2,
          'line-dasharray': [2, 1],
        },
      });
    }

    // 4. Flash Flood Hazard Layer
    if (!map.getSource('flood-hazard-source')) {
      map.addSource('flood-hazard-source', {
        type: 'geojson',
        data: FLOOD_HAZARD_GEOJSON,
      });

      map.addLayer({
        id: 'flood-hazard-fill',
        type: 'fill',
        source: 'flood-hazard-source',
        paint: {
          'fill-color': '#ef4444',
          'fill-opacity': 0.38,
        },
      });

      map.addLayer({
        id: 'flood-hazard-line',
        type: 'line',
        source: 'flood-hazard-source',
        paint: {
          'line-color': '#dc2626',
          'line-width': 3.0,
        },
      });
    }

    // 5. Landslide Susceptibility Layer
    if (!map.getSource('landslide-hazard-source')) {
      map.addSource('landslide-hazard-source', {
        type: 'geojson',
        data: LANDSLIDE_HAZARD_GEOJSON,
      });

      map.addLayer({
        id: 'landslide-hazard-fill',
        type: 'fill',
        source: 'landslide-hazard-source',
        paint: {
          'fill-color': '#f97316',
          'fill-opacity': 0.38,
        },
      });

      map.addLayer({
        id: 'landslide-hazard-line',
        type: 'line',
        source: 'landslide-hazard-source',
        paint: {
          'line-color': '#ea580c',
          'line-width': 3.0,
          'line-dasharray': [2, 2],
        },
      });
    }

    // 6. Terrain Slope > 30° Layer
    if (!map.getSource('terrain-slope-source')) {
      map.addSource('terrain-slope-source', {
        type: 'geojson',
        data: TERRAIN_SLOPE_GEOJSON,
      });

      map.addLayer({
        id: 'terrain-slope-fill',
        type: 'fill',
        source: 'terrain-slope-source',
        paint: {
          'fill-color': '#eab308',
          'fill-opacity': 0.32,
        },
      });

      map.addLayer({
        id: 'terrain-slope-line',
        type: 'line',
        source: 'terrain-slope-source',
        paint: {
          'line-color': '#ca8a04',
          'line-width': 2.0,
          'line-dasharray': [2, 1],
        },
      });
    }

    // 7. Rivers Vectors Layer
    if (!map.getSource('himalayan-rivers')) {
      map.addSource('himalayan-rivers', {
        type: 'geojson',
        data: HIMALAYAN_RIVERS_GEOJSON,
      });

      map.addLayer({
        id: 'rivers-glow-layer',
        type: 'line',
        source: 'himalayan-rivers',
        paint: {
          'line-color': '#38bdf8',
          'line-width': 5.0,
          'line-opacity': 0.45,
          'line-blur': 3,
        },
      });

      map.addLayer({
        id: 'rivers-core-layer',
        type: 'line',
        source: 'himalayan-rivers',
        paint: {
          'line-color': '#7dd3fc',
          'line-width': 2.2,
          'line-opacity': 0.95,
        },
      });
    }

    // 8. Administrative Boundaries (State & Districts)
    if (!map.getSource('admin-boundaries-source')) {
      map.addSource('admin-boundaries-source', {
        type: 'geojson',
        data: ADMIN_BOUNDARIES_GEOJSON,
      });

      map.addLayer({
        id: 'admin-boundaries-fill',
        type: 'fill',
        source: 'admin-boundaries-source',
        paint: {
          'fill-color': '#00d4ff',
          'fill-opacity': 0.06,
        },
      });

      map.addLayer({
        id: 'admin-boundaries-line',
        type: 'line',
        source: 'admin-boundaries-source',
        paint: {
          'line-color': '#00d4ff',
          'line-width': 2.2,
          'line-dasharray': [3, 2],
        },
      });
    }

    // 10. Historical Disaster Footprints Layer
    if (!map.getSource('historical-events-source')) {
      map.addSource('historical-events-source', {
        type: 'geojson',
        data: HISTORICAL_EVENTS_GEOJSON,
      });

      map.addLayer({
        id: 'historical-events-fill',
        type: 'fill',
        source: 'historical-events-source',
        paint: {
          'fill-color': '#a855f7',
          'fill-opacity': 0.35,
        },
      });

      map.addLayer({
        id: 'historical-events-line',
        type: 'line',
        source: 'historical-events-source',
        paint: {
          'line-color': '#9333ea',
          'line-width': 2.8,
          'line-dasharray': [4, 2],
        },
      });
    }

    // 11. Tropical Cyclone BOB-03 Track & Teleconnection Layer
    if (!map.getSource('tropical-track-source')) {
      map.addSource('tropical-track-source', {
        type: 'geojson',
        data: TROPICAL_TRACK_GEOJSON,
      });

      map.addLayer({
        id: 'tropical-cone-fill',
        type: 'fill',
        source: 'tropical-track-source',
        filter: ['==', ['get', 'type'], 'cone'],
        paint: {
          'fill-color': '#06b6d4',
          'fill-opacity': 0.22,
        },
      });

      map.addLayer({
        id: 'tropical-cone-line',
        type: 'line',
        source: 'tropical-track-source',
        filter: ['==', ['get', 'type'], 'cone'],
        paint: {
          'line-color': '#38bdf8',
          'line-width': 1.8,
          'line-dasharray': [3, 2],
        },
      });

      map.addLayer({
        id: 'tropical-track-line',
        type: 'line',
        source: 'tropical-track-source',
        filter: ['==', ['get', 'type'], 'track'],
        paint: {
          'line-color': '#ef4444',
          'line-width': 3.5,
        },
      });

      map.addLayer({
        id: 'tropical-moisture-line',
        type: 'line',
        source: 'tropical-track-source',
        filter: ['==', ['get', 'type'], 'moisture_feed'],
        paint: {
          'line-color': '#a855f7',
          'line-width': 2.6,
          'line-dasharray': [4, 3],
        },
      });
    }

    // 11. Monitored River Watershed Basins (High-Risk Flood Catchments)
    if (!map.getSource('watershed-basins-source')) {
      try {
        map.addSource('watershed-basins-source', {
          type: 'geojson',
          data: WATERSHED_BASINS_GEOJSON,
        });

        map.addLayer({
          id: 'watershed-basins-fill',
          type: 'fill',
          source: 'watershed-basins-source',
          paint: {
            'fill-color': ['get', 'color'],
            'fill-opacity': 0.08,
          },
        });

        map.addLayer({
          id: 'watershed-basins-line',
          type: 'line',
          source: 'watershed-basins-source',
          paint: {
            'line-color': ['get', 'color'],
            'line-width': 1.6,
            'line-dasharray': [3, 2],
            'line-opacity': 0.75,
          },
        });
      } catch (err) {
        console.warn('watershed basins layer error:', err);
      }
    }
  }, []);

  // Helper to update all layer visibility properties
  const updateLayersVisibility = useCallback((map: maplibregl.Map, l: Record<string, boolean>) => {
    const setVis = (layerId: string, visible: boolean) => {
      if (map.getLayer(layerId)) {
        map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
      }
    };

    // 1. Precipitation Radar
    setVis('precipitation-radar-layer', !!l.precipitation);

    // 2. Rainfall Accumulation
    setVis('rainfall-accum-fill', !!l.rainfall_accumulation);
    setVis('rainfall-accum-line', !!l.rainfall_accumulation);

    // 3. Soil Moisture
    setVis('soil-moisture-fill', !!l.soil_moisture);
    setVis('soil-moisture-line', !!l.soil_moisture);

    // 4. Flood Risk
    setVis('flood-hazard-fill', !!l.flood_risk);
    setVis('flood-hazard-line', !!l.flood_risk);

    // 5. Landslide Risk
    setVis('landslide-hazard-fill', !!l.landslide_risk);
    setVis('landslide-hazard-line', !!l.landslide_risk);

    // 6. Terrain Slope
    setVis('terrain-slope-fill', !!l.terrain_slope);
    setVis('terrain-slope-line', !!l.terrain_slope);

    // 7. Rivers
    setVis('rivers-glow-layer', !!l.rivers_gauges);
    setVis('rivers-core-layer', !!l.rivers_gauges);

    // 8. Administrative Boundaries
    setVis('admin-boundaries-fill', !!l.admin_boundaries);
    setVis('admin-boundaries-line', !!l.admin_boundaries);

    // 10. Historical Events
    setVis('historical-events-fill', !!l.historical_events);
    setVis('historical-events-line', !!l.historical_events);

    // 11. Watershed Basins (Always visible as strategic background corridors)
    setVis('watershed-basins-fill', true);
    setVis('watershed-basins-line', true);
  }, []);

  // Helper to enable true 3D elevation terrain mesh in MapLibre
  const enable3DTerrain = useCallback((map: maplibregl.Map) => {
    try {
      if (!map.getSource('terrain-dem')) {
        map.addSource('terrain-dem', {
          type: 'raster-dem',
          tiles: ['https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'],
          encoding: 'terrarium',
          tileSize: 256,
          maxzoom: 15,
        });
      }
      map.setTerrain({ source: 'terrain-dem', exaggeration: 1.4 });
    } catch (err) {
      console.warn('enable3DTerrain error:', err);
    }
  }, []);

  // Generate MapLibre basemap style with reliable global satellite & vector tile servers
  const getMapStyle = useCallback((b: BasemapId): maplibregl.StyleSpecification => {
    if (b === 'satellite') {
      return {
        version: 8,
        sources: {
          'satellite-hybrid': {
            type: 'raster',
            tiles: [
              'https://mt0.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
              'https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
              'https://mt2.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
              'https://mt3.google.com/vt/lyrs=y&x={x}&y={y}&z={z}',
            ],
            tileSize: 256,
            attribution: '&copy; Google Satellite Imagery &amp; Cartography',
            maxzoom: 21,
          },
        },
        layers: [
          {
            id: 'satellite-hybrid-tiles',
            type: 'raster',
            source: 'satellite-hybrid',
            minzoom: 0,
            maxzoom: 22,
          },
        ],
      };
    }

    if (b === 'streets' || b === 'light') {
      return {
        version: 8,
        sources: {
          'google-streets': {
            type: 'raster',
            tiles: [
              'https://mt0.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
              'https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
              'https://mt2.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
              'https://mt3.google.com/vt/lyrs=m&x={x}&y={y}&z={z}',
            ],
            tileSize: 256,
            attribution: '&copy; Google Maps Roadways &amp; Infrastructure',
            maxzoom: 20,
          },
        },
        layers: [
          { id: 'google-streets-tiles', type: 'raster', source: 'google-streets', minzoom: 0, maxzoom: 20 },
        ],
      };
    }

    if (b === 'dark') {
      return {
        version: 8,
        sources: {
          'carto-dark': {
            type: 'raster',
            tiles: [
              'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
              'https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
              'https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png',
            ],
            tileSize: 256,
            attribution: '&copy; CartoDB',
            maxzoom: 20,
          },
        },
        layers: [
          { id: 'carto-dark-tiles', type: 'raster', source: 'carto-dark', minzoom: 0, maxzoom: 20 },
        ],
      };
    }

    if (b === 'terrain') {
      return {
        version: 8,
        sources: {
          'google-terrain': {
            type: 'raster',
            tiles: [
              'https://mt0.google.com/vt/lyrs=p&x={x}&y={y}&z={z}',
              'https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}',
              'https://mt2.google.com/vt/lyrs=p&x={x}&y={y}&z={z}',
              'https://mt3.google.com/vt/lyrs=p&x={x}&y={y}&z={z}',
            ],
            tileSize: 256,
            attribution: '&copy; Google Topo &amp; Relief',
            maxzoom: 20,
          },
        },
        layers: [
          { id: 'terrain-tiles', type: 'raster', source: 'google-terrain', minzoom: 0, maxzoom: 20 },
        ],
      };
    }

    return {
      version: 8,
      sources: {
        'osm-tiles': {
          type: 'raster',
          tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
          tileSize: 256,
          maxzoom: 19,
        },
      },
      layers: [
        { id: 'osm-layer', type: 'raster', source: 'osm-tiles', minzoom: 0, maxzoom: 19 },
      ],
    };
  }, []);

  // Map Initialization
  useEffect(() => {
    if (!mapContainerRef.current) return;

    const initialStyle = getMapStyle(basemap);

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: initialStyle,
      center: [79.25, 30.12],
      zoom: 3.8,
      pitch: 35,
      bearing: 0,
      maxPitch: 80,
      attributionControl: false,
    });

    try {
      if (typeof (map as unknown as { setProjection: (p: { type: string }) => void }).setProjection === 'function') {
        (map as unknown as { setProjection: (p: { type: string }) => void }).setProjection({ type: 'globe' });
      }
    } catch {
      // Safe fallback
    }

    map.on('rotate', () => setCompassAngle(-map.getBearing()));
    map.on('zoom', () => setCurrentZoom(Math.round(map.getZoom() * 10) / 10));

    map.on('load', () => {
      if (is3DActive) {
        enable3DTerrain(map);
      }
      addAllCustomLayers(map);
      updateLayersVisibility(map, layers);
    });

    mapRef.current = map;

    const resizeObserver = new ResizeObserver(() => map.resize());
    resizeObserver.observe(mapContainerRef.current);

    return () => {
      resizeObserver.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, [getMapStyle, addAllCustomLayers, updateLayersVisibility, enable3DTerrain, is3DActive]);

  // Handle Basemap Switching
  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;
    const newStyle = getMapStyle(basemap);
    map.setStyle(newStyle);

    map.once('style.load', () => {
      try {
        if (typeof (map as unknown as { setProjection: (p: { type: string }) => void }).setProjection === 'function') {
          (map as unknown as { setProjection: (p: { type: string }) => void }).setProjection({ type: 'globe' });
        }
      } catch {
        // Safe fallback
      }

      if (is3DActive) {
        enable3DTerrain(map);
      }
      addAllCustomLayers(map);
      updateLayersVisibility(map, layers);
    });
  }, [basemap, getMapStyle, addAllCustomLayers, updateLayersVisibility, layers, enable3DTerrain, is3DActive]);

  // Handle Layer Visibility Toggles (Instant Response to Left Panel)
  useEffect(() => {
    if (!mapRef.current) return;
    updateLayersVisibility(mapRef.current, layers);
  }, [layers, updateLayersVisibility]);

  // Render HTML CWC Gauge Markers (Layer: rivers_gauges)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    cwcMarkersRef.current.forEach((m: maplibregl.Marker) => m.remove());
    cwcMarkersRef.current = [];

    if (!layers.rivers_gauges) return;

    CWC_GAUGES.forEach((g) => {
      const el = document.createElement('div');
      el.className = 'cwc-gauge-marker';
      el.innerHTML = `
        <div style="
          background: rgba(10, 20, 36, 0.94);
          border: 1.5px solid ${g.color};
          border-radius: 6px;
          padding: 3px 7px;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          box-shadow: 0 4px 12px rgba(0,0,0,0.6);
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 1px;
          backdrop-filter: blur(4px);
          white-space: nowrap;
        ">
          <div style="display: flex; align-items: center; gap: 5px;">
            <span style="font-size: 10px;">🌊</span>
            <span style="font-size: 10.5px; font-weight: 700; color: #f8fafc;">${g.name}</span>
          </div>
          <div style="font-size: 9px; color: ${g.color}; font-weight: 700; font-family: monospace;">
            ${g.currentLvl} / ${g.dangerLvl} (${g.status})
          </div>
        </div>
        <div style="width: 2px; height: 6px; background: ${g.color}; margin: 0 auto;"></div>
      `;

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([g.lng, g.lat])
        .addTo(map);

      cwcMarkersRef.current.push(marker);
    });
  }, [layers.rivers_gauges]);

  // Render HTML IoT Sensor Markers (Layer: iot_sensors)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    iotMarkersRef.current.forEach((m: maplibregl.Marker) => m.remove());
    iotMarkersRef.current = [];

    if (!layers.iot_sensors) return;

    IOT_SENSORS.forEach((s) => {
      const el = document.createElement('div');
      el.className = 'iot-sensor-marker';
      el.innerHTML = `
        <div style="
          background: rgba(15, 23, 42, 0.94);
          border: 1.5px solid ${s.color};
          border-radius: 6px;
          padding: 3px 8px;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          box-shadow: 0 4px 12px rgba(0,0,0,0.6);
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 1px;
          backdrop-filter: blur(4px);
          white-space: nowrap;
        ">
          <div style="display: flex; align-items: center; gap: 5px;">
            <span style="font-size: 10px;">📡</span>
            <span style="font-size: 10px; font-weight: 800; color: ${s.color}; font-family: monospace;">[${s.id}]</span>
            <span style="font-size: 10px; font-weight: 600; color: #e2e8f0;">${s.name}</span>
          </div>
          <div style="font-size: 9px; color: #38bdf8; font-family: monospace; font-weight: 700;">
            ${s.loc} &bull; ${s.telemetry}
          </div>
        </div>
        <div style="width: 2px; height: 6px; background: ${s.color}; margin: 0 auto;"></div>
      `;

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([s.lng, s.lat])
        .addTo(map);

      iotMarkersRef.current.push(marker);
    });
  }, [layers.iot_sensors]);

  // Render HTML Historical Disaster Markers (Layer: historical_events)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    historicalMarkersRef.current.forEach((m: maplibregl.Marker) => m.remove());
    historicalMarkersRef.current = [];

    if (!layers.historical_events) return;

    HISTORICAL_DISASTER_PINS.forEach((h) => {
      const el = document.createElement('div');
      el.className = 'historical-event-marker';
      el.innerHTML = `
        <div style="
          background: rgba(46, 16, 101, 0.94);
          border: 1.5px solid #c084fc;
          border-radius: 6px;
          padding: 4px 8px;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          box-shadow: 0 4px 14px rgba(0,0,0,0.7);
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 1px;
          backdrop-filter: blur(4px);
          white-space: nowrap;
        ">
          <div style="display: flex; align-items: center; gap: 5px;">
            <span style="font-size: 10px;">📜</span>
            <span style="font-size: 10.5px; font-weight: 700; color: #f8fafc;">${h.name}</span>
          </div>
          <div style="font-size: 9px; color: #e9d5ff; font-family: monospace;">
            ${h.summary}
          </div>
        </div>
        <div style="width: 2px; height: 6px; background: #c084fc; margin: 0 auto;"></div>
      `;

      const marker = new maplibregl.Marker({ element: el })
        .setLngLat([h.lng, h.lat])
        .addTo(map);

      historicalMarkersRef.current.push(marker);
    });
  }, [layers.historical_events]);

  // Render HTML Interactive Markers (Zoom-Adaptive LOD: Corridor Hubs when < 6.0, Village Pins when >= 6.0)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    // Remove existing markers
    corridorMarkersRef.current.forEach((m) => m.remove());
    corridorMarkersRef.current = [];
    villageMarkersRef.current.forEach((m) => m.remove());
    villageMarkersRef.current = [];

    const isOverview = currentZoom < 6.0;

    if (isOverview) {
      // --- MODE A: RENDER 4 NATIONAL CORRIDOR CLUSTER HUBS ---
      NATIONAL_CORRIDORS.forEach((c) => {
        const corridorLocs = locations.filter((l) =>
          l.state?.toLowerCase().includes(c.matchState)
        );
        const count = corridorLocs.length || 4;
        const hasCritical = corridorLocs.some((l) => l.risk_level === 'CRITICAL');
        const hasHigh = corridorLocs.some((l) => l.risk_level === 'HIGH');
        const hasMod = corridorLocs.some((l) => l.risk_level === 'MODERATE');
        const maxRisk = hasCritical ? 'CRITICAL' : hasHigh ? 'HIGH' : hasMod ? 'MODERATE' : 'LOW';
        const hubColor = hasCritical ? '#ef4444' : hasHigh ? '#f97316' : hasMod ? '#facc15' : '#22c55e';
        const maxRain = Math.max(0, ...corridorLocs.map((l) => l.current_rainfall_mm || 0));

        const el = document.createElement('div');
        el.className = 'corridor-hub-marker';
        el.style.display = 'flex';
        el.style.flexDirection = 'column';
        el.style.alignItems = 'center';
        el.style.cursor = 'pointer';

        el.innerHTML = `
          <div style="
            background: rgba(10, 16, 26, 0.94);
            border: 1.5px solid ${hubColor};
            border-radius: 24px;
            padding: 5px 12px;
            box-shadow: 0 4px 18px rgba(0,0,0,0.65), 0 0 12px ${hubColor}40;
            display: flex;
            align-items: center;
            gap: 8px;
            white-space: nowrap;
            backdrop-filter: blur(8px);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
          ">
            <span style="font-size: 15px;">${c.icon}</span>
            <div style="display: flex; flex-direction: column; align-items: flex-start; line-height: 1.15;">
              <div style="display: flex; align-items: center; gap: 6px;">
                <span style="font-size: 11.5px; font-weight: 800; color: #ffffff; letter-spacing: 0.02em;">${c.name}</span>
                <span style="font-size: 9px; font-weight: 800; background: ${hubColor}; color: #000; padding: 1px 6px; border-radius: 10px;">${count} STATIONS</span>
              </div>
              <div style="font-size: 9px; color: #94a3b8; font-weight: 600; margin-top: 1px;">
                ${c.basin} &bull; <span style="color: ${hubColor}; font-weight: 700;">${maxRisk}</span>
                ${maxRain > 0 ? `<span style="color: #38bdf8; font-family: monospace;"> &bull; ${maxRain.toFixed(1)} mm/h</span>` : ''}
              </div>
            </div>
            <span style="font-size: 11px; color: #38bdf8; margin-left: 2px;">&rarr;</span>
          </div>
          <!-- Google Maps Needle Point -->
          <div style="width: 2px; height: 10px; background: ${hubColor}; margin-top: -1px;"></div>
          <div style="width: 8px; height: 8px; border-radius: 50%; background: ${hubColor}; border: 2px solid #ffffff; box-shadow: 0 0 10px ${hubColor};"></div>
        `;

        el.addEventListener('mouseenter', () => {
          el.style.transform = 'scale(1.06)';
        });
        el.addEventListener('mouseleave', () => {
          el.style.transform = 'scale(1.0)';
        });

        el.addEventListener('click', (e) => {
          e.stopPropagation();
          map.flyTo({
            center: [c.lng, c.lat],
            zoom: c.zoomTarget,
            pitch: c.pitchTarget,
            bearing: -10,
            duration: 1600,
            essential: true,
          });
        });

        const marker = new maplibregl.Marker({ element: el, anchor: 'bottom' })
          .setLngLat([c.lng, c.lat])
          .addTo(map);

        corridorMarkersRef.current.push(marker);
      });
    } else {
      // --- MODE B: RENDER 16 AUTHENTIC GOOGLE MAPS TEARDROP NEEDLE PINS ---
      locations.forEach((loc: LocationRisk) => {
        const el = document.createElement('div');
        el.className = 'google-maps-station-marker';
        el.style.display = 'flex';
        el.style.flexDirection = 'column';
        el.style.alignItems = 'center';
        el.style.cursor = 'pointer';

        const color =
          loc.risk_level === 'CRITICAL'
            ? '#ef4444'
            : loc.risk_level === 'HIGH'
            ? '#f97316'
            : loc.risk_level === 'MODERATE'
            ? '#facc15'
            : '#22c55e';

        el.innerHTML = `
          <!-- Google Maps Pill Label -->
          <div style="
            background: rgba(10, 16, 26, 0.94);
            border: 1.5px solid ${color};
            border-radius: 12px;
            padding: 2px 7px;
            box-shadow: 0 3px 10px rgba(0,0,0,0.6);
            display: flex;
            align-items: center;
            gap: 5px;
            white-space: nowrap;
            backdrop-filter: blur(6px);
            margin-bottom: 2px;
          ">
            <span style="width: 6px; height: 6px; border-radius: 50%; background: ${color}; box-shadow: 0 0 6px ${color};"></span>
            <span style="font-size: 11px; font-weight: 700; color: #ffffff;">${loc.name}</span>
            <span style="font-size: 9px; font-family: monospace; font-weight: 700; color: #38bdf8;">${loc.current_rainfall_mm} mm/h</span>
          </div>
          <!-- Authentic Google Maps Teardrop SVG Pin -->
          <svg width="24" height="32" viewBox="0 0 24 32" fill="none" xmlns="http://www.w3.org/2000/svg" style="filter: drop-shadow(0 3px 6px rgba(0,0,0,0.4));">
            <path d="M12 0C5.37 0 0 5.37 0 12C0 21 12 32 12 32C12 32 24 21 24 12C24 5.37 18.63 0 12 0Z" fill="${color}"/>
            <circle cx="12" cy="12" r="5.5" fill="#ffffff"/>
            <circle cx="12" cy="12" r="3" fill="${color}"/>
          </svg>
        `;

        el.addEventListener('click', (e) => {
          e.stopPropagation();
          onSelectLocation(loc);

          // Open Google Maps InfoWindow Popup
          if (activePopupRef.current) {
            activePopupRef.current.remove();
          }

          const popupContent = `
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; min-width: 210px; color: #0f172a; padding: 2px 4px;">
              <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; margin-bottom: 8px;">
                <div>
                  <div style="font-size: 14px; font-weight: 800; color: #0f172a;">${loc.name}</div>
                  <div style="font-size: 10.5px; color: #64748b;">${loc.district}, ${loc.state}</div>
                </div>
                <span style="font-size: 9.5px; font-weight: 800; padding: 2px 7px; border-radius: 8px; background: ${color}; color: ${color === '#facc15' ? '#000' : '#ffffff'};">
                  ${loc.risk_level}
                </span>
              </div>
              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-bottom: 8px; font-size: 11px;">
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; padding: 4px 6px; border-radius: 4px;">
                  <div style="color: #64748b; font-size: 8.5px; font-weight: 600;">RAINFALL</div>
                  <div style="font-weight: 800; color: #0284c7; font-family: monospace;">${loc.current_rainfall_mm} mm/h</div>
                </div>
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; padding: 4px 6px; border-radius: 4px;">
                  <div style="color: #64748b; font-size: 8.5px; font-weight: 600;">RIVER RISE</div>
                  <div style="font-weight: 800; color: #d97706; font-family: monospace;">+${loc.river_level_rise_m} m</div>
                </div>
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; padding: 4px 6px; border-radius: 4px;">
                  <div style="color: #64748b; font-size: 8.5px; font-weight: 600;">SOIL SAT</div>
                  <div style="font-weight: 800; color: #16a34a; font-family: monospace;">${Math.round(loc.soil_moisture_saturation * 100)}%</div>
                </div>
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; padding: 4px 6px; border-radius: 4px;">
                  <div style="color: #64748b; font-size: 8.5px; font-weight: 600;">ELEVATION</div>
                  <div style="font-weight: 800; color: #475569; font-family: monospace;">${loc.elevation_m} m</div>
                </div>
              </div>
              <div style="font-size: 9.5px; color: #64748b; font-weight: 600; text-align: center; border-top: 1px dashed #e2e8f0; padding-top: 5px;">
                🎯 Synchronized to Overview Panel &amp; Hydrograph
              </div>
            </div>
          `;

          const popup = new maplibregl.Popup({
            offset: [0, -32],
            closeButton: true,
            closeOnClick: true,
            maxWidth: '300px',
          })
            .setLngLat([loc.longitude, loc.latitude])
            .setHTML(popupContent)
            .addTo(map);

          activePopupRef.current = popup;

          map.flyTo({
            center: [loc.longitude, loc.latitude],
            zoom: 13.5,
            pitch: 55,
            bearing: -15,
            duration: 1600,
            essential: true,
          });
        });

        const marker = new maplibregl.Marker({ element: el, anchor: 'bottom' })
          .setLngLat([loc.longitude, loc.latitude])
          .addTo(map);

        villageMarkersRef.current.push(marker);
      });
    }
  }, [locations, onSelectLocation, currentZoom < 6.0]);

  // Render HTML Tropical Cyclone Markers (BOB-03 in Bay of Bengal & AS-01 in Arabian Sea)
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    cycloneMarkersRef.current.forEach((m: maplibregl.Marker) => m.remove());
    cycloneMarkersRef.current = [];

    // 1. Deep Depression BOB-03 Marker in Bay of Bengal
    const el = document.createElement('div');
    el.className = 'cyclone-storm-marker';
    el.style.cursor = 'pointer';
    el.innerHTML = `
      <div style="
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 3px;
        transform: translate(-50%, -50%);
        filter: drop-shadow(0 4px 14px rgba(239, 68, 68, 0.7));
      ">
        <div style="
          position: relative;
          width: 44px;
          height: 44px;
          display: flex;
          align-items: center;
          justify-content: center;
        ">
          <!-- Pulsing Gale Ring -->
          <div style="
            position: absolute;
            width: 100%;
            height: 100%;
            border-radius: 50%;
            border: 2px dashed #ef4444;
            background: rgba(239, 68, 68, 0.18);
          "></div>
          <!-- Storm Center Eye -->
          <div style="
            width: 22px;
            height: 22px;
            border-radius: 50%;
            background: #ef4444;
            border: 2px solid #ffffff;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 0 14px rgba(239, 68, 68, 0.95);
          ">
            <span style="font-size: 11px;">🌀</span>
          </div>
        </div>
        <div style="
          background: rgba(10, 20, 38, 0.94);
          border: 1.5px solid #ef4444;
          border-radius: 5px;
          padding: 2px 7px;
          color: #ffffff;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
          font-size: 9.5px;
          font-weight: 700;
          white-space: nowrap;
          box-shadow: 0 4px 12px rgba(0,0,0,0.6);
          display: flex;
          align-items: center;
          gap: 4px;
        ">
          <span style="color: #f87171;">BOB-03</span>
          <span style="color: #94a3b8;">•</span>
          <span style="color: #38bdf8;">65 km/h</span>
        </div>
      </div>
    `;

    el.onclick = () => {
      if (onOpenTropicalActivity) {
        onOpenTropicalActivity();
      }
    };

    const marker = new maplibregl.Marker({ element: el })
      .setLngLat([88.42, 19.45])
      .addTo(map);

    cycloneMarkersRef.current.push(marker);
  }, [onOpenTropicalActivity]);

  // Handle Focus Target from Search or Region Tabs
  useEffect(() => {
    if (!focusTarget || !mapRef.current) return;
    const map = mapRef.current;

    let targetZoom = focusTarget.zoom !== undefined ? focusTarget.zoom : 11;
    let targetPitch = focusTarget.pitch !== undefined ? focusTarget.pitch : 45;

    if (focusTarget.zoom === undefined) {
      if (focusTarget.zoomDistance && focusTarget.zoomDistance > 10) {
        targetZoom = 1.8;
        targetPitch = 0;
      } else if (focusTarget.zoomDistance && focusTarget.zoomDistance > 7) {
        targetZoom = 4.6;
        targetPitch = 15;
      } else if (focusTarget.zoomDistance && focusTarget.zoomDistance > 6) {
        targetZoom = 7.2;
        targetPitch = 30;
      } else if (focusTarget.zoomDistance && focusTarget.zoomDistance > 5) {
        targetZoom = 10.8;
        targetPitch = 45;
      } else {
        targetZoom = 14.2;
        targetPitch = 55;
      }
    }

    map.flyTo({
      center: [focusTarget.lng, focusTarget.lat],
      zoom: targetZoom,
      pitch: targetPitch,
      essential: true,
      duration: 2200,
    });
  }, [focusTarget]);

  // Selected Location auto-centering
  useEffect(() => {
    if (!selectedLocation || !mapRef.current) return;
    mapRef.current.flyTo({
      center: [selectedLocation.longitude, selectedLocation.latitude],
      zoom: 14.2,
      pitch: 55,
      essential: true,
      duration: 1600,
    });
  }, [selectedLocation]);

  // Control Handlers
  const handleZoomIn = () => mapRef.current?.zoomIn();
  const handleZoomOut = () => mapRef.current?.zoomOut();

  const handleResetHome = () => {
    mapRef.current?.flyTo({
      center: [79.25, 23.5],
      zoom: 3.8,
      pitch: 35,
      bearing: 0,
      duration: 1800,
      essential: true,
    });
  };

  const handleResetNorth = () => {
    mapRef.current?.easeTo({ bearing: 0, pitch: 0, duration: 800 });
  };

  const handleToggle3DPitch = () => {
    if (!mapRef.current) return;
    const map = mapRef.current;
    const next3D = !is3DActive;
    setIs3DActive(next3D);
    map.easeTo({ pitch: next3D ? 58 : 0, duration: 900 });
    try {
      if (next3D) {
        enable3DTerrain(map);
      } else {
        map.setTerrain(null);
      }
    } catch {
      // safe fallback
    }
  };

  // Count active layers for feedback indicator
  const activeLayersCount = Object.values(layers).filter(Boolean).length;

  return (
    <div
      ref={mapContainerRef}
      className="global-earth-container"
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        background: '#060b14',
      }}
    >
      {/* Floating Left Navigation Controls */}
      <div className="globe-controls-left">
        {/* Compass Needle */}
        <div
          className="globe-ctrl-btn compass-btn"
          title="Reset North"
          onClick={handleResetNorth}
        >
          <div className="compass-inner" style={{ transform: `rotate(${compassAngle}deg)` }}>
            <span className="compass-n">N</span>
            <div className="compass-needle" />
          </div>
        </div>

        {/* Home / Global Reset Button */}
        <button
          className="globe-ctrl-btn"
          title="Overview View / Reset"
          onClick={handleResetHome}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
            <polyline points="9 22 9 12 15 12 15 22" />
          </svg>
        </button>

        {/* 3D Himalayan Terrain Tilt Button */}
        <button
          className={`globe-ctrl-btn ${is3DActive ? 'active' : ''}`}
          title={is3DActive ? 'Switch to 2D Top-Down View' : 'Switch to 3D Mountain Perspective'}
          onClick={handleToggle3DPitch}
          style={{
            fontSize: '11px',
            fontWeight: 800,
            color: is3DActive ? '#00d4ff' : '#94a3b8',
          }}
        >
          3D
        </button>

        {/* Zoom In Button */}
        <button
          className="globe-ctrl-btn"
          title="Zoom In"
          onClick={handleZoomIn}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>

        {/* Zoom Out Button */}
        <button
          className="globe-ctrl-btn"
          title="Zoom Out"
          onClick={handleZoomOut}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
      </div>

      {/* Floating Right Basemap Selectors */}
      <div className="globe-controls-right">
        {(['satellite', 'terrain', 'streets', 'dark'] as BasemapId[]).map((b) => (
          <button
            key={b}
            className={`basemap-btn ${basemap === b || (b === 'streets' && basemap === 'light') ? 'active' : ''}`}
            onClick={() => onBasemapChange(b)}
          >
            {b === 'satellite' && '🛰️ Google Satellite'}
            {b === 'terrain' && '🏔️ 3D Terrain'}
            {b === 'streets' && '🗺️ Google Streets'}
            {b === 'dark' && '🌑 Tactical Dark'}
          </button>
        ))}
      </div>

      {/* Floating Real-Time Spatial Radar & Multilayer Status Pill */}
      <div
        style={{
          position: 'absolute',
          top: '16px',
          left: '50%',
          transform: 'translateX(-50%)',
          zIndex: 30,
          background: 'rgba(10, 16, 26, 0.88)',
          border: '1px solid rgba(255, 255, 255, 0.12)',
          borderRadius: '20px',
          padding: '5px 14px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          backdropFilter: 'blur(8px)',
          boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
          pointerEvents: 'none',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#22c55e', boxShadow: '0 0 6px #22c55e' }}></span>
          <span style={{ fontSize: '11px', fontWeight: 600, color: '#f1f5f9', letterSpacing: '0.3px' }}>
            MULTILAYER GIS ACTIVE ({activeLayersCount}/10)
          </span>
        </div>
        <span style={{ width: '1px', height: '12px', background: 'rgba(255,255,255,0.15)' }}></span>
        <span style={{ fontSize: '11px', color: '#38bdf8', fontFamily: 'monospace' }}>
          {replayTime}
        </span>
        <span style={{ width: '1px', height: '12px', background: 'rgba(255,255,255,0.15)' }}></span>
        <span style={{ fontSize: '11px', color: '#94a3b8' }}>
          Zoom: {currentZoom}x
        </span>
      </div>
    </div>
  );
};

export default GlobalEarthGlobe;
