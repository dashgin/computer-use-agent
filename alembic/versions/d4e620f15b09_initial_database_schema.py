"""Initial database schema

Revision ID: d4e620f15b09
Revises:
Create Date: 2025-07-25 22:17:57.434495

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e620f15b09"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create sessions table
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("status", sa.String(), server_default="active", nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("session_metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create messages table
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(), server_default="text", nullable=False),
        sa.Column("tool_use_id", sa.String(), nullable=True),
        sa.Column(
            "timestamp",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("message_metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create tool_executions table
    op.create_table(
        "tool_executions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("tool_input", sa.JSON(), nullable=False),
        sa.Column("tool_output", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("tool_executions")
    op.drop_table("messages")
    op.drop_table("sessions")
