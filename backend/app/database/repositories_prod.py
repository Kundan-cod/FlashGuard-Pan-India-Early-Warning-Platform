"""
Track B repositories — PostGIS-backed DAL exposing the SAME function surface as
the Track A repositories.py (master prompt sections 7, 10). The shared layers
above the DAL (features, models, risk, prediction_service, replay_driver, seed)
import `repositories` by name; on Track B the process swaps this module in via
an env flag so NONE of that code changes — only the storage engine does.

Wiring (done once at process start, e.g. in main.py or a small bootstrap):
    import sys
    from app.database import repositories_prod
    sys.modules["app.database.repositories"] = repositories_prod

Idempotency mirrors Track A exactly: every upsert targets the natural-key
UNIQUE constraints declared in models_orm.py, so re-ingesting identical data
never duplicates rows (section 7).

Geometry differs from Track A: instead of GeoJSON text + a bbox, we persist real
PostGIS geometry(...,4326) via ST_GeomFromGeoJSON / ST_MakePoint, and read it
back out as GeoJSON with ST_AsGeoJSON so the API payloads are byte-identical to
Track A. Spatial "near a point" reads use ST_DWithin on a geography cast (metres)
rather than a lat/lon bbox, which is both correct and index-accelerated by GiST.

STATUS: skeleton — pending local run (needs SQLAlchemy/GeoAlchemy2 + a live
PostGIS instance, none of which are installed in the build sandbox). It is
written against the SQLAlchemy 2.0 Core API and the schema in models_orm.py.
No secrets here; the engine/session come from app.database.session, which reads
DATABASE_URL from settings/env only.
"""
from __future__ import annotations

import json
from datetime import timezone
from typing import Any

# Lazy heavy imports so importing this module never explodes in a sandbox that
# lacks SQLAlchemy. The functions below import `text`/session on first use.
from app.database.session import get_session


def _session():
    """Yield a short-lived session (context-managed by callers via with/next)."""
    gen = get_session()
    return gen


# A tiny helper: run a unit of work in a transaction and return the result.
def _run(fn):
    from contextlib import closing
    gen = get_session()
    sess = next(gen)
    try:
        out = fn(sess)
        sess.commit()
        return out
    except Exception:
        sess.rollback()
        raise
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def _degree_tol_to_metres(tol_deg: float) -> float:
    """Track A used lat/lon degree bboxes; convert that tolerance to metres for
    ST_DWithin (~111.32 km per degree of latitude). Keeps behaviour comparable."""
    return tol_deg * 111_320.0


def _iso_z(v):
    """PostGIS timestamptz columns come back as Python datetime objects, but
    Track A (SQLite) returns ISO-8601 'Z' strings. To keep the DAL output
    storage-agnostic — so shared consumers and API payloads are byte-identical
    across tracks — every datetime leaving this module is rendered as ...Z."""
    from datetime import datetime
    if isinstance(v, datetime):
        dt = v.astimezone(timezone.utc) if v.tzinfo else v
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return v


def _norm_row(d: dict) -> dict:
    """Normalize a mapping row: datetimes -> ISO-Z strings (Track A parity)."""
    return {k: _iso_z(val) for k, val in d.items()}


# --------------------------------------------------------------------------
# Locations
# --------------------------------------------------------------------------
def upsert_location(loc: dict) -> int:
    from sqlalchemy import text
    geom = loc.get("geometry")
    lat, lon = loc.get("latitude"), loc.get("longitude")

    def work(s):
        # Derive centroid lat/lon from the polygon when not supplied, so village
        # points line up with Track A (which used spatial.polygon_centroid).
        nonlocal lat, lon
        geom_json = json.dumps(geom) if geom is not None else None
        if geom is not None and (lat is None or lon is None):
            row = s.execute(
                text("SELECT ST_Y(ST_Centroid(ST_GeomFromGeoJSON(:g))) AS y, "
                     "       ST_X(ST_Centroid(ST_GeomFromGeoJSON(:g))) AS x"),
                {"g": geom_json},
            ).mappings().first()
            lat, lon = row["y"], row["x"]

        s.execute(
            text("""
                INSERT INTO locations
                    (ext_code,name,level,parent_id,state,district,block,village,
                     latitude,longitude,geom,is_synthetic)
                VALUES
                    (:ext_code,:name,:level,:parent_id,:state,:district,:block,:village,
                     :latitude,:longitude,
                     CASE WHEN :geom IS NULL THEN NULL
                          ELSE ST_SetSRID(ST_GeomFromGeoJSON(:geom),4326) END,
                     :is_synthetic)
                ON CONFLICT (ext_code) DO UPDATE SET
                     name=EXCLUDED.name, level=EXCLUDED.level,
                     parent_id=EXCLUDED.parent_id, state=EXCLUDED.state,
                     district=EXCLUDED.district, block=EXCLUDED.block,
                     village=EXCLUDED.village, latitude=EXCLUDED.latitude,
                     longitude=EXCLUDED.longitude, geom=EXCLUDED.geom,
                     is_synthetic=EXCLUDED.is_synthetic
            """),
            {"ext_code": loc.get("ext_code"), "name": loc["name"],
             "level": loc["level"], "parent_id": loc.get("parent_id"),
             "state": loc.get("state"), "district": loc.get("district"),
             "block": loc.get("block"), "village": loc.get("village"),
             "latitude": lat, "longitude": lon, "geom": geom_json,
             "is_synthetic": int(loc.get("is_synthetic", 0))},
        )
        row = s.execute(text("SELECT id FROM locations WHERE ext_code=:e"),
                        {"e": loc.get("ext_code")}).mappings().first()
        return row["id"] if row else -1

    return _run(work)


def _loc_row(s, sql: str, params: dict) -> list[dict]:
    from sqlalchemy import text
    rows = s.execute(text(sql), params).mappings().all()
    out = []
    for r in rows:
        d = _norm_row(dict(r))
        gj = d.pop("geometry_geojson", None)
        d["geometry"] = json.loads(gj) if gj else None
        out.append(d)
    return out


def get_location(location_id: int) -> dict | None:
    def work(s):
        rows = _loc_row(
            s,
            "SELECT *, ST_AsGeoJSON(geom) AS geometry_geojson "
            "FROM locations WHERE id=:id",
            {"id": location_id})
        return rows[0] if rows else None
    return _run(work)


def list_locations(level: str | None = None, parent_id: int | None = None) -> list[dict]:
    def work(s):
        sql = ("SELECT *, ST_AsGeoJSON(geom) AS geometry_geojson "
               "FROM locations WHERE 1=1")
        params: dict[str, Any] = {}
        if level:
            sql += " AND level=:level"; params["level"] = level
        if parent_id is not None:
            sql += " AND parent_id=:pid"; params["pid"] = parent_id
        sql += " ORDER BY name"
        return _loc_row(s, sql, params)
    return _run(work)


def upsert_terrain(location_id: int, t: dict) -> None:
    from sqlalchemy import text

    def work(s):
        s.execute(
            text("""
                INSERT INTO terrain_features
                    (location_id,elevation,slope,aspect,curvature,flow_accumulation,
                     drainage_density,distance_to_drainage,relative_relief,
                     is_synthetic,source)
                VALUES
                    (:location_id,:elevation,:slope,:aspect,:curvature,:flow_accumulation,
                     :drainage_density,:distance_to_drainage,:relative_relief,
                     :is_synthetic,:source)
                ON CONFLICT (location_id) DO UPDATE SET
                     elevation=EXCLUDED.elevation, slope=EXCLUDED.slope,
                     aspect=EXCLUDED.aspect, curvature=EXCLUDED.curvature,
                     flow_accumulation=EXCLUDED.flow_accumulation,
                     drainage_density=EXCLUDED.drainage_density,
                     distance_to_drainage=EXCLUDED.distance_to_drainage,
                     relative_relief=EXCLUDED.relative_relief,
                     is_synthetic=EXCLUDED.is_synthetic, source=EXCLUDED.source
            """),
            {"location_id": location_id, "elevation": t.get("elevation"),
             "slope": t.get("slope"), "aspect": t.get("aspect"),
             "curvature": t.get("curvature"),
             "flow_accumulation": t.get("flow_accumulation"),
             "drainage_density": t.get("drainage_density"),
             "distance_to_drainage": t.get("distance_to_drainage"),
             "relative_relief": t.get("relative_relief"),
             "is_synthetic": int(t.get("is_synthetic", 0)), "source": t.get("source")},
        )
    _run(work)


