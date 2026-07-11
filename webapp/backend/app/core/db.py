"""
Database engine + session.

SQLite for pilot (single-file, zero-ops); the same SQLModel code runs on
Postgres for production by changing DATABASE_URL only. WAL mode + a busy
timeout give safe concurrent reads/writes — replacing the non-atomic JSON
read-modify-write that caused audit finding C-2.
"""
import os
from pathlib import Path
from contextlib import contextmanager
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy import event

_DEFAULT = f"sqlite:///{Path(__file__).parent.parent / 'engine' / 'nexus.db'}"
DATABASE_URL = os.getenv("DATABASE_URL", _DEFAULT)
# Railway/Heroku-style URLs sometimes use the old "postgres://" scheme;
# SQLAlchemy 1.4+ requires "postgresql://" and raises on the old one.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=_connect_args)


if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")     # concurrent readers + one writer
        cur.execute("PRAGMA busy_timeout=5000;")    # wait for locks instead of failing
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.close()


def run_alembic_upgrade():
    """The real schema bootstrap: run every migration up to head via Alembic,
    same as `alembic upgrade head` on the CLI. This is what makes schema
    changes safe going forward — a new column ships as a migration file,
    not a silent create_all() no-op against an already-existing table."""
    from alembic.config import Config
    from alembic import command
    backend_dir = Path(__file__).parent.parent.parent
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(cfg, "head")


def init_db():
    """Dev/test convenience only — creates tables directly from the current
    models with no migration history. Production and any environment that
    cares about schema evolution should call `run_alembic_upgrade()` instead."""
    from . import models  # noqa: F401
    SQLModel.metadata.create_all(engine)


def get_session():
    """FastAPI dependency — yields a request-scoped session."""
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope():
    """Transactional scope for scripts/services: commit on success, roll back
    on error. Atomicity here is what kills the lost-update / corruption class."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
