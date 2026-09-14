"""Add due dates to PTGOTW assignments."""

from alembic import op
import sqlalchemy as sa

revision = "20260913_0006"
down_revision = "20260913_0005"


def upgrade():
    op.add_column("ptgotw_writeups", sa.Column("due_date", sa.Date(), nullable=True))


def downgrade():
    op.drop_column("ptgotw_writeups", "due_date")
