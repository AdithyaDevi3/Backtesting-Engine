"""Persist position sizing and exit controls."""

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "backtest_results",
        sa.Column("position_size_pct", sa.Float(), nullable=False, server_default="100"),
    )
    op.add_column("backtest_results", sa.Column("stop_loss_pct", sa.Float(), nullable=True))
    op.add_column("backtest_results", sa.Column("take_profit_pct", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("backtest_results", "take_profit_pct")
    op.drop_column("backtest_results", "stop_loss_pct")
    op.drop_column("backtest_results", "position_size_pct")
