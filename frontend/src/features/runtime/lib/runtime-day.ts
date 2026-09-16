import type { RuntimeView, RuntimeWorkoutSession } from '@/entities/runtime/model/types'

const TRAINING_DAY_RESET_HOUR = 3

export function getTrainingDayStart(reference = new Date()) {
  const dayStart = new Date(reference)
  dayStart.setHours(TRAINING_DAY_RESET_HOUR, 0, 0, 0)
  if (reference.getTime() < dayStart.getTime()) {
    dayStart.setDate(dayStart.getDate() - 1)
  }
  return dayStart
}

export function isSessionInCurrentTrainingDay(session: Pick<RuntimeWorkoutSession, 'startedAt'> | null | undefined, reference = new Date()) {
  if (!session?.startedAt) {
    return false
  }

  const startedAt = new Date(session.startedAt)
  if (Number.isNaN(startedAt.getTime())) {
    return false
  }

  return startedAt.getTime() >= getTrainingDayStart(reference).getTime()
}

export function getRuntimeResumeView(session: Pick<RuntimeWorkoutSession, 'view' | 'photoProgress'>): RuntimeView {
  if (session.view === 'photo-progress') {
    return session.photoProgress.mode === 'post-workout' ? 'workout-summary' : 'exercise-setup'
  }

  return session.view
}

export function runtimeViewPath(view: RuntimeView) {
  switch (view) {
    case 'photo-progress':
      return '/exercise-setup'
    case 'exercise-session':
      return '/exercise-session'
    case 'rest':
      return '/rest'
    case 'exercise-summary':
      return '/exercise-summary'
    case 'workout-summary':
      return '/workout-summary'
    case 'exercise-setup':
    default:
      return '/exercise-setup'
  }
}