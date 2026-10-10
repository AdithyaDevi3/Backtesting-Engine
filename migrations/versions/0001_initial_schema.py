"""Create OHLCV and backtest result tables."""

from alembic import op
import sqlalchemy as sa


revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ohlcv",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "date", name="uq_ohlcv_ticker_date"),
    )
    op.create_index("ix_ohlcv_ticker", "ohlcv", ["ticker"])
    op.create_index("ix_ohlcv_lookup", "ohlcv", ["ticker", "date"])
    op.create_table(
        "backtest_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("strategy", sa.String(length=30), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("trades", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backtest_results_strategy", "backtest_results", ["strategy"])
    op.create_index("ix_backtest_results_ticker", "backtest_results", ["ticker"])
    op.create_index("ix_backtest_results_created_at", "backtest_results", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_backtest_results_created_at", table_name="backtest_results")
    op.drop_index("ix_backtest_results_ticker", table_name="backtest_results")
    op.drop_index("ix_backtest_results_strategy", table_name="backtest_results")
    op.drop_table("backtest_results")
    op.drop_index("ix_ohlcv_lookup", table_name="ohlcv")
    op.drop_index("ix_ohlcv_ticker", table_name="ohlcv")
    op.drop_table("ohlcv")
