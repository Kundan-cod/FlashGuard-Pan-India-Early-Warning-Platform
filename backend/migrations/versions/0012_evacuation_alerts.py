"""evacuation_centres, alert_recipients, and alerts table extensions (Track B) — SIH 26192

Revision ID: 0012_evacuation_alerts
Revises: 0011_ndem_capabilities
Create Date: 2026-09-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_evacuation_alerts"
down_revision = "0011_ndem_capabilities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. evacuation_centres
    op.create_table(
        "evacuation_centres",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("address", sa.String),
        sa.Column("village", sa.String, nullable=False),
        sa.Column("ward", sa.String),
        sa.Column("district", sa.String, nullable=False),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("capacity", sa.Integer, nullable=False, server_default="100"),
        sa.Column("contact_number", sa.String),
        sa.Column("accessibility", sa.String),
        sa.Column("verified", sa.Integer, nullable=False, server_default="1"),
        sa.Column("active", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_demo", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_evac_village", "evacuation_centres", ["village"])
    op.create_index("ix_evac_district", "evacuation_centres", ["district"])

    # 2. alert_recipients
    op.create_table(
        "alert_recipients",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("phone_number", sa.String, nullable=False),
        sa.Column("village", sa.String, nullable=False),
        sa.Column("ward", sa.String),
        sa.Column("district", sa.String, nullable=False),
        sa.Column("preferred_language", sa.String, nullable=False, server_default="en"),
        sa.Column("active", sa.Integer, nullable=False, server_default="1"),
        sa.Column("emergency_notification_enabled", sa.Integer, nullable=False, server_default="1"),
        sa.Column("is_demo", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_recip_village", "alert_recipients", ["village"])

    # 3. alerts table extensions
    op.add_column("alerts", sa.Column("risk_level", sa.String))
    op.add_column("alerts", sa.Column("risk_probability", sa.Float))
    op.add_column("alerts", sa.Column("lead_time_window", sa.String))
    op.add_column("alerts", sa.Column("evacuation_centre_id", sa.Integer, sa.ForeignKey("evacuation_centres.id", ondelete="SET NULL")))
    op.add_column("alerts", sa.Column("evacuation_guidance", sa.Text))
    op.add_column("alerts", sa.Column("recipient_count", sa.Integer, server_default="0"))
    op.add_column("alerts", sa.Column("sms_status", sa.String, server_default="PENDING"))
    op.add_column("alerts", sa.Column("push_status", sa.String, server_default="PENDING"))
    op.add_column("alerts", sa.Column("fingerprint", sa.String))
    op.add_column("alerts", sa.Column("dispatched_at", sa.DateTime(timezone=True)))
    op.create_index("ix_alert_fingerprint", "alerts", ["fingerprint"])


def downgrade() -> None:
    op.drop_index("ix_alert_fingerprint", table_name="alerts")
    op.drop_column("alerts", "dispatched_at")
    op.drop_column("alerts", "fingerprint")
    op.drop_column("alerts", "push_status")
    op.drop_column("alerts", "sms_status")
    op.drop_column("alerts", "recipient_count")
    op.drop_column("alerts", "evacuation_guidance")
    op.drop_column("alerts", "evacuation_centre_id")
    op.drop_column("alerts", "lead_time_window")
    op.drop_column("alerts", "risk_probability")
    op.drop_column("alerts", "risk_level")

    op.drop_table("alert_recipients")
    op.drop_table("evacuation_centres")
