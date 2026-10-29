"""Индексы внешних ключей для проверки связей и удаления справочников."""

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_rooms_building_id", "rooms", ["building_id"])
    op.create_index("ix_rooms_department_id", "rooms", ["department_id"])
