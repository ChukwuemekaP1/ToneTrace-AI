"""create system audit log table

Revision ID: d4fb69f808c5
Revises:
Create Date: 2026-10-26 23:28:04.101324

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4fb69f808c5"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_audit_logs",
        sa.Column(
            "event_name",
            sa.String(length=100),
            nullable=False,
            comment="Categorical name of the lifecycle event",
        ),
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            comment="Subsystem emitting the event",
        ),
        sa.Column(
            "details",
            sa.Text(),
            nullable=True,
            comment="Sanitized diagnostic context or description",
        ),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_system_audit_logs_event_name"),
        "system_audit_logs",
        ["event_name"],
        unique=False,
    )
    op.create_index(
        "ix_system_audit_logs_event_name_created_at",
        "system_audit_logs",
        ["event_name", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_system_audit_logs_source"),
        "system_audit_logs",
        ["source"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_system_audit_logs_source"), table_name="system_audit_logs")
    op.drop_index(
        "ix_system_audit_logs_event_name_created_at",
        table_name="system_audit_logs",
    )
    op.drop_index(op.f("ix_system_audit_logs_event_name"), table_name="system_audit_logs")
    op.drop_table("system_audit_logs")
