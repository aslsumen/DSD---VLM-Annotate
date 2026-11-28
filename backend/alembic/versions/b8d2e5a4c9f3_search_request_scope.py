"""search request scope

Persists the request that created a search, so an ``Idempotency-Key`` replay is
compared against a snapshot of the request instead of the current
``search_videos`` rows.  Without this column a replay could not tell a changed
``params`` payload (or a switch between an explicit subset and every video),
and deleting one selected video made the original request stop matching itself.

Existing rows keep ``"{}"``, which the endpoint treats as "no stored scope" and
falls back to the old dataset + prompt comparison.

Revision ID: b8d2e5a4c9f3
Revises: f1a4b8c2d6e9
Create Date: 2026-11-26 00:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d2e5a4c9f3'
down_revision: Union[str, Sequence[str], None] = 'f1a4b8c2d6e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('searches', schema=None) as batch_op:
        # server_default so rows written before this revision are valid SQL; it
        # is then dropped so the application owns the value from now on.
        batch_op.add_column(
            sa.Column(
                'request_scope_json',
                sa.Text(),
                nullable=False,
                server_default='{}',
            )
        )
    with op.batch_alter_table('searches', schema=None) as batch_op:
        batch_op.alter_column('request_scope_json', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('searches', schema=None) as batch_op:
        batch_op.drop_column('request_scope_json')
