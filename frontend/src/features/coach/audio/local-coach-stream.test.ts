import { describe, expect, it } from 'vitest'
import type { CoachAudio, CoachScope } from '../model/contracts'
import { FakeClock, FakeContext } from './audio-test-fakes'
import { encodeCoachFrame } from './coach-frames'
import { LocalCoachAudioManager } from './local-coach-audio-manager'
import type { BeginStreamOptions } from './local-coach-audio-manager'
import { playCoachStream } from './network-stream'
import { createTestClipBuffer } from './test-clips'

const scope: CoachScope = { schemaVersion: 1, userId: 'u', runId: 'r', exerciseId: 'e', setOrdinal: 1, scopeEpoch: 1 }
const RATE = 8000
const pcm = (seconds: number) => new Uint8Array(Math.round(seconds * RATE) * 2)
function meta(id: string, sequence: number, bytes: number, extra: Partial<CoachAudio> = {}): CoachAudio {
  return { schemaVersion: 1, utteranceId: id, generationId: `g-${id}`, scope, sequence, source: 'realtime', codec: 'pcm_s16le',
    sampleRate: RATE, channels: 1, byteLength: bytes, durationMs: bytes / 2 / RATE * 1000, final: false, ...extra }
}
function setup() {
  const context = new FakeContext()
  const clock = new FakeClock()
  const manager = new LocalCoachAudioManager({ context: context.asAudioContext(), clock, scope })
  const buffer = createTestClipBuffer(context.asAudioContext())
  const play = (id: string) => manager.playLocal({ id, scope, buffer, source: 'local', baseGain: 1, startDeadlineMs: 10_000, revalidate: () => true })
  const begin = (id: string, extra: Partial<BeginStreamOptions> = {}) => manager.beginStream({ id, generationId: `g-${id}`, scope,
    source: 'realtime', sampleRate: RATE, startDeadlineMs: 10_000, baseGain: 1, revalidate: () => true, ...extra })
  const push = (id: string, sequence: number, seconds: number, extra: Partial<CoachAudio> = {}) => {
    const data = pcm(seconds)
    return manager.pushStream(meta(id, sequence, data.length, extra), data)
  }
  const advance = (ms = 20) => clock.advance(ms, context)
  const byId = (id: string) => manager.snapshot().utterances.find(entry => entry.id === id)
  return { context, clock, manager, play, begin, push, advance, byId }
}

