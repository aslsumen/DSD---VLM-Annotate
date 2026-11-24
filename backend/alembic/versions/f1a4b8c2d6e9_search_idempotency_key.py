"""search idempotency key

Adds ``searches.idempotency_key`` so a repeated ``POST
/datasets/{id}/searches`` with the same ``Idempotency-Key`` header returns the
original search instead of fanning out a second set of jobs.

Revision ID: f1a4b8c2d6e9
Revises: c9f0d3a1b2e4
Create Date: 2026-11-24 23:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a4b8c2d6e9'
down_revision: Union[str, Sequence[str], None] = 'c9f0d3a1b2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('searches', schema=None) as batch_op:
        batch_op.add_column(sa.Column('idempotency_key', sa.String(length=100), nullable=True))
        batch_op.create_unique_constraint('uq_search_idempotency_key', ['idempotency_key'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('searches', schema=None) as batch_op:
        batch_op.drop_constraint('uq_search_idempotency_key', type_='unique')
        batch_op.drop_column('idempotency_key')