def get_terrain(location_id: int) -> dict | None:
    from sqlalchemy import text

    def work(s):
        r = s.execute(text("SELECT * FROM terrain_features WHERE location_id=:id"),
                      {"id": location_id}).mappings().first()
        return _norm_row(dict(r)) if r else None
    return _run(work)


# --------------------------------------------------------------------------
# Observations (idempotent upserts on natural keys)
# --------------------------------------------------------------------------
def _point(lat, lon) -> str:
    # PostGIS point literal builder handled inline in SQL via ST_MakePoint.
    return f"{lon} {lat}"


def upsert_rainfall(o: dict) -> int:
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                INSERT INTO rainfall_observations
                    (source,ts,latitude,longitude,geom,rainfall_30m,rainfall_3h,
                     rainfall_24h,quality_flag,resolution_m,realtime_class,units,granule_id)
                VALUES
                    (:source,:ts,:latitude,:longitude,
                     ST_SetSRID(ST_MakePoint(:longitude,:latitude),4326),
                     :rainfall_30m,:rainfall_3h,:rainfall_24h,:quality_flag,
                     :resolution_m,:realtime_class,:units,:granule_id)
                ON CONFLICT ON CONSTRAINT uq_rain_natural DO UPDATE SET
                     rainfall_30m=EXCLUDED.rainfall_30m,
                     rainfall_3h=EXCLUDED.rainfall_3h,
                     rainfall_24h=EXCLUDED.rainfall_24h,
                     quality_flag=EXCLUDED.quality_flag,
                     resolution_m=EXCLUDED.resolution_m,
                     realtime_class=EXCLUDED.realtime_class,
                     units=EXCLUDED.units,
                     granule_id=EXCLUDED.granule_id
                RETURNING id
            """),
            {"source": o["source"], "ts": o["ts"], "latitude": o["latitude"],
             "longitude": o["longitude"], "rainfall_30m": o.get("rainfall_30m"),
             "rainfall_3h": o.get("rainfall_3h"), "rainfall_24h": o.get("rainfall_24h"),
             "quality_flag": o.get("quality_flag", "GOOD"),
             "resolution_m": o.get("resolution_m"),
             "realtime_class": o.get("realtime_class"),
             "units": o.get("units", "mm"),
             "granule_id": o.get("granule_id")},
        ).mappings().first()
        return row["id"]
    return _run(work)



def upsert_soil(o: dict) -> int:
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                INSERT INTO soil_moisture_observations
                    (source,ts,latitude,longitude,geom,surface_moisture,
                     root_zone_moisture,quality_flag,resolution_m,realtime_class)
                VALUES
                    (:source,:ts,:latitude,:longitude,
                     ST_SetSRID(ST_MakePoint(:longitude,:latitude),4326),
                     :surface_moisture,:root_zone_moisture,:quality_flag,
                     :resolution_m,:realtime_class)
                ON CONFLICT ON CONSTRAINT uq_soil_natural DO UPDATE SET
                     surface_moisture=EXCLUDED.surface_moisture,
                     root_zone_moisture=EXCLUDED.root_zone_moisture,
                     quality_flag=EXCLUDED.quality_flag,
                     resolution_m=EXCLUDED.resolution_m,
                     realtime_class=EXCLUDED.realtime_class
                RETURNING id
            """),
            {"source": o["source"], "ts": o["ts"], "latitude": o["latitude"],
             "longitude": o["longitude"],
             "surface_moisture": o.get("surface_moisture"),
             "root_zone_moisture": o.get("root_zone_moisture"),
             "quality_flag": o.get("quality_flag", "GOOD"),
             "resolution_m": o.get("resolution_m"),
             "realtime_class": o.get("realtime_class")},
        ).mappings().first()
        return row["id"]
    return _run(work)


def upsert_river(o: dict) -> int:
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                INSERT INTO river_observations
                    (source,station_id,ts,latitude,longitude,geom,water_level,
                     flow,rate_of_rise,quality_flag,realtime_class)
                VALUES
                    (:source,:station_id,:ts,:latitude,:longitude,
                     CASE WHEN :latitude IS NULL OR :longitude IS NULL THEN NULL
                          ELSE ST_SetSRID(ST_MakePoint(:longitude,:latitude),4326) END,
                     :water_level,:flow,:rate_of_rise,:quality_flag,:realtime_class)
                ON CONFLICT ON CONSTRAINT uq_river_natural DO UPDATE SET
                     water_level=EXCLUDED.water_level, flow=EXCLUDED.flow,
                     rate_of_rise=EXCLUDED.rate_of_rise,
                     quality_flag=EXCLUDED.quality_flag,
                     realtime_class=EXCLUDED.realtime_class
                RETURNING id
            """),
            {"source": o["source"], "station_id": o.get("station_id"),
             "ts": o["ts"], "latitude": o.get("latitude"),
             "longitude": o.get("longitude"), "water_level": o.get("water_level"),
             "flow": o.get("flow"), "rate_of_rise": o.get("rate_of_rise"),
             "quality_flag": o.get("quality_flag", "GOOD"),
             "realtime_class": o.get("realtime_class")},
        ).mappings().first()
        return row["id"]
    return _run(work)


def upsert_iot(o: dict) -> int:
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                INSERT INTO iot_observations
                    (sensor_id,ts,latitude,longitude,geom,rainfall,soil_moisture,
                     water_level,temperature,quality_flag,is_simulated)
                VALUES
                    (:sensor_id,:ts,:latitude,:longitude,
                     CASE WHEN :latitude IS NULL OR :longitude IS NULL THEN NULL
                          ELSE ST_SetSRID(ST_MakePoint(:longitude,:latitude),4326) END,
                     :rainfall,:soil_moisture,:water_level,:temperature,
                     :quality_flag,:is_simulated)
                ON CONFLICT ON CONSTRAINT uq_iot_natural DO UPDATE SET
                     rainfall=EXCLUDED.rainfall, soil_moisture=EXCLUDED.soil_moisture,
                     water_level=EXCLUDED.water_level, temperature=EXCLUDED.temperature,
                     quality_flag=EXCLUDED.quality_flag,
                     is_simulated=EXCLUDED.is_simulated
                RETURNING id
            """),
            {"sensor_id": o["sensor_id"], "ts": o["ts"],
             "latitude": o.get("latitude"), "longitude": o.get("longitude"),
             "rainfall": o.get("rainfall"), "soil_moisture": o.get("soil_moisture"),
             "water_level": o.get("water_level"), "temperature": o.get("temperature"),
             "quality_flag": o.get("quality_flag", "GOOD"),
             "is_simulated": int(o.get("is_simulated", 1))},
        ).mappings().first()
        return row["id"]
    return _run(work)


def upsert_iot_raw(r: dict) -> int:
    import json
    from sqlalchemy import text
    payload_str = json.dumps(r.get("raw_payload", {})) if isinstance(r.get("raw_payload"), dict) else str(r.get("raw_payload", ""))

    def work(s):
        row = s.execute(
            text("""
                INSERT INTO iot_raw_telemetry
                    (source, channel_id, entry_id, ts, raw_payload, quality_flag)
                VALUES
                    (:source, :channel_id, :entry_id, :ts, :raw_payload, :quality_flag)
                ON CONFLICT (channel_id, entry_id) DO UPDATE SET
                    raw_payload=EXCLUDED.raw_payload, quality_flag=EXCLUDED.quality_flag, ts=EXCLUDED.ts
                RETURNING id
            """),
            {"source": r.get("source", "thingspeak"), "channel_id": str(r["channel_id"]),
             "entry_id": int(r["entry_id"]), "ts": r["ts"],
             "raw_payload": payload_str, "quality_flag": r.get("quality_flag", "GOOD")},
        ).mappings().first()
        return row["id"]
    return _run(work)


