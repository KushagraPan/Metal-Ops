"""report sample number text

Revision ID: 49ec9e1bddc0
Revises: 67f958817c9e
Create Date: 2026-11-10 18:15:48.607128

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '49ec9e1bddc0'
down_revision: Union[str, None] = '67f958817c9e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("spectro_reports", schema=None) as batch_op:
        batch_op.drop_constraint("sample_no_per_heat", type_="unique")
        if bind.dialect.name != "sqlite":
            batch_op.drop_constraint(
                "ck_spectro_reports_sample_no_positive", type_="check"
            )
        batch_op.alter_column(
            "sample_no",
            existing_type=sa.Integer(),
            type_=sa.String(length=50),
            existing_nullable=False,
            postgresql_using="sample_no::varchar",
        )


def downgrade() -> None:
    # The old schema only stored numeric sample numbers. Downgrading a report
    # whose sample number contains letters requires a manual data decision.
    bind = op.get_bind()
    with op.batch_alter_table("spectro_reports", schema=None) as batch_op:
        batch_op.alter_column(
            "sample_no",
            existing_type=sa.String(length=50),
            type_=sa.Integer(),
            existing_nullable=False,
            postgresql_using="sample_no::integer",
        )
        if bind.dialect.name != "sqlite":
            batch_op.create_check_constraint(
                "ck_spectro_reports_sample_no_positive", "sample_no > 0"
            )
        batch_op.create_unique_constraint(
            "sample_no_per_heat", ["heat_id", "sample_no"]
        )
