from enum import StrEnum


class AccessRole(StrEnum):
    member = "member"
    coach = "coach"
    admin = "admin"
    service = "service"


class UserAccent(StrEnum):
    gold = "gold"
    green = "green"


class MachineState(StrEnum):
    ready = "ready"
    warning = "warning"
    blocked = "blocked"


class DriveState(StrEnum):
    connected = "connected"
    warning = "warning"
    error = "error"


class SafetyState(StrEnum):
    enabled = "enabled"
    disabled = "disabled"
    emergency_stop = "emergency_stop"


class GoalType(StrEnum):
    strength = "strength"
    body_composition = "body_composition"
    habit = "habit"


class NotificationTone(StrEnum):
    info = "info"
    warning = "warning"
    blocked = "blocked"


class SafetySeverity(StrEnum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AuditSeverity(StrEnum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AuditAction(StrEnum):
    user_selected = "user_selected"
    emergency_stop = "emergency_stop"
    settings_changed = "settings_changed"


class RuntimeExerciseKind(StrEnum):
    machine = "machine"
    bodyweight = "bodyweight"
    timed = "timed"
    stretch = "stretch"
    group = "group"


class WorkoutSessionStatus(StrEnum):
    in_progress = "in_progress"
    completed = "completed"
    partial = "partial"
    aborted = "aborted"


class ExerciseSessionStatus(StrEnum):
    in_progress = "in_progress"
    completed = "completed"
    partial = "partial"
    aborted = "aborted"
    skipped = "skipped"


class RuntimeFlowSource(StrEnum):
    quick_start = "quick-start"
    planned_workout = "planned_workout"
    today = "today"
    calendar = "calendar"
    programs = "programs"
    builder = "builder"
    catalog = "catalog"
    progress = "progress"


class RuntimePhotoMode(StrEnum):
    pre_workout = "pre-workout"
    post_workout = "post-workout"
    manual = "manual"


class RuntimePhotoView(StrEnum):
    front = "front"
    side = "side"
    back = "back"


class MuscleRole(StrEnum):
    primary = "primary"
    secondary = "secondary"
    assisting = "assisting"
    stabilizer = "stabilizer"


class FatigueEventSource(StrEnum):
    exercise_set = "exercise_set"
    exercise_summary = "exercise_summary"
    workout_summary = "workout_summary"
    manual_adjustment = "manual_adjustment"


class FeelingLevel(StrEnum):
    great = "great"
    easy = "easy"
    strong = "strong"
    normal = "normal"
    tired = "tired"
    hard = "hard"
    exhausted = "exhausted"


class DiscomfortLevel(StrEnum):
    none = "none"
    light = "light"
    minor = "minor"
    moderate = "moderate"
    high = "high"
    reduce_next_time = "reduce-next-time"


class ProgressPeriod(StrEnum):
    days_7 = "7d"
    days_30 = "30d"
    months_3 = "3m"
    months_6 = "6m"
    year_1 = "1y"
    all_time = "all"