def latest_iot_raw(channel_id: str, limit: int = 10) -> list[dict]:
    from sqlalchemy import text

    def work(s):
        rows = s.execute(
            text("""
                SELECT id, source, channel_id, entry_id, ts, raw_payload, quality_flag, ingested_at
                FROM iot_raw_telemetry
                WHERE channel_id = :cid
                ORDER BY entry_id DESC
                LIMIT :limit
            """),
            {"cid": str(channel_id), "limit": limit},
        ).mappings().all()
        return [_norm_row(dict(x)) for x in rows]
    return _run(work)


def iot_series(sensor_id: str, limit: int = 100) -> list[dict]:
    from sqlalchemy import text

    def work(s):
        rows = s.execute(
            text("SELECT * FROM iot_observations WHERE sensor_id=:sid ORDER BY ts DESC LIMIT :limit"),
            {"sid": sensor_id, "limit": limit}
        ).mappings().all()
        return [_norm_row(dict(x)) for x in rows]
    return _run(work)


def iot_latest(sensor_id: str) -> dict | None:
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("SELECT * FROM iot_observations WHERE sensor_id=:sid ORDER BY ts DESC LIMIT 1"),
            {"sid": sensor_id}
        ).mappings().first()
        return _norm_row(dict(row)) if row else None
    return _run(work)


def upsert_susceptibility(location_id: int, source: str, susceptibility: float,
                          is_synthetic: bool = True) -> None:
    from sqlalchemy import text
    loc = get_location(location_id)
    if not loc:
        return

    def work(s):
        s.execute(
            text("""
                INSERT INTO landslide_data
                    (source,event_time,latitude,longitude,geom,susceptibility,is_synthetic)
                VALUES
                    (:source,NULL,:latitude,:longitude,
                     CASE WHEN :latitude IS NULL OR :longitude IS NULL THEN NULL
                          ELSE ST_SetSRID(ST_MakePoint(:longitude,:latitude),4326) END,
                     :susceptibility,:is_synthetic)
            """),
            {"source": source, "latitude": loc.get("latitude"),
             "longitude": loc.get("longitude"), "susceptibility": susceptibility,
             "is_synthetic": int(is_synthetic)},
        )
    _run(work)


def upsert_gpm_discovery(d: dict) -> int:
    """Track B twin of repositories.upsert_gpm_discovery. Stores a GPM PMM
    dataset-discovery record (NOT a rainfall observation). numeric_value stays
    NULL until the gated raster-sampling stage; the feature pipeline never reads
    this table, so a discovery record can never masquerade as rainfall."""
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                INSERT INTO gpm_discovery
                    (source,product,observed_date,latitude,longitude,geom,
                     resolution,download_url,media_type,item_id,numeric_value,
                     stage,raw_reference,retrieved_at)
                VALUES
                    (:source,:product,:observed_date,:latitude,:longitude,
                     CASE WHEN :latitude IS NULL OR :longitude IS NULL THEN NULL
                          ELSE ST_SetSRID(ST_MakePoint(:longitude,:latitude),4326) END,
                     :resolution,:download_url,:media_type,:item_id,:numeric_value,
                     :stage,:raw_reference,:retrieved_at)
                ON CONFLICT ON CONSTRAINT uq_gpmdisc_natural DO UPDATE SET
                     product=EXCLUDED.product, observed_date=EXCLUDED.observed_date,
                     latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude,
                     geom=EXCLUDED.geom, resolution=EXCLUDED.resolution,
                     media_type=EXCLUDED.media_type,
                     numeric_value=EXCLUDED.numeric_value, stage=EXCLUDED.stage,
                     raw_reference=EXCLUDED.raw_reference,
                     retrieved_at=EXCLUDED.retrieved_at
                RETURNING id
            """),
            {"source": d.get("source", "gpm"), "product": d.get("product"),
             "observed_date": d.get("observed_date"),
             "latitude": d.get("latitude"), "longitude": d.get("longitude"),
             "resolution": d.get("resolution"),
             "download_url": d.get("download_url"),
             "media_type": d.get("media_type"), "item_id": d.get("item_id"),
             "numeric_value": d.get("numeric_value"),
             "stage": d.get("stage", "DISCOVERY_ONLY"),
             "raw_reference": d.get("raw_reference"),
             "retrieved_at": d.get("retrieved_at")},
        ).mappings().first()
        return row["id"]
    return _run(work)


def gpm_discovery_recent(limit: int = 50) -> list[dict]:
    from sqlalchemy import text

    def work(s):
        rows = s.execute(
            text("SELECT * FROM gpm_discovery "
                 "ORDER BY ingested_at DESC, id DESC LIMIT :lim"),
            {"lim": limit},
        ).mappings().all()
        return [_norm_row(dict(r)) for r in rows]
    return _run(work)


def upsert_smap_discovery(d: dict) -> int:
    """Track B twin of repositories.upsert_smap_discovery. Stores a NASA SMAP
    CMR granule-discovery record (NOT a soil-moisture observation). surface_sm /
    rootzone_sm stay NULL until a gated parse stage; the feature pipeline never
    reads this table, so a discovery record can never masquerade as a measurement."""
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                INSERT INTO smap_discovery
                    (source,product,version,observed_date,end_time,latitude,
                     longitude,geom,grid,download_url,concept_id,
                     producer_granule_id,surface_sm,rootzone_sm,quality_flag,
                     stage,raw_reference,retrieved_at)
                VALUES
                    (:source,:product,:version,:observed_date,:end_time,:latitude,
                     :longitude,
                     CASE WHEN :latitude IS NULL OR :longitude IS NULL THEN NULL
                          ELSE ST_SetSRID(ST_MakePoint(:longitude,:latitude),4326) END,
                     :grid,:download_url,:concept_id,:producer_granule_id,
                     :surface_sm,:rootzone_sm,:quality_flag,:stage,:raw_reference,
                     :retrieved_at)
                ON CONFLICT ON CONSTRAINT uq_smapdisc_natural DO UPDATE SET
                     product=EXCLUDED.product, version=EXCLUDED.version,
                     observed_date=EXCLUDED.observed_date, end_time=EXCLUDED.end_time,
                     latitude=EXCLUDED.latitude, longitude=EXCLUDED.longitude,
                     geom=EXCLUDED.geom, grid=EXCLUDED.grid,
                     producer_granule_id=EXCLUDED.producer_granule_id,
                     surface_sm=EXCLUDED.surface_sm, rootzone_sm=EXCLUDED.rootzone_sm,
                     quality_flag=EXCLUDED.quality_flag, stage=EXCLUDED.stage,
                     raw_reference=EXCLUDED.raw_reference,
                     retrieved_at=EXCLUDED.retrieved_at
                RETURNING id
            """),
            {"source": d.get("source", "smap"), "product": d.get("product"),
             "version": d.get("version"), "observed_date": d.get("observed_date"),
             "end_time": d.get("end_time"), "latitude": d.get("latitude"),
             "longitude": d.get("longitude"), "grid": d.get("grid"),
             "download_url": d.get("download_url"),
             "concept_id": d.get("concept_id"),
             "producer_granule_id": d.get("producer_granule_id"),
             "surface_sm": d.get("surface_sm"),
             "rootzone_sm": d.get("rootzone_sm"),
             "quality_flag": d.get("quality_flag", "UNKNOWN"),
             "stage": d.get("stage", "DISCOVERY_ONLY"),
             "raw_reference": d.get("raw_reference"),
             "retrieved_at": d.get("retrieved_at")},
        ).mappings().first()
        return row["id"]
    return _run(work)


