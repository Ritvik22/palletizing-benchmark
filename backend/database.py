"""Shared database configuration for the admin API and public dataset readers."""
import os
from pathlib import Path
import sqlite3
import tempfile

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker


_SEED = Path(__file__).with_name('palletizer.db')
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    data_dir = os.environ.get('DATA_DIR')
    target = Path(data_dir).resolve() / 'palletizer.db' if data_dir else _SEED
    if data_dir:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            # Publish a complete seed atomically; never overwrite persisted data.
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as f:
                temporary = Path(f.name)
            try:
                with sqlite3.connect(f'{_SEED.as_uri()}?mode=ro', uri=True) as source:
                    with sqlite3.connect(temporary) as destination:
                        source.backup(destination)
                try:
                    os.link(temporary, target)
                except FileExistsError:
                    pass
            finally:
                temporary.unlink(missing_ok=True)
    DATABASE_URL = f'sqlite:///{target}'

_url = make_url(DATABASE_URL)
engine = create_engine(
    DATABASE_URL,
    connect_args={'check_same_thread': False, 'timeout': 30} if _url.get_backend_name() == 'sqlite' else {},
)
if _url.get_backend_name() == 'sqlite':
    @event.listens_for(engine, 'connect')
    def _enable_sqlite_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
