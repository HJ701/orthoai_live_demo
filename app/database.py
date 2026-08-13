from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

engine_kwargs = {}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}


def register_sqlite_functions(dbapi_connection, _connection_record=None):
    """Provide functions referenced by the historical SQLite migration DDL."""

    dbapi_connection.create_function(
        "now",
        0,
        lambda: datetime.now(timezone.utc).isoformat(sep=" "),
    )


engine = create_engine(settings.database_url, pool_pre_ping=True, **engine_kwargs)

if settings.database_url.startswith("sqlite"):
    event.listen(engine, "connect", register_sqlite_functions)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
