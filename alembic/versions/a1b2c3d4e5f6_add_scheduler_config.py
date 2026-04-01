"""add_scheduler_config

Revision ID: a1b2c3d4e5f6
Revises: 86d2fa9131b9
Create Date: 2026-04-02 10:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '86d2fa9131b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    table = op.create_table(
        'scheduler_config',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('key', sa.String(length=50), nullable=False),
        sa.Column('value', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key'),
    )
    op.bulk_insert(table, [
        {'key': 'shortfall_penalty', 'value': -1000, 'label': 'Shortfall Penalty', 'description': 'S0: Penalty per unfilled demand slot'},
        {'key': 'overstaff_reward', 'value': 100, 'label': 'Overstaff Reward', 'description': 'S0: Reward per assignment on demanded slot'},
        {'key': 'seniority_max_score', 'value': 100, 'label': 'Seniority Max Score', 'description': 'S1: Max seniority score (normalization cap)'},
        {'key': 'shift_pref_match', 'value': 300, 'label': 'Shift Preference Match', 'description': 'S2: Reward for matching shift preference'},
        {'key': 'shift_pref_mismatch', 'value': -300, 'label': 'Shift Preference Mismatch', 'description': 'S2: Penalty for mismatching shift preference'},
        {'key': 'shift_flexible_bonus', 'value': 10, 'label': 'Shift Flexible Bonus', 'description': 'S2: Small bonus for flexible/no preference'},
        {'key': 'preferred_day_off_penalty', 'value': -200, 'label': 'Preferred Day Off Penalty', 'description': 'S3: Penalty for scheduling on preferred day off'},
        {'key': 'ride_share_mismatch', 'value': -200, 'label': 'Ride Share Mismatch', 'description': 'S4: Penalty per ride-share pair mismatch'},
        {'key': 'min_one_shift_reward', 'value': 500, 'label': 'Min One Shift Reward', 'description': 'S5: Reward for giving dealer at least 1 shift'},
        {'key': 'fairness_gap_penalty', 'value': -200, 'label': 'Fairness Gap Penalty', 'description': 'S6: Penalty multiplied by max-min shift gap'},
    ])


def downgrade() -> None:
    op.drop_table('scheduler_config')
