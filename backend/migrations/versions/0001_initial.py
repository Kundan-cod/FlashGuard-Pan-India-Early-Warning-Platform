"""initial PostGIS schema (Track B) — mirrors schema_sqlite.sql

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-06

Creates the same 8 core tables as the portable SQLite schema, with real PostGIS
geometry columns + GiST spatial indexes instead of GeoJSON-text + bbox. Enable
the postgis extension first (env.py also does this defensively).

STATUS: skeleton — pending local run against a PostGIS instance.
"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")

    op.create_table(
        "locations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ext_code", sa.String, unique=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("level", sa.String, nullable=False),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("locations.id")),
        sa.Column("state", sa.String), sa.Column("district", sa.String),
        sa.Column("block", sa.String), sa.Column("village", sa.String),
        sa.Column("latitude", sa.Float), sa.Column("longitude", sa.Float),
        sa.Column("geom", Geometry(geometry_type="GEOMETRY", srid=4326,
                                    spatial_index=False)),
        sa.Column("is_synthetic", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_locations_level", "locations", ["level"])
    op.create_index("ix_locations_parent", "locations", ["parent_id"])
    op.create_index("ix_locations_geom", "locations", ["geom"],
                    postgresql_using="gist")

    op.create_table(
        "terrain_features",
        sa.Column("location_id", sa.Integer,
                  sa.ForeignKey("locations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("elevation", sa.Float), sa.Column("slope", sa.Float),
        sa.Column("aspect", sa.Float), sa.Column("curvature", sa.Float),
        sa.Column("flow_accumulation", sa.Float),
        sa.Column("drainage_density", sa.Float),
        sa.Column("distance_to_drainage", sa.Float),
        sa.Column("relative_relief", sa.Float),
        sa.Column("is_synthetic", sa.Integer, nullable=False, server_default="0"),
        sa.Column("source", sa.String),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # NOTE: the constraint name MUST match the name referenced by
    # models_orm.py and repositories_prod.py's `ON CONFLICT ON CONSTRAINT ...`
    # (uq_rain_natural / uq_soil_natural) — NOT a name derived from the table
    # name, or every rainfall/soil upsert would raise on first seed/replay.
    for tbl, uq_name, extra in (("rainfall_observations", "uq_rain_natural",
                        [sa.Column("rainfall_30m", sa.Float),
                         sa.Column("rainfall_3h", sa.Float),
                         sa.Column("rainfall_24h", sa.Float),
                         sa.Column("resolution_m", sa.Float)]),
                       ("soil_moisture_observations", "uq_soil_natural",
                        [sa.Column("surface_moisture", sa.Float),
                         sa.Column("root_zone_moisture", sa.Float),
                         sa.Column("resolution_m", sa.Float)])):
        op.create_table(
            tbl,
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("source", sa.String, nullable=False),
            sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
            sa.Column("latitude", sa.Float, nullable=False),
            sa.Column("longitude", sa.Float, nullable=False),
            sa.Column("geom", Geometry(geometry_type="POINT", srid=4326,
                                       spatial_index=False)),
            *extra,
            sa.Column("quality_flag", sa.String, nullable=False, server_default="GOOD"),
            sa.Column("realtime_class", sa.String),
            sa.Column("ingested_at", sa.DateTime(timezone=True),
                      server_default=sa.func.now()),
            sa.UniqueConstraint("source", "ts", "latitude", "longitude",
                                name=uq_name),
        )
        op.create_index(f"ix_{tbl}_ts", tbl, ["ts"])
        op.create_index(f"ix_{tbl}_geom", tbl, ["geom"], postgresql_using="gist")

    op.create_table(
        "river_observations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("station_id", sa.String),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Float), sa.Column("longitude", sa.Float),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326,
                                   spatial_index=False)),
        sa.Column("water_level", sa.Float), sa.Column("flow", sa.Float),
        sa.Column("rate_of_rise", sa.Float),
        sa.Column("quality_flag", sa.String, nullable=False, server_default="GOOD"),
        sa.Column("realtime_class", sa.String),
        sa.Column("ingested_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("source", "station_id", "ts", name="uq_river_natural"),
    )
    op.create_index("ix_river_ts", "river_observations", ["ts"])
    op.create_index("ix_river_geom", "river_observations", ["geom"],
                    postgresql_using="gist")

    op.create_table(
        "landslide_data",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True)),
        sa.Column("latitude", sa.Float), sa.Column("longitude", sa.Float),
        sa.Column("geom", Geometry(geometry_type="GEOMETRY", srid=4326,
                                   spatial_index=False)),
        sa.Column("susceptibility", sa.Float),
        sa.Column("impact_probability", sa.Float), sa.Column("severity", sa.String),
        sa.Column("is_synthetic", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ingested_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_landslide_geom", "landslide_data", ["geom"],
                    postgresql_using="gist")

    op.create_table(
        "iot_observations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sensor_id", sa.String, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latitude", sa.Float), sa.Column("longitude", sa.Float),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326,
                                   spatial_index=False)),
        sa.Column("rainfall", sa.Float), sa.Column("soil_moisture", sa.Float),
        sa.Column("water_level", sa.Float), sa.Column("temperature", sa.Float),
        sa.Column("quality_flag", sa.String, nullable=False, server_default="GOOD"),
        sa.Column("is_simulated", sa.Integer, nullable=False, server_default="1"),
        sa.Column("ingested_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("sensor_id", "ts", name="uq_iot_natural"),
    )
    op.create_index("ix_iot_ts", "iot_observations", ["ts"])

    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("location_id", sa.Integer,
                  sa.ForeignKey("locations.id", ondelete="CASCADE")),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon", sa.String, nullable=False, server_default="now"),
        sa.Column("flood_probability", sa.Float),
        sa.Column("landslide_probability", sa.Float),
        sa.Column("risk_level", sa.String), sa.Column("confidence", sa.Float),
        sa.Column("lead_time_min_lo", sa.Integer),
        sa.Column("lead_time_min_hi", sa.Integer),
        sa.Column("data_completeness", sa.Float),
        sa.Column("top_factors", sa.Text), sa.Column("model_version", sa.String),
        sa.Column("mode", sa.String),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_pred_loc", "predictions", ["location_id"])
    op.create_index("ix_pred_ts", "predictions", ["ts"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("location_id", sa.Integer,
                  sa.ForeignKey("locations.id", ondelete="CASCADE")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("severity", sa.String, nullable=False),
        sa.Column("hazard_type", sa.String, nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("prediction_id", sa.Integer, sa.ForeignKey("predictions.id")),
        sa.Column("status", sa.String, nullable=False, server_default="active"),
        sa.Column("mode", sa.String),
    )
    op.create_index("ix_alert_loc", "alerts", ["location_id"])

    op.create_table(
        "source_health",
        sa.Column("source", sa.String, primary_key=True),
        sa.Column("status", sa.String, nullable=False, server_default="unknown"),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("last_latency_ms", sa.Integer),
        sa.Column("last_error", sa.Text),
        sa.Column("records_last_run", sa.Integer),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # Operational logs written by collectors/base.py through the DAL. These
    # mirror schema_sqlite.sql; without them, the replay run's per-source
    # health/ingestion/quality writes raise "relation does not exist" on boot.
    op.create_table(
        "ingestion_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String),
        sa.Column("records_received", sa.Integer, server_default="0"),
        sa.Column("records_stored", sa.Integer, server_default="0"),
        sa.Column("records_rejected", sa.Integer, server_default="0"),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("error", sa.Text),
    )
    op.create_index("ix_inglog_source", "ingestion_log", ["source"])

    op.create_table(
        "data_quality_flags",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("table_name", sa.String, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True)),
        sa.Column("flag", sa.String, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_dq_source", "data_quality_flags", ["source"])


def downgrade() -> None:
    for t in ("data_quality_flags", "ingestion_log", "alerts", "predictions",
              "iot_observations", "landslide_data", "river_observations",
              "soil_moisture_observations", "rainfall_observations",
              "terrain_features", "source_health", "locations"):
        op.drop_table(t)
