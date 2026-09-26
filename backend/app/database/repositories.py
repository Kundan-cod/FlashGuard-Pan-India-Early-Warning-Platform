"""
Repositories — the storage-agnostic DAL surface (master prompt sections 7, 10).

All upserts are idempotent on the natural keys declared in schema_sqlite.sql
(section 7: re-ingesting the same data must not create duplicates). Track B
implements these same function names over SQLAlchemy/PostGIS.
"""
from __future__ import annotations

import json
from typing import Any

from app.database import db
from app.geospatial import spatial


# --------------------------------------------------------------------------
# Locations
# --------------------------------------------------------------------------
def upsert_location(loc: dict) -> int:
    geom = loc.get("geometry")
    gj = db.dump_geojson(geom)
    bx = (None, None, None, None)
    lat, lon = loc.get("latitude"), loc.get("longitude")
    if geom:
        bx = spatial.bbox(geom)
        if lat is None or lon is None:
            cx, cy = spatial.polygon_centroid(geom)
            lon, lat = cx, cy
    db.execute(
        """INSERT INTO locations(ext_code,name,level,parent_id,state,district,
             block,village,latitude,longitude,geometry_geojson,
             bbox_minx,bbox_miny,bbox_maxx,bbox_maxy,is_synthetic)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(ext_code) DO UPDATE SET
             name=excluded.name, level=excluded.level, parent_id=excluded.parent_id,
             state=excluded.state, district=excluded.district, block=excluded.block,
             village=excluded.village, latitude=excluded.latitude,
             longitude=excluded.longitude, geometry_geojson=excluded.geometry_geojson,
             bbox_minx=excluded.bbox_minx, bbox_miny=excluded.bbox_miny,
             bbox_maxx=excluded.bbox_maxx, bbox_maxy=excluded.bbox_maxy,
             is_synthetic=excluded.is_synthetic""",
        (loc.get("ext_code"), loc["name"], loc["level"], loc.get("parent_id"),
         loc.get("state"), loc.get("district"), loc.get("block"),
         loc.get("village"), lat, lon, gj, bx[0], bx[1], bx[2], bx[3],
         int(loc.get("is_synthetic", 0))),
    )
    row = db.query_one("SELECT id FROM locations WHERE ext_code=?", (loc.get("ext_code"),))
    return row["id"] if row else -1


def get_location(location_id: int) -> dict | None:
    row = db.query_one("SELECT * FROM locations WHERE id=?", (location_id,))
    if row:
        row["geometry"] = db.load_geojson(row.get("geometry_geojson"))
    return row


def list_locations(level: str | None = None, parent_id: int | None = None) -> list[dict]:
    sql = "SELECT * FROM locations WHERE 1=1"
    params: list[Any] = []
    if level:
        sql += " AND level=?"
        params.append(level)
    if parent_id is not None:
        sql += " AND parent_id=?"
        params.append(parent_id)
    sql += " ORDER BY name"
    rows = db.query(sql, params)
    for r in rows:
        r["geometry"] = db.load_geojson(r.get("geometry_geojson"))
    return rows


def upsert_terrain(location_id: int, t: dict) -> None:
    db.execute(
        """INSERT INTO terrain_features(location_id,elevation,slope,aspect,
             curvature,flow_accumulation,drainage_density,distance_to_drainage,
             relative_relief,is_synthetic,source)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(location_id) DO UPDATE SET
             elevation=excluded.elevation, slope=excluded.slope,
             aspect=excluded.aspect, curvature=excluded.curvature,
             flow_accumulation=excluded.flow_accumulation,
             drainage_density=excluded.drainage_density,
             distance_to_drainage=excluded.distance_to_drainage,
             relative_relief=excluded.relative_relief,
             is_synthetic=excluded.is_synthetic, source=excluded.source""",
        (location_id, t.get("elevation"), t.get("slope"), t.get("aspect"),
         t.get("curvature"), t.get("flow_accumulation"), t.get("drainage_density"),
         t.get("distance_to_drainage"), t.get("relative_relief"),
         int(t.get("is_synthetic", 0)), t.get("source")),
    )


def get_terrain(location_id: int) -> dict | None:
    return db.query_one("SELECT * FROM terrain_features WHERE location_id=?", (location_id,))


# --------------------------------------------------------------------------
# Observations (idempotent upserts on natural keys)
# --------------------------------------------------------------------------
def upsert_rainfall(o: dict) -> int:
    return db.execute(
        """INSERT INTO rainfall_observations(source,ts,latitude,longitude,
             rainfall_30m,rainfall_3h,rainfall_24h,quality_flag,resolution_m,realtime_class,units,granule_id)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(source,ts,latitude,longitude) DO UPDATE SET
             rainfall_30m=excluded.rainfall_30m, rainfall_3h=excluded.rainfall_3h,
             rainfall_24h=excluded.rainfall_24h, quality_flag=excluded.quality_flag,
             resolution_m=excluded.resolution_m, realtime_class=excluded.realtime_class,
             units=excluded.units, granule_id=excluded.granule_id""",
        (o["source"], o["ts"], o["latitude"], o["longitude"], o.get("rainfall_30m"),
         o.get("rainfall_3h"), o.get("rainfall_24h"), o.get("quality_flag", "GOOD"),
         o.get("resolution_m"), o.get("realtime_class"),
         o.get("units", "mm"), o.get("granule_id")),
    )



