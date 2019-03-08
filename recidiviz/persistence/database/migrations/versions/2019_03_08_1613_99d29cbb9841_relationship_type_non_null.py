"""relationship_type_non_null

Revision ID: 99d29cbb9841
Revises: 477d5b664b63
Create Date: 2019-03-08 16:13:16.880800

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '99d29cbb9841'
down_revision = '477d5b664b63'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('sentence_relationship', 'type',
               existing_type=postgresql.ENUM('CONCURRENT', 'CONSECUTIVE', name='sentence_relationship_type'),
               nullable=False)
    op.alter_column('sentence_relationship_history', 'type',
               existing_type=postgresql.ENUM('CONCURRENT', 'CONSECUTIVE', name='sentence_relationship_type'),
               nullable=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('sentence_relationship_history', 'type',
               existing_type=postgresql.ENUM('CONCURRENT', 'CONSECUTIVE', name='sentence_relationship_type'),
               nullable=True)
    op.alter_column('sentence_relationship', 'type',
               existing_type=postgresql.ENUM('CONCURRENT', 'CONSECUTIVE', name='sentence_relationship_type'),
               nullable=True)
    # ### end Alembic commands ###
