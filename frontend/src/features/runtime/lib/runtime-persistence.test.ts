import { beforeEach, describe, expect, it, vi } from 'vitest'
import { resetExercisesOnBackend } from './runtime-persistence'
import { expandPerSidePlan } from './per-side'
import { createRuntimeSession } from '@/mocks/stage3-data'
import { apiPost } from '@/shared/api/client'

vi.mock('@/shared/api/client', async () => ({
  ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'),
  apiPost: vi.fn(),
}))

describe('resetExercisesOnBackend plan metadata', () => {
  beforeEach(() => vi.mocked(apiPost).mockReset().mockResolvedValue({}))

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

    expect(apiPost).toHaveBeenCalledExactlyOnceWith('/api/runtime/exercises', expect.objectContaining({
      exerciseSessionId: 7, perSide, plannedTotal: 47 * (perSide ? 2 : 1),
      targetSets: 4 * (perSide ? 2 : 1), resetSets: true, sets: [],
    }))
  })
})