def upsert_soil(o: dict) -> int:
    return db.execute(
        """INSERT INTO soil_moisture_observations(source,ts,latitude,longitude,
             surface_moisture,root_zone_moisture,quality_flag,resolution_m,realtime_class)
           VALUES(?,?,?,?,?,?,?,?,?)
           ON CONFLICT(source,ts,latitude,longitude) DO UPDATE SET
             surface_moisture=excluded.surface_moisture,
             root_zone_moisture=excluded.root_zone_moisture,
             quality_flag=excluded.quality_flag, resolution_m=excluded.resolution_m,
             realtime_class=excluded.realtime_class""",
        (o["source"], o["ts"], o["latitude"], o["longitude"], o.get("surface_moisture"),
         o.get("root_zone_moisture"), o.get("quality_flag", "GOOD"),
         o.get("resolution_m"), o.get("realtime_class")),
    )


def upsert_river(o: dict) -> int:
    return db.execute(
        """INSERT INTO river_observations(source,station_id,ts,latitude,longitude,
             water_level,flow,rate_of_rise,quality_flag,realtime_class)
           VALUES(?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(source,station_id,ts) DO UPDATE SET
             water_level=excluded.water_level, flow=excluded.flow,
             rate_of_rise=excluded.rate_of_rise, quality_flag=excluded.quality_flag,
             realtime_class=excluded.realtime_class""",
        (o["source"], o.get("station_id"), o["ts"], o.get("latitude"),
         o.get("longitude"), o.get("water_level"), o.get("flow"),
         o.get("rate_of_rise"), o.get("quality_flag", "GOOD"), o.get("realtime_class")),
    )


def upsert_iot(o: dict) -> int:
    return db.execute(
        """INSERT INTO iot_observations(sensor_id,ts,latitude,longitude,rainfall,
             soil_moisture,water_level,temperature,quality_flag,is_simulated)
           VALUES(?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(sensor_id,ts) DO UPDATE SET
             rainfall=excluded.rainfall, soil_moisture=excluded.soil_moisture,
             water_level=excluded.water_level, temperature=excluded.temperature,
             quality_flag=excluded.quality_flag, is_simulated=excluded.is_simulated""",
        (o["sensor_id"], o["ts"], o.get("latitude"), o.get("longitude"),
         o.get("rainfall"), o.get("soil_moisture"), o.get("water_level"),
         o.get("temperature"), o.get("quality_flag", "GOOD"), int(o.get("is_simulated", 1))),
    )


def upsert_iot_raw(r: dict) -> int:
    import json
    payload_str = json.dumps(r.get("raw_payload", {})) if isinstance(r.get("raw_payload"), dict) else str(r.get("raw_payload", ""))
    return db.execute(
        """INSERT INTO iot_raw_telemetry(source, channel_id, entry_id, ts, raw_payload, quality_flag)
           VALUES(?,?,?,?,?,?)
           ON CONFLICT(channel_id, entry_id) DO UPDATE SET
             raw_payload=excluded.raw_payload, quality_flag=excluded.quality_flag, ts=excluded.ts""",
        (r.get("source", "thingspeak"), str(r["channel_id"]), int(r["entry_id"]),
         r["ts"], payload_str, r.get("quality_flag", "GOOD")),
    )


def latest_iot_raw(channel_id: str, limit: int = 10) -> list[dict]:
    return db.query(
        "SELECT * FROM iot_raw_telemetry WHERE channel_id=? ORDER BY entry_id DESC LIMIT ?",
        (str(channel_id), limit),
    )


def iot_series(sensor_id: str, limit: int = 100) -> list[dict]:
    return db.query(
        "SELECT * FROM iot_observations WHERE sensor_id=? ORDER BY ts DESC LIMIT ?",
        (sensor_id, limit),
    )


def iot_latest(sensor_id: str) -> dict | None:
    return db.query_one(
        "SELECT * FROM iot_observations WHERE sensor_id=? ORDER BY ts DESC LIMIT 1",
        (sensor_id,),
    )


def upsert_gpm_discovery(d: dict) -> int:
    """Store a GPM PMM dataset-discovery record. This is NOT a rainfall
    observation: numeric_value stays NULL until the gated raster-sampling stage
    computes a real mm value. The feature pipeline never reads this table, so a
    discovery record can never masquerade as rainfall (see feature engineer)."""
    return db.execute(
        """INSERT INTO gpm_discovery(source,product,observed_date,latitude,
             longitude,resolution,download_url,media_type,item_id,numeric_value,
             stage,raw_reference,retrieved_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(item_id,download_url) DO UPDATE SET
             product=excluded.product, observed_date=excluded.observed_date,
             latitude=excluded.latitude, longitude=excluded.longitude,
             resolution=excluded.resolution, media_type=excluded.media_type,
             numeric_value=excluded.numeric_value, stage=excluded.stage,
             raw_reference=excluded.raw_reference,
             retrieved_at=excluded.retrieved_at""",
        (d.get("source", "gpm"), d.get("product"), d.get("observed_date"),
         d.get("latitude"), d.get("longitude"), d.get("resolution"),
         d.get("download_url"), d.get("media_type"), d.get("item_id"),
         d.get("numeric_value"), d.get("stage", "DISCOVERY_ONLY"),
         d.get("raw_reference"), d.get("retrieved_at")),
    )