def smap_discovery_recent(limit: int = 50) -> list[dict]:
    from sqlalchemy import text

    def work(s):
        rows = s.execute(
            text("SELECT * FROM smap_discovery "
                 "ORDER BY ingested_at DESC, id DESC LIMIT :lim"),
            {"lim": limit},
        ).mappings().all()
        return [_norm_row(dict(r)) for r in rows]
    return _run(work)


def upsert_mosdac_discovery(d: dict) -> int:
    """Track B twin of repositories.upsert_mosdac_discovery. Stores an ISRO
    MOSDAC INSAT granule-discovery record (NOT a rainfall observation).
    numeric_value stays NULL until a gated raster/HDF-parse stage; the feature
    pipeline never reads this table, so a discovery record can never masquerade
    as a numeric rainfall value."""
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                INSERT INTO mosdac_discovery
                    (source,dataset_id,satellite,product,observed_date,end_time,
                     latitude,longitude,geom,resolution,download_url,granule_id,
                     numeric_value,quality_flag,stage,raw_reference,retrieved_at)
                VALUES
                    (:source,:dataset_id,:satellite,:product,:observed_date,
                     :end_time,:latitude,:longitude,
                     CASE WHEN :latitude IS NULL OR :longitude IS NULL THEN NULL
                          ELSE ST_SetSRID(ST_MakePoint(:longitude,:latitude),4326) END,
                     :resolution,:download_url,:granule_id,:numeric_value,
                     :quality_flag,:stage,:raw_reference,:retrieved_at)
                ON CONFLICT ON CONSTRAINT uq_mosdacdisc_natural DO UPDATE SET
                     source=EXCLUDED.source, satellite=EXCLUDED.satellite,
                     product=EXCLUDED.product,
                     observed_date=EXCLUDED.observed_date,
                     end_time=EXCLUDED.end_time, latitude=EXCLUDED.latitude,
                     longitude=EXCLUDED.longitude, geom=EXCLUDED.geom,
                     resolution=EXCLUDED.resolution,
                     numeric_value=EXCLUDED.numeric_value,
                     quality_flag=EXCLUDED.quality_flag, stage=EXCLUDED.stage,
                     raw_reference=EXCLUDED.raw_reference,
                     retrieved_at=EXCLUDED.retrieved_at
                RETURNING id
            """),
            {"source": d.get("source", "mosdac"),
             "dataset_id": d.get("dataset_id"), "satellite": d.get("satellite"),
             "product": d.get("product"),
             "observed_date": d.get("observed_date"),
             "end_time": d.get("end_time"), "latitude": d.get("latitude"),
             "longitude": d.get("longitude"), "resolution": d.get("resolution"),
             "download_url": d.get("download_url"),
             "granule_id": d.get("granule_id"),
             "numeric_value": d.get("numeric_value"),
             "quality_flag": d.get("quality_flag", "UNKNOWN"),
             "stage": d.get("stage", "DISCOVERY_ONLY"),
             "raw_reference": d.get("raw_reference"),
             "retrieved_at": d.get("retrieved_at")},
        ).mappings().first()
        return row["id"]
    return _run(work)


def mosdac_discovery_recent(limit: int = 50) -> list[dict]:
    from sqlalchemy import text

    def work(s):
        rows = s.execute(
            text("SELECT * FROM mosdac_discovery "
                 "ORDER BY ingested_at DESC, id DESC LIMIT :lim"),
            {"lim": limit},
        ).mappings().all()
        return [_norm_row(dict(r)) for r in rows]
    return _run(work)


def upsert_bhuvan_layer(d: dict) -> int:
    """Track B twin of repositories.upsert_bhuvan_layer. Bhuvan/NRSC is a static
    OGC WMS/WMTS context source: this catalogs verified layer endpoints + roles
    only, carries NO numeric terrain value, and has NO geometry column (a catalog
    entry describes a service endpoint, not a point observation). The feature
    pipeline never reads this table. Idempotent on
    (source, layer_key, service_url)."""
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                INSERT INTO bhuvan_layers
                    (source,layer_key,service_type,role,service_url,layer_name,
                     stage,raw_reference,retrieved_at)
                VALUES
                    (:source,:layer_key,:service_type,:role,:service_url,
                     :layer_name,:stage,:raw_reference,:retrieved_at)
                ON CONFLICT ON CONSTRAINT uq_bhuvanlayer_natural DO UPDATE SET
                    service_type=EXCLUDED.service_type, role=EXCLUDED.role,
                    layer_name=EXCLUDED.layer_name, stage=EXCLUDED.stage,
                    raw_reference=EXCLUDED.raw_reference,
                    retrieved_at=EXCLUDED.retrieved_at
                RETURNING id
            """),
            {
                "source": d.get("source", "bhuvan"),
                "layer_key": d["layer_key"],
                "service_type": d.get("service_type"),
                "role": d.get("role"),
                "service_url": d.get("service_url"),
                "layer_name": d.get("layer_name"),
                "stage": d.get("stage", "CATALOG_ONLY"),
                "raw_reference": d.get("raw_reference"),
                "retrieved_at": d.get("retrieved_at"),
            },
        ).mappings().first()
        return row["id"]
    return _run(work)


def bhuvan_layers_recent(limit: int = 50) -> list[dict]:
    from sqlalchemy import text

    def work(s):
        rows = s.execute(
            text("SELECT * FROM bhuvan_layers "
                 "ORDER BY ingested_at DESC, id DESC LIMIT :lim"),
            {"lim": limit},
        ).mappings().all()
        return [_norm_row(dict(r)) for r in rows]
    return _run(work)


def upsert_gsi_layer(d: dict) -> int:
    """Track B twin of repositories.upsert_gsi_layer. GSI/Bhusanket is a portal
    layer catalog (forecast bulletin / susceptibility / impact-probability /
    inventory): this carries NO numeric landslide value, preserves a
    geographic_scope coverage note, and has NO geometry column (a catalog entry
    describes a portal layer, not a point observation). The ML landslide model
    never reads this table. Idempotent on (source, layer_key, service_url)."""
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                INSERT INTO gsi_layers
                    (source,layer_key,role,service_url,geographic_scope,public,
                     stage,raw_reference,retrieved_at)
                VALUES
                    (:source,:layer_key,:role,:service_url,:geographic_scope,
                     :public,:stage,:raw_reference,:retrieved_at)
                ON CONFLICT ON CONSTRAINT uq_gsilayer_natural DO UPDATE SET
                    role=EXCLUDED.role,
                    geographic_scope=EXCLUDED.geographic_scope,
                    public=EXCLUDED.public, stage=EXCLUDED.stage,
                    raw_reference=EXCLUDED.raw_reference,
                    retrieved_at=EXCLUDED.retrieved_at
                RETURNING id
            """),
            {
                "source": d.get("source", "gsi"),
                "layer_key": d["layer_key"],
                "role": d.get("role"),
                "service_url": d.get("service_url"),
                "geographic_scope": d.get("geographic_scope"),
                "public": 1 if d.get("public", True) else 0,
                "stage": d.get("stage", "CATALOG_ONLY"),
                "raw_reference": d.get("raw_reference"),
                "retrieved_at": d.get("retrieved_at"),
            },
        ).mappings().first()
        return row["id"]
    return _run(work)


def gsi_layers_recent(limit: int = 50) -> list[dict]:
    from sqlalchemy import text

    def work(s):
        rows = s.execute(
            text("SELECT * FROM gsi_layers "
                 "ORDER BY ingested_at DESC, id DESC LIMIT :lim"),
            {"lim": limit},
        ).mappings().all()
        return [_norm_row(dict(r)) for r in rows]
    return _run(work)


def upsert_cwc_resource(d: dict) -> int:
    """Track B twin of repositories.upsert_cwc_resource. CWC/NWIC is an NWDP
    dataset-page catalog (river level / telemetry rainfall / reservoir storage):
    this carries NO numeric hydrological value, records only the verified dataset
    URL + advertised format + cadence, and has NO geometry column (a catalog entry
    describes a dataset page, not a point observation). The ML feature pipeline
    (river_observations / rainfall_observations) never reads this table.
    Idempotent on (source, dataset_key, dataset_url)."""
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                INSERT INTO cwc_resources
                    (source,dataset_key,role,dataset_url,resource_format,
                     frequency,stage,raw_reference,retrieved_at)
                VALUES
                    (:source,:dataset_key,:role,:dataset_url,:resource_format,
                     :frequency,:stage,:raw_reference,:retrieved_at)
                ON CONFLICT ON CONSTRAINT uq_cwcresource_natural DO UPDATE SET
                    role=EXCLUDED.role,
                    resource_format=EXCLUDED.resource_format,
                    frequency=EXCLUDED.frequency, stage=EXCLUDED.stage,
                    raw_reference=EXCLUDED.raw_reference,
                    retrieved_at=EXCLUDED.retrieved_at
                RETURNING id
            """),
            {
                "source": d.get("source", "cwc"),
                "dataset_key": d["dataset_key"],
                "role": d.get("role"),
                "dataset_url": d.get("dataset_url"),
                "resource_format": d.get("resource_format"),
                "frequency": d.get("frequency"),
                "stage": d.get("stage", "CATALOG_ONLY"),
                "raw_reference": d.get("raw_reference"),
                "retrieved_at": d.get("retrieved_at"),
            },
        ).mappings().first()
        return row["id"]
    return _run(work)


