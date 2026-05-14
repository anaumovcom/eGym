import { createRuntimeSession } from '@/mocks/stage3-data'

describe('stage3 runtime session builder', () => {
  it('builds a today workout with machine, bodyweight, timed and group exercises', () => {
    const session = createRuntimeSession({ source: 'today', photoMode: 'pre-workout' })

    expect(session.photoProgress.mode).toBe('pre-workout')
    expect(session.exercises.map((exercise) => exercise.kind)).toEqual(expect.arrayContaining(['machine', 'bodyweight', 'timed', 'group']))
  })

  it('builds a builder session as an alternating group runtime', () => {
    const session = createRuntimeSession({ source: 'builder' })

    expect(session.exercises).toHaveLength(1)
    expect(session.exercises[0]?.kind).toBe('group')
    expect(session.exercises[0]?.groupMeta?.groupName).toBe('Подтягивания + Присед')
  })
})