def gpm_discovery_recent(limit: int = 50) -> list[dict]:
    return db.query(
        "SELECT * FROM gpm_discovery ORDER BY ingested_at DESC, id DESC LIMIT ?",
        (limit,))


def upsert_smap_discovery(d: dict) -> int:
    """Store a NASA SMAP CMR granule-discovery record. This is NOT a soil-
    moisture observation: surface_sm/rootzone_sm stay NULL until a gated
    HDF5/NetCDF parse stage computes real m3/m3 values. The feature pipeline
    never reads this table, so a discovery record can never masquerade as a
    measurement."""
    return db.execute(
        """INSERT INTO smap_discovery(source,product,version,observed_date,
             end_time,latitude,longitude,grid,download_url,concept_id,
             producer_granule_id,surface_sm,rootzone_sm,quality_flag,stage,
             raw_reference,retrieved_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(concept_id,download_url) DO UPDATE SET
             product=excluded.product, version=excluded.version,
             observed_date=excluded.observed_date, end_time=excluded.end_time,
             latitude=excluded.latitude, longitude=excluded.longitude,
             grid=excluded.grid, producer_granule_id=excluded.producer_granule_id,
             surface_sm=excluded.surface_sm, rootzone_sm=excluded.rootzone_sm,
             quality_flag=excluded.quality_flag, stage=excluded.stage,
             raw_reference=excluded.raw_reference,
             retrieved_at=excluded.retrieved_at""",
        (d.get("source", "smap"), d.get("product"), d.get("version"),
         d.get("observed_date"), d.get("end_time"), d.get("latitude"),
         d.get("longitude"), d.get("grid"), d.get("download_url"),
         d.get("concept_id"), d.get("producer_granule_id"),
         d.get("surface_sm"), d.get("rootzone_sm"),
         d.get("quality_flag", "UNKNOWN"), d.get("stage", "DISCOVERY_ONLY"),
         d.get("raw_reference"), d.get("retrieved_at")),
    )


def smap_discovery_recent(limit: int = 50) -> list[dict]:
    return db.query(
        "SELECT * FROM smap_discovery ORDER BY ingested_at DESC, id DESC LIMIT ?",
        (limit,))


def upsert_mosdac_discovery(d: dict) -> int:
    """Store an ISRO MOSDAC INSAT granule-discovery record. This is NOT a
    rainfall observation: numeric_value stays NULL until a gated raster/HDF-parse
    stage computes a real mm value. The feature pipeline never reads this table,
    so a discovery record can never masquerade as a numeric rainfall observation.
    Idempotent on (dataset_id, granule_id, download_url)."""
    return db.execute(
        """INSERT INTO mosdac_discovery(source,dataset_id,satellite,product,
             observed_date,end_time,latitude,longitude,resolution,download_url,
             granule_id,numeric_value,quality_flag,stage,raw_reference,
             retrieved_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(dataset_id,granule_id,download_url) DO UPDATE SET
             source=excluded.source, satellite=excluded.satellite,
             product=excluded.product, observed_date=excluded.observed_date,
             end_time=excluded.end_time, latitude=excluded.latitude,
             longitude=excluded.longitude, resolution=excluded.resolution,
             numeric_value=excluded.numeric_value,
             quality_flag=excluded.quality_flag, stage=excluded.stage,
             raw_reference=excluded.raw_reference,
             retrieved_at=excluded.retrieved_at""",
        (d.get("source", "mosdac"), d.get("dataset_id"), d.get("satellite"),
         d.get("product"), d.get("observed_date"), d.get("end_time"),
         d.get("latitude"), d.get("longitude"), d.get("resolution"),
         d.get("download_url"), d.get("granule_id"), d.get("numeric_value"),
         d.get("quality_flag", "UNKNOWN"), d.get("stage", "DISCOVERY_ONLY"),
         d.get("raw_reference"), d.get("retrieved_at")),
    )


def mosdac_discovery_recent(limit: int = 50) -> list[dict]:
    return db.query(
        "SELECT * FROM mosdac_discovery ORDER BY ingested_at DESC, id DESC LIMIT ?",
        (limit,))


def upsert_bhuvan_layer(d: dict) -> int:
    """Store one Bhuvan/NRSC OGC layer-catalog record. This is NOT a numeric
    terrain value: Bhuvan is a static WMS/WMTS context source, and the verified
    note forbids scraping rendered pixels as a DEM substitute. Real terrain
    values only enter terrain_features after a gated DEM-tile processing stage.
    The feature pipeline never reads this table, so a catalog row can never
    masquerade as a terrain feature. Idempotent on
    (source, layer_key, service_url)."""
    return db.execute(
        """INSERT INTO bhuvan_layers(source,layer_key,service_type,role,
             service_url,layer_name,stage,raw_reference,retrieved_at)
           VALUES(?,?,?,?,?,?,?,?,?)
           ON CONFLICT(source,layer_key,service_url) DO UPDATE SET
             service_type=excluded.service_type, role=excluded.role,
             layer_name=excluded.layer_name, stage=excluded.stage,
             raw_reference=excluded.raw_reference,
             retrieved_at=excluded.retrieved_at""",
        (d.get("source", "bhuvan"), d["layer_key"], d.get("service_type"),
         d.get("role"), d.get("service_url"), d.get("layer_name"),
         d.get("stage", "CATALOG_ONLY"), d.get("raw_reference"),
         d.get("retrieved_at")),
    )


