"""BLE scale provenance; weight stays in the existing body history."""

import sqlalchemy as sa

from alembic import op

revision = "20261018_0013"
down_revision = "20261017_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Local bootstrap uses create_all; tolerate a table already created there.
    if sa.inspect(op.get_bind()).has_table("scale_readings"):
        return
    op.create_table(
        "scale_readings",
        sa.Column("measurement_id", sa.Integer(), sa.ForeignKey("body_measurements.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("device_id", sa.String(128), nullable=False),
        sa.Column("measurement_key", sa.String(64), nullable=False),
        sa.Column("impedance_ohm", sa.Integer(), nullable=True),
        sa.UniqueConstraint("device_id", "measurement_key", name="uq_scale_reading_packet"),
    )
    op.create_index("ix_scale_readings_device_id", "scale_readings", ["device_id"])


def downgrade() -> None:
    op.drop_table("scale_readings")