"""add product_name to order_items

Revision ID: 1a18e1ed71ec
Revises: fb15a87444da
Create Date: 2026-10-05 13:29:48.580293

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1a18e1ed71ec'
down_revision: Union[str, Sequence[str], None] = 'fb15a87444da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add a NOT NULL column to a table that may already contain rows.

    Autogenerate wrote one line: add_column(..., nullable=False). PostgreSQL
    rejects that as soon as order_items has a single row, because the existing
    rows would hold NULL in a NOT NULL column. So the change is done in 3 steps.
    """
    # 1. Add the column as NULLable, so the existing rows are accepted.
    op.add_column('order_items', sa.Column('product_name', sa.String(length=200), nullable=True))

    # 2. Backfill: old orders get the product's CURRENT name. It is the best
    #    information that still exists; from now on checkout stores the real snapshot.
    op.execute(
        """
        UPDATE order_items
        SET product_name = products.name
        FROM products
        WHERE products.id = order_items.product_id
        """
    )

    # 3. Every row has a value now, so the column can become NOT NULL.
    op.alter_column('order_items', 'product_name', nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('order_items', 'product_name')