def bhuvan_layers_recent(limit: int = 50) -> list[dict]:
    return db.query(
        "SELECT * FROM bhuvan_layers ORDER BY ingested_at DESC, id DESC LIMIT ?",
        (limit,))


def upsert_gsi_layer(d: dict) -> int:
    """Store one GSI/Bhusanket portal layer-catalog record. This is NOT a numeric
    landslide value: GSI's verified note forbids hard-coding an undocumented API
    and stresses that GSI forecasting is REGIONAL, not a nationwide live feed, so
    each layer carries a geographic_scope coverage note. The ML landslide model
    reads landslide_data and never reads this table, so a catalog row can never
    masquerade as a susceptibility/probability. Idempotent on
    (source, layer_key, service_url)."""
    return db.execute(
        """INSERT INTO gsi_layers(source,layer_key,role,service_url,
             geographic_scope,public,stage,raw_reference,retrieved_at)
           VALUES(?,?,?,?,?,?,?,?,?)
           ON CONFLICT(source,layer_key,service_url) DO UPDATE SET
             role=excluded.role, geographic_scope=excluded.geographic_scope,
             public=excluded.public, stage=excluded.stage,
             raw_reference=excluded.raw_reference,
             retrieved_at=excluded.retrieved_at""",
        (d.get("source", "gsi"), d["layer_key"], d.get("role"),
         d.get("service_url"), d.get("geographic_scope"),
         1 if d.get("public", True) else 0,
         d.get("stage", "CATALOG_ONLY"), d.get("raw_reference"),
         d.get("retrieved_at")),
    )


def gsi_layers_recent(limit: int = 50) -> list[dict]:
    return db.query(
        "SELECT * FROM gsi_layers ORDER BY ingested_at DESC, id DESC LIMIT ?",
        (limit,))


def upsert_cwc_resource(d: dict) -> int:
    """Store one CWC/NWIC NWDP dataset-catalog record. This is NOT a numeric
    hydrological value: the verified note forbids inventing an undocumented API
    URL and warns not to claim every station is live or every API anonymous, so
    we record only the verified NWDP dataset-page URL + advertised format +
    cadence. The ML feature pipeline reads river_observations /
    rainfall_observations and never reads this table, so a catalog row can never
    masquerade as a water-level/rainfall value. Idempotent on
    (source, dataset_key, dataset_url)."""
    return db.execute(
        """INSERT INTO cwc_resources(source,dataset_key,role,dataset_url,
             resource_format,frequency,stage,raw_reference,retrieved_at)
           VALUES(?,?,?,?,?,?,?,?,?)
           ON CONFLICT(source,dataset_key,dataset_url) DO UPDATE SET
             role=excluded.role, resource_format=excluded.resource_format,
             frequency=excluded.frequency, stage=excluded.stage,
             raw_reference=excluded.raw_reference,
             retrieved_at=excluded.retrieved_at""",
        (d.get("source", "cwc"), d["dataset_key"], d.get("role"),
         d.get("dataset_url"), d.get("resource_format"), d.get("frequency"),
         d.get("stage", "CATALOG_ONLY"), d.get("raw_reference"),
         d.get("retrieved_at")),
    )


def cwc_resources_recent(limit: int = 50) -> list[dict]:
    return db.query(
        "SELECT * FROM cwc_resources ORDER BY ingested_at DESC, id DESC LIMIT ?",
        (limit,))


def upsert_lgd_directory(d: dict) -> int:
    """Store one LGD administrative-directory catalog record. This is NOT boundary
    geometry and NOT a measurement: the verified note forbids assuming the
    directory tables are polygon datasets (geometry must come from an authoritative
    GIS product joined by LGD code) and mandates LGD codes (never names) as stable
    join keys. So we record only the verified directory dataset (one per admin
    level) + its level + purpose + the verified download-portal URL. The ML feature
    pipeline never reads this table, so a catalog row can never masquerade as an
    administrative unit or a measurement. Idempotent on
    (source, dataset_key, directory_url)."""
    return db.execute(
        """INSERT INTO lgd_directory(source,dataset_key,admin_level,purpose,
             directory_url,stage,raw_reference,retrieved_at)
           VALUES(?,?,?,?,?,?,?,?)
           ON CONFLICT(source,dataset_key,directory_url) DO UPDATE SET
             admin_level=excluded.admin_level, purpose=excluded.purpose,
             stage=excluded.stage, raw_reference=excluded.raw_reference,
             retrieved_at=excluded.retrieved_at""",
        (d.get("source", "lgd"), d["dataset_key"], d.get("admin_level"),
         d.get("purpose"), d.get("directory_url"),
         d.get("stage", "CATALOG_ONLY"), d.get("raw_reference"),
         d.get("retrieved_at")),
    )


