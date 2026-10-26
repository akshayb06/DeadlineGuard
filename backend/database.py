import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

DATA = Path(__file__).resolve().parents[1] / 'data'
DATA.mkdir(exist_ok=True)
DB_URL = os.environ.get("DG_DB", f"sqlite:///{DATA / 'deadlineguard.db'}")

# check_same_thread=False lets FastAPI's worker threads share the SQLite file
engine = create_engine(DB_URL, connect_args={"check_same_thread": False, 'timeout': 20})

@event.listens_for(engine, 'connect')
def configure_sqlite(connection, _):
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('PRAGMA journal_mode=WAL')
SessionLocal = sessionmaker(bind=engine, autoflush=False)
Base = declarative_base()


def get_db():
    """FastAPI dependency: opens a DB session per request, always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
