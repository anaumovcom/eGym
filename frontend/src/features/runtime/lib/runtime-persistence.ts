import type { RuntimeSetResult, RuntimeWorkoutOutcome, RuntimeWorkoutSession, RuntimeWorkoutSummaryState } from '@/entities/runtime/model/types'
import { apiPost } from '@/shared/api/client'

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

/** Full declared intent, never reconstructed from completed summaries/results. */
export function buildCoachWorkoutPlan(session: RuntimeWorkoutSession) {
  if (!session.exercises.length || session.exercises.length > 100
    || session.exercises.reduce((sum, e) => sum + e.plan.length, 0) > 2000
    || session.exercises.some(e => !e.plan.length || e.plan.length > 100)) return null
  return {
    schemaVersion: 1,
    origin: 'declared-client-plan',
    exercises: session.exercises.map(exercise => ({
      exerciseId: exercise.id,
      orderIndex: exercise.order,
      slug: exercise.slug,
      kind: exercise.kind,
      perSide: exercise.perSide ?? false,
      trainingMode: exercise.strengthMode.id,
      trainingDayType: exercise.strengthMode.dayType ?? null,
      sets: exercise.plan.map((set, index) => {
        const exact = set.targetSeconds ?? set.targetReps
        const ranged = set.targetMinReps != null && set.targetMaxReps != null && set.targetMinReps !== set.targetMaxReps
        const open = set.setType === 'failure'
        const value = exact ?? set.targetMaxReps
        return {
          ordinal: set.setNumber ?? index + 1,
          side: set.side ?? null,
          roundNumber: set.roundNumber ?? null,
          setType: set.setType === 'warmup' ? 'warmup' : 'working',
          targetType: open ? 'open' : ranged ? 'range' : value != null && value > 0 ? 'exact' : 'unknown',
          unit: exercise.kind === 'timed' || exercise.kind === 'stretch' ? 'seconds' : 'reps',
          minimum: open ? null : ranged ? set.targetMinReps : value != null && value > 0 ? value : null,
          maximum: open ? null : ranged ? set.targetMaxReps : value != null && value > 0 ? value : null,
          plannedWeightKg: set.recommendedWeightKg ?? (exercise.kind === 'machine' ? exercise.loadSettings.weight : 0),
          restSeconds: set.restSeconds,
        }
      }),
    })),
  }
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
    coachPlan: buildCoachWorkoutPlan(session),
  })
}

type RuntimeExercise = RuntimeWorkoutSession['exercises'][number]

export function shouldSaveSetResult(result: RuntimeSetResult) {
  return result.completionStatus !== 'skipped' && Math.max(result.actualValue, result.reps ?? 0) > 0
}

export function toBackendSetPayload(exercise: RuntimeExercise, result: RuntimeSetResult) {
  const open = exercise.plan[result.setNumber - 1]?.setType === 'failure'
  return {
    setNumber: result.setNumber,
    plannedValue: open ? 0 : result.plannedValue,
    actualValue: result.actualValue,
    setType: result.setType,
    targetMinReps: open ? null : result.targetMinReps,
    targetMaxReps: open ? null : result.targetMaxReps,
    reps: result.reps,
    weightKg: result.weightKg,
    tempoLabel: result.tempoLabel,
    amplitudePercent: result.amplitudePercent,
    restDurationSeconds: exercise.plan[result.setNumber - 1]?.restSeconds,
    rir: result.rir,
    subjectiveEffort: result.subjectiveEffort,
    discomfortLevel: result.discomfortLevel,
    pain: result.pain,
    techniqueBreakdown: result.techniqueBreakdown,
    comment: result.comment,
    syncLabel: result.syncLabel,
    machineMetrics: {
      ...(exercise.loadSettings.mode === 'Обычный вес' || exercise.loadSettings.mode === 'constant' ? { loadMode: 'constant' } : {}),
      ...(open ? { targetType: 'open' } : {}),
      trainingMode: exercise.strengthMode.id,
      trainingDayType: exercise.strengthMode.dayType,
      // Warm-up/pyramid sets lift a share of it: the exercise profile remembers the working weight.
      workingWeightKg: exercise.loadSettings.weight,
      completionStatus: result.completionStatus,
      side: result.side,
      roundNumber: result.roundNumber,
    },
  }
}

function buildExerciseResetPayload(session: RuntimeWorkoutSession, exercise: RuntimeExercise, exerciseSessionId: number, userId: string) {
  return {
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
    finishedAt: null,
    calibrationState: exercise.calibrationState,
    targetSets: exercise.plan.length,
    perSide: exercise.perSide ?? false,
    plannedTotal: exercise.plan.reduce((total, plan) => total + (plan.targetSeconds ?? plan.targetMaxReps ?? plan.targetReps ?? 0), 0),
    trainingMode: exercise.strengthMode.id,
    trainingDayType: exercise.strengthMode.dayType,
    muscles: exercise.muscles.map((name, index) => ({ muscleId: name, name, role: index === 0 ? 'primary' : 'secondary' })),
    sets: [] as ReturnType<typeof toBackendSetPayload>[],
    resetSets: true,
  }
}

/**
 * Drops the saved sets of the given exercises before they are done again.
 * Returns the ids whose backend record is already gone, so the redo creates fresh ones.
 */
export async function resetExercisesOnBackend(session: RuntimeWorkoutSession, exercises: RuntimeWorkoutSession['exercises'], userId: string) {
  const resets = exercises.flatMap((exercise) => {
    const exerciseSessionId = session.backendExerciseSessionIds?.[exercise.id]
    return exerciseSessionId ? [buildExerciseResetPayload(session, exercise, exerciseSessionId, userId)] : []
  })
  if (!resets.length) return []
  // Both exercises are reset in one transaction: a failed second reset must not erase the first.
  const response = await apiPost<{ missingExerciseSessionIds: number[] }>('/api/runtime/exercises/reset', { exercises: resets })
  return exercises.filter(exercise => response.missingExerciseSessionIds.includes(session.backendExerciseSessionIds?.[exercise.id] ?? -1))
    .map(exercise => exercise.id)
}

/**
 * Keeps only the first `keepSets` saved sets of an exercise that is done again from a later set.
 * Returns the ids whose backend record is already gone, like resetExercisesOnBackend.
 */
export async function truncateExerciseOnBackend(session: RuntimeWorkoutSession, exercise: RuntimeExercise, keepSets: number, userId: string) {
  const results = session.completedSets[exercise.id] ?? []
  const exerciseSessionId = session.backendExerciseSessionIds?.[exercise.id]
  if (!exerciseSessionId || results.length <= keepSets) return []
  if (keepSets <= 0) return resetExercisesOnBackend(session, [exercise], userId)

  // One request clears the sets and writes the kept ones back, so a failure never leaves a half-truncated exercise.
  await apiPost('/api/runtime/exercises', {
    ...buildExerciseResetPayload(session, exercise, exerciseSessionId, userId),
    sets: results.slice(0, keepSets).filter(shouldSaveSetResult).map((result) => toBackendSetPayload(exercise, result)),
  })
  return []
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
