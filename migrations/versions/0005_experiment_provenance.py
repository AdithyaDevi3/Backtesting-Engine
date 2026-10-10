"""Persist reproducible experiment provenance."""

from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "backtest_results",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="completed"),
    )
    op.add_column("backtest_results", sa.Column("request_snapshot", sa.JSON(), nullable=True))
    op.add_column("backtest_results", sa.Column("request_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("backtest_results", sa.Column("engine_revision", sa.String(length=80), nullable=True))
    op.add_column("backtest_results", sa.Column("data_fingerprint", sa.String(length=64), nullable=True))
    op.add_column("backtest_results", sa.Column("data_row_count", sa.Integer(), nullable=True))
    op.add_column("backtest_results", sa.Column("data_start", sa.Date(), nullable=True))
    op.add_column("backtest_results", sa.Column("data_end", sa.Date(), nullable=True))
    op.add_column("backtest_results", sa.Column("source_result_id", sa.Integer(), nullable=True))
    op.create_index("ix_backtest_results_status", "backtest_results", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_backtest_results_status", table_name="backtest_results")
    op.drop_column("backtest_results", "source_result_id")
    op.drop_column("backtest_results", "data_end")
    op.drop_column("backtest_results", "data_start")
    op.drop_column("backtest_results", "data_row_count")
    op.drop_column("backtest_results", "data_fingerprint")
    op.drop_column("backtest_results", "engine_revision")
    op.drop_column("backtest_results", "request_fingerprint")
    op.drop_column("backtest_results", "request_snapshot")
    op.drop_column("backtest_results", "status")
