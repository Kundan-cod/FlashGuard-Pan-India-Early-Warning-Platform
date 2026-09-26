import React, { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { LocationRisk, BasemapId } from '../types';

interface TacticalMapViewProps {
  locations: LocationRisk[];
  selectedLocation: LocationRisk | null;
  onSelectLocation: (loc: LocationRisk) => void;
  basemap: BasemapId;
  layers: Record<string, boolean>;
  focusTarget?: { lat: number; lng: number; zoomDistance?: number; zoom?: number; pitch?: number } | null;
}

export const TacticalMapView: React.FC<TacticalMapViewProps> = ({
  locations,
  selectedLocation,
  onSelectLocation,
  basemap,
  focusTarget,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  const getTileUrl = (b: BasemapId) => {
    switch (b) {
      case 'satellite':
        return 'https://mt0.google.com/vt/lyrs=y&x={x}&y={y}&z={z}';
      case 'dark':
        return 'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png';
      case 'terrain':
        return 'https://mt0.google.com/vt/lyrs=p&x={x}&y={y}&z={z}';
      case 'streets':
        return 'https://mt0.google.com/vt/lyrs=m&x={x}&y={y}&z={z}';
      case 'light':
      default:
        return 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
    }
  };

  useEffect(() => {
    if (!mapContainerRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {
          'tactical-basemap': {
            type: 'raster',
            tiles: [getTileUrl(basemap)],
            tileSize: 256,
            attribution: '© OpenStreetMap, ESRI, FlashGuard Tactical GIS',
          },
        },
        layers: [
          {
            id: 'tactical-basemap-layer',
            type: 'raster',
            source: 'tactical-basemap',
            minzoom: 0,
            maxzoom: 19,
          },
        ],
      },
      center: [79.25, 30.12], // Centered on Devgaon / Uttarakhand
      zoom: 9.5,
    });

    mapRef.current = map;

    map.on('load', () => {
      // 1. Create Village GeoJSON Polygons
      const villageFeatures: any[] = locations.map((loc) => {
        const offset = 0.035;
        return {
          type: 'Feature',
          properties: {
            id: loc.id,
            name: loc.name,
            risk_level: loc.risk_level,
            overall_risk: loc.overall_risk,
            flood_probability: loc.flood_probability,
            landslide_probability: loc.landslide_probability,
            color:
              loc.risk_level === 'CRITICAL'
                ? '#ef4444'
                : loc.risk_level === 'HIGH'
                ? '#f59e0b'
                : loc.risk_level === 'MODERATE'
                ? '#00d4ff'
                : '#10b981',
          },
          geometry: {
            type: 'Polygon',
            coordinates: [
              [
                [loc.longitude - offset, loc.latitude - offset],
                [loc.longitude + offset, loc.latitude - offset],
                [loc.longitude + offset, loc.latitude + offset],
                [loc.longitude - offset, loc.latitude + offset],
                [loc.longitude - offset, loc.latitude - offset],
              ],
            ],
          },
        };
      });

      map.addSource('village-polygons', {
        type: 'geojson',
        data: {
          type: 'FeatureCollection',
          features: villageFeatures,
        },
      });

      // Polygon Fill
      map.addLayer({
        id: 'village-polygon-fill',
        type: 'fill',
        source: 'village-polygons',
        paint: {
          'fill-color': ['get', 'color'],
          'fill-opacity': 0.35,
        },
      });

      // Polygon Outline
      map.addLayer({
        id: 'village-polygon-line',
        type: 'line',
        source: 'village-polygons',
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 2.5,
        },
      });

      // Interactive Click on Polygons
      map.on('click', 'village-polygon-fill', (e) => {
        if (e.features && e.features[0]) {
          const feat = e.features[0];
          const found = locations.find((l) => l.name === feat.properties?.name);
          if (found) {
            onSelectLocation(found);
          }
        }
      });

      map.on('mouseenter', 'village-polygon-fill', () => {
        map.getCanvas().style.cursor = 'pointer';
      });

      map.on('mouseleave', 'village-polygon-fill', () => {
        map.getCanvas().style.cursor = '';
      });

      // 2. Add Markers for Villages
      locations.forEach((loc) => {
        const el = document.createElement('div');
        el.className = `tactical-marker ${loc.risk_level.toLowerCase()}`;
        el.style.width = '24px';
        el.style.height = '24px';
        el.style.borderRadius = '50%';
        el.style.display = 'flex';
        el.style.alignItems = 'center';
        el.style.justifyContent = 'center';
        el.style.color = '#ffffff';
        el.style.fontWeight = 'bold';
        el.style.fontSize = '10px';
        el.style.cursor = 'pointer';
        el.style.boxShadow = '0 0 10px rgba(0,0,0,0.8)';
        el.style.backgroundColor =
          loc.risk_level === 'CRITICAL'
            ? '#ef4444'
            : loc.risk_level === 'HIGH'
            ? '#f59e0b'
            : '#10b981';
        el.innerText = loc.name.slice(0, 1);

        el.addEventListener('click', () => {
          onSelectLocation(loc);
        });

        new maplibregl.Marker({ element: el })
          .setLngLat([loc.longitude, loc.latitude])
          .setPopup(
            new maplibregl.Popup({ offset: 25 }).setHTML(
              `<div style="color:#0f172a; font-family: Inter, sans-serif; padding: 4px;">
                <strong style="font-size: 12px;">${loc.name}</strong><br/>
                <span style="font-size: 10px; color: #64748b;">${loc.block}, ${loc.district}</span><br/>
                <span style="font-size: 11px; font-weight: bold; color: ${
                  loc.risk_level === 'CRITICAL' ? '#ef4444' : '#f59e0b'
                };">${loc.risk_level} RISK (${(loc.overall_risk * 100).toFixed(0)}%)</span>
              </div>`
            )
          )
          .addTo(map);
      });
    });

    return () => {
      map.remove();
    };
  }, []);

  // Update center when selectedLocation changes
  useEffect(() => {
    if (mapRef.current && selectedLocation) {
      mapRef.current.flyTo({
        center: [selectedLocation.longitude, selectedLocation.latitude],
        zoom: 12,
        speed: 1.2,
      });
    }
  }, [selectedLocation]);

  // Handle focusTarget
  useEffect(() => {
    if (!mapRef.current || !focusTarget) return;
    mapRef.current.flyTo({
      center: [focusTarget.lng, focusTarget.lat],
      zoom: focusTarget.zoom !== undefined ? focusTarget.zoom : 10,
      pitch: focusTarget.pitch !== undefined ? focusTarget.pitch : 0,
      duration: 1800,
    });
  }, [focusTarget]);

  return (
    <div
      ref={mapContainerRef}
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
      }}
    />
  );
};