describe('streamed network speech in the shared mixer', () => {
  it('reservation/prebuffer never duck; first observed start is the only start; final ends it', () => {
    const { play, begin, push, advance, byId, manager, context } = setup()
    play('local'); advance()
    expect(begin('s')).toBe(true)
    expect(push('s', 0, 0.05)).toBe(true) // Below the 120 ms prebuffer: nothing scheduled yet.
    expect(byId('s')).toMatchObject({ state: 'pending', startOrdinal: null })
    expect(context.sources).toHaveLength(1)
    expect(byId('local')!.coefficient).toBe(1)
    push('s', 1, 0.1)
    expect(context.sources).toHaveLength(3)
    const [first, second] = context.sources.slice(1)
    expect(first.start.mock.calls[0][0]).toBeCloseTo(0.03)
    expect(second.start.mock.calls[0][0]).toBeCloseTo(0.08) // Back-to-back on the audio clock.
    expect(byId('local')!.coefficient).toBe(1)
    advance()
    expect(manager.snapshot()).toMatchObject({ foreground: 's', startOrdinal: 2, lastActualSource: 'realtime' })
    expect(byId('local')!.coefficient).toBeCloseTo(0.65)
    push('s', 2, 0.1, { final: true })
    advance()
    expect(byId('s')).toMatchObject({ startOrdinal: 2, stream: { nextSequence: 3, final: true, gaps: 0 } })
    expect(context.sources[3].start.mock.calls[0][0]).toBeCloseTo(0.18)
    expect(manager.snapshot().counters.started).toBe(2)
    for (const source of context.sources.slice(1)) source.end()
    expect(byId('s')).toBeUndefined()
    expect(manager.snapshot()).toMatchObject({ foreground: 'local', counters: { finished: 1 } })
    expect(byId('local')!.coefficient).toBe(1)
  })

  it('late generations/unknown IDs are stale; protocol violations drop the stream', () => {
    const { begin, push, advance, manager, context, byId } = setup()
    begin('s'); push('s', 0, 0.2); advance()
    expect(push('s', 1, 0.1, { generationId: 'g-old' })).toBe(false)
    expect(manager.snapshot().reason).toBe('stale')
    expect(push('ghost', 0, 0.1)).toBe(false)
    expect(push('s', 1, 0.1, { scope: { ...scope, setOrdinal: 2 } })).toBe(false)
    expect(byId('s')).toBeDefined()
    expect(push('s', 5, 0.1)).toBe(false) // Sequence gap.
    expect(manager.snapshot().reason).toBe('invalid')
    expect(byId('s')).toBeUndefined()
    expect(context.sources[0].stop).toHaveBeenCalledOnce()
    expect(push('s', 1, 0.1)).toBe(false) // Never a new start for a dropped utterance.
    expect(manager.snapshot().counters).toMatchObject({ started: 1, finished: 0, cancelled: 1 })
    begin('t')
    expect(push('t', 0, 0.1, { sampleRate: 16000, durationMs: 0.1 / 2 * 1000 })).toBe(false)
    begin('v')
    expect(push('v', 0, 0.1, { source: 'tts' })).toBe(false)
    expect(begin('v')).toBe(false)
    expect(manager.snapshot().reason).toBe('duplicate')
  })

  it('a long underrun stops ducking other voices; resumed audio keeps its original start', () => {
    const { play, begin, push, advance, byId, manager } = setup()
    begin('s'); push('s', 0, 0.2); advance()
    play('local'); advance()
    expect(manager.snapshot().foreground).toBe('local')
    expect(byId('s')!.coefficient).toBeCloseTo(0.65)
    begin('x'); push('x', 0, 0.2); advance()
    expect(manager.snapshot().foreground).toBe('x')
    advance(500) // x ran dry at ~0.25 s; >250 ms gap.
    expect(byId('x')).toMatchObject({ coefficient: 0, stream: { inGap: true } })
    expect(manager.snapshot().foreground).toBe('local')
    expect(byId('local')!.coefficient).toBe(1)
    expect(manager.snapshot().timeline.some(event => event.reason === 'underrun')).toBe(true)
    push('x', 1, 0.2)
    expect(byId('x')).toMatchObject({ coefficient: 1, startOrdinal: 3, stream: { inGap: false, gaps: 1 } })
    expect(manager.snapshot()).toMatchObject({ foreground: 'x', startOrdinal: 3, counters: { started: 3 } })
  })

  it('stall watchdog cuts silent unfinished streams; a fixed 60 s watchdog is not extended by packets', () => {
    const stalled = setup()
    stalled.begin('s'); stalled.push('s', 0, 0.2); stalled.advance()
    stalled.advance(4_900)
    expect(stalled.byId('s')).toBeDefined()
    stalled.advance(200)
    expect(stalled.byId('s')).toBeUndefined()
    expect(stalled.manager.snapshot()).toMatchObject({ reason: 'watchdog', counters: { finished: 0, cancelled: 1 } })

    const long = setup()
    long.begin('s'); long.push('s', 0, 2); long.advance()
    for (let second = 1; second <= 59; second++) { long.push('s', second, 1); long.advance(1000) }
    expect(long.byId('s')).toBeDefined()
    long.push('s', 60, 1); long.advance(1000)
    expect(long.byId('s')).toBeUndefined()
    expect(long.manager.snapshot().reason).toBe('watchdog')
    expect(long.context.sources.at(-1)!.stop).toHaveBeenCalled()
  })

  it('set/rest change keeps a started stream, drops a pending one; mute and cancel stop audio', () => {
    const { begin, push, advance, byId, manager, context } = setup()
    begin('started'); push('started', 0, 0.2); advance()
    begin('pending'); push('pending', 0, 0.05)
    manager.updateScope({ ...scope, setOrdinal: 2, scopeEpoch: 2 })
    expect(byId('pending')).toBeUndefined()
    expect(push('started', 1, 0.2)).toBe(true) // Continuation of an already started utterance in its own scope.
    begin('c', { scope: { ...scope, setOrdinal: 2, scopeEpoch: 2 } })
    push('c', 0, 0.2, { scope: { ...scope, setOrdinal: 2, scopeEpoch: 2 } })
    advance()
    manager.cancelStream('c')
    expect(byId('c')).toBeUndefined()
    expect(push('c', 1, 0.1, { scope: { ...scope, setOrdinal: 2, scopeEpoch: 2 } })).toBe(false)
    manager.setVolume(1, true)
    expect(byId('started')).toBeUndefined()
    for (const source of context.sources) expect(source.stop).toHaveBeenCalled()
    expect(begin('after-mute')).toBe(false)
  })

  it('final without audio never starts; reservation honours start deadline', () => {
    const { begin, push, advance, byId, manager, context } = setup()
    begin('empty'); push('empty', 0, 0, { final: true }); advance()
    expect(byId('empty')).toBeUndefined()
    begin('late', { startDeadlineMs: 100 }); advance(150)
    expect(byId('late')).toBeUndefined()
    expect(manager.snapshot().counters.started).toBe(0)
    expect(context.sources).toHaveLength(0)
  })
})

