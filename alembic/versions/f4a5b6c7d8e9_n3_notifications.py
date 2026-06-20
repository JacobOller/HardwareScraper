"""n3_notifications

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-06-19 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, Sequence[str], None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('listing_id', sa.Integer(), sa.ForeignKey('listings.id'), nullable=False),
        sa.Column('channel', sa.String(32), nullable=False, server_default='discord'),
        sa.Column('sent_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('margin_pct_at_send', sa.Float(), nullable=False),
        sa.Column('ai_verdict', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('notifications')
