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
    # Get connection to execute raw SQL for updating existing records
    conn = op.get_bind()
    
    # Update existing records with NULL patient_id or title
    # Generate defaults for any NULL values
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
    
    # Alter columns to be nullable
    op.alter_column('cases', 'patient_id',
                    existing_type=sa.String(),
                    nullable=True)
    
    op.alter_column('cases', 'title',
                    existing_type=sa.String(),
                    nullable=True)


def downgrade() -> None:
    # Update any NULL values before making columns non-nullable
    conn = op.get_bind()
    
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
    
    # Alter columns back to non-nullable
    op.alter_column('cases', 'patient_id',
                    existing_type=sa.String(),
                    nullable=False)
    
    op.alter_column('cases', 'title',
                    existing_type=sa.String(),
                    nullable=False)

