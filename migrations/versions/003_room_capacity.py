"""Вместимость помещения: старые записи получают одно место."""

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE rooms ADD COLUMN capacity INTEGER NOT NULL DEFAULT 1 "
        "CHECK (capacity BETWEEN 1 AND 1000)"
    )
