import { describe, expect, it, vi } from 'vitest'
import type { CoachScope } from '../model/contracts'
import { FakeClock, FakeContext } from './audio-test-fakes'
import { LocalCoachAudioManager } from './local-coach-audio-manager'
import type { PlayLocalOptions } from './local-coach-audio-manager'
import { createTestClipBuffer } from './test-clips'
import { verifyLocalBuffer } from './local-buffers'

const scope: CoachScope = { schemaVersion: 1, userId: 'u', runId: 'r', exerciseId: 'e', setOrdinal: 1, scopeEpoch: 1 }
function setup(nativeHold = true) {
  const context = new FakeContext(); context.nativeHold = nativeHold
  const clock = new FakeClock()
  const manager = new LocalCoachAudioManager({ context: context.asAudioContext(), clock, scope })
  const buffer = createTestClipBuffer(context.asAudioContext())
  const play = (id: string, extra: Partial<PlayLocalOptions> = {}) => manager.playLocal({ id, scope, buffer,
    source: 'local', baseGain: 1, startDeadlineMs: 10_000, revalidate: () => true, ...extra })
  const advance = (ms = 20) => clock.advance(ms, context)
  const byId = (id: string) => manager.snapshot().utterances.find(entry => entry.id === id)!
  return { context, clock, manager, buffer, play, advance, byId }
}

