"""search and search_video

Revision ID: e5b9c3d7a2f1
Revises: d03f1c4ffd30
Create Date: 2026-11-20 11:26:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5b9c3d7a2f1'
down_revision: Union[str, Sequence[str], None] = 'd03f1c4ffd30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('searches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('dataset_id', sa.Integer(), nullable=False),
    sa.Column('prompt', sa.Text(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=True),
    sa.Column('status', sa.Enum('queued', 'running', 'done', 'partial', 'failed', name='search_status', native_enum=False, length=32), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['dataset_id'], ['datasets.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('searches', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_searches_dataset_id'), ['dataset_id'], unique=False)
        batch_op.create_index('ix_searches_dataset_status', ['dataset_id', 'status'], unique=False)

    op.create_table('search_videos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('search_id', sa.Integer(), nullable=False),
    sa.Column('video_id', sa.Integer(), nullable=False),
    sa.Column('job_id', sa.Integer(), nullable=True),
    sa.Column('status', sa.Enum('queued', 'running', 'done', 'failed', name='search_video_status', native_enum=False, length=32), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['job_id'], ['processing_jobs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['search_id'], ['searches.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('search_id', 'video_id', name='uq_search_video')
    )
    with op.batch_alter_table('search_videos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_search_videos_search_id'), ['search_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_search_videos_video_id'), ['video_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_search_videos_job_id'), ['job_id'], unique=False)

    with op.batch_alter_table('videos', schema=None) as batch_op:
        batch_op.alter_column('project_id',
               existing_type=sa.Integer(),
               existing_nullable=False,
               nullable=True)
        batch_op.add_column(sa.Column('dataset_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_videos_dataset_id_datasets', 'datasets', ['dataset_id'], ['id'], ondelete='CASCADE')
        batch_op.create_index(batch_op.f('ix_videos_dataset_id'), ['dataset_id'], unique=False)

    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('search_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_candidates_search_id_searches', 'searches', ['search_id'], ['id'], ondelete='CASCADE')
        batch_op.create_index(batch_op.f('ix_candidates_search_id'), ['search_id'], unique=False)

    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('candidates', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_candidates_search_id'))
        batch_op.drop_constraint('fk_candidates_search_id_searches', type_='foreignkey')
        batch_op.drop_column('search_id')

    with op.batch_alter_table('videos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_videos_dataset_id'))
        batch_op.drop_constraint('fk_videos_dataset_id_datasets', type_='foreignkey')
        batch_op.drop_column('dataset_id')
        batch_op.alter_column('project_id',
               existing_type=sa.Integer(),
               existing_nullable=True,
               nullable=False)

    with op.batch_alter_table('search_videos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_search_videos_job_id'))
        batch_op.drop_index(batch_op.f('ix_search_videos_video_id'))
        batch_op.drop_index(batch_op.f('ix_search_videos_search_id'))

    op.drop_table('search_videos')

    with op.batch_alter_table('searches', schema=None) as batch_op:
        batch_op.drop_index('ix_searches_dataset_status')
        batch_op.drop_index(batch_op.f('ix_searches_dataset_id'))

    op.drop_table('searches')
    # ### end Alembic commands ###
