"""lgd_directory table (Track B) — LGD administrative-directory catalog records

Revision ID: 0009_lgd_directory
Revises: 0008_cwc_resources
Create Date: 2026-09-06

Adds the lgd_directory table that catalogs the verified Local Government Directory
(LGD) downloadable directories: districts, sub-districts, development blocks,
villages, PRI local bodies, urban local bodies, wards. These are administrative-
identity/code directory DATASETS, NOT boundary geometry and NOT measurements.

The verified note (app/data_layer/sources/lgd/docs/lgd_verified.md) is explicit
about two honesty-critical boundaries: (1) "Do not assume LGD directory tables are
themselves polygon datasets. Boundary geometry must be sourced from an
authoritative GIS boundary product and versioned separately ... joined using LGD
codes." So this table has NO PostGIS geometry column: an LGD row is an
administrative-code directory entry, not a boundary polygon and not a point
observation. (2) "Use LGD codes as stable join keys. Names are display fields
only ... Never use village/ward names as primary keys because names can repeat or
change." The vendored adapter fetches only the directory download page and "does
not guess file names or fabricate geometry URLs"; it implements no row parser.

So each row records a verified LGD directory dataset (one per administrative
level) + its level + verified purpose + the verified download-portal URL. This
table is a catalog only; the ML feature pipeline never reads it. Real LGD unit
rows (codes+hierarchy) would only enter a separate administrative table after a
gated, verified directory-file parse (future work). Twin of the Bhuvan 0006, GSI
0007 and CWC 0008 migrations.

STATUS: skeleton — pending local run against a PostGIS instance.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_lgd_directory"
down_revision = "0008_cwc_resources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "lgd_directory",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String, nullable=False, server_default="lgd"),
        sa.Column("dataset_key", sa.String, nullable=False),
        sa.Column("admin_level", sa.String),
        sa.Column("purpose", sa.Text),
        sa.Column("directory_url", sa.Text),
        # Observation-stage flag (CATALOG_ONLY | PARSED), NOT a source health
        # status — the 7 SourceStatus states are unchanged.
        sa.Column("stage", sa.String, nullable=False,
                  server_default="CATALOG_ONLY"),
        sa.Column("raw_reference", sa.Text),
        sa.Column("retrieved_at", sa.DateTime(timezone=True)),
        sa.Column("ingested_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("source", "dataset_key", "directory_url",
                            name="uq_lgddirectory_natural"),
    )
    op.create_index("ix_lgddirectory_key", "lgd_directory", ["dataset_key"])


def downgrade() -> None:
    op.drop_table("lgd_directory")