describe('LocalCoachAudioManager actual-start mixer', () => {
  it.each([true, false])('anchors each ramp at the observed current value/time (native hold=%s)', nativeHold => {
    const { play, advance, context, byId } = setup(nativeHold)
    play('a'); advance(20)
    const events = context.gains[1].gain.events
    expect(events.at(-2)).toEqual({ kind: 'set', value: 0, time: 0.01 })
    expect(events.at(-1)!.time).toBeCloseTo(0.06)
    expect(byId('a').gain).toBeCloseTo(0.2)
  })

  it('never promotes a fully consumed silent buffer when the observer is throttled', () => {
    const { play, context, clock, manager } = setup()
    play('missed')
    context.currentTime = 0.5 // Audio advanced while the wall-clock observer was blocked.
    clock.advance(10, context, false)
    expect(manager.snapshot()).toMatchObject({ active: 0, pending: 0, startOrdinal: 0,
      lastActualSource: null, counters: { started: 0, finished: 0, cancelled: 1 } })
    expect(context.sources[0].stop).toHaveBeenCalledOnce()
  })

  it('orders crossed sources by audio time after observer throttling, not Map order', () => {
    const { play, advance, context, clock, manager } = setup()
    play('reserved-first', { delayMs: 100 }); play('earlier')
    context.currentTime = 0.05
    clock.time = 100
    // Scheduling a later source must still promote the already-crossed earlier one first.
    play('third', { delayMs: 500 })
    advance(20)
    expect(manager.snapshot().utterances.filter(item => item.startOrdinal !== null)
      .map(item => [item.id, item.startOrdinal])).toEqual([['reserved-first', 2], ['earlier', 1]])
    expect(manager.snapshot().foreground).toBe('reserved-first')
  })

  it('releases started sources immediately if the shared context closes', () => {
    const { play, advance, context, manager, clock } = setup()
    play('started'); advance(20); play('pending', { delayMs: 100 })
    context.setState('closed')
    expect(manager.snapshot()).toMatchObject({ active: 0, pending: 0, counters: { cancelled: 2 } })
    expect(clock.pendingTimers).toBe(0)
  })

  it('mixes 1/2/3 actual starts: latest 1, older .65/N, each scaled by baseGain', () => {
    const { play, advance, manager, byId, context } = setup()
    expect(play('a', { baseGain: 0.8 })).toBe(true)
    expect(manager.snapshot()).toMatchObject({ active: 0, pending: 1, startOrdinal: 0, foreground: null })
    advance(); expect(byId('a')).toMatchObject({ startOrdinal: 1, coefficient: 1, targetGain: 0.8 })
    play('b', { source: 'cache', baseGain: 0.5 }); advance()
    expect(byId('a').targetGain).toBeCloseTo(0.8 * 0.65)
    expect(byId('b')).toMatchObject({ coefficient: 1, targetGain: 0.5, startOrdinal: 2 })
    play('c', { baseGain: 0.6 }); advance()
    expect(byId('a').targetGain).toBeCloseTo(0.8 * 0.325)
    expect(byId('b').targetGain).toBeCloseTo(0.5 * 0.325)
    expect(byId('c')).toMatchObject({ coefficient: 1, targetGain: 0.6, startOrdinal: 3 })
    expect(context.sources).toHaveLength(3)
    expect(new Set(context.sources.map(source => source.buffer)).size).toBe(3)
    expect(manager.snapshot()).toMatchObject({ foreground: 'c', lastActualSource: 'local', active: 3 })
    for (const entry of manager.snapshot().utterances) expect(entry.targetGain).toBeLessThanOrEqual(entry.baseGain)
  })

  it('does not duck for reservations, delayed playback, or a frozen audio timeline', () => {
    const { play, advance, clock, context, manager, byId } = setup()
    play('a'); advance(100)
    play('delayed', { delayMs: 500 }); play('scheduled')
    clock.advance(100, context, false)
    expect(byId('a').coefficient).toBe(1)
    expect(byId('scheduled').startOrdinal).toBeNull()
    expect(byId('delayed').state).toBe('pending')
    expect(manager.snapshot().counters.started).toBe(1)
    advance(); expect(manager.snapshot().foreground).toBe('scheduled')
    advance(500); expect(manager.snapshot().foreground).toBe('delayed')
  })

  it('orders by actual start, not admission; onended restores older audio and alone counts finish', () => {
    const { play, advance, manager, context, byId } = setup()
    play('reserved-first', { delayMs: 200 }); play('immediate'); advance()
    expect(manager.snapshot().foreground).toBe('immediate')
    advance(220)
    expect(manager.snapshot().foreground).toBe('reserved-first')
    expect(manager.snapshot().counters.finished).toBe(0)
    context.sources[1].end()
    expect(manager.snapshot()).toMatchObject({ active: 1, foreground: 'immediate', counters: { finished: 1 } })
    expect(byId('immediate').targetGain).toBe(1)
    const last = context.gains[1].gain.events.at(-1)!
    expect(last.kind).toBe('ramp'); expect(last.time - context.currentTime).toBeCloseTo(0.15)
    context.sources[0].end()
    expect(manager.snapshot().counters.finished).toBe(2)
    expect(manager.snapshot().active).toBe(0)
  })

  it.each([true, false])('keeps interrupted ramps continuous (native hold=%s), with 50ms attack and 150ms restore', nativeHold => {
    const { play, advance, context, byId } = setup(nativeHold)
    play('a'); advance(100)
    play('b'); advance(20)
    const before = byId('a').gain
    play('c'); advance(20)
    const events = context.gains[1].gain.events
    const ramp = events.at(-1)!
    expect(ramp.time - (context.currentTime - 0.01)).toBeCloseTo(0.05)
    expect(byId('a').gain).toBeLessThan(before)
    if (!nativeHold) {
      const held = events.at(-2)!
      expect(held.kind).toBe('set')
      expect(held.value).toBeCloseTo(0.86) // .02/.05 through the 1 -> .65 attack.
      expect(events.at(-3)!.kind).toBe('cancel')
    } else {
      expect(events.at(-3)!.kind).toBe('hold')
      expect(events.at(-2)!.kind).toBe('set')
      expect(events.at(-2)!.value).toBeCloseTo(0.86)
    }
    context.sources[2].end(); context.sources[1].end()
    expect(context.gains[1].gain.events.at(-1)!.time - context.currentTime).toBeCloseTo(0.15)
    advance(160); expect(byId('a').gain).toBeCloseTo(1)
  })

  it('applies headroom/volume once in master, never in individual gains; mute cancels', () => {
    const { play, advance, context, manager, byId } = setup()
    manager.setVolume(0.4); play('a', { baseGain: 0.7 }); advance()
    expect(context.gains[0].gain.value).toBe(0.2)
    expect(byId('a').targetGain).toBe(0.7)
    expect(context.compressors).toHaveLength(1)
    manager.setVolume(0.2); expect(context.gains[0].gain.value).toBe(0.1)
    manager.setVolume(0.2, true)
    expect(context.gains[0].gain.value).toBe(0)
    expect(manager.snapshot()).toMatchObject({ active: 0, audible: 0, muted: true, counters: { finished: 0, cancelled: 1 } })
    expect(play('muted')).toBe(false)
    manager.setVolume(1); expect(play('new')).toBe(true)
    expect(() => manager.setVolume(Number.NaN)).toThrow('invalid_volume')
  })

  it('rechecks deadline/callback before delayed schedule and first observed start; started finishes past deadline', () => {
    const { play, advance, manager, context } = setup()
    play('late', { delayMs: 100, startDeadlineMs: 50 }); advance(110)
    expect(context.sources).toHaveLength(0)
    let valid = true
    play('stale', { revalidate: () => valid }); valid = false; advance()
    expect(manager.snapshot().counters.started).toBe(0)
    expect(context.sources[0].stop).toHaveBeenCalledOnce()
    play('expired-before-first', { startDeadlineMs: 135 }); advance()
    expect(manager.snapshot().counters.started).toBe(0)
    play('allowed', { startDeadlineMs: 180 }); advance()
    advance(1000)
    expect(manager.snapshot().active).toBe(1)
    context.sources.at(-1)!.end()
    expect(manager.snapshot().counters.finished).toBe(1)
  })

  it('preserves started audio on same-exercise set/rest epoch changes but cancels pending', () => {
    const { play, advance, manager, context } = setup()
    play('started'); advance(); play('pending', { delayMs: 100 })
    const next = { ...scope, setOrdinal: 2, scopeEpoch: 2 }
    manager.updateScope(next)
    expect(manager.snapshot()).toMatchObject({ active: 1, pending: 0 })
    expect(context.sources[0].stop).not.toHaveBeenCalled()
    expect(play('old')).toBe(false)
    expect(play('new', { scope: next })).toBe(true)
    manager.cancelScope(next)
    expect(manager.snapshot().active).toBe(1)
    manager.updateScope({ ...next, exerciseId: 'other' })
    expect(manager.snapshot().active).toBe(0)
    expect(context.sources[0].stop).toHaveBeenCalledOnce()
  })

  it.each(['userId', 'runId', 'exerciseId'] as const)('cancels all on %s boundary', field => {
    const { play, advance, manager } = setup()
    play('started'); advance(); play('pending', { delayMs: 100 })
    manager.updateScope({ ...scope, [field]: 'changed' })
    expect(manager.snapshot()).toMatchObject({ active: 0, pending: 0, reason: 'scope_changed' })
  })

  it('rejects locked/unavailable contexts without resume or autoplay fallback', () => {
    const { context, play, manager, clock } = setup()
    context.setState('suspended'); expect(play('locked')).toBe(false)
    expect(context.resume).not.toHaveBeenCalled()
    expect(manager.snapshot().reason).toBe('audio_locked')
    const missing = new LocalCoachAudioManager({ context: null, clock })
    expect(missing.snapshot().contextState).toBe('unavailable')
    expect(missing.playLocal({ id: 'none' } as PlayLocalOptions)).toBe(false)
    missing.dispose()
  })

  it('suspension never promotes scheduled audio; started audio becomes inaudible', () => {
    const { play, advance, context, manager, clock } = setup()
    play('a'); advance(100); play('b')
    context.setState('suspended'); clock.advance(100, context)
    expect(manager.snapshot()).toMatchObject({ active: 1, audible: 0, startOrdinal: 1, pending: 0 })
    context.setState('running'); expect(manager.snapshot().audible).toBe(1)
  })

  it('bounds active/pending, refuses duplicate IDs without eviction, and bounds immutable diagnostics', () => {
    const { play, advance, manager } = setup()
    for (let i = 0; i < 8; i++) { expect(play(`active-${i}`)).toBe(true); advance() }
    expect(play('over-active')).toBe(false)
    for (let i = 0; i < 16; i++) expect(play(`pending-${i}`, { delayMs: 500 })).toBe(true)
    expect(play('over-pending', { delayMs: 500 })).toBe(false)
    manager.cancelAll()
    expect(play('active-0')).toBe(false)
    for (let i = 0; i < 1100; i++) play(`id-${i}`)
    expect(manager.snapshot().reason).toBe('id_capacity')
    expect(play('active-0')).toBe(false)
    expect(manager.snapshot().reason).toBe('duplicate')
    const snapshot = manager.snapshot()
    expect(snapshot.timeline).toHaveLength(200)
    expect(Object.isFrozen(snapshot)).toBe(true)
    expect(Object.isFrozen(snapshot.utterances)).toBe(true)
    expect(Object.isFrozen(snapshot.counters)).toBe(true)
    expect(Object.isFrozen(snapshot.timeline[0])).toBe(true)
    expect(JSON.stringify(snapshot)).not.toContain('speechText')
  })

  it('rejects unverified/nonfinite/oversized buffers; owns attenuated copies', () => {
    const { play, advance, buffer, context, manager } = setup()
    expect(play('raw', { buffer: context.createBuffer(1, 20, 8000) })).toBe(false)
    buffer.getChannelData(0)[0] = Number.NaN
    expect(play('nonfinite')).toBe(false)
    buffer.getChannelData(0).fill(1)
    expect(play('normalized')).toBe(true)
    buffer.getChannelData(0).fill(0)
    advance()
    expect(context.sources[0].buffer).not.toBe(buffer)
    expect(Math.max(...context.sources[0].buffer!.getChannelData(0))).toBe(0.25)
    expect(() => verifyLocalBuffer(context.asAudioContext(), context.createBuffer(1, 480001, 8000))).toThrow()
    expect(() => verifyLocalBuffer(context.asAudioContext(), context.createBuffer(2, 400000, 8000))).toThrow()
    manager.dispose()
  })

  it('fixed watchdog cleans stuck sources, does not count cancellation as finished', () => {
    const { play, advance, manager, clock } = setup()
    play('stuck'); advance(125010)
    expect(manager.snapshot()).toMatchObject({ active: 0, counters: { started: 1, finished: 0, cancelled: 1 }, reason: 'watchdog' })
    expect(clock.pendingTimers).toBe(0)
  })

  it('a silent scheduled source ending before observation does not count start or finish or duck older audio', () => {
    const { play, advance, context, manager, byId } = setup()
    play('a'); advance(100); play('silent-scheduled')
    context.sources[1].end()
    expect(manager.snapshot()).toMatchObject({ active: 1, foreground: 'a', counters: { started: 1, finished: 0, cancelled: 1 } })
    expect(byId('a').coefficient).toBe(1)
    expect(byId('a').targetGain).toBe(1)
  })

  it('cancelAll accepts contract safety reasons and mute cancels pending as well as started clips', () => {
    const { play, advance, manager, clock, context } = setup()
    play('a'); advance(); play('b', { delayMs: 100 })
    manager.cancelAll('safety')
    expect(manager.snapshot()).toMatchObject({ active: 0, pending: 0, reason: 'safety', counters: { finished: 0, cancelled: 2 } })
    expect(clock.pendingTimers).toBe(0)
    const count = context.sources.length
    advance(200); expect(context.sources).toHaveLength(count)
    play('c', { delayMs: 100 }); manager.setVolume(0)
    advance(200)
    expect(manager.snapshot()).toMatchObject({ pending: 0, reason: 'mute', counters: { finished: 0, cancelled: 3 } })
    expect(play('zero-volume')).toBe(false)
  })

  it('checks delayed callback invalidation and callback exceptions without allocating a source', () => {
    const { play, advance, context, manager } = setup()
    let valid = true
    play('delayed', { delayMs: 100, revalidate: () => valid })
    valid = false; advance(120)
    expect(context.sources).toHaveLength(0)
    expect(manager.snapshot().reason).toBe('stale')
    expect(play('throws', { revalidate: () => { throw new Error('no longer valid') } })).toBe(false)
    expect(context.sources).toHaveLength(0)
  })

  it('publishes computed post-start gains/audibility; throwing observers never affect playback', () => {
    const { play, advance, manager } = setup()
    const snapshots: ReturnType<typeof manager.snapshot>[] = []
    const off = manager.subscribe(() => { snapshots.push(manager.snapshot()) })
    manager.subscribe(() => { throw new Error('bad observer') })
    play('a'); advance(100)
    expect(snapshots.some(snapshot => snapshot.active === 1 && snapshot.audible === 1)).toBe(true)
    expect(manager.snapshot().utterances[0].gain).toBe(1)
    const count = snapshots.length; off(); advance(100)
    expect(snapshots).toHaveLength(count)
    manager.dispose()
  })

  it('disposes idempotently, disconnects sources/master, clears timers/subscriptions, never closes context', () => {
    const { play, advance, manager, context, clock } = setup()
    const listener = vi.fn(); const unsubscribe = manager.subscribe(listener)
    play('a'); advance(); play('b', { delayMs: 100 })
    expect(listener).toHaveBeenCalled()
    unsubscribe(); listener.mockClear()
    const saved = manager.snapshot()
    manager.dispose(); manager.dispose(); advance(1000)
    expect(listener).not.toHaveBeenCalled()
    expect(context.close).not.toHaveBeenCalled(); expect(context.suspend).not.toHaveBeenCalled()
    expect(context.sources[0].disconnect).toHaveBeenCalled()
    expect(context.gains[0].disconnect).toHaveBeenCalled()
    expect(clock.pendingTimers).toBe(0)
    expect(manager.snapshot()).toMatchObject({ disposed: true, active: 0, pending: 0 })
    expect(saved.active).toBe(1)
    expect(play('after')).toBe(false)
    expect(manager.snapshot().reason).toBe('disposed')
  })
})