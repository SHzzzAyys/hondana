"""add file_format to books

Revision ID: 293a39d0fba2
Revises: e64d399aa829
Create Date: 2026-06-03 03:41:37.477251

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '293a39d0fba2'
down_revision = 'e64d399aa829'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('books', schema=None) as batch_op:
        batch_op.add_column(sa.Column('file_format', sa.String(length=16), nullable=True))
    # 老书全是 epub:backfill 已有 epub_filename 的书为 'epub'
    op.execute(
        "UPDATE books SET file_format = 'epub' "
        "WHERE epub_filename IS NOT NULL AND file_format IS NULL"
    )


def downgrade():
    with op.batch_alter_table('books', schema=None) as batch_op:
        batch_op.drop_column('file_format')
