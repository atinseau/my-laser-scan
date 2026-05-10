"""initial schema — projects + segments

Revision ID: 0001
Revises:
Create Date: 2026-05-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("kind", sa.String(length=16), nullable=True),
        sa.Column("origin_lat", sa.Float, nullable=True),
        sa.Column("origin_lon", sa.Float, nullable=True),
        sa.Column("origin_alt", sa.Float, nullable=True),
        sa.Column("current_workflow_id", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=False, server_default=""),
        sa.Column("metadata_json", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "segments",
        sa.Column("id", sa.String(length=26), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(length=26),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_s", sa.Float, nullable=False),
        sa.Column("fps", sa.Float, nullable=False, server_default="0"),
        sa.Column("width", sa.Integer, nullable=False, server_default="0"),
        sa.Column("height", sa.Integer, nullable=False, server_default="0"),
        sa.Column("has_lidar", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("raw_paths", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("notes", sa.String(length=2000), nullable=False, server_default=""),
        sa.Column("metadata_json", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("segments")
    op.drop_table("projects")
