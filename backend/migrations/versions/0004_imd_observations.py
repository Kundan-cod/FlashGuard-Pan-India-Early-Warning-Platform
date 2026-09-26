"""imd_observations table (Track B) — India Meteorological Department records

Revision ID: 0004_imd_observations
Revises: 0003_smap_discovery
Create Date: 2026-09-06

Adds the imd_observations table for India Meteorological Department
(api.imd.gov.in/api/v1) data: current weather, district rainfall, district
warnings and nowcasts. Unlike gpm_discovery/smap_discovery, IMD returns REAL
numeric values — but at DISTRICT or STATION granularity and WITHOUT coordinates
(verified spec app/data_layer/sources/imd/docs/imd_verified.md). It is kept out
of rainfall_observations (a point table the ML feature pipeline reads as
village-level rainfall) so a district figure can never masquerade as a village
value. IMD codes/colors are stored verbatim and never converted to an ML
probability. A separate, explicit district-polygon -> village spatial join would
be required before an IMD value could inform a village prediction; that join is
deliberately not performed at ingestion.

Mirrors the imd_observations block in schema_sqlite.sql (Track A parity) and the
ImdObservation ORM model.

STATUS: skeleton — pending local run against a PostGIS instance.
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_imd_observations"
down_revision = "0003_smap_discovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "imd_observations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String, nullable=False, server_default="imd"),
        sa.Column("record_type", sa.String, nullable=False),
        sa.Column("area_kind", sa.String),
        sa.Column("area_id", sa.String),
        sa.Column("area_name", sa.String),
        sa.Column("observed_at", sa.String),
        sa.Column("valid_upto", sa.String),
        sa.Column("temperature_c", sa.Float),
        sa.Column("humidity_pct", sa.Float),
        sa.Column("wind_speed_kmph", sa.Float),
        sa.Column("pressure_hpa", sa.Float),
        sa.Column("rainfall_24h_mm", sa.Float),
        sa.Column("daily_actual_mm", sa.Float),
        sa.Column("daily_normal_mm", sa.Float),
        sa.Column("cumulative_actual_mm", sa.Float),
        sa.Column("cumulative_normal_mm", sa.Float),
        sa.Column("rainfall_category", sa.String),
        sa.Column("warning_code", sa.String),
        sa.Column("warning_color", sa.Integer),
        sa.Column("warning_day", sa.Integer),
        sa.Column("message", sa.Text),
        sa.Column("quality_flag", sa.String, nullable=False,
                  server_default="GOOD"),
        sa.Column("realtime_class", sa.String),
        sa.Column("raw_reference", sa.Text),
        sa.Column("retrieved_at", sa.DateTime(timezone=True)),
        sa.Column("ingested_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("source", "record_type", "area_id", "observed_at",
                            "warning_day", name="uq_imd_natural"),
    )
    op.create_index("ix_imd_type", "imd_observations", ["record_type"])
    op.create_index("ix_imd_area", "imd_observations", ["area_id"])


def downgrade() -> None:
    op.drop_table("imd_observations")
