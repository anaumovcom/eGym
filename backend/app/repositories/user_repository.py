from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.models.enums import GoalType
from app.models.profile import UserGoal, UserProfile
from app.models.user import User
from app.schemas.user import UserProfileUpdateSchema


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
        return user

    def update_profile(self, session: Session, user_id: str, payload: UserProfileUpdateSchema) -> User | None:
        user = self.get_user(session, user_id)
        if user is None:
            return None

        user.name = payload.name.strip()
        profile = user.profile
        if profile is None:
            profile = UserProfile(user_id=user.id)
            user.profile = profile
            session.add(profile)
        profile.birth_date = payload.birth_date
        profile.height_cm = payload.height_cm
        profile.weight_kg = payload.weight_kg
        profile.notes = payload.notes

        primary_goal = next((goal for goal in user.goals if goal.is_primary), user.goals[0] if user.goals else None)
        try:
            goal_type = GoalType(payload.goal_type)
        except ValueError:
            goal_type = GoalType.habit
        if primary_goal is None:
            primary_goal = UserGoal(user_id=user.id, goal_type=goal_type, label=payload.goal_label.strip(), is_primary=True)
            user.goals.append(primary_goal)
            session.add(primary_goal)
        primary_goal.goal_type = goal_type
        primary_goal.label = payload.goal_label.strip()
        primary_goal.target_value = payload.target_value
        primary_goal.target_unit = payload.target_unit
        primary_goal.is_primary = True
        session.flush()
        return user
