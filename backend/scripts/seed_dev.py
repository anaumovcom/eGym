import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine

from app.db.base import Base
from app.db.seed import seed_dev_data
from app.db.session import SessionLocal, settings


def main() -> None:
    engine = create_engine(
        settings.database_url,
        future=True,
        connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    )
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        seed_dev_data(session)
    print("Seed data loaded")


if __name__ == "__main__":
    main()
