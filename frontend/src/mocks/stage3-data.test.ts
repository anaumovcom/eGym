import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { WorkoutBuilderData } from '@/entities/builder/model/types'
import { buildBackendBuilderRuntimeSession } from '@/features/runtime/lib/backend-builder-session'
import { getRuntimeInitOptions } from '@/features/runtime/lib/runtime-query'
import { createRuntimeSession } from '@/mocks/stage3-data'
import { apiGet } from '@/shared/api/client'

vi.mock('@/shared/api/client', async () => ({
  ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'),
  apiGet: vi.fn(),
}))

describe('stage3 runtime session builder', () => {
  beforeEach(() => {
    vi.mocked(apiGet).mockReset()
  })

  it('builds a today workout with machine, bodyweight, timed and group exercises', () => {
    const session = createRuntimeSession({ source: 'today', photoMode: 'pre-workout' })

    expect(session.view).toBe('exercise-setup')
    expect(session.photoProgress.mode).toBe('manual')
    expect(session.exercises.map((exercise) => exercise.kind)).toEqual(expect.arrayContaining(['machine', 'bodyweight', 'timed', 'group']))
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

  it('builds a builder session as an alternating group runtime', () => {
    const session = createRuntimeSession({ source: 'builder' })

    expect(session.exercises).toHaveLength(1)
    expect(session.exercises[0]?.kind).toBe('group')
    expect(session.exercises[0]?.groupMeta?.groupName).toBe('Подтягивания + Присед')
  })
})