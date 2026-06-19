"""phase2i_2j_columns

Revision ID: b7c8d9e0f1a2
Revises: 92fe7062100a
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = '92fe7062100a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # listings.is_local_pickup — True for in-person pickup, False for shipped items
    op.add_column('listings', sa.Column('is_local_pickup', sa.Boolean(), nullable=False, server_default='1'))

    # valuations.inbound_shipping — cost to receive non-local items (default 0)
    op.add_column('valuations', sa.Column('inbound_shipping', sa.Float(), nullable=False, server_default='0.0'))

    # valuations.amazon_price — scraped Amazon active listing price (nullable, Phase 2J)
    op.add_column('valuations', sa.Column('amazon_price', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('listings', 'is_local_pickup')
    op.drop_column('valuations', 'inbound_shipping')
    op.drop_column('valuations', 'amazon_price')
