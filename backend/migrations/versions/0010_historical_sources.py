"""historical_sources table (Track B) — historical-label SOURCE catalog records

Revision ID: 0010_historical_sources
Revises: 0009_lgd_directory
Create Date: 2026-09-06

Adds the historical_sources table that catalogs the verified official sources of
historical flood / landslide events used for model training and replay validation:
the NRSC/ISRO Landslide Atlas (~80,000 landslides mapped 1998-2022 across 17 states
+ 2 UTs), NRSC flood-hazard zonation, the Bhuvan historical flood-inundation
service (1998-2019 maximum-inundation layers), and NDEM disaster-specific
historical data (1999-present, portal/auth dependent).

The verified note (app/data_layer/sources/historical/docs/historical_labels_verified.md)
is explicit on the honesty-critical points: (1) these are AUTHORITATIVE EVENT
inventories, NOT complete presence/absence censuses — "do not interpret the
inventory as a complete nationwide absence/presence census" and "do not convert
missing observations into negatives"; (2) the labeling rule is three-state
(1=confirmed event, 0=confirmed non-event only where coverage is adequate,
-1=unobserved/unknown) so the model never learns "no record = no disaster." The
vendored package ships NO event rows and NO parser — only the source registry + the
labeling rule.

So each row records a verified historical-event SOURCE + its hazard + period + role
+ access note. This table carries NO event geometry, NO event time and NO training
label — it is a catalog only. Real event rows and the 1/0/-1 labels derived via the
verified rule would only enter a separate events/labels table after a gated,
verified inventory parse (future work), and the ML training pipeline reads that
table, never this catalog. Twin of the CWC 0008 migration (distinct source_url per
row). No PostGIS geometry: a source-catalog row is not a polygon.

STATUS: skeleton — pending local run against a PostGIS instance.
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_historical_sources"
down_revision = "0009_lgd_directory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "historical_sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String, nullable=False,
                  server_default="historical"),
        sa.Column("source_key", sa.String, nullable=False),
        sa.Column("hazard", sa.String),
        sa.Column("role", sa.String),
        sa.Column("source_url", sa.Text),
        sa.Column("period", sa.Text),
        sa.Column("access_note", sa.Text),
        # Observation-stage flag (CATALOG_ONLY | PARSED), NOT a source health
        # status — the 7 SourceStatus states are unchanged.
        sa.Column("stage", sa.String, nullable=False,
                  server_default="CATALOG_ONLY"),
        sa.Column("raw_reference", sa.Text),
        sa.Column("retrieved_at", sa.DateTime(timezone=True)),
        sa.Column("ingested_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("source", "source_key", "source_url",
                            name="uq_histsource_natural"),
    )
    op.create_index("ix_histsource_key", "historical_sources", ["source_key"])


def downgrade() -> None:
    op.drop_table("historical_sources")
