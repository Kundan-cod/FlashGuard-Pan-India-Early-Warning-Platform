"""
Track B ORM models (master prompt sections 6, 7) — SQLAlchemy 2.0 + GeoAlchemy2.

These mirror schema_sqlite.sql column-for-column, except geometry columns become
real PostGIS `geometry(..., 4326)` types instead of GeoJSON text + bbox. The
repository layer (repositories_prod.py) exposes the SAME function names as the
Track A repositories.py, so features/models/risk/API code is unchanged between
tracks — the only difference is which repository module is imported.

STATUS: skeleton — pending local run (needs SQLAlchemy/GeoAlchemy2/PostGIS,
which are not installed in the build sandbox).
"""
from __future__ import annotations

try:
    from sqlalchemy import (Column, Integer, Float, String, Text, ForeignKey,
                            UniqueConstraint, Index, DateTime, func)
    from sqlalchemy.orm import declarative_base, relationship
    from geoalchemy2 import Geometry
    _HAVE_ORM = True
except ImportError:  # pragma: no cover - Track B deps not in sandbox
    _HAVE_ORM = False
    Base = None

if _HAVE_ORM:
    Base = declarative_base()

    class Location(Base):
        __tablename__ = "locations"
        id = Column(Integer, primary_key=True)
        ext_code = Column(String, unique=True)
        name = Column(String, nullable=False)
        level = Column(String, nullable=False, index=True)
        parent_id = Column(Integer, ForeignKey("locations.id"), index=True)
        state = Column(String)
        district = Column(String)
        block = Column(String)
        village = Column(String)
        latitude = Column(Float)
        longitude = Column(Float)
        # PostGIS geometry (WGS84). Polygon/MultiPolygon for admin areas.
        # spatial_index=False: indexes are created explicitly in the Alembic
        # migration (source of truth), so we disable GeoAlchemy2's automatic
        # DDL listener here to avoid double-creation / autogenerate drift.
        geom = Column(Geometry(geometry_type="GEOMETRY", srid=4326,
                               spatial_index=False))
        is_synthetic = Column(Integer, nullable=False, default=0)
        created_at = Column(DateTime(timezone=True), server_default=func.now())
        terrain = relationship("TerrainFeature", uselist=False, back_populates="location")

    class TerrainFeature(Base):
        __tablename__ = "terrain_features"
        location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"),
                             primary_key=True)
        elevation = Column(Float)
        slope = Column(Float)
        aspect = Column(Float)
        curvature = Column(Float)
        flow_accumulation = Column(Float)
        drainage_density = Column(Float)
        distance_to_drainage = Column(Float)
        relative_relief = Column(Float)
        is_synthetic = Column(Integer, nullable=False, default=0)
        source = Column(String)
        updated_at = Column(DateTime(timezone=True), server_default=func.now())
        location = relationship("Location", back_populates="terrain")

    class RainfallObservation(Base):
        __tablename__ = "rainfall_observations"
        id = Column(Integer, primary_key=True)
        source = Column(String, nullable=False, index=True)
        ts = Column(DateTime(timezone=True), nullable=False, index=True)
        latitude = Column(Float, nullable=False)
        longitude = Column(Float, nullable=False)
        geom = Column(Geometry(geometry_type="POINT", srid=4326, spatial_index=False))
        rainfall_30m = Column(Float)
        rainfall_3h = Column(Float)
        rainfall_24h = Column(Float)
        quality_flag = Column(String, nullable=False, default="GOOD")
        resolution_m = Column(Float)
        realtime_class = Column(String)
        units = Column(String, default="mm")
        granule_id = Column(String)
        ingested_at = Column(DateTime(timezone=True), server_default=func.now())
        __table_args__ = (
            UniqueConstraint("source", "ts", "latitude", "longitude",
                             name="uq_rain_natural"),
        )

    class SoilMoistureObservation(Base):
        __tablename__ = "soil_moisture_observations"
        id = Column(Integer, primary_key=True)
        source = Column(String, nullable=False)
        ts = Column(DateTime(timezone=True), nullable=False, index=True)
        latitude = Column(Float, nullable=False)
        longitude = Column(Float, nullable=False)
        geom = Column(Geometry(geometry_type="POINT", srid=4326, spatial_index=False))
        surface_moisture = Column(Float)
        root_zone_moisture = Column(Float)
        quality_flag = Column(String, nullable=False, default="GOOD")
        resolution_m = Column(Float)
        realtime_class = Column(String)
        ingested_at = Column(DateTime(timezone=True), server_default=func.now())
        __table_args__ = (
            UniqueConstraint("source", "ts", "latitude", "longitude",
                             name="uq_soil_natural"),
        )

    class RiverObservation(Base):
        __tablename__ = "river_observations"
        id = Column(Integer, primary_key=True)
        source = Column(String, nullable=False)
        station_id = Column(String)
        ts = Column(DateTime(timezone=True), nullable=False, index=True)
        latitude = Column(Float)
        longitude = Column(Float)
        geom = Column(Geometry(geometry_type="POINT", srid=4326, spatial_index=False))
        water_level = Column(Float)
        flow = Column(Float)
        rate_of_rise = Column(Float)
        quality_flag = Column(String, nullable=False, default="GOOD")
        realtime_class = Column(String)
        ingested_at = Column(DateTime(timezone=True), server_default=func.now())
        __table_args__ = (
            UniqueConstraint("source", "station_id", "ts", name="uq_river_natural"),
        )

    class LandslideData(Base):
        __tablename__ = "landslide_data"
        id = Column(Integer, primary_key=True)
        source = Column(String, nullable=False)
        event_time = Column(DateTime(timezone=True))
        latitude = Column(Float)
        longitude = Column(Float)
        geom = Column(Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False))
        susceptibility = Column(Float)
        impact_probability = Column(Float)
        severity = Column(String)
        is_synthetic = Column(Integer, nullable=False, default=0)
        ingested_at = Column(DateTime(timezone=True), server_default=func.now())

    class IotObservation(Base):
        __tablename__ = "iot_observations"
        id = Column(Integer, primary_key=True)
        sensor_id = Column(String, nullable=False)
        ts = Column(DateTime(timezone=True), nullable=False, index=True)
        latitude = Column(Float)
        longitude = Column(Float)
        geom = Column(Geometry(geometry_type="POINT", srid=4326, spatial_index=False))
        rainfall = Column(Float)
        soil_moisture = Column(Float)
        water_level = Column(Float)
        temperature = Column(Float)
        quality_flag = Column(String, nullable=False, default="GOOD")
        is_simulated = Column(Integer, nullable=False, default=1)
        ingested_at = Column(DateTime(timezone=True), server_default=func.now())
        __table_args__ = (
            UniqueConstraint("sensor_id", "ts", name="uq_iot_natural"),
        )

    class IotRawTelemetry(Base):
        __tablename__ = "iot_raw_telemetry"
        id = Column(Integer, primary_key=True)
        source = Column(String, nullable=False)
        channel_id = Column(String, nullable=False)
        entry_id = Column(Integer, nullable=False)
        ts = Column(DateTime(timezone=True), nullable=False, index=True)
        raw_payload = Column(Text, nullable=False)
        quality_flag = Column(String, nullable=False, default="GOOD")
        ingested_at = Column(DateTime(timezone=True), server_default=func.now())
        __table_args__ = (
            UniqueConstraint("channel_id", "entry_id", name="uq_iot_raw_natural"),
        )

    class Prediction(Base):
        __tablename__ = "predictions"
        id = Column(Integer, primary_key=True)
        location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"),
                             index=True)
        ts = Column(DateTime(timezone=True), nullable=False, index=True)
        horizon = Column(String, nullable=False, default="now")
        flood_probability = Column(Float)
        landslide_probability = Column(Float)
        risk_level = Column(String)
        confidence = Column(Float)
        lead_time_min_lo = Column(Integer)
        lead_time_min_hi = Column(Integer)
        data_completeness = Column(Float)
        top_factors = Column(Text)      # JSON string (portable) / JSONB in Track B if desired
        model_version = Column(String)
        mode = Column(String)
        created_at = Column(DateTime(timezone=True), server_default=func.now())

    class EvacuationCentre(Base):
        __tablename__ = "evacuation_centres"
        id = Column(Integer, primary_key=True)
        name = Column(String, nullable=False)
        address = Column(String)
        village = Column(String, nullable=False, index=True)
        ward = Column(String)
        district = Column(String, nullable=False, index=True)
        latitude = Column(Float, nullable=False)
        longitude = Column(Float, nullable=False)
        capacity = Column(Integer, nullable=False, default=100)
        contact_number = Column(String)
        accessibility = Column(String)
        verified = Column(Integer, nullable=False, default=1)
        active = Column(Integer, nullable=False, default=1)
        is_demo = Column(Integer, nullable=False, default=0)
        created_at = Column(DateTime(timezone=True), server_default=func.now())

    class AlertRecipient(Base):
        __tablename__ = "alert_recipients"
        id = Column(Integer, primary_key=True)
        name = Column(String, nullable=False)
        phone_number = Column(String, nullable=False)
        village = Column(String, nullable=False, index=True)
        ward = Column(String)
        district = Column(String, nullable=False)
        preferred_language = Column(String, nullable=False, default="en")
        active = Column(Integer, nullable=False, default=1)
        emergency_notification_enabled = Column(Integer, nullable=False, default=1)
        is_demo = Column(Integer, nullable=False, default=1)
        created_at = Column(DateTime(timezone=True), server_default=func.now())

    class Alert(Base):
        __tablename__ = "alerts"
        id = Column(Integer, primary_key=True)
        location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"),
                             index=True)
        created_at = Column(DateTime(timezone=True), server_default=func.now())
        severity = Column(String, nullable=False)
        hazard_type = Column(String, nullable=False)
        message = Column(Text, nullable=False)
        prediction_id = Column(Integer, ForeignKey("predictions.id"))
        status = Column(String, nullable=False, default="active")
        mode = Column(String)
        risk_level = Column(String)
        risk_probability = Column(Float)
        lead_time_window = Column(String)
        evacuation_centre_id = Column(Integer, ForeignKey("evacuation_centres.id"))
        evacuation_guidance = Column(Text)
        recipient_count = Column(Integer, default=0)
        sms_status = Column(String, default="PENDING")
        push_status = Column(String, default="PENDING")
        fingerprint = Column(String, index=True)
        dispatched_at = Column(DateTime(timezone=True))

    class GpmDiscovery(Base):
        """GPM PMM dataset-discovery records — NOT rainfall observations.

        The ML feature pipeline never reads this table, so a discovery record
        (numeric_value NULL) can never be mistaken for a numeric rainfall
        observation. A real mm value only enters rainfall_observations after the
        gated raster-sampling stage. `stage` is an observation-stage flag
        (DISCOVERY_ONLY | RASTER_SAMPLED), deliberately distinct from the 7
        SourceStatus health states.
        """
        __tablename__ = "gpm_discovery"
        id = Column(Integer, primary_key=True)
        source = Column(String, nullable=False, default="gpm")
        product = Column(String)
        observed_date = Column(String)
        latitude = Column(Float)
        longitude = Column(Float)
        geom = Column(Geometry(geometry_type="POINT", srid=4326, spatial_index=False))
        resolution = Column(String)
        download_url = Column(Text)
        media_type = Column(String)
        item_id = Column(String)
        numeric_value = Column(Float)         # NULL at discovery; set only after raster sampling
        stage = Column(String, nullable=False, default="DISCOVERY_ONLY")
        raw_reference = Column(Text)
        retrieved_at = Column(DateTime(timezone=True))
        ingested_at = Column(DateTime(timezone=True), server_default=func.now())
        __table_args__ = (
            UniqueConstraint("item_id", "download_url", name="uq_gpmdisc_natural"),
        )

    class SmapDiscovery(Base):
        """NASA SMAP CMR granule-discovery records — NOT soil-moisture values.

        Twin of GpmDiscovery. The ML feature pipeline never reads this table, so
        a discovery record (surface_sm / rootzone_sm NULL) can never be mistaken
        for a numeric soil-moisture observation. Real m3/m3 values only enter
        soil_moisture_observations after a gated HDF5/NetCDF parse stage. `stage`
        is an observation-stage flag (DISCOVERY_ONLY | RASTER_SAMPLED), distinct
        from the 7 SourceStatus health states.
        """
        __tablename__ = "smap_discovery"
        id = Column(Integer, primary_key=True)
        source = Column(String, nullable=False, default="smap")
        product = Column(String)
        version = Column(String)
        observed_date = Column(String)
        end_time = Column(String)
        latitude = Column(Float)
        longitude = Column(Float)
        geom = Column(Geometry(geometry_type="POINT", srid=4326, spatial_index=False))
        grid = Column(String)
        download_url = Column(Text)
        concept_id = Column(String)
        producer_granule_id = Column(String)
        surface_sm = Column(Float)            # NULL at discovery; set only after parse stage
        rootzone_sm = Column(Float)           # NULL at discovery; set only after parse stage
        quality_flag = Column(String, default="UNKNOWN")
        stage = Column(String, nullable=False, default="DISCOVERY_ONLY")
        raw_reference = Column(Text)
        retrieved_at = Column(DateTime(timezone=True))
        ingested_at = Column(DateTime(timezone=True), server_default=func.now())
        __table_args__ = (
            UniqueConstraint("concept_id", "download_url", name="uq_smapdisc_natural"),
        )

    class ImdObservation(Base):
        """India Meteorological Department (api.imd.gov.in) records.

        IMD returns REAL numeric government weather/rainfall/warnings, but at
        DISTRICT or STATION granularity and WITHOUT coordinates. It is kept out
        of rainfall_observations (a point table read as village-level rainfall)
        because treating a district figure as a village value would violate the
        verified spec ("Do not treat district rainfall as village-level"). Codes
        and colors are preserved verbatim, never converted to an ML probability.
        """
        __tablename__ = "imd_observations"
        id = Column(Integer, primary_key=True)
        source = Column(String, nullable=False, default="imd")
        record_type = Column(String, nullable=False)
        area_kind = Column(String)
        area_id = Column(String)
        area_name = Column(String)
        observed_at = Column(String)
        valid_upto = Column(String)
        temperature_c = Column(Float)
        humidity_pct = Column(Float)
        wind_speed_kmph = Column(Float)
        pressure_hpa = Column(Float)
        rainfall_24h_mm = Column(Float)
        daily_actual_mm = Column(Float)
        daily_normal_mm = Column(Float)
        cumulative_actual_mm = Column(Float)
        cumulative_normal_mm = Column(Float)
        rainfall_category = Column(String)
        warning_code = Column(String)
        warning_color = Column(Integer)
        warning_day = Column(Integer)
        message = Column(Text)
        quality_flag = Column(String, nullable=False, default="GOOD")
        realtime_class = Column(String)
        raw_reference = Column(Text)
        retrieved_at = Column(DateTime(timezone=True))
        ingested_at = Column(DateTime(timezone=True), server_default=func.now())
        __table_args__ = (
            UniqueConstraint("source", "record_type", "area_id", "observed_at",
                             "warning_day", name="uq_imd_natural"),
        )

    class BhuvanLayer(Base):
        """Bhuvan/NRSC OGC layer-catalog records — NOT numeric terrain values.

        Bhuvan/NRSC is a STATIC terrain/context source exposed as OGC WMS/WMTS
        layers. The verified note is explicit: never scrape rendered map pixels
        as a substitute for the DEM, and quantitative terrain must be derived
        from downloaded DEM tiles and preprocessed once (a stage the verified
        package does not implement). So this table catalogs verified layer
        endpoints + roles ONLY; it carries no measured value and the ML feature
        pipeline (which reads terrain_features) never reads it. A catalog row can
        never masquerade as a numeric terrain feature. `stage` is an observation-
        stage flag (CATALOG_ONLY | DEM_PROCESSED), distinct from the 7
        SourceStatus health states.
        """
        __tablename__ = "bhuvan_layers"
        id = Column(Integer, primary_key=True)
        source = Column(String, nullable=False, default="bhuvan")
        layer_key = Column(String, nullable=False)
        service_type = Column(String)
        role = Column(String)
        service_url = Column(Text)
        layer_name = Column(String)
        stage = Column(String, nullable=False, default="CATALOG_ONLY")
        raw_reference = Column(Text)
        retrieved_at = Column(DateTime(timezone=True))
        ingested_at = Column(DateTime(timezone=True), server_default=func.now())
        __table_args__ = (
            UniqueConstraint("source", "layer_key", "service_url",
                             name="uq_bhuvanlayer_natural"),
        )

    class GsiLayer(Base):
        """GSI / Bhusanket portal layer-catalog records — NOT landslide values.

        Twin of BhuvanLayer (catalog-only). GSI's Bhusanket portal exposes a
        forecast bulletin, LSM 10K susceptibility, an impact-probability map and
        a field-validated landslide inventory, but the verified note forbids
        hard-coding an undocumented JSON API and stresses that GSI forecasting is
        REGIONAL, not a nationwide live API. So this table catalogs the verified
        portal layers + roles + a coverage (geographic_scope) note ONLY; it
        carries no numeric susceptibility/probability and the ML landslide model
        (which reads landslide_data) never reads it. A catalog row can never
        masquerade as a landslide value. `stage` is an observation-stage flag
        (CATALOG_ONLY | PARSED), distinct from the 7 SourceStatus health states.
        There is deliberately NO geometry column: a catalog entry describes a
        portal layer, not a point observation.
        """
        __tablename__ = "gsi_layers"
        id = Column(Integer, primary_key=True)
        source = Column(String, nullable=False, default="gsi")
        layer_key = Column(String, nullable=False)
        role = Column(String)
        service_url = Column(Text)
        geographic_scope = Column(Text)
        public = Column(Integer, nullable=False, default=1)
        stage = Column(String, nullable=False, default="CATALOG_ONLY")
        raw_reference = Column(Text)
        retrieved_at = Column(DateTime(timezone=True))
        ingested_at = Column(DateTime(timezone=True), server_default=func.now())
        __table_args__ = (
            UniqueConstraint("source", "layer_key", "service_url",
                             name="uq_gsilayer_natural"),
        )

    class CwcResource(Base):
        """CWC / NWIC NWDP dataset-catalog records — NOT numeric hydro values.

        Twin of BhuvanLayer / GsiLayer (catalog-only). CWC/NWIC hydrology (river
        water level, telemetry rainfall, reservoir storage) is exposed through the
        public National Water Data Portal (NWDP), which advertises CSV/API as data
        formats. The verified note forbids inventing an undocumented API URL and
        warns not to claim that every station is live or every API anonymous. So
        this table catalogs the verified NWDP dataset pages + roles + advertised
        formats ONLY; it carries no measured water-level/rainfall value and the ML
        feature pipeline (which reads river_observations / rainfall_observations)
        never reads it. A catalog row can never masquerade as a numeric hydro
        value. `stage` is an observation-stage flag (CATALOG_ONLY | PARSED),
        distinct from the 7 SourceStatus health states. There is deliberately NO
        geometry column: a catalog entry describes a dataset page, not a point
        observation.
        """
        __tablename__ = "cwc_resources"
        id = Column(Integer, primary_key=True)
        source = Column(String, nullable=False, default="cwc")
        dataset_key = Column(String, nullable=False)
        role = Column(String)
        dataset_url = Column(Text)
        resource_format = Column(String)
        frequency = Column(String)
        stage = Column(String, nullable=False, default="CATALOG_ONLY")
        raw_reference = Column(Text)
        retrieved_at = Column(DateTime(timezone=True))
        ingested_at = Column(DateTime(timezone=True), server_default=func.now())
        __table_args__ = (
            UniqueConstraint("source", "dataset_key", "dataset_url",
                             name="uq_cwcresource_natural"),
        )

    class LgdDirectory(Base):
        """LGD administrative-directory catalog records — NOT geometry, NOT values.

        Twin of BhuvanLayer / GsiLayer / CwcResource (catalog-only). The Local
        Government Directory is the authoritative directory of administrative
        identity + codes for the India -> State/UT -> District -> Sub-district ->
        Block -> Village/ULB -> Ward hierarchy, exposed as downloadable directories
        at the official portal. The verified note forbids two things: (1) assuming
        the directory tables are polygon datasets — boundary geometry must come from
        an authoritative GIS product and be joined by LGD code, so this table has
        NO geometry column at all; (2) using names as primary keys — LGD codes are
        the stable join keys, names are display-only. The vendored adapter fetches
        only the directory download page and implements no row parser, so this table
        catalogs the verified directory DATASETS (one per admin level) + their level
        + purpose ONLY; it produces no administrative-unit rows and no measurement,
        and the ML feature pipeline never reads it. `stage` is an observation-stage
        flag (CATALOG_ONLY | PARSED), distinct from the 7 SourceStatus health
        states.
        """
        __tablename__ = "lgd_directory"
        id = Column(Integer, primary_key=True)
        source = Column(String, nullable=False, default="lgd")
        dataset_key = Column(String, nullable=False)
        admin_level = Column(String)
        purpose = Column(Text)
        directory_url = Column(Text)
        stage = Column(String, nullable=False, default="CATALOG_ONLY")
        raw_reference = Column(Text)
        retrieved_at = Column(DateTime(timezone=True))
        ingested_at = Column(DateTime(timezone=True), server_default=func.now())
        __table_args__ = (
            UniqueConstraint("source", "dataset_key", "directory_url",
                             name="uq_lgddirectory_natural"),
        )

    class HistoricalSource(Base):
        """Historical-label SOURCE catalog records — NOT events, NOT labels.

        Twin of CwcResource (catalog-only, distinct source_url per row). The
        historical-labels layer defines the verified official sources of historical
        flood / landslide events used for training and replay: the NRSC/ISRO
        Landslide Atlas, NRSC flood-hazard zonation, the Bhuvan historical
        flood-inundation service, and NDEM historical disaster data. The verified
        note forbids two things: (1) treating these inventories as complete
        presence/absence censuses — "do not interpret the inventory as a complete
        nationwide absence/presence census" and "do not convert missing observations
        into negatives"; (2) reducing an event to a fake point label. The vendored
        package ships NO event rows and NO parser — only the source registry + the
        three-state labeling RULE (1=confirmed event, 0=confirmed non-event only
        where coverage is adequate, -1=unobserved/unknown). So this table catalogs
        the verified SOURCES (hazard + period + role + access) ONLY; it carries no
        event geometry, no event time and no training label. Real events and the
        1/0/-1 labels derived via the verified rule would only enter a separate
        events/labels table after a gated, verified inventory parse (future work),
        and the ML training pipeline reads that table, never this catalog. `stage`
        is an observation-stage flag (CATALOG_ONLY | PARSED), distinct from the 7
        SourceStatus health states.
        """
        __tablename__ = "historical_sources"
        id = Column(Integer, primary_key=True)
        source = Column(String, nullable=False, default="historical")
        source_key = Column(String, nullable=False)
        hazard = Column(String)
        role = Column(String)
        source_url = Column(Text)
        period = Column(Text)
        access_note = Column(Text)
        stage = Column(String, nullable=False, default="CATALOG_ONLY")
        raw_reference = Column(Text)
        retrieved_at = Column(DateTime(timezone=True))
        ingested_at = Column(DateTime(timezone=True), server_default=func.now())
        __table_args__ = (
            UniqueConstraint("source", "source_key", "source_url",
                             name="uq_histsource_natural"),
        )

    class NdemCapability(Base):
        """NDEM capability/access catalog records — NOT measurements, NOT events.

        Twin of GsiLayer / LgdDirectory (catalog-only, one shared portal URL for
        every capability so capability_key keeps rows distinct). NDEM (National
        Database for Emergency Management) is an NRSC/ISRO national GIS repository +
        DSS for disaster management. The verified note (ndem_verified.md) is
        explicit that NDEM's non-base products are PROTECTED and require authorized
        credentials (Central/State/District/NDRF/SDRF officials); only public/base
        layers may be visible without login. The vendored package implements ONLY
        public-portal discovery + this capability/access registry and "does not
        invent private API endpoints" and must "never bypass authentication". So
        this table catalogs the verified NDEM CAPABILITIES (name + access level +
        role + portal URL) ONLY; it carries no measurement, no geometry, no event
        and no risk score. Per the verified engineering decision, `access` (PUBLIC |
        AUTHORIZED | AUTHORIZED_OR_PRODUCT_SPECIFIC) is a capability-access
        classification copied verbatim and stored SEPARATELY from any risk score —
        never a data value. The ML pipeline never reads this catalog. `stage` is an
        observation-stage flag (CATALOG_ONLY | PARSED), distinct from the 7
        SourceStatus health states.
        """
        __tablename__ = "ndem_capabilities"
        id = Column(Integer, primary_key=True)
        source = Column(String, nullable=False, default="ndem")
        capability_key = Column(String, nullable=False)
        access = Column(String)
        role = Column(String)
        source_url = Column(Text)
        stage = Column(String, nullable=False, default="CATALOG_ONLY")
        raw_reference = Column(Text)
        retrieved_at = Column(DateTime(timezone=True))
        ingested_at = Column(DateTime(timezone=True), server_default=func.now())
        __table_args__ = (
            UniqueConstraint("source", "capability_key", "source_url",
                             name="uq_ndemcap_natural"),
        )

    class SourceHealth(Base):
        __tablename__ = "source_health"
        source = Column(String, primary_key=True)
        status = Column(String, nullable=False, default="unknown")
        last_success_at = Column(DateTime(timezone=True))
        last_attempt_at = Column(DateTime(timezone=True))
        last_latency_ms = Column(Integer)
        last_error = Column(Text)
        records_last_run = Column(Integer)
        updated_at = Column(DateTime(timezone=True), server_default=func.now())
