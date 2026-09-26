"""mosdac_discovery table (Track B) — ISRO MOSDAC INSAT granule-discovery records

Revision ID: 0005_mosdac_discovery
Revises: 0004_imd_observations
Create Date: 2026-09-06

Adds the mosdac_discovery table that stores ISRO MOSDAC INSAT precipitation
granule-discovery records (granule metadata + a documented mdapi download URL),
which are NOT numeric rainfall observations. This table is deliberately NOT read
by the ML feature pipeline, so a discovery record (numeric_value NULL) can never
masquerade as a numeric rainfall observation. A real mm value only enters
rainfall_observations after a gated raster/HDF-parse stage.

Mirrors the mosdac_discovery block added to schema_sqlite.sql (Track A parity)
and the MosdacDiscovery ORM model. Verified source spec: the documented MOSDAC
mdapi search/download workflow (app/data_layer/sources/mosdac/docs/
mosdac_verified.md) — "raw satellite files parsed by separate product parser;
ML must consume normalized values from the internal database, never call MOSDAC
directly."

STATUS: skeleton — pending local run against a PostGIS instance.
"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

revision = "0005_mosdac_discovery"
down_revision = "0004_imd_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mosdac_discovery",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String, nullable=False, server_default="mosdac"),
        sa.Column("dataset_id", sa.String),
        sa.Column("satellite", sa.String),
        sa.Column("product", sa.String),
        sa.Column("observed_date", sa.String),
        sa.Column("end_time", sa.String),
        sa.Column("latitude", sa.Float),
        sa.Column("longitude", sa.Float),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326,
                                   spatial_index=False)),
        sa.Column("resolution", sa.String),
        sa.Column("download_url", sa.Text),
        sa.Column("granule_id", sa.String),
        # ALWAYS NULL at discovery; set only after the gated raster/HDF-parse stage.
        sa.Column("numeric_value", sa.Float),
        sa.Column("quality_flag", sa.String, server_default="UNKNOWN"),
        # Observation-stage flag (DISCOVERY_ONLY | RASTER_SAMPLED), NOT a source
        # health status — the 7 SourceStatus states are unchanged.
        sa.Column("stage", sa.String, nullable=False,
                  server_default="DISCOVERY_ONLY"),
        sa.Column("raw_reference", sa.Text),
        sa.Column("retrieved_at", sa.DateTime(timezone=True)),
        sa.Column("ingested_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("dataset_id", "granule_id", "download_url",
                            name="uq_mosdacdisc_natural"),
    )
    op.create_index("ix_mosdacdisc_date", "mosdac_discovery", ["observed_date"])
    op.create_index("ix_mosdacdisc_dataset", "mosdac_discovery", ["dataset_id"])
    op.create_index("ix_mosdacdisc_geom", "mosdac_discovery", ["geom"],
                    postgresql_using="gist")


def downgrade() -> None:
    op.drop_table("mosdac_discovery")
