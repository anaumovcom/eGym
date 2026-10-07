import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import { captureRuntimeLifecycle, coachLifecycle, isCoachFoundationEnabled } from './runtime-observation'

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
  afterEach(() => { vi.unstubAllEnvs(); coachLifecycle.clear() })

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