"""add multi seller marketplace schema

Revision ID: f4a801d5c18a
Revises: e8c201d5c17f
Create Date: 2026-11-22 03:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f4a801d5c18a'
down_revision: Union[str, None] = 'e8c201d5c17f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. sellers table
    op.create_table(
        'sellers',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('seller_code', sa.String(length=32), nullable=False),
        sa.Column('gstin', sa.String(length=15), nullable=False),
        sa.Column('state', sa.String(length=64), nullable=False),
        sa.Column('address', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('seller_code', name='uq_sellers_seller_code')
    )

    # 2. seller_offers table
    op.create_table(
        'seller_offers',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('seller_id', sa.Uuid(), nullable=False),
        sa.Column('city', sa.String(length=64), nullable=False),
        sa.Column('price_inr', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('qty >= 0', name='chk_seller_offers_qty_non_negative'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['seller_id'], ['sellers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', 'seller_id', 'city', name='uq_seller_offers_product_seller_city')
    )

    # 3. seller_invoice_counters table
    op.create_table(
        'seller_invoice_counters',
        sa.Column('seller_id', sa.Uuid(), nullable=False),
        sa.Column('last_no', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.ForeignKeyConstraint(['seller_id'], ['sellers.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('seller_id')
    )

    # 4. sub_orders table
    op.create_table(
        'sub_orders',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('order_id', sa.Uuid(), nullable=False),
        sa.Column('seller_id', sa.Uuid(), nullable=False),
        sa.Column('city', sa.String(length=64), nullable=False),
        sa.Column('subtotal', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('tax', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('status', sa.String(length=32), server_default=sa.text("'placed'"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['seller_id'], ['sellers.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_sub_orders_order_id', 'sub_orders', ['order_id'], unique=False)
    op.create_index('ix_sub_orders_seller_id', 'sub_orders', ['seller_id'], unique=False)

    # 5. invoices table
    op.create_table(
        'invoices',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('sub_order_id', sa.Uuid(), nullable=False),
        sa.Column('seller_id', sa.Uuid(), nullable=False),
        sa.Column('invoice_no', sa.String(length=64), nullable=False),
        sa.Column('taxable_value', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('cgst', sa.Numeric(precision=12, scale=2), server_default=sa.text('0.00'), nullable=False),
        sa.Column('sgst', sa.Numeric(precision=12, scale=2), server_default=sa.text('0.00'), nullable=False),
        sa.Column('igst', sa.Numeric(precision=12, scale=2), server_default=sa.text('0.00'), nullable=False),
        sa.Column('total', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('issued_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['seller_id'], ['sellers.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['sub_order_id'], ['sub_orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sub_order_id', name='uq_invoices_sub_order_id'),
        sa.UniqueConstraint('seller_id', 'invoice_no', name='uq_invoices_seller_invoice_no')
    )

    # 6. shipments table
    op.create_table(
        'shipments',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('sub_order_id', sa.Uuid(), nullable=False),
        sa.Column('tracking_number', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), server_default=sa.text("'manifested'"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['sub_order_id'], ['sub_orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 7. Add columns to orders
    op.add_column('orders', sa.Column('grand_total', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('orders', sa.Column('invoices_expected', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('orders', sa.Column('invoices_ready', sa.Integer(), server_default=sa.text('0'), nullable=False))

    # 8. Add columns to order_items
    op.add_column('order_items', sa.Column('sub_order_id', sa.Uuid(), nullable=True))
    op.add_column('order_items', sa.Column('offer_id', sa.Uuid(), nullable=True))
    op.create_foreign_key('fk_order_items_sub_order_id', 'order_items', 'sub_orders', ['sub_order_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_order_items_offer_id', 'order_items', 'seller_offers', ['offer_id'], ['id'], ondelete='SET NULL')

    # 9. Backfill default seller and populate seller_offers from existing store_stock
    op.execute("""
        DO $$
        DECLARE
            v_seller_id UUID := '10000000-0000-0000-0000-000000000001';
        BEGIN
            -- Insert default seller
            INSERT INTO sellers (id, name, seller_code, gstin, state, address, created_at)
            VALUES (
                v_seller_id,
                'MyStore Retail',
                'MYS',
                '29AABCM1234F1Z5',
                'Karnataka',
                'Warehouse 1, Electronic City, Bengaluru, Karnataka 560100',
                NOW()
            )
            ON CONFLICT (id) DO NOTHING;

            -- Initialize invoice counter
            INSERT INTO seller_invoice_counters (seller_id, last_no)
            VALUES (v_seller_id, 0)
            ON CONFLICT (seller_id) DO NOTHING;

            -- Backfill seller_offers from store_stock + products.price_inr
            INSERT INTO seller_offers (id, product_id, seller_id, city, price_inr, qty, created_at, updated_at)
            SELECT gen_random_uuid(), s.product_id, v_seller_id, s.city, p.price_inr, s.qty, NOW(), NOW()
            FROM store_stock s
            JOIN products p ON p.id = s.product_id
            ON CONFLICT (product_id, seller_id, city) DO UPDATE SET qty = EXCLUDED.qty;
        END $$;
    """)


def downgrade() -> None:
    # 1. Drop foreign keys and columns on order_items and orders
    op.drop_constraint('fk_order_items_offer_id', 'order_items', type_='foreignkey')
    op.drop_constraint('fk_order_items_sub_order_id', 'order_items', type_='foreignkey')
    op.drop_column('order_items', 'offer_id')
    op.drop_column('order_items', 'sub_order_id')

    op.drop_column('orders', 'invoices_ready')
    op.drop_column('orders', 'invoices_expected')
    op.drop_column('orders', 'grand_total')

    # 2. Drop tables in reverse order of foreign keys
    op.drop_table('shipments')
    op.drop_table('invoices')
    op.drop_index('ix_sub_orders_seller_id', table_name='sub_orders')
    op.drop_index('ix_sub_orders_order_id', table_name='sub_orders')
    op.drop_table('sub_orders')
    op.drop_table('seller_invoice_counters')
    op.drop_table('seller_offers')
    op.drop_table('sellers')
