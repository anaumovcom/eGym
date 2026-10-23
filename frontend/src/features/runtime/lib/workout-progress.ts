import type { RuntimeSetResult, RuntimeWorkoutSession } from '@/entities/runtime/model/types'

type RuntimeExercise = RuntimeWorkoutSession['exercises'][number]

export type WorkoutExerciseStatus = 'done' | 'partial' | 'skipped' | 'current' | 'pending'
export type WorkoutSetStatus = 'done' | 'partial' | 'current' | 'next' | 'pending'

export type WorkoutSetStep = {
  index: number
  label: string
  side?: 'left' | 'right'
  status: WorkoutSetStatus
  /** Opening a done set redoes it and every later set of the exercise. */
  redo: boolean
  available: boolean
}

export type WorkoutExerciseProgress = {
  exercise: RuntimeExercise
  status: WorkoutExerciseStatus
  doneSets: number
  totalSets: number
  /** Next set to do, null once every set is done. */
  nextSetIndex: number | null
  sets: WorkoutSetStep[]
}

function isPartialResult(result: RuntimeSetResult) {
  return result.completionStatus === 'partial' || result.actualValue < (result.targetMinReps ?? result.plannedValue)
}

/** The step the workout is on: the next set of the current exercise, none after an exercise or the workout ended. */
export function getCurrentWorkoutStep(session: RuntimeWorkoutSession) {
  if (session.view === 'exercise-summary' || session.view === 'workout-summary' || session.completedExerciseIds.includes(session.currentExerciseId)) {
    return null
  }
  const exercise = session.exercises.find((item) => item.id === session.currentExerciseId)
  if (!exercise) return null
  const doneSets = session.completedSets[exercise.id]?.length ?? 0
  return { exerciseId: exercise.id, setIndex: Math.min(doneSets, Math.max(0, exercise.plan.length - 1)) }
}

/** Sets are done in order: any done set can be redone, otherwise only the next one can be opened. */
export function canJumpToWorkoutStep(session: RuntimeWorkoutSession, exerciseId: string, setIndex: number) {
  const exercise = session.exercises.find((item) => item.id === exerciseId)
  if (!exercise || !Number.isInteger(setIndex) || setIndex < 0 || setIndex >= exercise.plan.length) return false
  if (setIndex > (session.completedSets[exerciseId]?.length ?? 0)) return false
  const current = getCurrentWorkoutStep(session)
  return !(current && current.exerciseId === exerciseId && current.setIndex === setIndex)
}

export function getWorkoutProgress(session: RuntimeWorkoutSession): WorkoutExerciseProgress[] {
  const current = getCurrentWorkoutStep(session)
  return session.exercises.map((exercise) => {
    const results = session.completedSets[exercise.id] ?? []
    const totalSets = exercise.plan.length
    const doneSets = Math.min(results.length, totalSets)
    const outcome = session.exerciseOutcomes?.[exercise.id]
    const isCurrent = current?.exerciseId === exercise.id
    const finished = session.completedExerciseIds.includes(exercise.id)
    const status: WorkoutExerciseStatus = isCurrent
      ? 'current'
      : (finished && outcome === 'completed') || (doneSets >= totalSets && totalSets > 0)
        ? (results.some(isPartialResult) || outcome === 'partial' ? 'partial' : 'done')
        : doneSets > 0
          ? 'partial'
          : finished
            ? 'skipped'
            : 'pending'
    const nextSetIndex = doneSets < totalSets ? doneSets : null

    const sets = exercise.plan.map((plan, index): WorkoutSetStep => {
      const result = results[index]
      const setStatus: WorkoutSetStatus = result
        ? (isPartialResult(result) ? 'partial' : 'done')
        : isCurrent && current.setIndex === index
          ? 'current'
          : index === nextSetIndex
            ? 'next'
            : 'pending'
      const round = plan.roundNumber ?? index + 1
      return {
        index,
        label: plan.side ? `${round}${plan.side === 'left' ? 'Л' : 'П'}` : String(index + 1),
        side: plan.side,
        status: setStatus,
        redo: Boolean(result),
        available: canJumpToWorkoutStep(session, exercise.id, index),
      }
    })

    return { exercise, status, doneSets, totalSets, nextSetIndex, sets }
  })
}

export function describeWorkoutSet(exercise: RuntimeExercise, setIndex: number) {
  const plan = exercise.plan[setIndex]
  if (!plan) return `подход ${setIndex + 1}`
  if (plan.side) return `подход ${plan.roundNumber ?? setIndex + 1} · ${plan.side === 'left' ? 'левая сторона' : 'правая сторона'}`
  return `подход ${setIndex + 1}`
}

/** Short progress of an unfinished workout for the home indicator. */
export function getWorkoutResumeSummary(session: RuntimeWorkoutSession) {
  const progress = getWorkoutProgress(session)
  const doneExercises = progress.filter((item) => item.status === 'done').length
  const doneSets = progress.reduce((total, item) => total + item.doneSets, 0)
  const totalSets = progress.reduce((total, item) => total + item.totalSets, 0)
  const current = getCurrentWorkoutStep(session)
  const currentExercise = current ? session.exercises.find((item) => item.id === current.exerciseId) : undefined
  return {
    doneExercises,
    totalExercises: session.exercises.length,
    doneSets,
    totalSets,
    nextLabel: currentExercise && current ? `${currentExercise.name} · ${describeWorkoutSet(currentExercise, current.setIndex)}` : null,
  }
}
