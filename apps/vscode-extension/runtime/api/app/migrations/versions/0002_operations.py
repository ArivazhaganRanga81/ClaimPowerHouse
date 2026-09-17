"""Add operational authentication, RAG, import, LLM, and backup tables.

Revision ID: 0002_operations
Revises: 0001_initial
"""
from __future__ import annotations

from alembic import op

from app import models  # noqa: F401
from app.database import Base


revision = "0002_operations"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    # Operational data is intentionally retained on downgrade. Forward migrations are authoritative.
    pass
