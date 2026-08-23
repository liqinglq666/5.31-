"""add temperature to sys_model_configs

Revision ID: a1b2c3d4e5f6
Revises: 930233c86571
Create Date: 2026-05-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '930233c86571'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'sys_model_configs',
        sa.Column('temperature', sa.String(length=10), nullable=True, comment='模型采样温度，默认 0.0'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sys_model_configs', 'temperature')
