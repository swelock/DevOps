"""Исходная схема ЛР1/ЛР2; безопасное подключение уже заполненной БД."""

from pathlib import Path

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    root = Path(__file__).resolve().parents[2]
    # Старые SQL-схемы остаются неизменным снимком исходного состояния.
    path = root / (
        "campus/schema.sql"
        if op.get_bind().dialect.name == "sqlite"
        else "deploy/postgresql/schema.sql"
    )
    for statement in path.read_text().split(";"):
        if statement.strip() and not statement.strip().startswith("PRAGMA"):
            op.execute(statement)
