"""Add granule_id and units to rainfall_observations (Track B) — SIH 26192

Revision ID: 0013_rainfall_granule_provenance
Revises: 0012_evacuation_alerts
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_rainfall_granule_provenance"
down_revision = "0012_evacuation_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rainfall_observations",
        sa.Column("granule_id", sa.String, nullable=True)
    )
    op.add_column(
        "rainfall_observations",
        sa.Column("units", sa.String, nullable=True, server_default="mm")
    )


def downgrade() -> None:
    op.drop_column("rainfall_observations", "units")
    op.drop_column("rainfall_observations", "granule_id")
