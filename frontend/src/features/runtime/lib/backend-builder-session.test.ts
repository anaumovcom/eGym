import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BuilderExerciseItem, WorkoutBuilderData } from '@/entities/builder/model/types'
import { createRuntimeSession } from '@/mocks/stage3-data'
import { apiGet } from '@/shared/api/client'
import { buildBackendBuilderRuntimeSession } from './backend-builder-session'
import { getBuilderPlanSignature } from './builder-plan-signature'

vi.mock('@/shared/api/client', () => ({ apiGet: vi.fn() }))

describe('backend builder per-side runtime', () => {
  beforeEach(() => vi.mocked(apiGet).mockReset())

  async function build(overrides: Partial<BuilderExerciseItem> = {}) {
    const fixture = createRuntimeSession({ source: 'catalog', slug: 'barbell-floor-press' })
    const exercise = fixture.exercises[0]
    const builder = {
      info: { name: 'Sides', type: 'Силовая', duration: '30 минут', difficulty: 'Средняя', description: '' },
      groups: [{ id: 'g', kind: 'single', title: 'Exercise', items: [{
        id: 'e', slug: exercise.slug, name: exercise.name, muscleGroup: 'Грудь',
        sets: '1 × 10', rest: '60 сек', load: '20 кг', loadType: 'weighted', perSide: true,
        ...overrides,
      }] }],
    } satisfies Pick<WorkoutBuilderData, 'info' | 'groups'>
    vi.mocked(apiGet).mockResolvedValueOnce(builder).mockResolvedValueOnce(fixture.machine).mockResolvedValueOnce(exercise.details)
    return buildBackendBuilderRuntimeSession({ userId: 'alexey', programId: 'p' })
  }

  it.each(['weighted', 'bodyweight'] as const)('uses saved 1 × 10 per side for %s', async (loadType) => {
    const session = await build({ loadType })
    expect(session.exercises[0]).toMatchObject({ perSide: true, loadSettings: { sets: 1, reps: 10 } })
    expect(session.exercises[0].plan).toHaveLength(2)
    expect(session.exercises[0].plan.map((set) => [set.setNumber, set.side, set.roundNumber, set.targetReps, set.restSeconds])).toEqual([
      [1, 'left', 1, 10, 0], [2, 'right', 1, 10, 60],
    ])
    expect(session.workoutSummary.exercises[0].result).toContain('1 пар подходов')
  })

  it('expands timed duration without converting it into repetitions', async () => {
    const session = await build({ loadType: 'timed', sets: '2 × 45 сек' })
    expect(session.exercises[0].plan.map((set) => [set.targetSeconds, set.side, set.roundNumber])).toEqual([
      [45, 'left', 1], [45, 'right', 1], [45, 'left', 2], [45, 'right', 2],
    ])
    expect(session.exercises[0].plan.every((set) => set.targetReps === undefined)).toBe(true)
  })

  it('keeps one 60-second quick-feet set and an immutable server-plan signature', async () => {
    const session = await build({ slug: 'cardio-quick-feet', name: 'Быстрые шаги', loadType: 'timed', sets: '1×60 сек', rest: '30 сек', perSide: false })
    expect(session.exercises[0].loadSettings).toMatchObject({ sets: 1, reps: 60, restSeconds: 30 })
    expect(session.exercises[0].plan).toEqual([{ targetSeconds: 60, weightLabel: 'вес тела', restSeconds: 30 }])
    expect(session.builderPlanSignature).toBe(getBuilderPlanSignature(session))
    const edited = { ...session, exercises: session.exercises.map(exercise => ({ ...exercise, plan: exercise.plan.map(plan => ({ ...plan, recommendedWeightKg: 0 })) })) }
    expect(getBuilderPlanSignature(edited)).not.toBe(session.builderPlanSignature)
    expect(edited.builderPlanSignature).toBe(session.builderPlanSignature)
  })

  it('expands saved warmup/work/failure plans without adding template warmups', async () => {
    const session = await build({ strengthPlan: [
      { setNumber: 1, setType: 'warmup', label: 'Разминка', targetRepsLabel: '5', recommendedWeightLabel: '10 кг', restSeconds: 30, rirLabel: '4', note: 'warmup' },
      { setNumber: 2, setType: 'work', label: 'Рабочий', targetRepsLabel: '10', recommendedWeightLabel: '20 кг', restSeconds: 60, rirLabel: '2', note: 'work' },
      { setNumber: 3, setType: 'failure', label: 'Отказ', targetRepsLabel: 'максимум', recommendedWeightLabel: '20 кг', restSeconds: 90, rirLabel: '0', note: 'failure' },
    ] })
    expect(session.exercises[0].plan.map((set) => set.setType)).toEqual(['warmup', 'warmup', 'work', 'work', 'failure', 'failure'])
    expect(session.exercises[0].plan.map((set) => set.setNumber)).toEqual([1, 2, 3, 4, 5, 6])
  })

  it('preserves the legacy unflagged template', async () => {
    const session = await build({ perSide: undefined })
    expect(session.exercises[0].plan.map((set) => set.setType)).toEqual(['warmup', 'work', 'work', 'work'])
    expect(session.exercises[0].plan.every((set) => set.side === undefined && set.roundNumber === undefined)).toBe(true)
  })

  it.each(['—', '0 кг'])('does not restore the default weight for a saved zero load %s', async (load) => {
    const session = await build({ load, perSide: false })
    expect(session.exercises[0].loadSettings.weight).toBe(0)
    expect(session.exercises[0].plan.every((set) => !set.recommendedWeightKg)).toBe(true)
  })
})