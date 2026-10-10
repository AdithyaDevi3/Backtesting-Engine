"""Add reusable backtest configurations."""

from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_configurations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("strategy", sa.String(length=30), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("initial_capital", sa.Float(), nullable=False),
        sa.Column("execution_model", sa.String(length=20), nullable=False),
        sa.Column("commission", sa.Float(), nullable=False),
        sa.Column("slippage_bps", sa.Float(), nullable=False),
        sa.Column("position_size_pct", sa.Float(), nullable=False),
        sa.Column("stop_loss_pct", sa.Float(), nullable=True),
        sa.Column("take_profit_pct", sa.Float(), nullable=True),
        sa.Column("fractional_shares", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saved_configurations_created_at", "saved_configurations", ["created_at"])
    op.create_index("ix_saved_configurations_name", "saved_configurations", ["name"], unique=True)
    op.create_index("ix_saved_configurations_strategy", "saved_configurations", ["strategy"])
    op.create_index("ix_saved_configurations_ticker", "saved_configurations", ["ticker"])


def downgrade() -> None:
    op.drop_index("ix_saved_configurations_ticker", table_name="saved_configurations")
    op.drop_index("ix_saved_configurations_strategy", table_name="saved_configurations")
    op.drop_index("ix_saved_configurations_name", table_name="saved_configurations")
    op.drop_index("ix_saved_configurations_created_at", table_name="saved_configurations")
    op.drop_table("saved_configurations")
