"""init

Revision ID: b70d01be15e9
Revises: 
Create Date: 2026-06-25 15:14:31.486747

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = 'b70d01be15e9'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    tables = ['trades', 'events', 'agent_logs', 'trade_context', 'trade_lessons',
              'virtual_account', 'virtual_positions', 'equity_snapshots',
              'config_audit', 'profit_locks', 'scan_results', 'scheduler_logs']

    if all(t in existing_tables for t in tables):
        return

    op.create_table(
        'trades',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trade_id', sa.String(), nullable=False),
        sa.Column('ticker', sa.String(), nullable=False),
        sa.Column('action', sa.String(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('entry_price', sa.Float(), nullable=True),
        sa.Column('exit_price', sa.Float(), nullable=True),
        sa.Column('stop_loss', sa.Float(), nullable=True),
        sa.Column('take_profit', sa.Float(), nullable=True),
        sa.Column('pnl', sa.Float(), nullable=True),
        sa.Column('commission', sa.Float(), nullable=True),
        sa.Column('strategy', sa.String(), nullable=True),
        sa.Column('signal_context', sa.Text(), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('opened_at', sa.String(), nullable=True),
        sa.Column('closed_at', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('created_at', sa.String(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('trade_id'),
    )
    op.create_table(
        'events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_type', sa.String(), nullable=True),
        sa.Column('ticker', sa.String(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('impact_score', sa.Float(), nullable=True),
        sa.Column('sentiment', sa.String(), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('timestamp', sa.String(), nullable=True),
        sa.Column('created_at', sa.String(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'agent_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('agent_name', sa.String(), nullable=True),
        sa.Column('action', sa.String(), nullable=True),
        sa.Column('input_data', sa.Text(), nullable=True),
        sa.Column('output_data', sa.Text(), nullable=True),
        sa.Column('tool_calls', sa.Text(), nullable=True),
        sa.Column('timestamp', sa.String(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'trade_context',
        sa.Column('trade_id', sa.String(), nullable=False),
        sa.Column('ticker', sa.String(), nullable=True),
        sa.Column('rsi', sa.Float(), nullable=True),
        sa.Column('macd_signal', sa.String(), nullable=True),
        sa.Column('bb_position', sa.String(), nullable=True),
        sa.Column('atr', sa.Float(), nullable=True),
        sa.Column('volatility_regime', sa.String(), nullable=True),
        sa.Column('trend', sa.String(), nullable=True),
        sa.Column('volume_vs_avg', sa.Float(), nullable=True),
        sa.Column('sentiment_score', sa.Float(), nullable=True),
        sa.Column('sentiment_label', sa.String(), nullable=True),
        sa.Column('support', sa.Float(), nullable=True),
        sa.Column('resistance', sa.Float(), nullable=True),
        sa.Column('price_at_entry', sa.Float(), nullable=True),
        sa.Column('created_at', sa.String(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('trade_id'),
    )
    op.create_table(
        'trade_lessons',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trade_id', sa.String(), nullable=True),
        sa.Column('ticker', sa.String(), nullable=True),
        sa.Column('strategy', sa.String(), nullable=True),
        sa.Column('lesson_type', sa.String(), nullable=True),
        sa.Column('pattern_description', sa.Text(), nullable=True),
        sa.Column('conditions', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('times_observed', sa.Integer(), nullable=True),
        sa.Column('times_lost', sa.Integer(), nullable=True),
        sa.Column('win_rate', sa.Float(), nullable=True),
        sa.Column('severity', sa.String(), nullable=True),
        sa.Column('created_at', sa.String(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('last_updated', sa.String(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'virtual_account',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('initial_capital', sa.Float(), server_default=sa.text('100000'), nullable=True),
        sa.Column('current_balance', sa.Float(), server_default=sa.text('100000'), nullable=True),
        sa.Column('borrowed', sa.Float(), server_default=sa.text('0'), nullable=True),
        sa.Column('updated_at', sa.String(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'virtual_positions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trade_id', sa.String(), nullable=True),
        sa.Column('ticker', sa.String(), nullable=True),
        sa.Column('side', sa.String(), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=True),
        sa.Column('entry_price', sa.Float(), nullable=True),
        sa.Column('stop_loss', sa.Float(), nullable=True),
        sa.Column('take_profit', sa.Float(), nullable=True),
        sa.Column('status', sa.String(), server_default=sa.text("'open'"), nullable=True),
        sa.Column('opened_at', sa.String(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('closed_at', sa.String(), nullable=True),
        sa.Column('close_price', sa.Float(), nullable=True),
        sa.Column('pnl', sa.Float(), server_default=sa.text('0'), nullable=True),
        sa.Column('commission', sa.Float(), server_default=sa.text('0'), nullable=True),
        sa.Column('strategy', sa.String(), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('leverage', sa.Float(), server_default=sa.text('1.0'), nullable=True),
        sa.Column('borrowed', sa.Float(), server_default=sa.text('0'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('trade_id'),
    )
    op.create_table(
        'equity_snapshots',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('timestamp', sa.String(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('total_value', sa.Float(), nullable=True),
        sa.Column('balance', sa.Float(), nullable=True),
        sa.Column('positions_value', sa.Float(), nullable=True),
        sa.Column('pnl', sa.Float(), nullable=True),
        sa.Column('borrowed', sa.Float(), nullable=True),
        sa.Column('margin_level', sa.Float(), nullable=True),
        sa.Column('positions_count', sa.Integer(), nullable=True),
        sa.Column('cycle_id', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'config_audit',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('timestamp', sa.String(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('section', sa.String(), nullable=True),
        sa.Column('param', sa.String(), nullable=True),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('source', sa.String(), server_default=sa.text("'dashboard'"), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'profit_locks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('locked_at', sa.String(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('equity', sa.Float(), nullable=True),
        sa.Column('initial_capital', sa.Float(), nullable=True),
        sa.Column('target_percent', sa.Float(), nullable=True),
        sa.Column('target_equity', sa.Float(), nullable=True),
        sa.Column('positions_closed', sa.Integer(), server_default=sa.text('0'), nullable=True),
        sa.Column('total_pnl', sa.Float(), server_default=sa.text('0'), nullable=True),
        sa.Column('unlock_after_cycle', sa.Integer(), server_default=sa.text('0'), nullable=True),
        sa.Column('status', sa.String(), server_default=sa.text("'active'"), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'scan_results',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('scan_time', sa.String(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('method', sa.String(), server_default=sa.text("'filter'"), nullable=True),
        sa.Column('total_scanned', sa.Integer(), server_default=sa.text('0'), nullable=True),
        sa.Column('filtered_count', sa.Integer(), server_default=sa.text('0'), nullable=True),
        sa.Column('selected_count', sa.Integer(), server_default=sa.text('0'), nullable=True),
        sa.Column('market_outlook', sa.String(), server_default=sa.text("'neutral'"), nullable=True),
        sa.Column('selected_tickers', sa.Text(), server_default=sa.text("'[]'"), nullable=True),
        sa.Column('all_candidates', sa.Text(), server_default=sa.text("'[]'"), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'scheduler_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('cycle_id', sa.String(), nullable=True),
        sa.Column('timestamp', sa.String(), nullable=True),
        sa.Column('tickers', sa.Text(), nullable=True),
        sa.Column('proposals', sa.Integer(), nullable=True),
        sa.Column('approved', sa.Integer(), nullable=True),
        sa.Column('executed', sa.Integer(), nullable=True),
        sa.Column('errors', sa.Integer(), nullable=True),
        sa.Column('error_msg', sa.Text(), nullable=True),
        sa.Column('capital', sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('scheduler_logs')
    op.drop_table('scan_results')
    op.drop_table('profit_locks')
    op.drop_table('config_audit')
    op.drop_table('equity_snapshots')
    op.drop_table('virtual_positions')
    op.drop_table('virtual_account')
    op.drop_table('trade_lessons')
    op.drop_table('trade_context')
    op.drop_table('agent_logs')
    op.drop_table('events')
    op.drop_table('trades')
