"""n2_working_comp

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-06-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, Sequence[str], None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # working_comp_price / working_comp_count — eBay used/working median for for_parts listings.
    # ebay_median_price stores the for-parts floor; these store the post-repair resale target.
    op.add_column('valuations', sa.Column('working_comp_price', sa.Float(), nullable=True))
    op.add_column('valuations', sa.Column('working_comp_count', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('valuations', 'working_comp_count')
    op.drop_column('valuations', 'working_comp_price')
