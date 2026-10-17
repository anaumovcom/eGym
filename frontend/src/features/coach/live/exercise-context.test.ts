import { beforeEach, describe, expect, it } from 'vitest'
import { exerciseIdentity } from './coach-network-client'
import { useRuntimeStore } from '@/stores/runtime-store'

describe('bounded loaded coach exercise identity', () => {
  beforeEach(() => {
    localStorage.clear()
    useRuntimeStore.getState().initializeSession({ source: 'catalog', slug: 'machine-pulldown' })
  })
  it('declares only the identifier and known ordinary-load label, never guide strings', () => {
    const session = { ...useRuntimeStore.getState().session!, dataSource: 'backend' as const }
    const exercise = session.exercises[0]
    expect(exerciseIdentity(session, exercise)).toEqual({ exerciseSlug: exercise.slug, variant: exercise.slug, controlMode: 'constant' })
  })
  it('does not guess a missing, mismatched, mock or malformed loaded definition', () => {
    const session = { ...useRuntimeStore.getState().session!, dataSource: 'backend' as const }
    const exercise = session.exercises[0]
    expect(exerciseIdentity({ ...session, dataSource: 'mock' }, exercise)).toEqual({})
    expect(exerciseIdentity(session, { ...exercise, slug: '../machine-pulldown' })).toEqual({})
    expect(exerciseIdentity(session, { ...exercise, details: { ...exercise.details, slug: 'cable-pulldown' } })).toEqual({})
    expect(exerciseIdentity(session, { ...exercise, slug: undefined } as never)).toEqual({})
  })
  it('keeps unknown load control unknown rather than substituting the training program mode', () => {
    const session = { ...useRuntimeStore.getState().session!, dataSource: 'backend' as const }
    const exercise = session.exercises[0]
    expect(exerciseIdentity(session, { ...exercise, loadSettings: { ...exercise.loadSettings, mode: 'basic' } }))
      .toEqual({ exerciseSlug: exercise.slug, variant: exercise.slug })
  })
})