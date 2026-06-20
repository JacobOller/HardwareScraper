"""add_portfolio_tracking

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-06-19 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('listings', sa.Column('bought_at', sa.DateTime(), nullable=True))
    op.add_column('listings', sa.Column('bought_price', sa.Float(), nullable=True))
    op.add_column('listings', sa.Column('sold_at', sa.DateTime(), nullable=True))
    op.add_column('listings', sa.Column('sold_price', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('listings', 'sold_price')
    op.drop_column('listings', 'sold_at')
    op.drop_column('listings', 'bought_price')
    op.drop_column('listings', 'bought_at')
