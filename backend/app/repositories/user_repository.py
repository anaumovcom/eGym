from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.models.user import User


class UserRepository:
    def list_users(self, session: Session) -> list[User]:
        statement = select(User).where(User.is_active.is_(True)).order_by(User.name)
        return list(session.scalars(statement))

    def get_user(self, session: Session, user_id: str) -> User | None:
        statement = (
            select(User)
            .where(User.id == user_id)
            .options(joinedload(User.profile), joinedload(User.goals), joinedload(User.body_measurements))
        )
        return session.scalars(statement).unique().first()

    def get_current_user(self, session: Session) -> User | None:
        statement = (
            select(User)
            .where(User.is_current.is_(True))
            .options(joinedload(User.profile), joinedload(User.goals), joinedload(User.body_measurements))
        )
        return session.scalars(statement).unique().first()

    def set_current_user(self, session: Session, user_id: str) -> User | None:
        user = self.get_user(session, user_id)
        if user is None:
            return None

        session.execute(update(User).values(is_current=False))
        user.is_current = True
        session.add(user)
        session.flush()
        return self.get_user(session, user_id)
