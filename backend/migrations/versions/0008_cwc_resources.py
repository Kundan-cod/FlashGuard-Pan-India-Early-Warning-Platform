"""cwc_resources table (Track B) — CWC/NWIC NWDP dataset-catalog records

Revision ID: 0008_cwc_resources
Revises: 0007_gsi_layers
Create Date: 2026-09-06

Adds the cwc_resources table that catalogs verified CWC/NWIC National Water Data
Portal (NWDP) dataset pages + roles + advertised resource formats: river water
level (telemetry hourly), rainfall (telemetry hourly), reservoir water storage
(manual daily). These are dataset-page metadata, NOT numeric hydrological values.
The verified note (app/data_layer/sources/cwc_nwic/docs/cwc_nwic_verified.md) is
explicit that this package "intentionally does not invent an undocumented API
URL", that the portal only advertises API as a data format ("the exact API
endpoint/auth contract was not verified in this pass"), and that we must not claim
every station is live or every API anonymous. So each row records the verified
NWDP dataset-page URL + advertised format + cadence only.

This table is a catalog only; the ML feature pipeline reads river_observations /
rainfall_observations (its own numeric values) and never reads cwc_resources, so
a catalog row can never masquerade as a hydrological value. Real CWC values would
only enter those observation tables after a separate, gated, verified CSV/API
parse of a specific dataset resource (future work).

Mirrors the cwc_resources block added to schema_sqlite.sql (Track A parity) and
the CwcResource ORM model. There is deliberately NO PostGIS geometry column: a
catalog entry describes a dataset page, not a point observation. Twin of the
Bhuvan 0006 and GSI 0007 migrations.

STATUS: skeleton — pending local run against a PostGIS instance.
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_cwc_resources"
down_revision = "0007_gsi_layers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cwc_resources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String, nullable=False, server_default="cwc"),
        sa.Column("dataset_key", sa.String, nullable=False),
        sa.Column("role", sa.String),
        sa.Column("dataset_url", sa.Text),
        sa.Column("resource_format", sa.String),
        sa.Column("frequency", sa.String),
        # Observation-stage flag (CATALOG_ONLY | PARSED), NOT a source health
        # status — the 7 SourceStatus states are unchanged.
        sa.Column("stage", sa.String, nullable=False,
                  server_default="CATALOG_ONLY"),
        sa.Column("raw_reference", sa.Text),
        sa.Column("retrieved_at", sa.DateTime(timezone=True)),
        sa.Column("ingested_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("source", "dataset_key", "dataset_url",
                            name="uq_cwcresource_natural"),
    )
    op.create_index("ix_cwcresource_key", "cwc_resources", ["dataset_key"])


def downgrade() -> None:
    op.drop_table("cwc_resources")
