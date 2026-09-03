"""orca/db — SQLAlchemy models + repositories over infra/db/001_init.sql
(plan §5.3, D1 Day 8). No Alembic: there are no ORM-as-source-of-truth
models here, `infra/db/001_init.sql` (applied by `infra/db/migrate.sh`) is
the schema source of truth and these models follow it, they do not lead it —
same rule ORCAState follows against the architecture doc.
"""
