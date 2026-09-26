"""gsi_layers table (Track B) — GSI/Bhusanket portal layer-catalog records

Revision ID: 0007_gsi_layers
Revises: 0006_bhuvan_layers
Create Date: 2026-09-06

Adds the gsi_layers table that catalogs verified GSI National Landslide
Forecasting Centre (Bhusanket portal) layers + roles + coverage: forecast
bulletin, LSM 10K susceptibility, impact-probability map, field-validated
landslide inventory. These are portal-layer metadata, NOT numeric landslide
values. The verified note (app/data_layer/sources/gsi_bhusanket/docs/
gsi_verified.md) is explicit that this adapter must NOT hard-code an undocumented
JSON API and that GSI forecasting is REGIONAL (Darjeeling/Kalimpong/Nilgiris
operational, others experimental), NOT a nationwide live API — so each layer
carries a geographic_scope coverage note. This table is a catalog only; the ML
landslide model reads landslide_data (its own susceptibility/impact_probability)
and never reads gsi_layers, so a catalog row can never masquerade as a landslide
value. Real GSI inventory/bulletin values would only enter after a separate,
gated, verified parse of a specific documented public resource (future work).

Mirrors the gsi_layers block added to schema_sqlite.sql (Track A parity) and the
GsiLayer ORM model. There is deliberately NO PostGIS geometry column: a catalog
entry describes a portal layer, not a point observation. Twin of the Bhuvan
0006 migration.

STATUS: skeleton — pending local run against a PostGIS instance.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_gsi_layers"
down_revision = "0006_bhuvan_layers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gsi_layers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String, nullable=False, server_default="gsi"),
        sa.Column("layer_key", sa.String, nullable=False),
        sa.Column("role", sa.String),
        sa.Column("service_url", sa.Text),
        sa.Column("geographic_scope", sa.Text),
        sa.Column("public", sa.Integer, nullable=False, server_default="1"),
        # Observation-stage flag (CATALOG_ONLY | PARSED), NOT a source health
        # status — the 7 SourceStatus states are unchanged.
        sa.Column("stage", sa.String, nullable=False,
                  server_default="CATALOG_ONLY"),
        sa.Column("raw_reference", sa.Text),
        sa.Column("retrieved_at", sa.DateTime(timezone=True)),
        sa.Column("ingested_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("source", "layer_key", "service_url",
                            name="uq_gsilayer_natural"),
    )
    op.create_index("ix_gsilayer_key", "gsi_layers", ["layer_key"])


def downgrade() -> None:
    op.drop_table("gsi_layers")
