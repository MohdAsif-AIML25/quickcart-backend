"""order management and checkout details

Revision ID: c4d2a7e91b35
Revises: 1a18e1ed71ec
Create Date: 2026-10-08 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d2a7e91b35'
down_revision: Union[str, Sequence[str], None] = '1a18e1ed71ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add payment, delivery address, delivery dates and soft delete to orders.

    Every new column is NULLable and NO existing row is changed. Orders placed
    before this migration never had an address or a payment method, so they
    keep NULL there ("not recorded"). Inventing a value such as 'cod' for them
    would put facts into the database that nobody ever stated.
    """
    op.add_column('orders', sa.Column('payment_method', sa.String(length=20), nullable=True))
    op.add_column('orders', sa.Column('payment_status', sa.String(length=20), nullable=True))
    op.add_column('orders', sa.Column('shipping_recipient_name', sa.String(length=100), nullable=True))
    op.add_column('orders', sa.Column('shipping_phone', sa.String(length=20), nullable=True))
    op.add_column('orders', sa.Column('shipping_address_line1', sa.String(length=200), nullable=True))
    op.add_column('orders', sa.Column('shipping_address_line2', sa.String(length=200), nullable=True))
    op.add_column('orders', sa.Column('shipping_city', sa.String(length=100), nullable=True))
    op.add_column('orders', sa.Column('shipping_state', sa.String(length=100), nullable=True))
    op.add_column('orders', sa.Column('shipping_postal_code', sa.String(length=12), nullable=True))
    op.add_column('orders', sa.Column('shipping_country', sa.String(length=60), nullable=True))
    op.add_column('orders', sa.Column('estimated_delivery_date', sa.Date(), nullable=True))
    op.add_column('orders', sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('orders', sa.Column('stock_restored_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('orders', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))

    # Until now the only status ever written was 'confirmed', so existing rows
    # satisfy this. If a row held anything else, PostgreSQL would refuse the
    # constraint and roll the whole migration back: nothing is half-applied.
    op.create_check_constraint(
        op.f('ck_orders_status_valid'),
        'orders',
        "status IN ('confirmed', 'processing', 'shipped', 'delivered', 'cancelled')",
    )
    # A CHECK passes when the value is NULL, so the old orders are accepted.
    op.create_check_constraint(op.f('ck_orders_payment_method_valid'), 'orders', "payment_method IN ('cod')")
    op.create_check_constraint(
        op.f('ck_orders_payment_status_valid'), 'orders', "payment_status IN ('pending', 'paid')"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f('ck_orders_payment_status_valid'), 'orders', type_='check')
    op.drop_constraint(op.f('ck_orders_payment_method_valid'), 'orders', type_='check')
    op.drop_constraint(op.f('ck_orders_status_valid'), 'orders', type_='check')
    op.drop_column('orders', 'deleted_at')
    op.drop_column('orders', 'stock_restored_at')
    op.drop_column('orders', 'delivered_at')
    op.drop_column('orders', 'estimated_delivery_date')
    op.drop_column('orders', 'shipping_country')
    op.drop_column('orders', 'shipping_postal_code')
    op.drop_column('orders', 'shipping_state')
    op.drop_column('orders', 'shipping_city')
    op.drop_column('orders', 'shipping_address_line2')
    op.drop_column('orders', 'shipping_address_line1')
    op.drop_column('orders', 'shipping_phone')
    op.drop_column('orders', 'shipping_recipient_name')
    op.drop_column('orders', 'payment_status')
    op.drop_column('orders', 'payment_method')