def cwc_resources_recent(limit: int = 50) -> list[dict]:
    from sqlalchemy import text

    def work(s):
        rows = s.execute(
            text("SELECT * FROM cwc_resources "
                 "ORDER BY ingested_at DESC, id DESC LIMIT :lim"),
            {"lim": limit},
        ).mappings().all()
        return [_norm_row(dict(r)) for r in rows]
    return _run(work)


def upsert_lgd_directory(d: dict) -> int:
    """Track B twin of repositories.upsert_lgd_directory. LGD is an administrative
    directory catalog (districts / subdistricts / blocks / villages / local bodies
    / wards): this carries NO boundary geometry and NO measurement, records only
    the verified directory dataset + admin level + purpose + download-portal URL,
    and has NO geometry column (the verified note forbids treating the directory as
    a polygon dataset — geometry comes from an authoritative GIS product joined by
    LGD code). The ML feature pipeline never reads this table. Idempotent on
    (source, dataset_key, directory_url)."""
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                INSERT INTO lgd_directory
                    (source,dataset_key,admin_level,purpose,directory_url,
                     stage,raw_reference,retrieved_at)
                VALUES
                    (:source,:dataset_key,:admin_level,:purpose,:directory_url,
                     :stage,:raw_reference,:retrieved_at)
                ON CONFLICT ON CONSTRAINT uq_lgddirectory_natural DO UPDATE SET
                    admin_level=EXCLUDED.admin_level,
                    purpose=EXCLUDED.purpose, stage=EXCLUDED.stage,
                    raw_reference=EXCLUDED.raw_reference,
                    retrieved_at=EXCLUDED.retrieved_at
                RETURNING id
            """),
            {
                "source": d.get("source", "lgd"),
                "dataset_key": d["dataset_key"],
                "admin_level": d.get("admin_level"),
                "purpose": d.get("purpose"),
                "directory_url": d.get("directory_url"),
                "stage": d.get("stage", "CATALOG_ONLY"),
                "raw_reference": d.get("raw_reference"),
                "retrieved_at": d.get("retrieved_at"),
            },
        ).mappings().first()
        return row["id"]
    return _run(work)


def lgd_directory_recent(limit: int = 50) -> list[dict]:
    from sqlalchemy import text

    def work(s):
        rows = s.execute(
            text("SELECT * FROM lgd_directory "
                 "ORDER BY ingested_at DESC, id DESC LIMIT :lim"),
            {"lim": limit},
        ).mappings().all()
        return [_norm_row(dict(r)) for r in rows]
    return _run(work)


def upsert_historical_source(d: dict) -> int:
    """Track B twin of repositories.upsert_historical_source. The historical-labels
    layer catalogs the verified official SOURCES of historical flood/landslide
    events (NRSC Landslide Atlas, NRSC/Bhuvan flood-hazard, NDEM): this carries NO
    event geometry, NO event time and NO training label, records only the verified
    source + hazard + period + role + access note, and has NO geometry column (a
    source-catalog row is not a polygon; the verified note forbids treating an
    inventory as a complete presence/absence census). The ML training pipeline never
    reads this table. Idempotent on (source, source_key, source_url)."""
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                INSERT INTO historical_sources
                    (source,source_key,hazard,role,source_url,period,
                     access_note,stage,raw_reference,retrieved_at)
                VALUES
                    (:source,:source_key,:hazard,:role,:source_url,:period,
                     :access_note,:stage,:raw_reference,:retrieved_at)
                ON CONFLICT ON CONSTRAINT uq_histsource_natural DO UPDATE SET
                    hazard=EXCLUDED.hazard, role=EXCLUDED.role,
                    period=EXCLUDED.period, access_note=EXCLUDED.access_note,
                    stage=EXCLUDED.stage, raw_reference=EXCLUDED.raw_reference,
                    retrieved_at=EXCLUDED.retrieved_at
                RETURNING id
            """),
            {
                "source": d.get("source", "historical"),
                "source_key": d["source_key"],
                "hazard": d.get("hazard"),
                "role": d.get("role"),
                "source_url": d.get("source_url"),
                "period": d.get("period"),
                "access_note": d.get("access_note"),
                "stage": d.get("stage", "CATALOG_ONLY"),
                "raw_reference": d.get("raw_reference"),
                "retrieved_at": d.get("retrieved_at"),
            },
        ).mappings().first()
        return row["id"]
    return _run(work)


def historical_sources_recent(limit: int = 50) -> list[dict]:
    from sqlalchemy import text

    def work(s):
        rows = s.execute(
            text("SELECT * FROM historical_sources "
                 "ORDER BY ingested_at DESC, id DESC LIMIT :lim"),
            {"lim": limit},
        ).mappings().all()
        return [_norm_row(dict(r)) for r in rows]
    return _run(work)


