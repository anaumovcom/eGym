import { beforeEach, describe, expect, it } from 'vitest'
import type { RuntimeExerciseKind, RuntimeSetResult } from '@/entities/runtime/model/types'
import { expandPerSidePlan } from '@/features/runtime/lib/per-side'
import { buildExerciseSummary, buildWorkoutSummary, createRuntimeSession } from '@/mocks/stage3-data'
import { useRuntimeStore } from './runtime-store'

describe('runtime store per-side progression', () => {
  beforeEach(() => {
    localStorage.clear()
    useRuntimeStore.setState({ session: null, sessionSignature: null })
  })

  function initialize(kind: RuntimeExerciseKind = 'machine', perSide = true) {
    const session = createRuntimeSession({ source: 'catalog', slug: 'barbell-floor-press' })
    const original = session.exercises[0]
    const exercise = {
      ...original, kind, perSide,
      loadSettings: { ...original.loadSettings, sets: 1, reps: kind === 'timed' ? 45 : 10, restSeconds: 60 },
      plan: expandPerSidePlan([{
        ...(kind === 'timed' ? { targetSeconds: 45 } : { targetReps: 10, targetMinReps: 10, targetMaxReps: 10 }),
        weightLabel: kind === 'machine' ? '20 кг' : 'вес тела', restSeconds: 60,
      }], perSide),
    }
    useRuntimeStore.getState().initializeBackendSession({ ...session, exercises: [exercise] }, { source: 'catalog' })
    useRuntimeStore.getState().startExercise()
    return exercise
  }

  it('requires explicit continuation after left, finishes only after right, and totals 20 reps', () => {
    const exercise = initialize()
    expect(useRuntimeStore.getState().session?.sessionState).toMatchObject({ setNumber: 1, totalSets: 2, roundNumber: 1, totalRounds: 1, side: 'left', targetValue: 10 })
    useRuntimeStore.getState().finishCurrentSet()
    let session = useRuntimeStore.getState().session!
    expect(session.view).toBe('rest')
    expect(session.exerciseSummary).toBeUndefined()
    expect(session.completedExerciseIds).not.toContain(exercise.id)
    expect(session.restState).toMatchObject({ title: 'Смените сторону', totalSeconds: 0, remainingSeconds: 0, timerPaused: true })
    expect(session.restState?.nextExercise?.name).toContain('правая сторона')
    for (let i = 0; i < 5; i++) useRuntimeStore.getState().tickRestTimer()
    expect(useRuntimeStore.getState().session?.currentSetIndex).toBe(0)
    expect(buildExerciseSummary(session, 'partial').totals.setsCompleted).toBe('0 из 1 пар · 1 из 2 сторон')

    useRuntimeStore.getState().beginNextStep()
    expect(useRuntimeStore.getState().session?.sessionState).toMatchObject({ setNumber: 2, totalSets: 2, roundNumber: 1, totalRounds: 1, side: 'right', targetValue: 10 })
    // Caller objects are not mutated; metadata comes from the physical plan, not a display counter.
    const provided: RuntimeSetResult = { setNumber: 1, plannedValue: 10, actualValue: 10, reps: 10, tempoLabel: 'good' }
    useRuntimeStore.getState().finishCurrentSet(provided)
    session = useRuntimeStore.getState().session!
    expect(provided).not.toHaveProperty('side')
    expect(session.view).toBe('exercise-summary')
    expect(session.completedSets[exercise.id].map((set) => [set.setNumber, set.side, set.roundNumber])).toEqual([[1, 'left', 1], [2, 'right', 1]])
    expect(session.exerciseSummary?.totals).toMatchObject({ repsOrTime: '20 повторов', setsCompleted: '1 из 1 пар · 2 из 2 сторон' })
    expect(session.exerciseSummary?.currentSets).toBe(1)
    expect(session.exerciseSummary?.restSeconds).toBe(60)
    expect(session.exerciseSummary?.planVsFact[0].label).toBe('Стороны')
    expect(buildWorkoutSummary([], 'completed', session).exercises[0].result).toContain('1 из 1 пар')
    expect(buildWorkoutSummary([], 'completed', session).metrics).toContainEqual({ label: 'подходов / сторон', value: '2 / 2', hint: 'стороны считаются отдельно' })
  })

  it('keeps normal rest after right and advances to the next logical set', () => {
    initialize()
    useRuntimeStore.getState().updateLoadSettings({ sets: 2 })
    useRuntimeStore.getState().finishCurrentSet()
    useRuntimeStore.getState().beginNextStep()
    useRuntimeStore.getState().finishCurrentSet()
    expect(useRuntimeStore.getState().session?.restState).toMatchObject({ title: 'Отдых между подходами', totalSeconds: 60, timerPaused: false })
    useRuntimeStore.getState().beginNextStep()
    expect(useRuntimeStore.getState().session?.sessionState).toMatchObject({ setNumber: 3, roundNumber: 2, totalRounds: 2, side: 'left' })
  })

  it('normalizes only performed sets and never counts timed seconds as reps or volume', () => {
    const exercise = initialize()
    const session = useRuntimeStore.getState().session!
    const timed = { ...exercise, id: 'timed', kind: 'timed' as const }
    const result: RuntimeSetResult = { setNumber: 1, plannedValue: 10, actualValue: 5, reps: 5, weightKg: 20, tempoLabel: 'good' }
    useRuntimeStore.setState({ session: { ...session, exercises: [exercise, timed], completedSets: {
      [exercise.id]: [result, { ...result, setNumber: 2, actualValue: 0, reps: 99 }, { ...result, setNumber: 3, completionStatus: 'skipped' }],
      [timed.id]: [{ ...result, actualValue: 45, reps: null }],
    } } })
    useRuntimeStore.getState().replaceWorkoutSummary(session.workoutSummary)
    expect(useRuntimeStore.getState().session!.workoutSummary.metrics).toEqual(expect.arrayContaining([
      expect.objectContaining({ label: 'подходов / сторон', value: '2 / 4' }),
      expect.objectContaining({ label: 'повторов', value: '5' }),
      expect.objectContaining({ label: 'объём', value: '100 кг' }),
    ]))
  })

  it.each(['machine', 'bodyweight', 'timed'] as const)('rebuilds %s targets and counts without repeated expansion', (kind) => {
    initialize(kind)
    const store = useRuntimeStore.getState()
    store.updateLoadSettings({ sets: 3, reps: 30, restSeconds: 90, weight: 40 })
    store.updateLoadSettings({ reps: 20 })
    let exercise = useRuntimeStore.getState().session!.exercises[0]
    expect(exercise.plan).toHaveLength(6)
    expect(exercise.plan.map((set) => set.setNumber)).toEqual([1, 2, 3, 4, 5, 6])
    expect(exercise.plan.map((set) => set.roundNumber)).toEqual([1, 1, 2, 2, 3, 3])
    expect(exercise.plan.map((set) => set.restSeconds)).toEqual([0, kind === 'machine' ? 60 : 90, 0, 90, 0, 90])
    expect(exercise.plan.slice(-2).map((set) => kind === 'timed' ? set.targetSeconds : set.targetReps)).toEqual([20, 20])
    expect(exercise.plan.filter((set) => set.setType === 'warmup')).toHaveLength(kind === 'machine' ? 2 : 0)
    if (kind === 'machine') {
      store.selectStrengthMode('last_set_failure')
      store.updateLoadSettings({ weight: 50 })
      exercise = useRuntimeStore.getState().session!.exercises[0]
      expect(exercise.plan).toHaveLength(6)
      expect(exercise.plan.map((set) => set.setType)).toEqual(['warmup', 'warmup', 'work', 'work', 'failure', 'failure'])
    }
    store.updateLoadSettings({ sets: 1 })
    expect(useRuntimeStore.getState().session!.exercises[0].plan).toHaveLength(2)
  })

  it('runs both timed sides and totals seconds instead of reps', () => {
    initialize('timed')
    useRuntimeStore.getState().finishCurrentSet()
    expect(useRuntimeStore.getState().session?.view).toBe('rest')
    useRuntimeStore.getState().beginNextStep()
    useRuntimeStore.getState().finishCurrentSet()
    expect(useRuntimeStore.getState().session?.exerciseSummary?.totals.repsOrTime).toBe('90 сек')
    expect(useRuntimeStore.getState().session?.exerciseSummary?.setResults.every((set) => set.reps === undefined)).toBe(true)
  })

  it('leaves unflagged progression, result metadata and legacy rebuilds unchanged', () => {
    initialize('machine', false)
    expect(useRuntimeStore.getState().session?.sessionState).toMatchObject({ setNumber: 1, totalSets: 1 })
    expect(useRuntimeStore.getState().session?.sessionState).not.toHaveProperty('side')
    useRuntimeStore.getState().finishCurrentSet()
    expect(useRuntimeStore.getState().session?.view).toBe('exercise-summary')
    expect(useRuntimeStore.getState().session?.exerciseSummary?.setResults[0]).not.toHaveProperty('side')
    useRuntimeStore.getState().updateLoadSettings({ sets: 1 })
    expect(useRuntimeStore.getState().session!.exercises[0].plan.map((set) => set.setType)).toEqual(['warmup', 'work', 'work', 'work'])
  })
})