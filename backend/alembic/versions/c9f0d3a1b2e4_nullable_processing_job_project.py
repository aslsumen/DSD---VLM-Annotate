"""make processing_jobs.project_id nullable

Search fan-out creates candidate-proposal jobs for dataset videos, which have
``project_id == NULL``.  The legacy project/action path is unaffected.

Revision ID: c9f0d3a1b2e4
Revises: e5b9c3d7a2f1
Create Date: 2026-11-20 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9f0d3a1b2e4'
down_revision: Union[str, Sequence[str], None] = 'e5b9c3d7a2f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('processing_jobs', schema=None) as batch_op:
        batch_op.alter_column('project_id',
               existing_type=sa.Integer(),
               existing_nullable=False,
               nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('processing_jobs', schema=None) as batch_op:
        batch_op.alter_column('project_id',
               existing_type=sa.Integer(),
               existing_nullable=True,
               nullable=False)