def upsert_ndem_capability(d: dict) -> int:
    """Track B twin of repositories.upsert_ndem_capability. NDEM's non-base products
    are PROTECTED (authorized officials only); the verified note mandates we never
    bypass authentication or invent a private API, and that access_level and
    source-health be stored SEPARATELY from any risk score. So this catalogs only the
    verified capability + its access level + role + the verified portal URL: NO
    measurement, NO geometry, NO event, NO risk score, and NO geometry column (a
    capability-catalog row is not a polygon). The ML pipeline never reads this table.
    Idempotent on (source, capability_key, source_url)."""
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                INSERT INTO ndem_capabilities
                    (source,capability_key,access,role,source_url,
                     stage,raw_reference,retrieved_at)
                VALUES
                    (:source,:capability_key,:access,:role,:source_url,
                     :stage,:raw_reference,:retrieved_at)
                ON CONFLICT ON CONSTRAINT uq_ndemcap_natural DO UPDATE SET
                    access=EXCLUDED.access, role=EXCLUDED.role,
                    stage=EXCLUDED.stage, raw_reference=EXCLUDED.raw_reference,
                    retrieved_at=EXCLUDED.retrieved_at
                RETURNING id
            """),
            {
                "source": d.get("source", "ndem"),
                "capability_key": d["capability_key"],
                "access": d.get("access"),
                "role": d.get("role"),
                "source_url": d.get("source_url"),
                "stage": d.get("stage", "CATALOG_ONLY"),
                "raw_reference": d.get("raw_reference"),
                "retrieved_at": d.get("retrieved_at"),
            },
        ).mappings().first()
        return row["id"]
    return _run(work)


def ndem_capabilities_recent(limit: int = 50) -> list[dict]:
    from sqlalchemy import text

    def work(s):
        rows = s.execute(
            text("SELECT * FROM ndem_capabilities "
                 "ORDER BY ingested_at DESC, id DESC LIMIT :lim"),
            {"lim": limit},
        ).mappings().all()
        return [_norm_row(dict(r)) for r in rows]
    return _run(work)


def upsert_imd_observation(o: dict) -> int:
    """Track B twin of repositories.upsert_imd_observation. IMD is district/
    station-level with NO coordinates, so it lands in imd_observations (never
    rainfall_observations) and codes/colors are preserved verbatim. Idempotent
    on (source, record_type, area_id, observed_at, warning_day)."""
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                INSERT INTO imd_observations
                    (source,record_type,area_kind,area_id,area_name,observed_at,
                     valid_upto,temperature_c,humidity_pct,wind_speed_kmph,
                     pressure_hpa,rainfall_24h_mm,daily_actual_mm,daily_normal_mm,
                     cumulative_actual_mm,cumulative_normal_mm,rainfall_category,
                     warning_code,warning_color,warning_day,message,quality_flag,
                     realtime_class,raw_reference,retrieved_at)
                VALUES
                    (:source,:record_type,:area_kind,:area_id,:area_name,
                     :observed_at,:valid_upto,:temperature_c,:humidity_pct,
                     :wind_speed_kmph,:pressure_hpa,:rainfall_24h_mm,
                     :daily_actual_mm,:daily_normal_mm,:cumulative_actual_mm,
                     :cumulative_normal_mm,:rainfall_category,:warning_code,
                     :warning_color,:warning_day,:message,:quality_flag,
                     :realtime_class,:raw_reference,:retrieved_at)
                ON CONFLICT ON CONSTRAINT uq_imd_natural DO UPDATE SET
                     area_kind=EXCLUDED.area_kind, area_name=EXCLUDED.area_name,
                     valid_upto=EXCLUDED.valid_upto,
                     temperature_c=EXCLUDED.temperature_c,
                     humidity_pct=EXCLUDED.humidity_pct,
                     wind_speed_kmph=EXCLUDED.wind_speed_kmph,
                     pressure_hpa=EXCLUDED.pressure_hpa,
                     rainfall_24h_mm=EXCLUDED.rainfall_24h_mm,
                     daily_actual_mm=EXCLUDED.daily_actual_mm,
                     daily_normal_mm=EXCLUDED.daily_normal_mm,
                     cumulative_actual_mm=EXCLUDED.cumulative_actual_mm,
                     cumulative_normal_mm=EXCLUDED.cumulative_normal_mm,
                     rainfall_category=EXCLUDED.rainfall_category,
                     warning_code=EXCLUDED.warning_code,
                     warning_color=EXCLUDED.warning_color,
                     message=EXCLUDED.message, quality_flag=EXCLUDED.quality_flag,
                     realtime_class=EXCLUDED.realtime_class,
                     raw_reference=EXCLUDED.raw_reference,
                     retrieved_at=EXCLUDED.retrieved_at
                RETURNING id
            """),
            {"source": o.get("source", "imd"), "record_type": o["record_type"],
             "area_kind": o.get("area_kind"), "area_id": o.get("area_id"),
             "area_name": o.get("area_name"), "observed_at": o.get("observed_at"),
             "valid_upto": o.get("valid_upto"),
             "temperature_c": o.get("temperature_c"),
             "humidity_pct": o.get("humidity_pct"),
             "wind_speed_kmph": o.get("wind_speed_kmph"),
             "pressure_hpa": o.get("pressure_hpa"),
             "rainfall_24h_mm": o.get("rainfall_24h_mm"),
             "daily_actual_mm": o.get("daily_actual_mm"),
             "daily_normal_mm": o.get("daily_normal_mm"),
             "cumulative_actual_mm": o.get("cumulative_actual_mm"),
             "cumulative_normal_mm": o.get("cumulative_normal_mm"),
             "rainfall_category": o.get("rainfall_category"),
             "warning_code": o.get("warning_code"),
             "warning_color": o.get("warning_color"),
             "warning_day": o.get("warning_day"), "message": o.get("message"),
             "quality_flag": o.get("quality_flag", "GOOD"),
             "realtime_class": o.get("realtime_class"),
             "raw_reference": o.get("raw_reference"),
             "retrieved_at": o.get("retrieved_at")},
        ).mappings().first()
        return row["id"]
    return _run(work)


def imd_recent(limit: int = 50) -> list[dict]:
    from sqlalchemy import text

    def work(s):
        rows = s.execute(
            text("SELECT * FROM imd_observations "
                 "ORDER BY ingested_at DESC, id DESC LIMIT :lim"),
            {"lim": limit},
        ).mappings().all()
        return [_norm_row(dict(r)) for r in rows]
    return _run(work)


# --------------------------------------------------------------------------
# Time-series reads for feature engineering
#   ST_DWithin on a geography cast gives a true metric radius (GiST-accelerated),
#   the correct Track B analogue of Track A's lat/lon bbox tolerance.
# --------------------------------------------------------------------------
def rainfall_series(lat: float, lon: float, tol: float = 0.25) -> list[dict]:
    from sqlalchemy import text
    r = _degree_tol_to_metres(tol)

    def work(s):
        rows = s.execute(
            text("""
                SELECT * FROM rainfall_observations
                WHERE ST_DWithin(geom::geography,
                                 ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography,
                                 :r)
                ORDER BY ts DESC LIMIT 500
            """),
            {"lat": lat, "lon": lon, "r": r}).mappings().all()
        return [_norm_row(dict(x)) for x in rows]
    return _run(work)


def soil_latest(lat: float, lon: float, tol: float = 0.5,
                up_to_ts: str | None = None) -> dict | None:
    from sqlalchemy import text
    r = _degree_tol_to_metres(tol)

    def work(s):
        sql = ("""SELECT * FROM soil_moisture_observations
                  WHERE ST_DWithin(geom::geography,
                                   ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography,
                                   :r)""")
        params = {"lat": lat, "lon": lon, "r": r}
        if up_to_ts:
            sql += " AND ts <= :cut"; params["cut"] = up_to_ts
        sql += " ORDER BY ts DESC LIMIT 1"
        row = s.execute(text(sql), params).mappings().first()
        return _norm_row(dict(row)) if row else None
    return _run(work)


def river_series_near(lat: float, lon: float, tol: float = 0.5) -> list[dict]:
    from sqlalchemy import text
    r = _degree_tol_to_metres(tol)

    def work(s):
        rows = s.execute(
            text("""
                SELECT * FROM river_observations
                WHERE geom IS NOT NULL
                  AND ST_DWithin(geom::geography,
                                 ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography,
                                 :r)
                ORDER BY ts DESC LIMIT 200
            """),
            {"lat": lat, "lon": lon, "r": r}).mappings().all()
        return [_norm_row(dict(x)) for x in rows]
    return _run(work)


def latest_susceptibility(lat: float, lon: float, tol: float = 0.3) -> float | None:
    from sqlalchemy import text
    r = _degree_tol_to_metres(tol)

    def work(s):
        row = s.execute(
            text("""
                SELECT susceptibility FROM landslide_data
                WHERE susceptibility IS NOT NULL AND geom IS NOT NULL
                  AND ST_DWithin(geom::geography,
                                 ST_SetSRID(ST_MakePoint(:lon,:lat),4326)::geography,
                                 :r)
                ORDER BY ingested_at DESC LIMIT 1
            """),
            {"lat": lat, "lon": lon, "r": r}).mappings().first()
        return row["susceptibility"] if row else None
    return _run(work)


