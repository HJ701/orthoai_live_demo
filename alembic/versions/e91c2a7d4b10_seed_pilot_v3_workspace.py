"""Provision the canonical Research Mode v3 pilot workspace.

Revision ID: e91c2a7d4b10
Revises: d7e2f8a19c44
Create Date: 2026-08-13 00:00:00

The migration is intentionally idempotent at the data level. It removes the
need for a clinician-facing study initialization action while leaving paused or
closed studies untouched.
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "e91c2a7d4b10"
down_revision = "d7e2f8a19c44"
branch_labels = None
depends_on = None


STUDY_CODE = "ORTHOAI-HCI-V3"


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc)

    studies = sa.table(
        "research_studies",
        sa.column("id", sa.Integer),
        sa.column("code", sa.String),
        sa.column("title", sa.String),
        sa.column("protocol_version", sa.String),
        sa.column("consent_version", sa.String),
        sa.column("primary_task", sa.String),
        sa.column("primary_outcome", sa.String),
        sa.column("status", sa.String),
        sa.column("minimum_reference_reviews", sa.Integer),
        sa.column("config", sa.JSON),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("activated_at", sa.DateTime(timezone=True)),
    )
    sites = sa.table(
        "research_sites",
        sa.column("id", sa.Integer),
        sa.column("study_id", sa.Integer),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("timezone", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    epochs = sa.table(
        "research_epochs",
        sa.column("id", sa.Integer),
        sa.column("study_id", sa.Integer),
        sa.column("code", sa.String),
        sa.column("label", sa.String),
        sa.column("protocol_version", sa.String),
        sa.column("task_schema_version", sa.String),
        sa.column("ui_version", sa.String),
        sa.column("model_version", sa.String),
        sa.column("model_artifact_sha256", sa.String),
        sa.column("deployment_policy_version", sa.String),
        sa.column("result_schema_version", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("starts_at", sa.DateTime(timezone=True)),
        sa.column("config", sa.JSON),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    study_row = bind.execute(
        sa.select(studies.c.id, studies.c.status).where(studies.c.code == STUDY_CODE)
    ).first()
    if study_row is None:
        bind.execute(
            studies.insert().values(
                code=STUDY_CODE,
                title="OrthoAI longitudinal HCI pilot v3",
                protocol_version="orthoai-hci-v3/1.0.0",
                consent_version="orthoai-pilot-consent/3.0.0",
                primary_task="malocclusion_classification",
                primary_outcome="Human-AI decision quality and calibrated reliance",
                status="active",
                minimum_reference_reviews=2,
                config={
                    "clinical_effect": "shadow_only",
                    "case_pulse_every_n": 3,
                    "provisioned_by": revision,
                },
                created_at=now,
                activated_at=now,
            )
        )
        study_row = bind.execute(
            sa.select(studies.c.id, studies.c.status).where(
                studies.c.code == STUDY_CODE
            )
        ).one()
    elif study_row.status == "draft":
        bind.execute(
            studies.update()
            .where(studies.c.id == study_row.id)
            .values(status="active", activated_at=now)
        )

    study_id = study_row.id
    active_site_id = bind.execute(
        sa.select(sites.c.id)
        .where(sites.c.study_id == study_id, sites.c.is_active.is_(True))
        .order_by(sites.c.id)
    ).scalar()
    if active_site_id is None:
        bind.execute(
            sites.insert().values(
                study_id=study_id,
                code="PILOT",
                name="OrthoAI Pilot Clinical Network",
                timezone="Asia/Dubai",
                is_active=True,
                created_at=now,
            )
        )

    active_epoch_id = bind.execute(
        sa.select(epochs.c.id)
        .where(epochs.c.study_id == study_id, epochs.c.is_active.is_(True))
        .order_by(epochs.c.id.desc())
    ).scalar()
    effective_status = bind.execute(
        sa.select(studies.c.status).where(studies.c.id == study_id)
    ).scalar_one()
    if active_epoch_id is None and effective_status == "active":
        bind.execute(
            epochs.insert().values(
                study_id=study_id,
                code="PILOT-V3-E1",
                label="Pilot v3 research instrumentation epoch",
                protocol_version="orthoai-hci-v3/1.0.0",
                task_schema_version="orthoai.malocclusion-decision/1.0.0",
                ui_version="research-ui/3.0.0",
                model_version="v2.0.0",
                model_artifact_sha256=(
                    "059e6fec013e4777d592814716146f4e319644e2d7ee4b33b37d3eac9fb64e99"
                ),
                deployment_policy_version="shadow-1.0.0",
                result_schema_version="orthoai.combined-result/2.0.0",
                is_active=True,
                starts_at=now,
                config={
                    "score_fusion": "none",
                    "clinical_effect": "shadow_only",
                    "provisioned_by": revision,
                },
                created_at=now,
            )
        )


def downgrade() -> None:
    # Pilot records may already reference these rows. A downgrade must not
    # destroy governed research data or silently close an active study.
    pass
