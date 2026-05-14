from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db.session import get_db_session


def get_session() -> Iterator[Session]:
    yield from get_db_session()
