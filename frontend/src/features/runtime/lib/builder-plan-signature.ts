import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'

/** Immutable server-plan identity, independent of runtime edits and restored settings. */
export function getBuilderPlanSignature(session: RuntimeWorkoutSession) {
  return JSON.stringify({
    title: session.workoutTitle,
    exercises: session.exercises.map(exercise => ({
      id: exercise.id,
      slug: exercise.slug,
      kind: exercise.kind,
      perSide: Boolean(exercise.perSide),
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
    })),
  })
}