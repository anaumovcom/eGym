import { beforeEach, describe, expect, it, vi } from 'vitest'
import { buildCoachWorkoutPlan, resetExercisesOnBackend, saveWorkoutToBackend } from './runtime-persistence'
import { expandPerSidePlan } from './per-side'
import { createRuntimeSession } from '@/mocks/stage3-data'
import { apiPost } from '@/shared/api/client'

vi.mock('@/shared/api/client', async () => ({
  ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'),
  apiPost: vi.fn(),
}))

describe('resetExercisesOnBackend plan metadata', () => {
  beforeEach(() => { vi.mocked(apiPost).mockReset().mockResolvedValue({ missingExerciseSessionIds: [] }) })

  it.each([false, true])('sends physical set count and full target sum with perSide=%s', async (perSide) => {
    const session = createRuntimeSession({ source: 'catalog', slug: 'barbell-floor-press' })
    const exercise = session.exercises[0]
    exercise.perSide = perSide ? true : undefined
    exercise.plan = expandPerSidePlan([
      { targetSeconds: 30, targetMaxReps: 99, weightLabel: '', restSeconds: 0 },
      { targetMaxReps: 12, targetReps: 8, weightLabel: '', restSeconds: 0 },
      { targetReps: 5, weightLabel: '', restSeconds: 0 },
      { weightLabel: '', restSeconds: 0 },
    ], perSide)
    session.backendExerciseSessionIds = { [exercise.id]: 7 }

    expect(await resetExercisesOnBackend(session, [exercise], 'alexey')).toEqual([])

    expect(apiPost).toHaveBeenCalledExactlyOnceWith('/api/runtime/exercises/reset', { exercises: [expect.objectContaining({
      exerciseSessionId: 7, perSide, plannedTotal: 47 * (perSide ? 2 : 1),
      targetSets: 4 * (perSide ? 2 : 1), resetSets: true, sets: [], finishedAt: null,
    })] })
  })

  it('resets both records atomically and forgets only records reported missing', async () => {
    const session = createRuntimeSession({ source: 'catalog', slug: 'barbell-floor-press' })
    const first = session.exercises[0]
    const second = { ...first, id: 'second', order: 2 }
    session.backendExerciseSessionIds = { [first.id]: 7, [second.id]: 8 }
    vi.mocked(apiPost).mockResolvedValue({ missingExerciseSessionIds: [7] })
    expect(await resetExercisesOnBackend(session, [first, second], 'alexey')).toEqual([first.id])
    expect(apiPost).toHaveBeenCalledExactlyOnceWith('/api/runtime/exercises/reset', { exercises: [
      expect.objectContaining({ exerciseSessionId: 7 }), expect.objectContaining({ exerciseSessionId: 8 }),
    ] })
  })

  it('propagates reset failure rather than treating it as a missing record', async () => {
    const session = createRuntimeSession({ source: 'catalog', slug: 'barbell-floor-press' })
    session.backendExerciseSessionIds = { [session.exercises[0].id]: 7 }
    vi.mocked(apiPost).mockRejectedValue(new Error('Сеть недоступна'))
    await expect(resetExercisesOnBackend(session, session.exercises, 'alexey')).rejects.toThrow('Сеть недоступна')
  })
})

describe('declared workout plan snapshot', () => {
  beforeEach(() => { vi.mocked(apiPost).mockReset().mockResolvedValue({ workoutSessionId: 42 }) })

  it('captures every planned occurrence before any results, and sends edits on later saves', async () => {
    const session = createRuntimeSession({ source: 'catalog', slug: 'barbell-floor-press' })
    const first = session.exercises[0]
    session.exercises = [first, { ...first, id: 'repeated-occurrence', order: 2 }]
    session.completedSets = {}
    session.completedExerciseIds = []
    const baseline = buildCoachWorkoutPlan(session)
    await saveWorkoutToBackend(session, 'alexey', 'in_progress')
    expect(apiPost).toHaveBeenLastCalledWith('/api/runtime/workouts', expect.objectContaining({
      status: 'in_progress', exercises: [], exerciseSessionIds: [], coachPlan: baseline,
    }))
    expect(baseline?.exercises.map(e => [e.exerciseId, e.orderIndex, e.slug])).toEqual([
      [first.id, 1, first.slug], ['repeated-occurrence', 2, first.slug],
    ])
    session.backendWorkoutSessionId = 42
    session.exercises = [first]
    await saveWorkoutToBackend(session, 'alexey', 'completed')
    expect(apiPost).toHaveBeenLastCalledWith('/api/runtime/workouts', expect.objectContaining({
      workoutSessionId: 42, coachPlan: expect.objectContaining({ exercises: expect.any(Array) }),
    }))
    expect(vi.mocked(apiPost).mock.calls[1][1]).not.toEqual(vi.mocked(apiPost).mock.calls[0][1])
  })

  it('captures physical side order, exact/range/open/unknown and declared weights without guide prose', () => {
    const session = createRuntimeSession({ source: 'catalog', slug: 'barbell-floor-press' })
    const exercise = session.exercises[0]
    exercise.perSide = true
    exercise.plan = expandPerSidePlan([
      { targetReps: 10, setType: 'work', weightLabel: '', recommendedWeightKg: 20, restSeconds: 60 },
      { targetMinReps: 8, targetMaxReps: 12, setType: 'warmup', weightLabel: '', restSeconds: 30 },
      { targetReps: 10, setType: 'failure', weightLabel: '', restSeconds: 60 },
      { weightLabel: '', restSeconds: 0, note: 'not part of the snapshot' },
    ], true)
    const snapshot = buildCoachWorkoutPlan(session)!
    const sets = snapshot.exercises[0].sets
    expect(sets.map(s => s.ordinal)).toEqual([1, 2, 3, 4, 5, 6, 7, 8])
    expect(sets.map(s => s.targetType)).toEqual(['exact', 'exact', 'range', 'range', 'open', 'open', 'unknown', 'unknown'])
    expect(sets[0]).toMatchObject({ side: 'left', roundNumber: 1, minimum: 10, maximum: 10, plannedWeightKg: 20 })
    expect(sets[1]).toMatchObject({ side: 'right', roundNumber: 1 })
    expect(sets[4]).toMatchObject({ minimum: null, maximum: null })
    expect(JSON.stringify(snapshot)).not.toContain('not part of the snapshot')
  })

  it('does not send an oversized plan that could block ordinary saves', () => {
    const session = createRuntimeSession({ source: 'catalog', slug: 'barbell-floor-press' })
    session.exercises = Array.from({ length: 101 }, () => session.exercises[0])
    expect(buildCoachWorkoutPlan(session)).toBeNull()
  })
})