def lgd_directory_recent(limit: int = 50) -> list[dict]:
    return db.query(
        "SELECT * FROM lgd_directory ORDER BY ingested_at DESC, id DESC LIMIT ?",
        (limit,))


def upsert_historical_source(d: dict) -> int:
    """Store one historical-label SOURCE catalog record. This is NOT an event and
    NOT a training label: the verified note forbids treating these inventories as
    complete presence/absence censuses ("do not convert missing observations into
    negatives") and reduces an event to a fake point label. So we record only the
    verified source (one per registry key) + its hazard + period + role + access
    note. The ML training pipeline never reads this table, so a catalog row can
    never masquerade as a confirmed event or a 1/0/-1 label. Idempotent on
    (source, source_key, source_url)."""
    return db.execute(
        """INSERT INTO historical_sources(source,source_key,hazard,role,
             source_url,period,access_note,stage,raw_reference,retrieved_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(source,source_key,source_url) DO UPDATE SET
             hazard=excluded.hazard, role=excluded.role, period=excluded.period,
             access_note=excluded.access_note, stage=excluded.stage,
             raw_reference=excluded.raw_reference,
             retrieved_at=excluded.retrieved_at""",
        (d.get("source", "historical"), d["source_key"], d.get("hazard"),
         d.get("role"), d.get("source_url"), d.get("period"),
         d.get("access_note"), d.get("stage", "CATALOG_ONLY"),
         d.get("raw_reference"), d.get("retrieved_at")),
    )


def historical_sources_recent(limit: int = 50) -> list[dict]:
    return db.query(
        "SELECT * FROM historical_sources ORDER BY ingested_at DESC, id DESC "
        "LIMIT ?", (limit,))


def upsert_ndem_capability(d: dict) -> int:
    """Store one NDEM capability/access catalog record. This is NOT a measurement,
    NOT an event and NOT a risk score: the verified note keeps NDEM's protected
    products behind authentication and mandates that access_level and source-health
    be stored SEPARATELY from any risk score, and that we "never bypass
    authentication or invent an undocumented API." So we record only the verified
    capability (one per registry key) + its access level + role + the verified
    portal URL. The ML pipeline never reads this table, so a catalog row can never
    masquerade as a flood/landslide value. Idempotent on
    (source, capability_key, source_url)."""
    return db.execute(
        """INSERT INTO ndem_capabilities(source,capability_key,access,role,
             source_url,stage,raw_reference,retrieved_at)
           VALUES(?,?,?,?,?,?,?,?)
           ON CONFLICT(source,capability_key,source_url) DO UPDATE SET
             access=excluded.access, role=excluded.role, stage=excluded.stage,
             raw_reference=excluded.raw_reference,
             retrieved_at=excluded.retrieved_at""",
        (d.get("source", "ndem"), d["capability_key"], d.get("access"),
         d.get("role"), d.get("source_url"), d.get("stage", "CATALOG_ONLY"),
         d.get("raw_reference"), d.get("retrieved_at")),
    )


def ndem_capabilities_recent(limit: int = 50) -> list[dict]:
    return db.query(
        "SELECT * FROM ndem_capabilities ORDER BY ingested_at DESC, id DESC "
        "LIMIT ?", (limit,))


def upsert_imd_observation(o: dict) -> int:
    """Store one IMD record (current weather / district rainfall / warning /
    nowcast). IMD is district/station-level with NO coordinates, so it lands in
    its own table — NEVER rainfall_observations — and codes/colors are preserved
    verbatim (never mapped to an ML probability). Idempotent on
    (source, record_type, area_id, observed_at, warning_day)."""
    return db.execute(
        """INSERT INTO imd_observations(source,record_type,area_kind,area_id,
             area_name,observed_at,valid_upto,temperature_c,humidity_pct,
             wind_speed_kmph,pressure_hpa,rainfall_24h_mm,daily_actual_mm,
             daily_normal_mm,cumulative_actual_mm,cumulative_normal_mm,
             rainfall_category,warning_code,warning_color,warning_day,message,
             quality_flag,realtime_class,raw_reference,retrieved_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(source,record_type,area_id,observed_at,warning_day)
           DO UPDATE SET
             area_kind=excluded.area_kind, area_name=excluded.area_name,
             valid_upto=excluded.valid_upto, temperature_c=excluded.temperature_c,
             humidity_pct=excluded.humidity_pct,
             wind_speed_kmph=excluded.wind_speed_kmph,
             pressure_hpa=excluded.pressure_hpa,
             rainfall_24h_mm=excluded.rainfall_24h_mm,
             daily_actual_mm=excluded.daily_actual_mm,
             daily_normal_mm=excluded.daily_normal_mm,
             cumulative_actual_mm=excluded.cumulative_actual_mm,
             cumulative_normal_mm=excluded.cumulative_normal_mm,
             rainfall_category=excluded.rainfall_category,
             warning_code=excluded.warning_code,
             warning_color=excluded.warning_color, message=excluded.message,
             quality_flag=excluded.quality_flag,
             realtime_class=excluded.realtime_class,
             raw_reference=excluded.raw_reference,
             retrieved_at=excluded.retrieved_at""",
        (o.get("source", "imd"), o["record_type"], o.get("area_kind"),
         o.get("area_id"), o.get("area_name"), o.get("observed_at"),
         o.get("valid_upto"), o.get("temperature_c"), o.get("humidity_pct"),
         o.get("wind_speed_kmph"), o.get("pressure_hpa"),
         o.get("rainfall_24h_mm"), o.get("daily_actual_mm"),
         o.get("daily_normal_mm"), o.get("cumulative_actual_mm"),
         o.get("cumulative_normal_mm"), o.get("rainfall_category"),
         o.get("warning_code"), o.get("warning_color"), o.get("warning_day"),
         o.get("message"), o.get("quality_flag", "GOOD"),
         o.get("realtime_class"), o.get("raw_reference"), o.get("retrieved_at")),
    )


