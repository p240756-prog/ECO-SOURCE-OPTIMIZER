from sqlalchemy import text

from app.db.sessions import get_db


def test_database_connection():
    """
    Verify that the application can create a working
    database session and execute a basic SQL query.
    """

    db_generator = get_db()
    db = next(db_generator)

    try:
        result = db.execute(text("SELECT 1"))
        assert result.scalar() == 1

    finally:
        try:
            next(db_generator)
        except StopIteration:
            pass