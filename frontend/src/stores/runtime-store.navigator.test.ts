import { beforeEach, describe, expect, it } from 'vitest'
import { canJumpToWorkoutStep, getCurrentWorkoutStep, getWorkoutProgress, getWorkoutResumeSummary } from '@/features/runtime/lib/workout-progress'
import { useAppStore } from '@/stores/app-store'
import { getNextPendingExercise, useRuntimeStore } from '@/stores/runtime-store'

function session() {
  return useRuntimeStore.getState().session!
}

function finishWholeExercise() {
  const store = useRuntimeStore.getState()
  const exercise = session().exercises.find((item) => item.id === session().currentExerciseId)!
  for (let index = 0; index < exercise.plan.length; index += 1) {
    store.finishCurrentSet()
    if (session().view === 'rest') store.beginNextStep()
  }
}

describe('workout navigator jumps', () => {
  beforeEach(() => {
    localStorage.clear()
    useAppStore.setState({ selectedUserId: 'alexey' })
    useRuntimeStore.setState({ session: null, sessionSignature: null })
    useRuntimeStore.getState().initializeSession({ source: 'today' })
  })

  it('has a multi-set, multi-exercise workout to navigate', () => {
    expect(session().exercises.length).toBeGreaterThanOrEqual(3)
    expect(session().exercises[0].plan.length).toBeGreaterThanOrEqual(2)
  })

  it('leaves a started exercise as partial when jumping forward and keeps its sets', () => {
    const [first, second, third] = session().exercises
    useRuntimeStore.getState().finishCurrentSet()
    expect(session().view).toBe('rest')

    expect(useRuntimeStore.getState().jumpToWorkoutStep(third.id, 0)).toBe(true)

    expect(session()).toMatchObject({ currentExerciseId: third.id, currentSetIndex: 0, view: 'exercise-setup', restState: undefined })
    expect(session().completedSets[first.id]).toHaveLength(1)
    expect(session().completedExerciseIds).toContain(first.id)
    expect(session().exerciseOutcomes?.[first.id]).toBe('partial')
    expect(session().sessionState?.exerciseId).toBe(third.id)

    const progress = getWorkoutProgress(session())
    expect(progress[0].status).toBe('partial')
    expect(progress[1].status).toBe('pending')
    expect(progress[2].status).toBe('current')
    // The partial exercise can be finished later from its next set.
    expect(progress[0].nextSetIndex).toBe(1)
    expect(canJumpToWorkoutStep(session(), first.id, 1)).toBe(true)
    expect(canJumpToWorkoutStep(session(), second.id, 0)).toBe(true)
  })

  it('does not mark an untouched exercise as done when it is left', () => {
    const [first, second] = session().exercises
    useRuntimeStore.getState().jumpToWorkoutStep(second.id, 0)

    expect(session().completedExerciseIds).not.toContain(first.id)
    expect(getWorkoutProgress(session())[0].status).toBe('pending')
  })

  it('redoes a done set: later results of that exercise are dropped and the exercise is open again', () => {
    const [first, second] = session().exercises
    finishWholeExercise()
    expect(session().view).toBe('exercise-summary')
    expect(getWorkoutProgress(session())[0].status).toBe('done')

    expect(useRuntimeStore.getState().jumpToWorkoutStep(first.id, 1, [])).toBe(true)

    expect(session()).toMatchObject({ currentExerciseId: first.id, currentSetIndex: 1, view: 'exercise-setup', exerciseSummary: undefined })
    expect(session().completedSets[first.id]).toHaveLength(1)
    expect(session().completedExerciseIds).not.toContain(first.id)
    expect(session().exerciseOutcomes?.[first.id]).toBeUndefined()
    expect(session().sessionState?.setNumber).toBe(2)
    expect(getCurrentWorkoutStep(session())).toEqual({ exerciseId: first.id, setIndex: 1 })

    // Finishing the redone sets goes on with the next exercise as usual.
    for (let index = 1; index < first.plan.length; index += 1) {
      useRuntimeStore.getState().finishCurrentSet()
      if (session().view === 'rest') useRuntimeStore.getState().beginNextStep()
    }
    expect(session().completedSets[first.id]).toHaveLength(first.plan.length)
    expect(getNextPendingExercise(session())?.id).toBe(second.id)
  })

  it('redoing from the first set forgets the stale backend record', () => {
    const [first] = session().exercises
    useRuntimeStore.getState().finishCurrentSet()
    useRuntimeStore.setState({ session: { ...session(), backendExerciseSessionIds: { [first.id]: 41 } } })

    useRuntimeStore.getState().jumpToWorkoutStep(first.id, 0, [first.id])

    expect(session().completedSets[first.id]).toBeUndefined()
    expect(session().backendExerciseSessionIds?.[first.id]).toBeUndefined()
  })

  it('rejects sets that cannot be opened', () => {
    const [first, second] = session().exercises
    const before = session()

    // the current position, a set after the next one, and unknown targets
    expect(canJumpToWorkoutStep(before, first.id, 0)).toBe(false)
    expect(canJumpToWorkoutStep(before, second.id, 1)).toBe(false)
    expect(canJumpToWorkoutStep(before, second.id, -1)).toBe(false)
    expect(canJumpToWorkoutStep(before, 'missing', 0)).toBe(false)
    expect(useRuntimeStore.getState().jumpToWorkoutStep(second.id, 1)).toBe(false)
    expect(session()).toBe(before)
  })

  it('summarizes an unfinished workout for the home indicator', () => {
    const [first] = session().exercises
    useRuntimeStore.getState().finishCurrentSet()

    const summary = getWorkoutResumeSummary(session())
    expect(summary.doneSets).toBe(1)
    expect(summary.doneExercises).toBe(0)
    expect(summary.totalExercises).toBe(session().exercises.length)
    expect(summary.nextLabel).toBe(`${first.name} · подход 2`)
  })
})
