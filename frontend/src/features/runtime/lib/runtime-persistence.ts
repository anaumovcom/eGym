import type { RuntimeWorkoutOutcome, RuntimeWorkoutSession, RuntimeWorkoutSummaryState } from '@/entities/runtime/model/types'
import { ApiError, apiPost } from '@/shared/api/client'

export type WorkoutSaveStatus = RuntimeWorkoutOutcome | 'in_progress'
export type LoadAdjustmentDirection = 'increase' | 'decrease'

export type LoadAdjustmentResponse = {
  userId: string
  exerciseSlug: string
  direction: LoadAdjustmentDirection
  loadLabel: string
  weightKg?: number | null
  reps?: number | null
  sets?: number | null
  restSeconds?: number | null
  trainingMode?: string | null
  trainingDayType?: string | null
  recommendation: string
}

function getSessionStartedAt(session: RuntimeWorkoutSession) {
  return session.startedAt ?? new Date(Date.now() - 60_000).toISOString()
}

function getDurationSeconds(session: RuntimeWorkoutSession) {
  const startedAt = Date.parse(getSessionStartedAt(session))
  if (Number.isNaN(startedAt)) {
    return 0
  }

  return Math.max(0, Math.round((Date.now() - startedAt) / 1000))
}

export function resolveWorkoutSaveStatus(session: RuntimeWorkoutSession): Exclude<WorkoutSaveStatus, 'in_progress'> {
  if (session.workoutSummary.outcome === 'aborted') {
    return 'aborted'
  }

  const outcomes = session.exerciseOutcomes ?? {}
  const hasIncompleteExercise = session.completedExerciseIds.some((exerciseId) => outcomes[exerciseId] && outcomes[exerciseId] !== 'completed')
  return session.workoutSummary.outcome === 'partial' || hasIncompleteExercise ? 'partial' : 'completed'
}

export async function saveWorkoutToBackend(session: RuntimeWorkoutSession, userId: string, status: WorkoutSaveStatus) {
  const finishedAt = status === 'in_progress' ? undefined : new Date().toISOString()
  return apiPost<RuntimeWorkoutSummaryState>('/api/runtime/workouts', {
    workoutSessionId: session.backendWorkoutSessionId,
    userId,
    source: session.source,
    title: session.workoutTitle,
    subtitle: session.workoutSubtitle,
    status,
    startedAt: getSessionStartedAt(session),
    finishedAt,
    durationSeconds: getDurationSeconds(session),
    feeling: session.workoutSummary.feeling,
    discomfort: session.workoutSummary.discomfort,
    exerciseSessionIds: Object.values(session.backendExerciseSessionIds ?? {}),
    exercises: [],
  })
}

/**
 * Drops the saved sets of the given exercises before they are done again.
 * Returns the ids whose backend record is already gone, so the redo creates fresh ones.
 */
export async function resetExercisesOnBackend(session: RuntimeWorkoutSession, exercises: RuntimeWorkoutSession['exercises'], userId: string) {
  const staleIds: string[] = []
  for (const exercise of exercises) {
    const exerciseSessionId = session.backendExerciseSessionIds?.[exercise.id]
    if (!exerciseSessionId) continue
    try {
      await apiPost('/api/runtime/exercises', {
        exerciseSessionId,
        userId,
        workoutSessionId: session.backendWorkoutSessionId,
        exerciseSlug: exercise.slug,
        exerciseName: exercise.name,
        exerciseSecondaryName: exercise.secondaryName,
        kind: exercise.kind,
        orderIndex: exercise.order,
        status: 'in_progress',
        startedAt: new Date(Date.now() - 90_000).toISOString(),
        finishedAt: new Date().toISOString(),
        calibrationState: exercise.calibrationState,
        targetSets: exercise.plan.length,
        trainingMode: exercise.strengthMode.id,
        trainingDayType: exercise.strengthMode.dayType,
        muscles: exercise.muscles.map((name, index) => ({ muscleId: name, name, role: index === 0 ? 'primary' : 'secondary' })),
        sets: [],
        resetSets: true,
      })
    } catch (error) {
      // the record is already gone: nothing to clear
      if (!(error instanceof ApiError && error.status === 404)) throw error
      staleIds.push(exercise.id)
    }
  }
  return staleIds
}

export async function adjustExerciseLoadOnBackend({
  userId,
  exerciseSlug,
  direction,
  trainingMode,
  trainingDayType,
  kind,
  currentWeightKg,
  currentReps,
  currentSets,
  restSeconds,
}: {
  userId: string
  exerciseSlug: string
  direction: LoadAdjustmentDirection
  trainingMode?: string | null
  trainingDayType?: string | null
  kind?: string | null
  currentWeightKg?: number | null
  currentReps?: number | null
  currentSets?: number | null
  restSeconds?: number | null
}) {
  return apiPost<LoadAdjustmentResponse>('/api/runtime/exercises/load-adjustment', {
    userId,
    exerciseSlug,
    direction,
    trainingMode,
    trainingDayType,
    kind,
    currentWeightKg,
    currentReps,
    currentSets,
    restSeconds,
  })
}
