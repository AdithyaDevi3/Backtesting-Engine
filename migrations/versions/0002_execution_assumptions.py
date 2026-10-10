"""Persist backtest execution assumptions."""

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "backtest_results",
        sa.Column("execution_model", sa.String(length=20), nullable=False, server_default="next_open"),
    )
    op.add_column(
        "backtest_results",
        sa.Column("commission", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "backtest_results",
        sa.Column("slippage_bps", sa.Float(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("backtest_results", "slippage_bps")
    op.drop_column("backtest_results", "commission")
    op.drop_column("backtest_results", "execution_model")
