"""gpm_discovery table (Track B) — GPM PMM dataset-discovery records

Revision ID: 0002_gpm_discovery
Revises: 0001_initial
Create Date: 2026-09-06

Adds the gpm_discovery table that stores NASA GPM PMM Publisher dataset-discovery
records (dataset footprint + download URL), which are NOT numeric rainfall
observations. This table is deliberately NOT read by the ML feature pipeline, so
a discovery record (numeric_value NULL) can never masquerade as rainfall. A real
mm value only enters rainfall_observations after the gated raster-sampling stage.

Mirrors the gpm_discovery block added to schema_sqlite.sql (Track A parity).

STATUS: skeleton — pending local run against a PostGIS instance.
"""
from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry

revision = "0002_gpm_discovery"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gpm_discovery",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String, nullable=False, server_default="gpm"),
        sa.Column("product", sa.String),
        sa.Column("observed_date", sa.String),
        sa.Column("latitude", sa.Float),
        sa.Column("longitude", sa.Float),
        sa.Column("geom", Geometry(geometry_type="POINT", srid=4326,
                                   spatial_index=False)),
        sa.Column("resolution", sa.String),
        sa.Column("download_url", sa.Text),
        sa.Column("media_type", sa.String),
        sa.Column("item_id", sa.String),
        # ALWAYS NULL at discovery; set only after the gated raster-sampling stage.
        sa.Column("numeric_value", sa.Float),
        # Observation-stage flag (DISCOVERY_ONLY | RASTER_SAMPLED), NOT a source
        # health status — the 7 SourceStatus states are unchanged.
        sa.Column("stage", sa.String, nullable=False,
                  server_default="DISCOVERY_ONLY"),
        sa.Column("raw_reference", sa.Text),
        sa.Column("retrieved_at", sa.DateTime(timezone=True)),
        sa.Column("ingested_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("item_id", "download_url", name="uq_gpmdisc_natural"),
    )
    op.create_index("ix_gpmdisc_date", "gpm_discovery", ["observed_date"])
    op.create_index("ix_gpmdisc_geom", "gpm_discovery", ["geom"],
                    postgresql_using="gist")


def downgrade() -> None:
    op.drop_table("gpm_discovery")