# --------------------------------------------------------------------------
# Predictions & alerts
# --------------------------------------------------------------------------
def insert_prediction(p: dict) -> int:
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                INSERT INTO predictions
                    (location_id,ts,horizon,flood_probability,landslide_probability,
                     risk_level,confidence,lead_time_min_lo,lead_time_min_hi,
                     data_completeness,top_factors,model_version,mode)
                VALUES
                    (:location_id,:ts,:horizon,:flood_probability,:landslide_probability,
                     :risk_level,:confidence,:lead_time_min_lo,:lead_time_min_hi,
                     :data_completeness,:top_factors,:model_version,:mode)
                RETURNING id
            """),
            {"location_id": p["location_id"], "ts": p["ts"],
             "horizon": p.get("horizon", "now"),
             "flood_probability": p.get("flood_probability"),
             "landslide_probability": p.get("landslide_probability"),
             "risk_level": p.get("risk_level"), "confidence": p.get("confidence"),
             "lead_time_min_lo": p.get("lead_time_min_lo"),
             "lead_time_min_hi": p.get("lead_time_min_hi"),
             "data_completeness": p.get("data_completeness"),
             "top_factors": json.dumps(p.get("top_factors", [])),
             "model_version": p.get("model_version"), "mode": p.get("mode")},
        ).mappings().first()
        return row["id"]
    return _run(work)


def latest_prediction(location_id: int) -> dict | None:
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("SELECT * FROM predictions WHERE location_id=:id "
                 "ORDER BY ts DESC, id DESC LIMIT 1"),
            {"id": location_id}).mappings().first()
        if not row:
            return None
        d = _norm_row(dict(row))
        if d.get("top_factors"):
            d["top_factors"] = json.loads(d["top_factors"])
        return d
    return _run(work)


def prediction_history(location_id: int, limit: int = 50) -> list[dict]:
    from sqlalchemy import text

    def work(s):
        rows = s.execute(
            text("SELECT * FROM predictions WHERE location_id=:id "
                 "ORDER BY ts DESC LIMIT :lim"),
            {"id": location_id, "lim": limit}).mappings().all()
        out = []
        for r in rows:
            d = _norm_row(dict(r))
            if d.get("top_factors"):
                d["top_factors"] = json.loads(d["top_factors"])
            out.append(d)
        return out
    return _run(work)


def insert_alert(a: dict) -> int:
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                INSERT INTO alerts
                    (location_id,severity,hazard_type,message,prediction_id,status,mode,
                     risk_level,risk_probability,lead_time_window,evacuation_centre_id,
                     evacuation_guidance,recipient_count,sms_status,push_status,fingerprint,dispatched_at)
                VALUES
                    (:location_id,:severity,:hazard_type,:message,:prediction_id,:status,:mode,
                     :risk_level,:risk_probability,:lead_time_window,:evacuation_centre_id,
                     :evacuation_guidance,:recipient_count,:sms_status,:push_status,:fingerprint,:dispatched_at)
                RETURNING id
            """),
            {"location_id": a["location_id"], "severity": a["severity"],
             "hazard_type": a["hazard_type"], "message": a["message"],
             "prediction_id": a.get("prediction_id"),
             "status": a.get("status", "active"), "mode": a.get("mode"),
             "risk_level": a.get("risk_level"),
             "risk_probability": a.get("risk_probability"),
             "lead_time_window": a.get("lead_time_window"),
             "evacuation_centre_id": a.get("evacuation_centre_id"),
             "evacuation_guidance": a.get("evacuation_guidance"),
             "recipient_count": a.get("recipient_count", 0),
             "sms_status": a.get("sms_status", "PENDING"),
             "push_status": a.get("push_status", "PENDING"),
             "fingerprint": a.get("fingerprint"),
             "dispatched_at": a.get("dispatched_at")},
        ).mappings().first()
        return row["id"]
    return _run(work)