def imd_recent(limit: int = 50) -> list[dict]:
    return db.query(
        "SELECT * FROM imd_observations ORDER BY ingested_at DESC, id DESC LIMIT ?",
        (limit,))


def upsert_susceptibility(location_id: int, source: str, susceptibility: float,
                          is_synthetic: bool = True) -> None:
    """Store static landslide susceptibility as a point at the location centroid."""
    loc = get_location(location_id)
    if not loc:
        return
    db.execute(
        """INSERT INTO landslide_data(source,event_time,latitude,longitude,
             susceptibility,is_synthetic) VALUES(?,?,?,?,?,?)""",
        (source, None, loc.get("latitude"), loc.get("longitude"),
         susceptibility, int(is_synthetic)),
    )


# --------------------------------------------------------------------------
# Time-series reads for feature engineering
# --------------------------------------------------------------------------
def rainfall_series(lat: float, lon: float, tol: float = 0.25) -> list[dict]:
    """Rainfall obs near a point (bbox tolerance in degrees), newest first."""
    return db.query(
        """SELECT * FROM rainfall_observations
           WHERE latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?
           ORDER BY ts DESC LIMIT 500""",
        (lat - tol, lat + tol, lon - tol, lon + tol),
    )


def soil_latest(lat: float, lon: float, tol: float = 0.5,
                up_to_ts: str | None = None) -> dict | None:
    if up_to_ts:
        return db.query_one(
            """SELECT * FROM soil_moisture_observations
               WHERE latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?
                 AND ts <= ?
               ORDER BY ts DESC LIMIT 1""",
            (lat - tol, lat + tol, lon - tol, lon + tol, up_to_ts),
        )
    return db.query_one(
        """SELECT * FROM soil_moisture_observations
           WHERE latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?
           ORDER BY ts DESC LIMIT 1""",
        (lat - tol, lat + tol, lon - tol, lon + tol),
    )


def river_series_near(lat: float, lon: float, tol: float = 0.5) -> list[dict]:
    return db.query(
        """SELECT * FROM river_observations
           WHERE latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?
           ORDER BY ts DESC LIMIT 200""",
        (lat - tol, lat + tol, lon - tol, lon + tol),
    )


def latest_susceptibility(lat: float, lon: float, tol: float = 0.3) -> float | None:
    row = db.query_one(
        """SELECT susceptibility FROM landslide_data
           WHERE latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?
             AND susceptibility IS NOT NULL
           ORDER BY ingested_at DESC LIMIT 1""",
        (lat - tol, lat + tol, lon - tol, lon + tol),
    )
    return row["susceptibility"] if row else None


