import datetime as dt
import sqlite3

from app.database import register_sqlite_functions


def test_historical_now_default_works_in_local_sqlite():
    connection = sqlite3.connect(":memory:")
    try:
        register_sqlite_functions(connection)
        connection.execute(
            "CREATE TABLE observations "
            "(id INTEGER PRIMARY KEY, created_at DATETIME DEFAULT (now()))"
        )
        connection.execute("INSERT INTO observations DEFAULT VALUES")
        created_at = connection.execute(
            "SELECT created_at FROM observations"
        ).fetchone()[0]
    finally:
        connection.close()

    parsed = dt.datetime.fromisoformat(created_at)
    assert parsed.tzinfo is not None
