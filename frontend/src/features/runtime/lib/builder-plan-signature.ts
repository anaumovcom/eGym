import type { RuntimeExercisePlan, RuntimeWorkoutSession } from '@/entities/runtime/model/types'

const STRUCTURE_VERSION = 2

/**
 * Immutable server-plan identity: the workout and its exercises, in order.
 * Loads are not part of it: they come from the exercise profiles shared by every workout and
 * legitimately change during a run (a new weight, a load adjustment, an edit in "Мои тренировки").
 */
export function getBuilderPlanSignature(session: RuntimeWorkoutSession) {
  return JSON.stringify({
    version: STRUCTURE_VERSION,
    title: session.workoutTitle,
    exercises: session.exercises.map(exercise => ({ id: exercise.id, slug: exercise.slug })),
  })
}

/** Older persisted runs signed loads too; their identity is re-derived from the run's own structure. */
export function getStoredBuilderPlanSignature(session: RuntimeWorkoutSession) {
  const signature = session.builderPlanSignature
  return signature?.startsWith(`{"version":${STRUCTURE_VERSION},`) ? signature : getBuilderPlanSignature(session)
}

/** Server load of one exercise: lets a run tell server changes apart from its own local edits. */
export function getBuilderExerciseSignature(exercise: RuntimeExercisePlan) {
  return JSON.stringify({
    kind: exercise.kind,
    perSide: Boolean(exercise.perSide),
    strengthMode: [exercise.strengthMode.id, exercise.strengthMode.dayType ?? null],
    sets: exercise.plan.map(plan => ({
      targetReps: plan.targetReps,
      targetMinReps: plan.targetMinReps,
      targetMaxReps: plan.targetMaxReps,
      targetSeconds: plan.targetSeconds,
      recommendedWeightKg: plan.recommendedWeightKg,
      restSeconds: plan.restSeconds,
      side: plan.side,
      roundNumber: plan.roundNumber,
      setType: plan.setType ?? null,
    })),
  })
}

export function getBuilderExerciseSignatures(session: RuntimeWorkoutSession) {
  return Object.fromEntries(session.exercises.map(exercise => [exercise.id, getBuilderExerciseSignature(exercise)]))
}
