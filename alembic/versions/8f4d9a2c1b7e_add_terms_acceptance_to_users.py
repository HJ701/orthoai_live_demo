"""add_terms_acceptance_to_users

Revision ID: 8f4d9a2c1b7e
Revises: 3279515f6aee
Create Date: 2026-05-28 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8f4d9a2c1b7e"
down_revision = "3279515f6aee"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "terms_accepted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users",
        sa.Column("terms_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("users", "terms_accepted", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "terms_accepted_at")
    op.drop_column("users", "terms_accepted")
