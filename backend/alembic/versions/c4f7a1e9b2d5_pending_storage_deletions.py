"""pending storage deletions

Deleting a video commits the row removal before the bytes are unlinked.  A
process that dies in between left the files unreachable: the only record of
their keys was the row just deleted, so no later pass could find them.  This
table records the keys to remove inside the deleting transaction, making "the
row is gone" imply "the cleanup is still queued"; a worker sweep drains it.

Revision ID: c4f7a1e9b2d5
Revises: b8d2e5a4c9f3
Create Date: 2026-11-27 13:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f7a1e9b2d5'
down_revision: Union[str, Sequence[str], None] = 'b8d2e5a4c9f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pending_deletions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('storage_key', sa.String(length=512), nullable=False),
        sa.Column('is_tree', sa.Boolean(), nullable=False),
        sa.Column('reason', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('pending_deletions', schema=None) as batch_op:
        batch_op.create_index(
            'ix_pending_deletions_created_at', ['created_at'], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('pending_deletions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pending_deletions_created_at'))
    op.drop_table('pending_deletions')
