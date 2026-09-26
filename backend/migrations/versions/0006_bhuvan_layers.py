"""bhuvan_layers table (Track B) — Bhuvan/NRSC OGC layer-catalog records

Revision ID: 0006_bhuvan_layers
Revises: 0005_mosdac_discovery
Create Date: 2026-09-06

Adds the bhuvan_layers table that catalogs verified Bhuvan/NRSC OGC WMS/WMTS
layer endpoints + roles (CartoDEM, LULC, geomorphology, lineament, flood-hazard/
annual layers). These are metadata, NOT numeric terrain values. The verified note
(app/data_layer/sources/bhuvan_nrsc/docs/bhuvan_verified.md) is explicit that
rendered map pixels must never be scraped as a substitute for the DEM, and that
quantitative terrain must be derived from downloaded DEM tiles and preprocessed
once — a stage NOT implemented by the verified package. So this table is a
catalog only; the ML feature pipeline (which reads terrain_features) never reads
it, and a catalog row can never masquerade as a numeric terrain feature. Real
terrain values only enter terrain_features after a gated DEM-tile processing
stage (future work).

Mirrors the bhuvan_layers block added to schema_sqlite.sql (Track A parity) and
the BhuvanLayer ORM model. There is deliberately NO PostGIS geometry column: a
catalog entry describes a service endpoint, not a point observation.

STATUS: skeleton — pending local run against a PostGIS instance.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_bhuvan_layers"
down_revision = "0005_mosdac_discovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bhuvan_layers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String, nullable=False, server_default="bhuvan"),
        sa.Column("layer_key", sa.String, nullable=False),
        sa.Column("service_type", sa.String),
        sa.Column("role", sa.String),
        sa.Column("service_url", sa.Text),
        sa.Column("layer_name", sa.String),
        # Observation-stage flag (CATALOG_ONLY | DEM_PROCESSED), NOT a source
        # health status — the 7 SourceStatus states are unchanged.
        sa.Column("stage", sa.String, nullable=False,
                  server_default="CATALOG_ONLY"),
        sa.Column("raw_reference", sa.Text),
        sa.Column("retrieved_at", sa.DateTime(timezone=True)),
        sa.Column("ingested_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("source", "layer_key", "service_url",
                            name="uq_bhuvanlayer_natural"),
    )
    op.create_index("ix_bhuvanlayer_key", "bhuvan_layers", ["layer_key"])


def downgrade() -> None:
    op.drop_table("bhuvan_layers")
