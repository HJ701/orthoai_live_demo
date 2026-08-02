"""Add traceable repeat attempts to research episodes.

Revision ID: d7e2f8a19c44
Revises: c4f39d8a10b2
Create Date: 2026-07-28 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "d7e2f8a19c44"
down_revision = "c4f39d8a10b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("research_episodes") as batch_op:
        batch_op.add_column(
            sa.Column(
                "attempt_index",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch_op.add_column(
            sa.Column("repeat_of_episode_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_research_episode_repeat_of",
            "research_episodes",
            ["repeat_of_episode_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.drop_constraint(
            "uq_research_episode_study_participant_case",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_research_episode_study_participant_case_attempt",
            ["study_id", "participant_id", "case_id", "attempt_index"],
        )
        batch_op.create_check_constraint(
            "ck_research_episode_attempt",
            "attempt_index >= 1",
        )
        batch_op.create_index(
            "ix_research_episodes_repeat_of_episode_id",
            ["repeat_of_episode_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("research_episodes") as batch_op:
        batch_op.drop_index("ix_research_episodes_repeat_of_episode_id")
        batch_op.drop_constraint(
            "ck_research_episode_attempt",
            type_="check",
        )
        batch_op.drop_constraint(
            "uq_research_episode_study_participant_case_attempt",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_research_episode_study_participant_case",
            ["study_id", "participant_id", "case_id"],
        )
        batch_op.drop_constraint(
            "fk_research_episode_repeat_of",
            type_="foreignkey",
        )
        batch_op.drop_column("repeat_of_episode_id")
        batch_op.drop_column("attempt_index")