# --------------------------------------------------------------------------
# Predictions & alerts
# --------------------------------------------------------------------------
def insert_prediction(p: dict) -> int:
    return db.execute(
        """INSERT INTO predictions(location_id,ts,horizon,flood_probability,
             landslide_probability,risk_level,confidence,lead_time_min_lo,
             lead_time_min_hi,data_completeness,top_factors,model_version,mode)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (p["location_id"], p["ts"], p.get("horizon", "now"),
         p.get("flood_probability"), p.get("landslide_probability"),
         p.get("risk_level"), p.get("confidence"), p.get("lead_time_min_lo"),
         p.get("lead_time_min_hi"), p.get("data_completeness"),
         json.dumps(p.get("top_factors", [])), p.get("model_version"), p.get("mode")),
    )


def latest_prediction(location_id: int) -> dict | None:
    row = db.query_one(
        "SELECT * FROM predictions WHERE location_id=? ORDER BY ts DESC, id DESC LIMIT 1",
        (location_id,))
    if row and row.get("top_factors"):
        row["top_factors"] = json.loads(row["top_factors"])
    return row


def prediction_history(location_id: int, limit: int = 50) -> list[dict]:
    rows = db.query(
        "SELECT * FROM predictions WHERE location_id=? ORDER BY ts DESC LIMIT ?",
        (location_id, limit))
    for r in rows:
        if r.get("top_factors"):
            r["top_factors"] = json.loads(r["top_factors"])
    return rows


def insert_alert(a: dict) -> int:
    return db.execute(
        """INSERT INTO alerts(location_id,severity,hazard_type,message,
             prediction_id,status,mode,risk_level,risk_probability,lead_time_window,
             evacuation_centre_id,evacuation_guidance,recipient_count,
             sms_status,push_status,fingerprint,dispatched_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (a["location_id"], a["severity"], a["hazard_type"], a["message"],
         a.get("prediction_id"), a.get("status", "active"), a.get("mode"),
         a.get("risk_level"), a.get("risk_probability"), a.get("lead_time_window"),
         a.get("evacuation_centre_id"), a.get("evacuation_guidance"),
         a.get("recipient_count", 0), a.get("sms_status", "PENDING"),
         a.get("push_status", "PENDING"), a.get("fingerprint"),
         a.get("dispatched_at")),
    )


def get_alert(alert_id: int) -> dict | None:
    return db.query_one(
        """SELECT a.*, l.name AS location_name, l.state, l.district,
                  ec.name AS evacuation_centre_name, ec.capacity AS evacuation_centre_capacity,
                  ec.address AS evacuation_centre_address, ec.contact_number AS evacuation_centre_contact
           FROM alerts a
           JOIN locations l ON l.id=a.location_id
           LEFT JOIN evacuation_centres ec ON ec.id=a.evacuation_centre_id
           WHERE a.id=?""",
        (alert_id,),
    )


def list_alerts(status: str | None = None, limit: int = 50) -> list[dict]:
    clauses = []
    params = []
    if status:
        clauses.append("a.status=?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    return db.query(
        f"""SELECT a.*, l.name AS location_name, l.state, l.district,
                   ec.name AS evacuation_centre_name, ec.capacity AS evacuation_centre_capacity
            FROM alerts a
            JOIN locations l ON l.id=a.location_id
            LEFT JOIN evacuation_centres ec ON ec.id=a.evacuation_centre_id
            {where}
            ORDER BY a.created_at DESC LIMIT ?""",
        tuple(params),
    )


def active_alerts() -> list[dict]:
    return list_alerts(status="active")


def update_alert_dispatch_status(alert_id: int, sms_status: str,
                                 push_status: str | None = None,
                                 dispatched_at: str | None = None) -> None:
    db.execute(
        """UPDATE alerts SET sms_status=?, push_status=COALESCE(?, push_status),
           dispatched_at=COALESCE(?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))
           WHERE id=?""",
        (sms_status, push_status, dispatched_at, alert_id),
    )


def get_latest_active_alert_by_fingerprint(fingerprint: str) -> dict | None:
    return db.query_one(
        """SELECT * FROM alerts WHERE fingerprint=? AND status='active'
           ORDER BY created_at DESC LIMIT 1""",
        (fingerprint,),
    )


# --------------------------------------------------------------------------
# Evacuation Centres DAL (SIH 26192)
# --------------------------------------------------------------------------
def upsert_evacuation_centre(c: dict) -> int:
    existing = None
    if c.get("id"):
        existing = db.query_one("SELECT id FROM evacuation_centres WHERE id=?", (c["id"],))
    elif c.get("name") and c.get("village"):
        existing = db.query_one("SELECT id FROM evacuation_centres WHERE name=? AND village=?",
                                (c["name"], c["village"]))
    
    if existing:
        cid = existing["id"]
        db.execute(
            """UPDATE evacuation_centres SET name=?, address=?, village=?, ward=?,
               district=?, latitude=?, longitude=?, capacity=?, contact_number=?,
               accessibility=?, verified=?, active=?, is_demo=? WHERE id=?""",
            (c["name"], c.get("address"), c["village"], c.get("ward"),
             c["district"], c["latitude"], c["longitude"], c.get("capacity", 100),
             c.get("contact_number"), c.get("accessibility"), c.get("verified", 1),
             c.get("active", 1), c.get("is_demo", 0), cid)
        )
        return cid
    return db.execute(
        """INSERT INTO evacuation_centres(name, address, village, ward, district,
           latitude, longitude, capacity, contact_number, accessibility, verified, active, is_demo)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (c["name"], c.get("address"), c["village"], c.get("ward"),
         c["district"], c["latitude"], c["longitude"], c.get("capacity", 100),
         c.get("contact_number"), c.get("accessibility"), c.get("verified", 1),
         c.get("active", 1), c.get("is_demo", 0))
    )


def get_evacuation_centre(centre_id: int) -> dict | None:
    return db.query_one("SELECT * FROM evacuation_centres WHERE id=?", (centre_id,))


def list_evacuation_centres(village: str | None = None, district: str | None = None,
                            active_only: bool = True) -> list[dict]:
    clauses = []
    params = []
    if active_only:
        clauses.append("active=1")
    if village:
        clauses.append("village=?")
        params.append(village)
    if district:
        clauses.append("district=?")
        params.append(district)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return db.query(f"SELECT * FROM evacuation_centres {where} ORDER BY name", tuple(params))


def nearest_evacuation_centres(lat: float, lon: float, limit: int = 5) -> list[dict]:
    import math
    centres = list_evacuation_centres(active_only=True)
    def dist(c):
        # Haversine distance in km
        r = 6371.0
        dlat = math.radians(c["latitude"] - lat)
        dlon = math.radians(c["longitude"] - lon)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat)) * math.cos(math.radians(c["latitude"])) * math.sin(dlon / 2) ** 2)
        return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    for c in centres:
        c["distance_km"] = round(dist(c), 2)
    centres.sort(key=lambda x: x["distance_km"])
    return centres[:limit]


# --------------------------------------------------------------------------
# Alert Recipients DAL (SIH 26192)
# --------------------------------------------------------------------------
def upsert_alert_recipient(r: dict) -> int:
    existing = None
    if r.get("phone_number"):
        existing = db.query_one("SELECT id FROM alert_recipients WHERE phone_number=? AND village=?",
                                (r["phone_number"], r["village"]))
    if existing:
        rid = existing["id"]
        db.execute(
            """UPDATE alert_recipients SET name=?, ward=?, district=?, preferred_language=?,
               active=?, emergency_notification_enabled=?, is_demo=? WHERE id=?""",
            (r["name"], r.get("ward"), r["district"], r.get("preferred_language", "en"),
             r.get("active", 1), r.get("emergency_notification_enabled", 1),
             r.get("is_demo", 1), rid)
        )
        return rid
    return db.execute(
        """INSERT INTO alert_recipients(name, phone_number, village, ward, district,
           preferred_language, active, emergency_notification_enabled, is_demo)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (r["name"], r["phone_number"], r["village"], r.get("ward"), r["district"],
         r.get("preferred_language", "en"), r.get("active", 1),
         r.get("emergency_notification_enabled", 1), r.get("is_demo", 1))
    )


def list_recipients_for_village(village: str, active_only: bool = True) -> list[dict]:
    clauses = ["village=?"]
    params = [village]
    if active_only:
        clauses.append("active=1")
        clauses.append("emergency_notification_enabled=1")
    return db.query(f"SELECT * FROM alert_recipients WHERE {' AND '.join(clauses)}", tuple(params))


def count_recipients_for_village(village: str, active_only: bool = True) -> int:
    clauses = ["village=?"]
    params = [village]
    if active_only:
        clauses.append("active=1")
        clauses.append("emergency_notification_enabled=1")
    row = db.query_one(f"SELECT COUNT(*) as count FROM alert_recipients WHERE {' AND '.join(clauses)}", tuple(params))
    return int(row["count"]) if row and row.get("count") is not None else 0


def all_source_health() -> list[dict]:
    return db.query("SELECT * FROM source_health ORDER BY source")


# --------------------------------------------------------------------------
# Source health / ingestion / quality logging
#   These used to be written directly against `db` from collectors/base.py,
#   which bypassed the DAL seam (and so missed PostGIS on Track B). They now
#   live behind the repositories surface like everything else.
# --------------------------------------------------------------------------
def get_source_health(source: str) -> dict | None:
    return db.query_one("SELECT * FROM source_health WHERE source=?", (source,))


def record_source_health(h: dict) -> None:
    """Idempotent upsert on the source PK. Preserves last_success_at when the
    current attempt did not succeed (COALESCE), matching prior behaviour — UNLESS
    the caller passes force_success_ts=True, which writes last_success_at exactly
    as given (used when a later stage must DOWNGRADE a within-run success, e.g.
    Bhuvan cataloging succeeds but the optional endpoint probe finds the service
    unreachable -> STALE with last_success_at cleared)."""
    force = bool(h.get("force_success_ts"))
    existing = db.query_one("SELECT source FROM source_health WHERE source=?",
                            (h["source"],))
    if existing:
        success_clause = "?" if force else "COALESCE(?, last_success_at)"
        db.execute(
            f"""UPDATE source_health SET status=?, last_attempt_at=?,
               last_latency_ms=?, last_error=?, records_last_run=?,
               last_success_at={success_clause}, updated_at=?
               WHERE source=?""",
            (h.get("status"), h.get("last_attempt_at"), h.get("last_latency_ms"),
             h.get("last_error"), h.get("records_last_run"),
             h.get("last_success_at"), h.get("updated_at"), h["source"]),
        )
    else:
        db.execute(
            """INSERT INTO source_health(source,status,last_success_at,
               last_attempt_at,last_latency_ms,last_error,records_last_run,updated_at)
               VALUES(?,?,?,?,?,?,?,?)""",
            (h["source"], h.get("status"), h.get("last_success_at"),
             h.get("last_attempt_at"), h.get("last_latency_ms"),
             h.get("last_error"), h.get("records_last_run"), h.get("updated_at")),
        )


def log_ingestion(e: dict) -> None:
    db.execute(
        """INSERT INTO ingestion_log(source,started_at,finished_at,status,
           records_received,records_stored,records_rejected,latency_ms,error)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (e["source"], e.get("started_at"), e.get("finished_at"), e.get("status"),
         e.get("records_received", 0), e.get("records_stored", 0),
         e.get("records_rejected", 0), e.get("latency_ms"), e.get("error")),
    )


def log_quality(q: dict) -> None:
    db.execute(
        """INSERT INTO data_quality_flags(source,table_name,ts,flag,reason)
           VALUES(?,?,?,?,?)""",
        (q["source"], q.get("table_name", ""), q.get("ts"), q.get("flag", "BAD"),
         q.get("reason")),
    )
