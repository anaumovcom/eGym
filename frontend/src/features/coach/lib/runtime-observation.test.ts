import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import type { LifecycleContext } from './lifecycle-observer'
import { captureRuntimeLifecycle, coachLifecycle, isCoachFoundationEnabled, setLifecycleVersionReader } from './runtime-observation'

describe('runtime read-only observation integration', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_COACH_ENABLED', 'true')
    localStorage.clear()
    useAppStore.setState({ selectedUserId: 'fixture-user' })
    useRuntimeStore.setState({ session: null, sessionSignature: null })
    useRuntimeStore.getState().initializeSession({ source: 'catalog', slug: 'barbell-floor-press' })
    const session = useRuntimeStore.getState().session!
    useRuntimeStore.setState({ session: { ...session, dataSource: 'backend' } })
    coachLifecycle.clear()
  })
  afterEach(() => { vi.unstubAllEnvs(); coachLifecycle.clear(); setLifecycleVersionReader(() => null) })

  it('reads detached live versions only at capture without mutating the workout', () => {
    const session = useRuntimeStore.getState().session!
    const original = JSON.stringify(session)
    let planRevision = 7
    const reader = vi.fn((current: LifecycleContext) => ({ phase: 'active-set' as const, planRevision, contextVersion: 8, scope: { schemaVersion: 1 as const,
      userId: current.userId!, runId: current.runId!, exerciseId: current.exerciseId, setOrdinal: current.setOrdinal, scopeEpoch: 40 } }))
    setLifecycleVersionReader(reader)
    const capture = captureRuntimeLifecycle(session, 'fixture-user')!
    planRevision = 9
    expect(coachLifecycle.publish(capture, 'set_persisted', { backendSetId: 2 })).toBe(true)
    const event = coachLifecycle.snapshot()[0]
    expect(event).toMatchObject({ phase: 'active-set', planRevision: 7, contextVersion: 8, scope: { scopeEpoch: 40 } })
    expect(Object.isFrozen(capture.versions)).toBe(true)
    expect(Object.isFrozen(capture.versions!.scope)).toBe(true)
    expect(reader).toHaveBeenCalledOnce()
    expect(JSON.stringify(useRuntimeStore.getState().session)).toBe(original)
  })

  it('keeps missing capture-time versions local-only instead of assigning them at publication', () => {
    setLifecycleVersionReader(() => null)
    const capture = captureRuntimeLifecycle(useRuntimeStore.getState().session!, 'fixture-user')!
    setLifecycleVersionReader(() => { throw new Error('Must not read at publication') })
    expect(coachLifecycle.publish(capture, 'set_persisted', { backendSetId: 2 })).toBe(true)
    expect(coachLifecycle.snapshot()[0]).toMatchObject({ planRevision: 0, contextVersion: 0 })
  })

  it('stays off by default even when legacy runtime exists', () => {
    vi.stubEnv('VITE_COACH_ENABLED', '')
    expect(isCoachFoundationEnabled()).toBe(false)
    expect(captureRuntimeLifecycle(useRuntimeStore.getState().session!, 'fixture-user')).toBeNull()
  })

  it('invalidates A→B→A captures, never sends a command or creates history', () => {
    const original = useRuntimeStore.getState().session!
    const capture = captureRuntimeLifecycle(original, 'fixture-user')
    useAppStore.setState({ selectedUserId: 'another-user' })
    useAppStore.setState({ selectedUserId: 'fixture-user' })
    expect(coachLifecycle.publish(capture, 'set_persisted', { backendSetId: 1 })).toBe(false)
    expect(useRuntimeStore.getState().session!.completedSets).toEqual(original.completedSets)
    expect(coachLifecycle.snapshot()).toEqual([])
  })

  it('ordinary view transitions keep scope; set advance invalidates capture', () => {
    const original = useRuntimeStore.getState().session!
    const capture = captureRuntimeLifecycle(original, 'fixture-user')
    useRuntimeStore.getState().startExercise()
    expect(coachLifecycle.publish(capture, 'set_stopped', { outcome: 'partial' })).toBe(true)
    useRuntimeStore.setState({ session: { ...useRuntimeStore.getState().session!, currentSetIndex: 1 } })
    expect(coachLifecycle.publish(capture, 'set_persisted', { backendSetId: 2 })).toBe(false)
  })

  it('rejects stale UI closures, anonymous and mock runtime identities', () => {
    const original = useRuntimeStore.getState().session!
    expect(captureRuntimeLifecycle(original, null)).toBeNull()
    expect(captureRuntimeLifecycle({ ...original, id: 'old-run' }, 'fixture-user')).toBeNull()
    useRuntimeStore.setState({ session: { ...original, dataSource: 'mock' } })
    expect(captureRuntimeLifecycle(useRuntimeStore.getState().session!, 'fixture-user')).toBeNull()
  })

  it('workout scope excludes exercise/set and needs a backend ack', () => {
    const capture = captureRuntimeLifecycle(useRuntimeStore.getState().session!, 'fixture-user', true)
    expect(capture!.scope.exerciseId).toBeNull()
    expect(capture!.scope.setOrdinal).toBeNull()
    expect(coachLifecycle.publish(capture, 'workout_finalized', { outcome: 'aborted' })).toBe(false)
    expect(coachLifecycle.publish(capture, 'workout_finalized', { outcome: 'aborted', backendWorkoutId: 10 })).toBe(true)
  })
})