"""Keep autosaved writeup drafts separate from published content."""

from alembic import op
import sqlalchemy as sa

revision = "20260923_0010"
down_revision = "20260914_0009"


def upgrade():
    op.add_column("ptgotw_writeups", sa.Column("draft", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("ptgotw_writeups", "draft")
