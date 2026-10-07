import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { canonicalCoachKey, DEFAULT_COACH_SETTINGS } from '../model/contracts'
import type { CoachEvent } from '../model/contracts'
import { CoachLifecycleObserver } from './lifecycle-observer'
import type { LifecycleContext } from './lifecycle-observer'

function setup() {
  const current: LifecycleContext = { userId: 'fixture-user', runId: 'fixture-run',
    exerciseId: 'fixture-exercise', setOrdinal: 1, scopeEpoch: 1, mock: false }
  let enabled = true
  const observer = new CoachLifecycleObserver({ enabled: () => enabled, current: () => current, clock: { nowMs: () => 1000 } })
  return { observer, current, disable: () => { enabled = false } }
}

describe('new E02 contracts and read-only lifecycle', () => {
  it('shares the synthetic wire fixture and keeps defaults off', () => {
    const fixture = JSON.parse(readFileSync('../backend/app/tests/fixtures/coach_e02_replay.json', 'utf8')) as { mode: string; events: CoachEvent[] }
    expect(fixture.mode).toBe('test')
    expect(fixture.events.every(event => event.source === 'synthetic')).toBe(true)
    expect(canonicalCoachKey(fixture.events[0])).toBe('["fixture-user","fixture-run","fixture-exercise",1,"set_stopped",0]')
    expect(canonicalCoachKey(fixture.events[1])).not.toBe(canonicalCoachKey(fixture.events[0]))
    expect(DEFAULT_COACH_SETTINGS.enabled).toBe(false)
    expect(DEFAULT_COACH_SETTINGS.consentVersion).toBeNull()
  })

  it('emits stopped before persisted and deduplicates canonical set after aliases', () => {
    const { observer } = setup()
    const capture = observer.capture('machine', false, 'hardware')
    expect(observer.publish(capture, 'set_stopped', { outcome: 'partial', actualValue: 8 })).toBe(true)
    expect(observer.publish(capture, 'set_persisted', { outcome: 'partial', actualValue: 8, backendSetId: 10 })).toBe(true)
    expect(observer.publish(capture, 'set_persisted', { outcome: 'partial', actualValue: 8, backendSetId: 11 })).toBe(false)
    expect(observer.snapshot().map(event => event.kind)).toEqual(['set_stopped', 'set_persisted'])
    expect(observer.snapshot()[0].source).toBe('hardware')
    expect(observer.snapshot()[1].source).toBe('runtime_ack')
    expect(Object.isFrozen(observer.snapshot()[0])).toBe(true)
  })

  it('does not fabricate saves for zero/no ack or skipped exercise', () => {
    const { observer } = setup()
    const capture = observer.capture('bodyweight')
    expect(observer.publish(capture, 'set_persisted', { actualValue: 0 })).toBe(false)
    expect(observer.publish(capture, 'exercise_finalized', { outcome: 'skipped' })).toBe(false)
    expect(observer.publish(capture, 'exercise_finalized', { outcome: 'skipped', backendExerciseId: 3 })).toBe(true)
    expect(observer.snapshot().map(event => event.kind)).toEqual(['exercise_finalized'])
  })

  it.each(['user', 'run', 'exercise', 'set', 'epoch', 'mock', 'disabled'] as const)('rejects late %s changes', change => {
    const { observer, current, disable } = setup()
    const capture = observer.capture('machine')
    if (change === 'user') current.userId = 'another-user'
    if (change === 'run') current.runId = 'another-run'
    if (change === 'exercise') current.exerciseId = 'another-exercise'
    if (change === 'set') current.setOrdinal = 2
    if (change === 'epoch') current.scopeEpoch++
    if (change === 'mock') current.mock = true
    if (change === 'disabled') disable()
    expect(observer.publish(capture, 'set_persisted', { backendSetId: 9 })).toBe(false)
    expect(observer.snapshot()).toEqual([])
  })

  it('is inert while feature off, absent user or mock source', () => {
    const { observer, current, disable } = setup()
    current.mock = true
    expect(observer.capture('machine')).toBeNull()
    current.mock = false
    current.userId = null
    expect(observer.capture('machine')).toBeNull()
    current.userId = 'fixture-user'
    disable()
    expect(observer.capture('machine')).toBeNull()
  })

  it('isolates observer failure from training', () => {
    const observer = new CoachLifecycleObserver({ enabled: () => { throw new Error('failure') },
      current: () => { throw new Error('never') }, clock: { nowMs: () => 1 } })
    expect(observer.capture('machine')).toBeNull()
    expect(observer.failureCount()).toBe(1)
  })

  it('bounds records and receipts without evicting dedup', () => {
    const { observer, current } = setup()
    for (let i = 1; i <= 1024; i++) {
      current.setOrdinal = i
      expect(observer.publish(observer.capture('machine'), 'set_stopped')).toBe(true)
    }
    expect(observer.snapshot()).toHaveLength(200)
    current.setOrdinal = 1025
    expect(observer.publish(observer.capture('machine'), 'set_stopped')).toBe(false)
    current.setOrdinal = 1
    expect(observer.publish(observer.capture('machine'), 'set_stopped')).toBe(false)
  })

  it('clears personal records on user/run capture and normalizes summary dedup', () => {
    const { observer, current } = setup()
    const capture = observer.capture('machine')!
    observer.publish(capture, 'set_stopped')
    current.userId = 'other-user'
    observer.capture('machine')
    expect(observer.snapshot()).toEqual([])
    const event = { scope: capture.scope, kind: 'exercise_finalized' as const, ordinal: 0 }
    expect(canonicalCoachKey(event)).toBe(canonicalCoachKey({ ...event, scope: { ...event.scope, setOrdinal: 5 } }))
  })
})