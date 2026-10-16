import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { WorkoutBuilderData } from '@/entities/builder/model/types'
import { buildBackendBuilderRuntimeSession } from '@/features/runtime/lib/backend-builder-session'
import { getRuntimeInitOptions } from '@/features/runtime/lib/runtime-query'
import { buildExerciseSummary, buildWorkoutSummary, createRuntimeSession } from '@/mocks/stage3-data'
import { expandPerSidePlan } from '@/features/runtime/lib/per-side'
import { apiGet } from '@/shared/api/client'

vi.mock('@/shared/api/client', async () => ({
  ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'),
  apiGet: vi.fn(),
}))

describe('stage3 runtime session builder', () => {
  it.each(['zero', 'skipped'] as const)('does not count a %s side as a completed pair', (invalid) => {
    const session = createRuntimeSession({ source: 'catalog', slug: 'barbell-floor-press' })
    const exercise = session.exercises[0]
    exercise.perSide = true
    exercise.plan = expandPerSidePlan(exercise.plan.slice(0, 1), true)
    session.completedSets[exercise.id] = [
      { setNumber: 1, actualValue: 10, plannedValue: 10, tempoLabel: 'good' },
      { setNumber: 2, actualValue: invalid === 'zero' ? 0 : 10, completionStatus: invalid === 'skipped' ? 'skipped' : 'partial', plannedValue: 10, tempoLabel: 'good' },
    ]
    expect(buildExerciseSummary(session, 'partial').totals.setsCompleted).toBe('0 из 1 пар · 1 из 2 сторон')
    expect(buildWorkoutSummary([], 'partial', session).exercises[0].result).toContain('0 из 1 пар · 1 из 2 сторон')
  })

  beforeEach(() => {
    vi.mocked(apiGet).mockReset()
  })

  it('builds a today workout with machine, bodyweight, timed and group exercises', () => {
    const session = createRuntimeSession({ source: 'today', photoMode: 'pre-workout' })

    expect(session.view).toBe('exercise-setup')
    expect(session.photoProgress.mode).toBe('manual')
    expect(session.exercises.map((exercise) => exercise.kind)).toEqual(expect.arrayContaining(['machine', 'bodyweight', 'timed', 'group']))
  })

  it.each(['catalog', 'quick-start'] as const)('treats a single %s exercise as a backend-persisted one-exercise workout', (source) => {
    const session = createRuntimeSession({ source, slug: 'barbell-floor-press' })

    expect(session.dataSource).toBe('backend')
    expect(session.exercises).toHaveLength(1)
    expect(session.workoutSubtitle).toBe('Одиночное упражнение')
  })

  it.each(['today', 'calendar', 'programs'] as const)('keeps the %s demo workout on mock data', (source) => {
    expect(createRuntimeSession({ source }).dataSource).toBe('mock')
  })

  it.each(['today', 'calendar', 'programs', 'builder', 'catalog', 'quick-start'] as const)('ignores new and legacy photo URL options for %s without changing the source', (source) => {
    for (const photo of ['', '&photo=before', '&photo=after', '&photo=manual']) {
      const options = getRuntimeInitOptions(new URLSearchParams(`source=${source}&calibration=missing${photo}`))
      const session = createRuntimeSession(options)

      expect(options.source).toBe(source)
      expect(options.photoMode).toBe(photo === '&photo=manual' ? 'manual' : null)
      expect(session.view).toBe('exercise-setup')
      expect(session.photoProgress.autoPrompt).toBe(false)
    }
  })

  it.each([undefined, 'pre-workout', 'post-workout', 'manual'] as const)('starts a real backend builder plan without a photo step (%s)', async (photoMode) => {
    const fixture = createRuntimeSession({ source: 'catalog', slug: 'barbell-floor-press' })
    const exercise = fixture.exercises[0]
    const builder = {
      info: { name: 'Backend workout', type: 'Силовая', duration: '30 минут', difficulty: 'Средняя', description: '' },
      groups: [{
        id: 'group-1', kind: 'single', title: 'Жим',
        items: [{ id: 'exercise-1', slug: exercise.slug, name: exercise.name, muscleGroup: 'Грудь', sets: '3 × 10', rest: '90 сек', load: '20 кг', loadType: 'weighted' }],
      }],
    } satisfies Pick<WorkoutBuilderData, 'info' | 'groups'>
    vi.mocked(apiGet)
      .mockResolvedValueOnce(builder)
      .mockResolvedValueOnce(fixture.machine)
      .mockResolvedValueOnce(exercise.details)

    const session = await buildBackendBuilderRuntimeSession({ userId: 'alexey', programId: 'program-1', runId: 'run-1', photoMode })

    expect(apiGet).toHaveBeenCalledWith('/api/builder?userId=alexey&programId=program-1')
    expect(apiGet).toHaveBeenCalledWith(`/api/exercises/${exercise.slug}?userId=alexey`)
    expect(session).toMatchObject({ source: 'builder', dataSource: 'backend', programId: 'program-1', runId: 'run-1', view: 'exercise-setup' })
    expect(session.photoProgress).toMatchObject({ mode: 'manual', autoPrompt: false })
    expect(session.exercises[0]).toMatchObject({ id: 'exercise-1', slug: exercise.slug, calibrationState: 'missing' })
    expect(session.exercises[0].loadSettings.sets).toBe(3)
    expect(session.exercises[0].plan.map((set) => set.setType)).toEqual(['warmup', 'work', 'work', 'work'])
  })

  it.each(['catalog order', 'reverse order'] as const)('keeps saved Smith modes and per-item settings when details resolve in %s', async (resolutionOrder) => {
    const fixture = createRuntimeSession({ source: 'catalog', slug: 'smith-machine-drag-curl' })
    const skullcrusherFixture = createRuntimeSession({ source: 'catalog', slug: 'smith-machine-bodyweight-skullcrusher' })
    const dragDetails = {
      ...fixture.exercises[0].details,
      slug: 'smith-machine-drag-curl',
      name: 'Smith Machine Drag Curl',
      force: 'Static' as const,
      loadSettings: {
        ...fixture.exercises[0].details.loadSettings,
        weight: 0, sets: 9, reps: 60, restSeconds: 180, mode: 'Темповый режим',
      },
    }
    const skullcrusherDetails = {
      ...skullcrusherFixture.exercises[0].details,
      slug: 'smith-machine-bodyweight-skullcrusher',
      name: 'Smith Machine Bodyweight Skullcrusher',
      force: 'Pull' as const,
      loadSettings: {
        ...skullcrusherFixture.exercises[0].details.loadSettings,
        weight: 80, sets: 7, reps: 12, restSeconds: 150, mode: 'Базовый режим',
      },
    }
    const builder = {
      info: { name: 'Saved Smith workout', type: 'Силовая', duration: '30 минут', difficulty: 'Средняя', description: '' },
      groups: [{
        id: 'smith-group', kind: 'single', title: 'Smith',
        items: [
          { id: 'drag-weighted', slug: dragDetails.slug, name: dragDetails.name, muscleGroup: 'Бицепс', sets: '3 × 8', rest: '75 сек', load: '40 кг', loadType: 'weighted' },
          { id: 'skullcrusher-timed', slug: skullcrusherDetails.slug, name: skullcrusherDetails.name, muscleGroup: 'Трицепс', sets: '2 × 45 сек', rest: '30 сек', load: 'вес тела', loadType: 'timed' },
          { id: 'drag-timed', slug: dragDetails.slug, name: dragDetails.name, muscleGroup: 'Бицепс', sets: '4 × 30 сек', rest: '45 сек', load: 'вес тела', loadType: 'timed' },
        ],
      }],
    } satisfies Pick<WorkoutBuilderData, 'info' | 'groups'>
    let resolveDrag!: (details: typeof dragDetails) => void
    let resolveSkullcrusher!: (details: typeof skullcrusherDetails) => void
    const dragResponse = new Promise<typeof dragDetails>((resolve) => { resolveDrag = resolve })
    const skullcrusherResponse = new Promise<typeof skullcrusherDetails>((resolve) => { resolveSkullcrusher = resolve })
    vi.mocked(apiGet)
      .mockResolvedValueOnce(builder)
      .mockResolvedValueOnce(fixture.machine)
      .mockReturnValueOnce(dragResponse)
      .mockReturnValueOnce(skullcrusherResponse)

    const sessionPromise = buildBackendBuilderRuntimeSession({ userId: 'alexey', programId: 'smith-plan' })
    await vi.waitFor(() => {
      expect(apiGet).toHaveBeenCalledTimes(4)
      expect(apiGet).toHaveBeenNthCalledWith(3, `/api/exercises/${dragDetails.slug}?userId=alexey`)
      expect(apiGet).toHaveBeenNthCalledWith(4, `/api/exercises/${skullcrusherDetails.slug}?userId=alexey`)
    })
    if (resolutionOrder === 'reverse order') {
      resolveSkullcrusher(skullcrusherDetails)
      await skullcrusherResponse
      resolveDrag(dragDetails)
    } else {
      resolveDrag(dragDetails)
      await dragResponse
      resolveSkullcrusher(skullcrusherDetails)
    }
    const session = await sessionPromise

    expect(session.exercises.map(({ id, slug }) => ({ id, slug }))).toEqual(
      builder.groups[0].items.map(({ id, slug }) => ({ id, slug })),
    )
    expect(session.currentExerciseId).toBe('drag-weighted')
    const [weighted, timed, duplicate] = session.exercises
    expect(weighted).toMatchObject({
      id: 'drag-weighted', kind: 'machine', calibrationState: 'missing', nextExerciseId: 'skullcrusher-timed',
      details: { slug: dragDetails.slug, force: 'Static' },
      loadSettings: { weight: 40, sets: 3, reps: 8, restSeconds: 75, calibration: 'required' },
    })
    expect(weighted.details.loadSettings).toEqual(weighted.loadSettings)
    expect(weighted.plan).toEqual(expect.arrayContaining([
      expect.objectContaining({ setType: 'work', weightLabel: '40 кг', recommendedWeightKg: 40 }),
    ]))
    for (const set of weighted.plan) {
      expect(set.targetReps).toBeGreaterThan(0)
      expect(set.targetSeconds).toBeUndefined()
    }
    expect(timed).toMatchObject({
      id: 'skullcrusher-timed', kind: 'timed', calibrationState: 'not-needed', nextExerciseId: 'drag-timed',
      details: { slug: skullcrusherDetails.slug, force: 'Pull' },
      loadSettings: { weight: 0, sets: 2, reps: 45, restSeconds: 30, mode: 'Темповый режим', calibration: 'unavailable' },
    })
    expect(timed.details.loadSettings).toEqual(timed.loadSettings)
    expect(timed.plan).toEqual(Array.from({ length: 2 }, () => ({ targetSeconds: 45, weightLabel: 'вес тела', restSeconds: 30 })))
    expect(duplicate).toMatchObject({
      id: 'drag-timed', kind: 'timed', calibrationState: 'not-needed',
      details: { slug: dragDetails.slug, force: 'Static' },
      loadSettings: { weight: 0, sets: 4, reps: 30, restSeconds: 45, mode: 'Темповый режим', calibration: 'unavailable' },
    })
    expect(duplicate.details.loadSettings).toEqual(duplicate.loadSettings)
    expect(duplicate.plan).toEqual(Array.from({ length: 4 }, () => ({ targetSeconds: 30, weightLabel: 'вес тела', restSeconds: 45 })))
    expect(apiGet).toHaveBeenCalledTimes(4)
  })

  it('builds a builder session as an alternating group runtime', () => {
    const session = createRuntimeSession({ source: 'builder' })

    expect(session.exercises).toHaveLength(1)
    expect(session.exercises[0]?.kind).toBe('group')
    expect(session.exercises[0]?.groupMeta?.groupName).toBe('Подтягивания + Присед')
  })
})