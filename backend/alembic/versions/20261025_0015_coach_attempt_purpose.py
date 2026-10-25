"""V0: budget bucket (purpose) on Coach attempts; existing rows are live speech."""

from alembic import op
from app.services.coach.schema import ATTEMPT_BUDGET_COLUMNS, ensure_columns

revision = "20261025_0015"
down_revision = "20261024_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    ensure_columns(op.get_bind(), ATTEMPT_BUDGET_COLUMNS)


def downgrade() -> None:
    op.drop_column("coach_attempts", "purpose")
