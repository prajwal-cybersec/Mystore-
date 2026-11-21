"""add returns and tryon schema

Revision ID: e8c201d5c17f
Revises: d9c301d5c16e
Create Date: 2026-11-22 02:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e8c201d5c17f'
down_revision: Union[str, None] = 'd9c301d5c16e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. orders: add delivered_at
    op.add_column('orders', sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True))

    # 2. products: add tryon columns if not exists
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'products' AND column_name = 'tryon_supported') THEN
                ALTER TABLE products ADD COLUMN tryon_supported BOOLEAN DEFAULT false;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'products' AND column_name = 'tryon_type') THEN
                ALTER TABLE products ADD COLUMN tryon_type VARCHAR(64);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'products' AND column_name = 'tryon_asset') THEN
                ALTER TABLE products ADD COLUMN tryon_asset VARCHAR(512);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'products' AND column_name = 'tryon_config') THEN
                ALTER TABLE products ADD COLUMN tryon_config JSONB DEFAULT '{}';
            END IF;
        END $$;
    """)

    # 3. tryon_events table
    op.create_table(
        'tryon_events',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=True),
        sa.Column('product_id', sa.Uuid(), nullable=True),
        sa.Column('sku', sa.String(length=64), nullable=True),
        sa.Column('tryon_type', sa.String(length=64), nullable=True),
        sa.Column('session_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # 4. return_requests table
    op.create_table(
        'return_requests',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('reference', sa.String(length=16), nullable=False),
        sa.Column('order_id', sa.Uuid(), nullable=False),
        sa.Column('order_item_id', sa.Uuid(), nullable=False),
        sa.Column('product_id', sa.Uuid(), nullable=False),
        sa.Column('customer_id', sa.Uuid(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('reason_code', sa.String(length=32), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('photo_urls', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('resolution', sa.String(length=16), nullable=False),
        sa.Column('exchange_size', sa.String(length=16), nullable=True),
        sa.Column('status', sa.String(length=32), server_default=sa.text("'requested'"), nullable=False),
        sa.Column('item_condition', sa.String(length=16), nullable=True),
        sa.Column('refund_amount_inr', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('pickup_date', sa.Date(), nullable=True),
        sa.Column('admin_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('quantity > 0', name='ck_return_requests_quantity_positive'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ),
        sa.ForeignKeyConstraint(['order_item_id'], ['order_items.id'], ),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reference')
    )
    op.create_index('ix_return_requests_order_id', 'return_requests', ['order_id'], unique=False)
    op.create_index('ix_return_requests_customer_id', 'return_requests', ['customer_id'], unique=False)
    op.create_index('ix_return_requests_status', 'return_requests', ['status'], unique=False)

    # 5. return_status_history table
    op.create_table(
        'return_status_history',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('return_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('actor', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['return_id'], ['return_requests.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_return_status_history_return_id', 'return_status_history', ['return_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_return_status_history_return_id', table_name='return_status_history')
    op.drop_table('return_status_history')
    op.drop_index('ix_return_requests_status', table_name='return_requests')
    op.drop_index('ix_return_requests_customer_id', table_name='return_requests')
    op.drop_index('ix_return_requests_order_id', table_name='return_requests')
    op.drop_table('return_requests')
    op.drop_table('tryon_events')
    op.drop_column('orders', 'delivered_at')
    # products tryon columns dropped as single statement or DO block for asyncpg
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'products' AND column_name = 'tryon_config') THEN
                ALTER TABLE products DROP COLUMN tryon_config;
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'products' AND column_name = 'tryon_asset') THEN
                ALTER TABLE products DROP COLUMN tryon_asset;
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'products' AND column_name = 'tryon_type') THEN
                ALTER TABLE products DROP COLUMN tryon_type;
            END IF;
            IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'products' AND column_name = 'tryon_supported') THEN
                ALTER TABLE products DROP COLUMN tryon_supported;
            END IF;
        END $$;
    """)