def get_alert(alert_id: int) -> dict | None:
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                SELECT a.*, l.name AS location_name, l.state, l.district,
                       ec.name AS evacuation_centre_name, ec.capacity AS evacuation_centre_capacity,
                       ec.address AS evacuation_centre_address, ec.contact_number AS evacuation_centre_contact
                FROM alerts a
                JOIN locations l ON l.id=a.location_id
                LEFT JOIN evacuation_centres ec ON ec.id=a.evacuation_centre_id
                WHERE a.id = :alert_id
            """),
            {"alert_id": alert_id},
        ).mappings().first()
        return _norm_row(dict(row)) if row else None
    return _run(work)


def list_alerts(status: str | None = None, limit: int = 50) -> list[dict]:
    from sqlalchemy import text

    def work(s):
        where = "WHERE a.status = :status" if status else ""
        rows = s.execute(
            text(f"""
                SELECT a.*, l.name AS location_name, l.state, l.district,
                       ec.name AS evacuation_centre_name, ec.capacity AS evacuation_centre_capacity
                FROM alerts a
                JOIN locations l ON l.id=a.location_id
                LEFT JOIN evacuation_centres ec ON ec.id=a.evacuation_centre_id
                {where}
                ORDER BY a.created_at DESC LIMIT :limit
            """),
            {"status": status, "limit": limit},
        ).mappings().all()
        return [_norm_row(dict(x)) for x in rows]
    return _run(work)


def active_alerts() -> list[dict]:
    return list_alerts(status="active")


def update_alert_dispatch_status(alert_id: int, sms_status: str,
                                 push_status: str | None = None,
                                 dispatched_at: str | None = None) -> None:
    from sqlalchemy import text

    def work(s):
        s.execute(
            text("""
                UPDATE alerts SET sms_status = :sms_status,
                       push_status = COALESCE(:push_status, push_status),
                       dispatched_at = COALESCE(:dispatched_at, NOW())
                WHERE id = :alert_id
            """),
            {"alert_id": alert_id, "sms_status": sms_status,
             "push_status": push_status, "dispatched_at": dispatched_at},
        )
    _run(work)


def get_latest_active_alert_by_fingerprint(fingerprint: str) -> dict | None:
    from sqlalchemy import text

    def work(s):
        row = s.execute(
            text("""
                SELECT * FROM alerts WHERE fingerprint = :fingerprint AND status = 'active'
                ORDER BY created_at DESC LIMIT 1
            """),
            {"fingerprint": fingerprint},
        ).mappings().first()
        return _norm_row(dict(row)) if row else None
    return _run(work)


# --------------------------------------------------------------------------
# Evacuation Centres DAL (Track B)
# --------------------------------------------------------------------------
def upsert_evacuation_centre(c: dict) -> int:
    from sqlalchemy import text

    def work(s):
        existing = None
        if c.get("id"):
            existing = s.execute(text("SELECT id FROM evacuation_centres WHERE id=:id"), {"id": c["id"]}).mappings().first()
        elif c.get("name") and c.get("village"):
            existing = s.execute(text("SELECT id FROM evacuation_centres WHERE name=:name AND village=:village"),
                                 {"name": c["name"], "village": c["village"]}).mappings().first()

        params = {
            "name": c["name"], "address": c.get("address"), "village": c["village"],
            "ward": c.get("ward"), "district": c["district"], "latitude": c["latitude"],
            "longitude": c["longitude"], "capacity": c.get("capacity", 100),
            "contact_number": c.get("contact_number"), "accessibility": c.get("accessibility"),
            "verified": c.get("verified", 1), "active": c.get("active", 1),
            "is_demo": c.get("is_demo", 0),
        }
        if existing:
            cid = existing["id"]
            params["id"] = cid
            s.execute(text("""
                UPDATE evacuation_centres SET name=:name, address=:address, village=:village,
                       ward=:ward, district=:district, latitude=:latitude, longitude=:longitude,
                       capacity=:capacity, contact_number=:contact_number, accessibility=:accessibility,
                       verified=:verified, active=:active, is_demo=:is_demo WHERE id=:id
            """), params)
            return cid
        row = s.execute(text("""
            INSERT INTO evacuation_centres(name, address, village, ward, district,
                   latitude, longitude, capacity, contact_number, accessibility, verified, active, is_demo)
            VALUES(:name, :address, :village, :ward, :district,
                   :latitude, :longitude, :capacity, :contact_number, :accessibility, :verified, :active, :is_demo)
            RETURNING id
        """), params).mappings().first()
        return row["id"]
    return _run(work)


def get_evacuation_centre(centre_id: int) -> dict | None:
    from sqlalchemy import text

    def work(s):
        row = s.execute(text("SELECT * FROM evacuation_centres WHERE id=:id"), {"id": centre_id}).mappings().first()
        return _norm_row(dict(row)) if row else None
    return _run(work)


def list_evacuation_centres(village: str | None = None, district: str | None = None,
                            active_only: bool = True) -> list[dict]:
    from sqlalchemy import text

    def work(s):
        clauses = []
        params = {}
        if active_only:
            clauses.append("active=1")
        if village:
            clauses.append("village=:village")
            params["village"] = village
        if district:
            clauses.append("district=:district")
            params["district"] = district
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = s.execute(text(f"SELECT * FROM evacuation_centres {where} ORDER BY name"), params).mappings().all()
        return [_norm_row(dict(x)) for x in rows]
    return _run(work)


def nearest_evacuation_centres(lat: float, lon: float, limit: int = 5) -> list[dict]:
    import math
    centres = list_evacuation_centres(active_only=True)
    def dist(c):
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
# Alert Recipients DAL (Track B)
# --------------------------------------------------------------------------
def upsert_alert_recipient(r: dict) -> int:
    from sqlalchemy import text

    def work(s):
        existing = s.execute(
            text("SELECT id FROM alert_recipients WHERE phone_number=:phone AND village=:village"),
            {"phone": r["phone_number"], "village": r["village"]},
        ).mappings().first()

        params = {
            "name": r["name"], "phone_number": r["phone_number"], "village": r["village"],
            "ward": r.get("ward"), "district": r["district"],
            "preferred_language": r.get("preferred_language", "en"),
            "active": r.get("active", 1),
            "emergency_notification_enabled": r.get("emergency_notification_enabled", 1),
            "is_demo": r.get("is_demo", 1),
        }
        if existing:
            rid = existing["id"]
            params["id"] = rid
            s.execute(text("""
                UPDATE alert_recipients SET name=:name, ward=:ward, district=:district,
                       preferred_language=:preferred_language, active=:active,
                       emergency_notification_enabled=:emergency_notification_enabled,
                       is_demo=:is_demo WHERE id=:id
            """), params)
            return rid
        row = s.execute(text("""
            INSERT INTO alert_recipients(name, phone_number, village, ward, district,
                   preferred_language, active, emergency_notification_enabled, is_demo)
            VALUES(:name, :phone_number, :village, :ward, :district,
                   :preferred_language, :active, :emergency_notification_enabled, :is_demo)
            RETURNING id
        """), params).mappings().first()
        return row["id"]
    return _run(work)


def list_recipients_for_village(village: str, active_only: bool = True) -> list[dict]:
    from sqlalchemy import text

    def work(s):
        clauses = ["village=:village"]
        params = {"village": village}
        if active_only:
            clauses.append("active=1")
            clauses.append("emergency_notification_enabled=1")
        where = f"WHERE {' AND '.join(clauses)}"
        rows = s.execute(text(f"SELECT * FROM alert_recipients {where}"), params).mappings().all()
        return [_norm_row(dict(x)) for x in rows]
    return _run(work)


def count_recipients_for_village(village: str, active_only: bool = True) -> int:
    from sqlalchemy import text

    def work(s):
        clauses = ["village=:village"]
        params = {"village": village}
        if active_only:
            clauses.append("active=1")
            clauses.append("emergency_notification_enabled=1")
        where = f"WHERE {' AND '.join(clauses)}"
        row = s.execute(text(f"SELECT COUNT(*) as count FROM alert_recipients {where}"), params).mappings().first()
        return int(row["count"]) if row and row.get("count") is not None else 0
    return _run(work)


def all_source_health() -> list[dict]:
    from sqlalchemy import text

    def work(s):
        rows = s.execute(text("SELECT * FROM source_health ORDER BY source")).mappings().all()
        return [_norm_row(dict(x)) for x in rows]
    return _run(work)


# --------------------------------------------------------------------------
# Source health / ingestion / quality logging (PostGIS mirror of the Track A
# functions). collectors/base.py calls these through the repositories seam.
# --------------------------------------------------------------------------
def get_source_health(source: str) -> dict | None:
    from sqlalchemy import text

    def work(s):
        row = s.execute(text("SELECT * FROM source_health WHERE source=:src"),
                        {"src": source}).mappings().first()
        return _norm_row(dict(row)) if row else None
    return _run(work)


def record_source_health(h: dict) -> None:
    """Idempotent upsert on the source PK. Preserves last_success_at on a failed
    attempt (COALESCE with EXCLUDED), matching Track A behaviour — UNLESS the
    caller passes force_success_ts=True, which writes last_success_at exactly as
    given (used to DOWNGRADE a within-run success, e.g. Bhuvan catalog succeeds
    but the optional endpoint probe finds the service unreachable -> STALE with
    last_success_at cleared)."""
    from sqlalchemy import text

    force = bool(h.get("force_success_ts"))
    success_expr = ("EXCLUDED.last_success_at" if force else
                    "COALESCE(EXCLUDED.last_success_at, "
                    "source_health.last_success_at)")

    def work(s):
        s.execute(
            text(f"""
                INSERT INTO source_health
                    (source,status,last_success_at,last_attempt_at,
                     last_latency_ms,last_error,records_last_run,updated_at)
                VALUES
                    (:source,:status,:last_success_at,:last_attempt_at,
                     :last_latency_ms,:last_error,:records_last_run,:updated_at)
                ON CONFLICT (source) DO UPDATE SET
                     status=EXCLUDED.status,
                     last_attempt_at=EXCLUDED.last_attempt_at,
                     last_latency_ms=EXCLUDED.last_latency_ms,
                     last_error=EXCLUDED.last_error,
                     records_last_run=EXCLUDED.records_last_run,
                     last_success_at={success_expr},
                     updated_at=EXCLUDED.updated_at
            """),
            {"source": h["source"], "status": h.get("status"),
             "last_success_at": h.get("last_success_at"),
             "last_attempt_at": h.get("last_attempt_at"),
             "last_latency_ms": h.get("last_latency_ms"),
             "last_error": h.get("last_error"),
             "records_last_run": h.get("records_last_run"),
             "updated_at": h.get("updated_at")},
        )
    _run(work)


def log_ingestion(e: dict) -> None:
    from sqlalchemy import text

    def work(s):
        s.execute(
            text("""
                INSERT INTO ingestion_log
                    (source,started_at,finished_at,status,records_received,
                     records_stored,records_rejected,latency_ms,error)
                VALUES
                    (:source,:started_at,:finished_at,:status,:records_received,
                     :records_stored,:records_rejected,:latency_ms,:error)
            """),
            {"source": e["source"], "started_at": e.get("started_at"),
             "finished_at": e.get("finished_at"), "status": e.get("status"),
             "records_received": e.get("records_received", 0),
             "records_stored": e.get("records_stored", 0),
             "records_rejected": e.get("records_rejected", 0),
             "latency_ms": e.get("latency_ms"), "error": e.get("error")},
        )
    _run(work)


def log_quality(q: dict) -> None:
    from sqlalchemy import text

    def work(s):
        s.execute(
            text("""
                INSERT INTO data_quality_flags
                    (source,table_name,ts,flag,reason)
                VALUES
                    (:source,:table_name,:ts,:flag,:reason)
            """),
            {"source": q["source"], "table_name": q.get("table_name", ""),
             "ts": q.get("ts"), "flag": q.get("flag", "BAD"),
             "reason": q.get("reason")},
        )
    _run(work)
