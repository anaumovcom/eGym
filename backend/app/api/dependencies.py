from collections.abc import Callable, Iterator

from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db_session


def get_session() -> Iterator[Session]:
    yield from get_db_session()


def get_session_factory() -> Callable[[], Session]:
    """Long-lived connections (coach live socket) open short sessions per step, never one per connection."""
    return SessionLocal