function body(chunks: Uint8Array[], split = 5): ReadableStream<Uint8Array> {
  const all = Uint8Array.from(chunks.flatMap(chunk => [...chunk]))
  return new ReadableStream({
    start(controller) {
      for (let i = 0; i < all.length; i += split) controller.enqueue(all.subarray(i, i + split))
      controller.close()
    },
  })
}
const frame = (sequence: number, seconds: number, final = false) => {
  const data = pcm(seconds)
  return encodeCoachFrame(meta('n', sequence, data.length, { final }), data)
}
const streamOptions = { scope, startDeadlineMs: 10_000, baseGain: 1, revalidate: () => true }

describe('playCoachStream', () => {
  it('feeds arbitrarily chunked frames into one utterance', async () => {
    const { manager, advance, byId } = setup()
    const result = await playCoachStream(manager, body([frame(0, 0.1), frame(1, 0.1), frame(2, 0.05, true)], 7), streamOptions)
    expect(result).toEqual({ status: 'delivered', reason: 'ready', frames: 3 })
    advance()
    expect(byId('n')).toMatchObject({ startOrdinal: 1, stream: { final: true, nextSequence: 3 } })
  })

  it('a stream without final frame or with trailing bytes fails and is cancelled', async () => {
    const missingFinal = setup()
    expect(await playCoachStream(missingFinal.manager, body([frame(0, 0.2)]), streamOptions))
      .toMatchObject({ status: 'failed', reason: 'truncated' })
    expect(missingFinal.byId('n')).toBeUndefined()
    const trailing = setup()
    const partial = frame(1, 0.1, true).subarray(0, 30)
    expect(await playCoachStream(trailing.manager, body([frame(0, 0.2), partial]), streamOptions))
      .toMatchObject({ status: 'failed', reason: 'truncated', frames: 1 })
    expect(trailing.byId('n')).toBeUndefined()
  })

  it('abort cancels the utterance; refused reservations are reported', async () => {
    const aborted = setup()
    const controller = new AbortController(); controller.abort()
    expect(await playCoachStream(aborted.manager, body([frame(0, 0.2, true)]), { ...streamOptions, signal: controller.signal }))
      .toMatchObject({ status: 'cancelled', frames: 0 })
    const muted = setup()
    muted.manager.setVolume(1, true)
    expect(await playCoachStream(muted.manager, body([frame(0, 0.2, true)]), streamOptions))
      .toMatchObject({ status: 'failed', reason: 'mute' })
  })
})
