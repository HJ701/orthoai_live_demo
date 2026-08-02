"""make_patient_id_title_nullable

Revision ID: 3279515f6aee
Revises: 001_initial
Create Date: 2025-01-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '3279515f6aee'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        conn.execute(text("""
            UPDATE cases
            SET patient_id = 'PATIENT_' || UPPER(SUBSTR(HEX(RANDOMBLOB(8)), 1, 8))
            WHERE patient_id IS NULL OR patient_id = ''
        """))
        conn.execute(text("""
            UPDATE cases
            SET title = 'Case ' || STRFTIME('%Y-%m-%d %H:%M', created_at)
            WHERE title IS NULL OR title = ''
        """))
        with op.batch_alter_table("cases") as batch_op:
            batch_op.alter_column(
                "patient_id",
                existing_type=sa.String(),
                nullable=True,
            )
            batch_op.alter_column(
                "title",
                existing_type=sa.String(),
                nullable=True,
            )
        return

    conn.execute(text("""
        UPDATE cases
        SET patient_id = 'PATIENT_' || UPPER(SUBSTRING(MD5(RANDOM()::TEXT) FROM 1 FOR 8))
        WHERE patient_id IS NULL OR patient_id = ''
    """))
    conn.execute(text("""
        UPDATE cases
        SET title = 'Case ' || TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI')
        WHERE title IS NULL OR title = ''
    """))
    op.alter_column(
        "cases",
        "patient_id",
        existing_type=sa.String(),
        nullable=True,
    )
    op.alter_column(
        "cases",
        "title",
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "sqlite":
        conn.execute(text("""
            UPDATE cases
            SET patient_id = 'PATIENT_' || UPPER(SUBSTR(HEX(RANDOMBLOB(8)), 1, 8))
            WHERE patient_id IS NULL
        """))
        conn.execute(text("""
            UPDATE cases
            SET title = 'Case ' || STRFTIME('%Y-%m-%d %H:%M', created_at)
            WHERE title IS NULL
        """))
        with op.batch_alter_table("cases") as batch_op:
            batch_op.alter_column(
                "patient_id",
                existing_type=sa.String(),
                nullable=False,
            )
            batch_op.alter_column(
                "title",
                existing_type=sa.String(),
                nullable=False,
            )
        return

    conn.execute(text("""
        UPDATE cases
        SET patient_id = 'PATIENT_' || UPPER(SUBSTRING(MD5(RANDOM()::TEXT) FROM 1 FOR 8))
        WHERE patient_id IS NULL
    """))
    conn.execute(text("""
        UPDATE cases
        SET title = 'Case ' || TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI')
        WHERE title IS NULL
    """))
    op.alter_column(
        "cases",
        "patient_id",
        existing_type=sa.String(),
        nullable=False,
    )
    op.alter_column(
        "cases",
        "title",
        existing_type=sa.String(),
        nullable=False,
    )
