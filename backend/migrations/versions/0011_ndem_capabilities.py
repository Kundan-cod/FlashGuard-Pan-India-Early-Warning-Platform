"""ndem_capabilities table (Track B) — NDEM capability/access catalog records

Revision ID: 0011_ndem_capabilities
Revises: 0010_historical_sources
Create Date: 2026-09-06

Adds the ndem_capabilities table that catalogs the verified capabilities of NDEM
(National Database for Emergency Management) — an NRSC/ISRO national GIS repository
+ DSS for disaster management, executed with MHA for near-real-time disaster
support (near-real-time flood monitoring, flood early warning/vulnerability,
landslide hazard inventory, district nowcast aggregation, historical flood
reference).

The verified note (app/data_layer/sources/ndem/docs/ndem_verified.md) is explicit
on the honesty-critical points: (1) NDEM's non-base products are PROTECTED — the
portal requires a username/password obtained through an authorization form, and the
authorized users are Central/State/District/NDRF/SDRF officials; only public/base
layers may be visible without login. (2) The engineering decision is that the MVP
must NOT depend on NDEM credentials, must "never bypass authentication or invent an
undocumented API", and must "store access_level and source-health separately from
risk score." The vendored package therefore implements ONLY public-portal discovery
plus a capability/access registry — no private endpoints, no product parser.

So each row records a verified NDEM CAPABILITY + its access level (PUBLIC |
AUTHORIZED | AUTHORIZED_OR_PRODUCT_SPECIFIC, verbatim) + role + the verified portal
URL. This table carries NO measurement, NO geometry, NO event and NO risk score — it
is a catalog only. Real NDEM products would only enter observation/event tables
after a future AUTHORIZED, gated adapter behind the same interface — a stage
deliberately NOT performed here. Twin of the GSI 0007 / LGD 0009 migrations (one
shared portal URL for every capability, so capability_key keeps rows distinct). No
PostGIS geometry: a capability-catalog row is not a polygon.

STATUS: skeleton — pending local run against a PostGIS instance.
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_ndem_capabilities"
down_revision = "0010_historical_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ndem_capabilities",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String, nullable=False,
                  server_default="ndem"),
        sa.Column("capability_key", sa.String, nullable=False),
        sa.Column("access", sa.String),
        sa.Column("role", sa.String),
        sa.Column("source_url", sa.Text),
        # Observation-stage flag (CATALOG_ONLY | PARSED), NOT a source health
        # status — the 7 SourceStatus states are unchanged.
        sa.Column("stage", sa.String, nullable=False,
                  server_default="CATALOG_ONLY"),
        sa.Column("raw_reference", sa.Text),
        sa.Column("retrieved_at", sa.DateTime(timezone=True)),
        sa.Column("ingested_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("source", "capability_key", "source_url",
                            name="uq_ndemcap_natural"),
    )
    op.create_index("ix_ndemcap_key", "ndem_capabilities", ["capability_key"])


def downgrade() -> None:
    op.drop_table("ndem_capabilities")
