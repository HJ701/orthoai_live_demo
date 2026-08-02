"""Add Research Mode v3 study instrumentation.

Revision ID: c4f39d8a10b2
Revises: 8f4d9a2c1b7e
Create Date: 2026-07-24 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "c4f39d8a10b2"
down_revision = "8f4d9a2c1b7e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_studies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("protocol_version", sa.String(length=64), nullable=False),
        sa.Column("consent_version", sa.String(length=64), nullable=False),
        sa.Column("primary_task", sa.String(length=128), nullable=False),
        sa.Column("primary_outcome", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column(
            "minimum_reference_reviews",
            sa.Integer(),
            nullable=False,
            server_default="2",
        ),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'paused', 'closed')",
            name="ck_research_study_status",
        ),
        sa.CheckConstraint(
            "minimum_reference_reviews >= 1",
            name="ck_research_study_minimum_reviews",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_research_studies_id", "research_studies", ["id"])
    op.create_index("ix_research_studies_code", "research_studies", ["code"])
    op.create_index("ix_research_studies_status", "research_studies", ["status"])

    op.create_table(
        "research_sites",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("study_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["study_id"],
            ["research_studies.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_id", "code", name="uq_research_site_study_code"),
    )
    op.create_index("ix_research_sites_id", "research_sites", ["id"])
    op.create_index("ix_research_sites_study_id", "research_sites", ["study_id"])

    op.create_table(
        "research_epochs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("study_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("protocol_version", sa.String(length=64), nullable=False),
        sa.Column("task_schema_version", sa.String(length=64), nullable=False),
        sa.Column("ui_version", sa.String(length=64), nullable=False),
        sa.Column("model_version", sa.String(length=255), nullable=False),
        sa.Column("model_artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("deployment_policy_version", sa.String(length=64), nullable=False),
        sa.Column("result_schema_version", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["study_id"],
            ["research_studies.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("study_id", "code", name="uq_research_epoch_study_code"),
    )
    op.create_index("ix_research_epochs_id", "research_epochs", ["id"])
    op.create_index("ix_research_epochs_study_id", "research_epochs", ["study_id"])
    op.create_index("ix_research_epochs_is_active", "research_epochs", ["is_active"])
    op.create_index(
        "uq_research_epoch_one_active_per_study",
        "research_epochs",
        ["study_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
        sqlite_where=sa.text("is_active = 1"),
    )

    op.create_table(
        "research_participants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("study_id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("participant_code", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default="clinician"),
        sa.Column("specialty", sa.String(length=128), nullable=True),
        sa.Column("experience_band", sa.String(length=64), nullable=True),
        sa.Column("consent_version", sa.String(length=64), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("participant_metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["research_sites.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["study_id"],
            ["research_studies.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "role IN ('clinician', 'reviewer', 'adjudicator', 'research_admin')",
            name="ck_research_participant_role",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "study_id",
            "participant_code",
            name="uq_research_participant_study_code",
        ),
        sa.UniqueConstraint(
            "study_id",
            "user_id",
            name="uq_research_participant_study_user",
        ),
    )
    op.create_index("ix_research_participants_id", "research_participants", ["id"])
    op.create_index(
        "ix_research_participants_study_id",
        "research_participants",
        ["study_id"],
    )
    op.create_index(
        "ix_research_participants_site_id",
        "research_participants",
        ["site_id"],
    )
    op.create_index(
        "ix_research_participants_user_id",
        "research_participants",
        ["user_id"],
    )
    op.create_index(
        "ix_research_participants_role",
        "research_participants",
        ["role"],
    )
    op.create_index(
        "ix_research_participants_is_active",
        "research_participants",
        ["is_active"],
    )

    op.create_table(
        "research_episodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("study_id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("epoch_id", sa.Integer(), nullable=False),
        sa.Column("participant_id", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="pre_ai"),
        sa.Column("condition_code", sa.String(length=64), nullable=True),
        sa.Column("client_session_id", sa.String(length=128), nullable=False),
        sa.Column("exposure_index", sa.Integer(), nullable=False),
        sa.Column("pre_ai_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pre_ai_locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_revealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("adjudicated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("protocol_deviation", sa.JSON(), nullable=True),
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
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["epoch_id"],
            ["research_epochs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["research_participants.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["research_sites.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["study_id"],
            ["research_studies.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "exposure_index >= 1",
            name="ck_research_episode_exposure",
        ),
        sa.CheckConstraint(
            "state IN ('pre_ai', 'pre_ai_locked', 'ai_revealed', "
            "'final_locked', 'adjudicated', 'withdrawn')",
            name="ck_research_episode_state",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "study_id",
            "participant_id",
            "case_id",
            name="uq_research_episode_study_participant_case",
        ),
    )
    for column in ("id", "study_id", "site_id", "epoch_id", "participant_id", "case_id", "state"):
        op.create_index(
            f"ix_research_episodes_{column}",
            "research_episodes",
            [column],
        )

    op.create_table(
        "pre_ai_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("task_schema_version", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("client_active_seconds", sa.Float(), nullable=True),
        sa.Column("server_elapsed_seconds", sa.Float(), nullable=False),
        sa.Column("client_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["episode_id"],
            ["research_episodes.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 100",
            name="ck_pre_ai_confidence",
        ),
        sa.CheckConstraint(
            "server_elapsed_seconds >= 0",
            name="ck_pre_ai_server_elapsed",
        ),
        sa.CheckConstraint(
            "client_active_seconds IS NULL OR client_active_seconds >= 0",
            name="ck_pre_ai_client_active",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_id"),
    )
    op.create_index("ix_pre_ai_decisions_id", "pre_ai_decisions", ["id"])
    op.create_index(
        "ix_pre_ai_decisions_episode_id",
        "pre_ai_decisions",
        ["episode_id"],
    )

    op.create_table(
        "ai_reveals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("inference_result_id", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=255), nullable=False),
        sa.Column("model_artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("result_schema_version", sa.String(length=128), nullable=False),
        sa.Column("ui_version", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=True),
        sa.Column("inference_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revealed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["episode_id"],
            ["research_episodes.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["inference_result_id"],
            ["inference_results.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_id"),
    )
    op.create_index("ix_ai_reveals_id", "ai_reveals", ["id"])
    op.create_index("ix_ai_reveals_episode_id", "ai_reveals", ["episode_id"])
    op.create_index(
        "ix_ai_reveals_inference_result_id",
        "ai_reveals",
        ["inference_result_id"],
    )

    op.create_table(
        "final_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("task_schema_version", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("agreement", sa.String(length=32), nullable=True),
        sa.Column("override", sa.Boolean(), nullable=True),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("usefulness", sa.Integer(), nullable=True),
        sa.Column("client_active_seconds", sa.Float(), nullable=True),
        sa.Column("server_elapsed_seconds", sa.Float(), nullable=False),
        sa.Column("client_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["episode_id"],
            ["research_episodes.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 100",
            name="ck_final_decision_confidence",
        ),
        sa.CheckConstraint(
            "server_elapsed_seconds >= 0",
            name="ck_final_decision_server_elapsed",
        ),
        sa.CheckConstraint(
            "client_active_seconds IS NULL OR client_active_seconds >= 0",
            name="ck_final_decision_client_active",
        ),
        sa.CheckConstraint(
            "usefulness IS NULL OR (usefulness >= 1 AND usefulness <= 5)",
            name="ck_final_decision_usefulness",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_id"),
    )
    op.create_index("ix_final_decisions_id", "final_decisions", ["id"])
    op.create_index(
        "ix_final_decisions_episode_id",
        "final_decisions",
        ["episode_id"],
    )

    op.create_table(
        "research_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("participant_id", sa.Integer(), nullable=False),
        sa.Column("event_uuid", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("client_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_timezone_offset_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "server_timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["episode_id"],
            ["research_episodes.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["research_participants.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "sequence_no >= 1",
            name="ck_research_event_sequence",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_uuid"),
        sa.UniqueConstraint(
            "episode_id",
            "sequence_no",
            name="uq_research_event_episode_sequence",
        ),
        sa.UniqueConstraint(
            "episode_id",
            "idempotency_key",
            name="uq_research_event_episode_idempotency",
        ),
    )
    for column in ("id", "episode_id", "participant_id", "event_uuid", "event_type", "server_timestamp"):
        op.create_index(
            f"ix_research_events_{column}",
            "research_events",
            [column],
        )

    op.create_table(
        "study_instruments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("study_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("construct", sa.String(length=128), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("schedule", sa.JSON(), nullable=True),
        sa.Column("scoring_spec", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["study_id"],
            ["research_studies.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "study_id",
            "code",
            "version",
            name="uq_study_instrument_code_version",
        ),
    )
    op.create_index("ix_study_instruments_id", "study_instruments", ["id"])
    op.create_index(
        "ix_study_instruments_study_id",
        "study_instruments",
        ["study_id"],
    )
    op.create_index(
        "ix_study_instruments_is_active",
        "study_instruments",
        ["is_active"],
    )

    op.create_table(
        "survey_responses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("participant_id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=True),
        sa.Column("period_code", sa.String(length=64), nullable=False),
        sa.Column("responses", sa.JSON(), nullable=True),
        sa.Column("completion_status", sa.String(length=32), nullable=False),
        sa.Column("missing_reason", sa.String(length=255), nullable=True),
        sa.Column("client_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["episode_id"],
            ["research_episodes.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["study_instruments.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["participant_id"],
            ["research_participants.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "completion_status IN ('completed', 'declined', 'missed')",
            name="ck_survey_response_completion",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "participant_id",
            "instrument_id",
            "episode_id",
            "period_code",
            name="uq_survey_response_period",
        ),
    )
    for column in ("id", "participant_id", "instrument_id", "episode_id"):
        op.create_index(
            f"ix_survey_responses_{column}",
            "survey_responses",
            [column],
        )

    op.create_table(
        "reference_assessments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_participant_id", sa.Integer(), nullable=False),
        sa.Column("review_round", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("task_schema_version", sa.String(length=64), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "blinded_to_clinician",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["episode_id"],
            ["research_episodes.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_participant_id"],
            ["research_participants.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "review_round >= 1",
            name="ck_reference_assessment_round",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100)",
            name="ck_reference_assessment_confidence",
        ),
        sa.CheckConstraint(
            "blinded_to_clinician = true",
            name="ck_reference_assessment_blinded",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "episode_id",
            "reviewer_participant_id",
            "review_round",
            name="uq_reference_assessment_reviewer_round",
        ),
    )
    for column in ("id", "episode_id", "reviewer_participant_id"):
        op.create_index(
            f"ix_reference_assessments_{column}",
            "reference_assessments",
            [column],
        )

    op.create_table(
        "adjudications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("adjudicator_participant_id", sa.Integer(), nullable=False),
        sa.Column("reference_standard_version", sa.String(length=64), nullable=False),
        sa.Column("task_schema_version", sa.String(length=64), nullable=False),
        sa.Column("consensus_decision", sa.JSON(), nullable=False),
        sa.Column("uncertainty", sa.String(length=64), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["adjudicator_participant_id"],
            ["research_participants.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["episode_id"],
            ["research_episodes.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("episode_id"),
    )
    op.create_index("ix_adjudications_id", "adjudications", ["id"])
    op.create_index("ix_adjudications_episode_id", "adjudications", ["episode_id"])
    op.create_index(
        "ix_adjudications_adjudicator_participant_id",
        "adjudications",
        ["adjudicator_participant_id"],
    )

    op.create_table(
        "research_corrections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("created_by_participant_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("corrected_payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_participant_id"],
            ["research_participants.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["episode_id"],
            ["research_episodes.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "target_type IN ("
            "'pre_ai_decision', 'ai_reveal', 'final_decision', "
            "'survey_response', 'reference_assessment', 'adjudication'"
            ")",
            name="ck_research_correction_target_type",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("id", "episode_id", "created_by_participant_id"):
        op.create_index(
            f"ix_research_corrections_{column}",
            "research_corrections",
            [column],
        )


def downgrade() -> None:
    op.drop_table("research_corrections")
    op.drop_table("adjudications")
    op.drop_table("reference_assessments")
    op.drop_table("survey_responses")
    op.drop_table("study_instruments")
    op.drop_table("research_events")
    op.drop_table("final_decisions")
    op.drop_table("ai_reveals")
    op.drop_table("pre_ai_decisions")
    op.drop_table("research_episodes")
    op.drop_table("research_participants")
    op.drop_table("research_epochs")
    op.drop_table("research_sites")
    op.drop_table("research_studies")
