"""smap_discovery table (Track B) — NASA SMAP CMR granule-discovery records

Revision ID: 0003_smap_discovery
Revises: 0002_gpm_discovery
Create Date: 2026-09-06

Adds the smap_discovery table that stores NASA SMAP L4 CMR granule-discovery
records (granule footprint + documented GET DATA URL), which are NOT numeric
soil-moisture observations. This table is deliberately NOT read by the ML
feature pipeline, so a discovery record (surface_sm / rootzone_sm NULL) can
never masquerade as a soil-moisture measurement. A real m3/m3 value only enters
soil_moisture_observations after a gated HDF5/NetCDF parse stage.

Mirrors the smap_discovery block added to schema_sqlite.sql (Track A parity) and
the SmapDiscovery ORM model. Verified source spec: NASA/NSIDC SMAP L4 V008 via
CMR granule search (app/data_layer/sources/smap/docs/smap_verified.md).

STATUS: skeleton — pending local run against a PostGIS instance.
"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

revision = "0003_smap_discovery"
down_revision = "0002_gpm_discovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "smap_discovery",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String, nullable=False, server_default="smap"),
        sa.Column("product", sa.String),
        sa.Column("version", sa.String),
        sa.Column("observed_date", sa.String),
        sa.Column("end_time", sa.String),
        sa.Column("latitude", sa.Float),
        sa.Column("longitude", sa.Float),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326,
                                   spatial_index=False)),
        sa.Column("grid", sa.String),
        sa.Column("download_url", sa.Text),
        sa.Column("concept_id", sa.String),
        sa.Column("producer_granule_id", sa.String),
        # ALWAYS NULL at discovery; set only after the gated HDF5/NetCDF parse stage.
        sa.Column("surface_sm", sa.Float),
        sa.Column("rootzone_sm", sa.Float),
        sa.Column("quality_flag", sa.String, server_default="UNKNOWN"),
        # Observation-stage flag (DISCOVERY_ONLY | RASTER_SAMPLED), NOT a source
        # health status — the 7 SourceStatus states are unchanged.
        sa.Column("stage", sa.String, nullable=False,
                  server_default="DISCOVERY_ONLY"),
        sa.Column("raw_reference", sa.Text),
        sa.Column("retrieved_at", sa.DateTime(timezone=True)),
        sa.Column("ingested_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("concept_id", "download_url",
                            name="uq_smapdisc_natural"),
    )
    op.create_index("ix_smapdisc_date", "smap_discovery", ["observed_date"])
    op.create_index("ix_smapdisc_geom", "smap_discovery", ["geom"],
                    postgresql_using="gist")


def downgrade() -> None:
    op.drop_table("smap_discovery")
