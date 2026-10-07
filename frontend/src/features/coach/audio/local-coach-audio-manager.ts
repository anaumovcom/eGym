import type { CoachAudio, CoachReason, CoachScope } from '../model/contracts'
import { MAX_STREAM_PCM_BYTES, pcmS16ToAudioBuffer } from './coach-frames'
import { copyNormalizedLocalBuffer, isVerifiedLocalBuffer } from './local-buffers'
import { getSharedAudioContext } from './shared-audio-context'

export type LocalAudioSource = 'local' | 'cache'
export type NetworkAudioSource = 'realtime' | 'tts' | 'fake'
export type MixerAudioSource = LocalAudioSource | NetworkAudioSource
export type AudioReason = CoachReason | 'ready' | 'started' | 'ended' | 'cancelled' | 'scope_changed' | 'mute' |
  'expired' | 'stale' | 'audio_locked' | 'unavailable' | 'duplicate' | 'id_capacity' |
  'queue_full' | 'invalid' | 'watchdog' | 'disposed' | 'volume' | 'context' | 'underrun'
export interface AudioTimerClock {
  now(): number
  setTimeout(callback: () => void, delayMs: number): unknown
  clearTimeout(handle: unknown): void
}
export type PlayLocalOptions = Readonly<{
  id: string; scope: CoachScope; source: LocalAudioSource; buffer: AudioBuffer
  startDeadlineMs: number; baseGain: number; delayMs?: number; revalidate: () => boolean
}>
/** Network utterance reservation. Chunks arrive later via pushStream; a reservation never ducks anything. */
export type BeginStreamOptions = Readonly<{
  id: string; generationId: string; scope: CoachScope; source: NetworkAudioSource; sampleRate: number
  startDeadlineMs: number; baseGain: number; revalidate: () => boolean; prebufferMs?: number
}>
export type AudioTimelineEvent = Readonly<{ atMs: number; reason: AudioReason; startOrdinal: number; source: MixerAudioSource | null }>
export type StreamSnapshot = Readonly<{ generationId: string; nextSequence: number; bytes: number; final: boolean; gaps: number; inGap: boolean }>
export type LocalAudioSnapshot = Readonly<{
  pending: number; active: number; audible: number; foreground: string | null; startOrdinal: number
  utterances: readonly Readonly<{ id: string; scope: CoachScope; source: MixerAudioSource; state: 'pending' | 'scheduled' | 'started';
    startOrdinal: number | null; baseGain: number; coefficient: number; gain: number; targetGain: number; scheduledStartTime: number | null
    stream: StreamSnapshot | null }>[]
  counters: Readonly<{ enqueued: number; started: number; finished: number; cancelled: number; rejected: number }>
  lastActualSource: MixerAudioSource | null; contextState: AudioContextState | 'unavailable'
  volume: number; muted: boolean; reason: AudioReason; disposed: boolean; timeline: readonly AudioTimelineEvent[]
}>
export type LocalAudioManagerOptions = Readonly<{ context?: AudioContext | null; clock?: AudioTimerClock; scope?: CoachScope; volume?: number }>
type Envelope = { from: number; to: number; start: number; end: number }
type EntryOptions = Readonly<{
  id: string; scope: CoachScope; source: MixerAudioSource; startDeadlineMs: number; baseGain: number
  delayMs?: number; revalidate: () => boolean
}>
type Stream = {
  generationId: string; sampleRate: number; prebufferSeconds: number; nextSequence: number; bytes: number
  final: boolean; queued: AudioBuffer[]; queuedSeconds: number; sources: AudioBufferSourceNode[]
  endTime: number; lastPushMs: number; gaps: number; inGap: boolean
}
type Entry = {
  options: EntryOptions; buffer: AudioBuffer | null; dueMs: number; watchdogMs: number
  source: AudioBufferSourceNode | null; gain: GainNode | null; scheduled: number | null
  ordinal: number | null; coefficient: number; envelope: Envelope; stream: Stream | null
}
const MAX_PENDING = 16
const MAX_ACTIVE = 8
const MAX_IDS = 1024
const WATCHDOG_MS = 125_000 // Fixed lifetime, never extended by new packets/state changes.
const STREAM_WATCHDOG_MS = 60_000 // From the first observed start of network speech; packets never extend it.
const STREAM_STALL_MS = 5_000 // A started stream without packets/final for this long is cut, not left hanging.
const GAP_SECONDS = 0.25 // Longer underruns stop holding other voices in the background.
const DEFAULT_PREBUFFER_MS = 120
const NETWORK_SOURCES = new Set<MixerAudioSource>(['realtime', 'tts', 'fake'])
const CHECK_MS = 10 // Observation only; gain automation runs on the audio timeline.
const ATTACK_SECONDS = 0.05
const RESTORE_SECONDS = 0.15
const HEADROOM = 0.5
const clockDefault: AudioTimerClock = {
  now: () => performance.now(),
  setTimeout: (callback, delay) => globalThis.setTimeout(callback, delay),
  clearTimeout: handle => globalThis.clearTimeout(handle as ReturnType<typeof setTimeout>),
}
const sameExercise = (a: CoachScope, b: CoachScope) => a.userId === b.userId && a.runId === b.runId && a.exerciseId === b.exerciseId
const sameScope = (a: CoachScope, b: CoachScope) => sameExercise(a, b) && a.setOrdinal === b.setOrdinal && a.scopeEpoch === b.scopeEpoch
const envelopeValue = (envelope: Envelope, time: number) => {
  if (time >= envelope.end) return envelope.to
  if (time <= envelope.start) return envelope.from
  return envelope.from + (envelope.to - envelope.from) * (time - envelope.start) / (envelope.end - envelope.start)
}

/** Shared latest-start mixer for local clips (E05) and streamed network speech (E08).
 * Observed start means running context.currentTime crossed source.start(time).
 * It is not an assertion about output-device latency or physical sound delivery.
 * A network utterance has exactly one start: later chunks continue it, never re-promote it.
 */
export class LocalCoachAudioManager {
  private readonly context: AudioContext | null
  private readonly clock: AudioTimerClock
  private readonly entries = new Map<string, Entry>()
  private readonly seenIds = new Set<string>() // No eviction/replay; a full manager rejects new IDs.
  private readonly listeners = new Set<() => void>()
  private readonly timeline: AudioTimelineEvent[] = []
  private readonly counters = { enqueued: 0, started: 0, finished: 0, cancelled: 0, rejected: 0 }
  private master: GainNode | null = null
  private compressor: DynamicsCompressorNode | null = null
  private scope: CoachScope | null
  private timer: unknown = null
  private ordinal = 0
  private volume = 1
  private muted = false
  private disposed = false
  private reason: AudioReason = 'ready'
  private lastActualSource: MixerAudioSource | null = null
  private lastNotificationMs = -Infinity

  constructor(options: LocalAudioManagerOptions = {}) {
    this.context = options.context === undefined ? getSharedAudioContext() : options.context
    this.clock = options.clock ?? clockDefault
    this.scope = options.scope ? Object.freeze({ ...options.scope }) : null
    if (options.volume !== undefined) this.volume = this.validVolume(options.volume)
    this.context?.addEventListener('statechange', this.onStateChange)
  }

  enqueue(options: PlayLocalOptions): boolean { return this.playLocal(options) }

  playLocal(options: PlayLocalOptions): boolean {
    if (this.disposed) return this.reject('disposed')
    if (typeof options.id !== 'string' || !options.id.length || options.id.length > 128) return this.reject('invalid')
    if (this.seenIds.has(options.id)) return this.reject('duplicate')
    if (this.seenIds.size >= MAX_IDS) return this.reject('id_capacity')
    this.seenIds.add(options.id)
    const context = this.context
    if (!context || context.state === 'closed') return this.reject('unavailable')
    if (context.state !== 'running') return this.reject('audio_locked')
    if (this.muted || this.volume === 0) return this.reject('mute')
    if (!['local', 'cache'].includes(options.source) || !Number.isFinite(options.baseGain) || options.baseGain < 0 || options.baseGain > 1 ||
        !Number.isFinite(options.startDeadlineMs) || !Number.isFinite(options.delayMs ?? 0) ||
        (options.delayMs ?? 0) < 0 || (options.delayMs ?? 0) > 60_000 || typeof options.revalidate !== 'function' ||
        !options.scope || options.scope.schemaVersion !== 1 || !isVerifiedLocalBuffer(options.buffer)) return this.reject('invalid')
    if (!this.scope) this.scope = Object.freeze({ ...options.scope })
    const invalid = this.invalidPending(options)
    if (invalid) return this.reject(invalid)
    if ([...this.entries.values()].filter(entry => entry.ordinal === null).length >= MAX_PENDING) return this.reject('queue_full')
    let buffer: AudioBuffer
    try { buffer = copyNormalizedLocalBuffer(context, options.buffer) } catch { return this.reject('invalid') }
    const now = this.clock.now()
    const entry: Entry = { options: Object.freeze({ ...options, buffer, scope: Object.freeze({ ...options.scope }) }), buffer,
      dueMs: now + (options.delayMs ?? 0), watchdogMs: now + WATCHDOG_MS,
      source: null, gain: null, scheduled: null, ordinal: null, coefficient: 0,
      envelope: { from: 0, to: 0, start: 0, end: 0 }, stream: null }
    this.entries.set(options.id, entry)
    this.increment('enqueued')
    this.record('ready')
    this.check()
    return this.entries.has(options.id)
  }

  /** Reserve a network utterance. Nothing is scheduled until the prebuffer (or final) arrives. */
  beginStream(options: BeginStreamOptions): boolean {
    if (this.disposed) return this.reject('disposed')
    if (typeof options.id !== 'string' || !options.id.length || options.id.length > 128) return this.reject('invalid')
    if (this.seenIds.has(options.id)) return this.reject('duplicate')
    if (this.seenIds.size >= MAX_IDS) return this.reject('id_capacity')
    this.seenIds.add(options.id)
    const context = this.context
    if (!context || context.state === 'closed') return this.reject('unavailable')
    if (context.state !== 'running') return this.reject('audio_locked')
    if (this.muted || this.volume === 0) return this.reject('mute')
    const prebuffer = options.prebufferMs ?? DEFAULT_PREBUFFER_MS
    if (!NETWORK_SOURCES.has(options.source) || typeof options.generationId !== 'string' || !options.generationId.length ||
        options.generationId.length > 120 || !Number.isInteger(options.sampleRate) || options.sampleRate < 8000 ||
        options.sampleRate > 96000 || !Number.isFinite(options.baseGain) || options.baseGain < 0 || options.baseGain > 1 ||
        !Number.isFinite(options.startDeadlineMs) || !Number.isFinite(prebuffer) || prebuffer < 0 || prebuffer > 2000 ||
        typeof options.revalidate !== 'function' || !options.scope || options.scope.schemaVersion !== 1) return this.reject('invalid')
    if (!this.scope) this.scope = Object.freeze({ ...options.scope })
    const invalid = this.invalidPending(options)
    if (invalid) return this.reject(invalid)
    if ([...this.entries.values()].filter(entry => entry.ordinal === null).length >= MAX_PENDING) return this.reject('queue_full')
    const now = this.clock.now()
    this.entries.set(options.id, { options: Object.freeze({ ...options, scope: Object.freeze({ ...options.scope }) }), buffer: null,
      dueMs: now, watchdogMs: now + WATCHDOG_MS, source: null, gain: null, scheduled: null, ordinal: null, coefficient: 0,
      envelope: { from: 0, to: 0, start: 0, end: 0 },
      stream: { generationId: options.generationId, sampleRate: options.sampleRate, prebufferSeconds: prebuffer / 1000,
        nextSequence: 0, bytes: 0, final: false, queued: [], queuedSeconds: 0, sources: [], endTime: 0,
        lastPushMs: now, gaps: 0, inGap: false } })
    this.increment('enqueued')
    this.record('ready')
    this.check()
    return this.entries.has(options.id)
  }

  /** Append one decoded wire frame. Late generations/cancelled utterances are rejected, never a new start. */
  pushStream(metadata: CoachAudio, pcm: Uint8Array): boolean {
    if (this.disposed) return this.reject('disposed')
    const entry = typeof metadata?.utteranceId === 'string' ? this.entries.get(metadata.utteranceId) : undefined
    const stream = entry?.stream
    if (!entry || !stream || metadata.generationId !== stream.generationId || !metadata.scope ||
        !sameScope(metadata.scope, entry.options.scope)) return this.reject('stale')
    if (stream.final || metadata.sequence !== stream.nextSequence || metadata.source !== entry.options.source ||
        metadata.codec !== 'pcm_s16le' || metadata.channels !== 1 || metadata.sampleRate !== stream.sampleRate ||
        !(pcm instanceof Uint8Array) || metadata.byteLength !== pcm.length || pcm.length % 2 ||
        stream.bytes + pcm.length > MAX_STREAM_PCM_BYTES) {
      this.remove(entry, 'invalid', false); return this.reject('invalid')
    }
    if (pcm.length) {
      let buffer: AudioBuffer
      try { buffer = pcmS16ToAudioBuffer(this.context!, pcm, stream.sampleRate) } catch { this.remove(entry, 'invalid', false); return this.reject('invalid') }
      stream.queued.push(buffer); stream.queuedSeconds += buffer.duration
    }
    stream.nextSequence++; stream.bytes += pcm.length; stream.lastPushMs = this.clock.now()
    if (metadata.final) stream.final = true
    if (entry.scheduled !== null) { this.flush(entry); this.remix() }
    this.check()
    return this.entries.has(entry.options.id)
  }

  cancelStream(id: string, reason: AudioReason = 'cancelled'): void {
    const entry = this.entries.get(id)
    if (!this.disposed && entry?.stream) this.remove(entry, reason, false)
  }

  cancelAll(reason: AudioReason = 'cancelled'): void {
    if (this.disposed && reason !== 'disposed') return
    for (const entry of [...this.entries.values()]) this.remove(entry, reason, false)
    this.record(reason)
  }

  /** Exact scope cancellation (including set/epoch). Exercise-boundary updates cancel all. */
  cancelScope(scope: CoachScope): void {
    if (this.disposed) return
    for (const entry of [...this.entries.values()]) if (sameScope(entry.options.scope, scope)) this.remove(entry, 'cancelled', false)
    this.remix(); this.record('cancelled')
  }

  updateScope(scope: CoachScope): void {
    if (this.disposed) return
    const previous = this.scope
    this.scope = Object.freeze({ ...scope })
    if (previous && !sameExercise(previous, scope)) this.cancelAll('scope_changed')
    else this.check() // Set/rest/epoch changes preserve started audio, invalidate pending.
    this.record('scope_changed')
  }

  /** Volume appears exactly once in master gain; .5 headroom is also master-only. */
  setVolume(volume: number, muted = false): void {
    if (this.disposed) return
    this.volume = this.validVolume(volume); this.muted = muted
    if (this.master && this.context) this.master.gain.setValueAtTime(muted ? 0 : volume * HEADROOM, this.context.currentTime)
    if (muted || volume === 0) this.cancelAll('mute')
    this.record(muted || volume === 0 ? 'mute' : 'volume')
  }

  dispose(): void {
    if (this.disposed) return
    this.disposed = true
    this.cancelAll('disposed')
    this.clearTimer()
    this.context?.removeEventListener('statechange', this.onStateChange)
    this.master?.disconnect(); this.compressor?.disconnect()
    this.master = null; this.compressor = null
    this.record('disposed'); this.listeners.clear()
    // The injected/shared context is not owned here: NEVER suspend or close it.
  }

  snapshot(): LocalAudioSnapshot {
    const now = this.context?.currentTime ?? 0
    const started = [...this.entries.values()].filter(entry => entry.ordinal !== null)
    const foreground = started.filter(entry => entry.coefficient === 1)
      .reduce<Entry | null>((latest, entry) => !latest || entry.ordinal! > latest.ordinal! ? entry : latest, null)
    return Object.freeze({
      pending: this.entries.size - started.length, active: started.length,
      audible: this.context?.state === 'running' && !this.muted && this.volume > 0 ? started.filter(entry => envelopeValue(entry.envelope, now) > 0).length : 0,
      foreground: foreground?.options.id ?? null, startOrdinal: this.ordinal,
      utterances: Object.freeze([...this.entries.values()].map(entry => Object.freeze({
        id: entry.options.id, scope: entry.options.scope, source: entry.options.source,
        state: entry.ordinal !== null ? 'started' as const : entry.scheduled !== null ? 'scheduled' as const : 'pending' as const,
        startOrdinal: entry.ordinal, baseGain: entry.options.baseGain, coefficient: entry.coefficient,
        gain: envelopeValue(entry.envelope, now), targetGain: entry.envelope.to, scheduledStartTime: entry.scheduled,
        stream: entry.stream ? Object.freeze({ generationId: entry.stream.generationId, nextSequence: entry.stream.nextSequence,
          bytes: entry.stream.bytes, final: entry.stream.final, gaps: entry.stream.gaps, inGap: entry.stream.inGap }) : null,
      }))), counters: Object.freeze({ ...this.counters }), lastActualSource: this.lastActualSource,
      contextState: this.context?.state ?? 'unavailable', volume: this.volume, muted: this.muted,
      reason: this.reason, disposed: this.disposed, timeline: Object.freeze([...this.timeline]),
    })
  }

  subscribe(listener: () => void): () => void {
    if (this.disposed) return () => {}
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }

  private readonly onStateChange = () => { this.check(); this.record('context') }

  private invalidPending(options: EntryOptions): AudioReason | null {
    if (this.clock.now() > options.startDeadlineMs) return 'expired'
    if (!this.scope || !sameScope(this.scope, options.scope)) return 'stale'
    try { if (!options.revalidate()) return 'stale' } catch { return 'stale' }
    return null
  }

  private check(): void {
    this.clearTimer()
    if (this.disposed) return
    const context = this.context
    if (!context) return
    if (context.state === 'closed') { this.cancelAll('unavailable'); return }
    for (const entry of [...this.entries.values()]) {
      if (!this.entries.has(entry.options.id)) continue
      if (this.clock.now() >= entry.watchdogMs) { this.remove(entry, 'watchdog', false); continue }
      const stream = entry.stream
      if (stream && entry.scheduled !== null && stream.final && !stream.sources.length && !stream.queued.length) {
        this.remove(entry, entry.ordinal !== null ? 'ended' : 'cancelled', entry.ordinal !== null); continue
      }
      if (stream && entry.ordinal !== null && !stream.final && context.currentTime >= stream.endTime &&
          this.clock.now() - stream.lastPushMs >= STREAM_STALL_MS) {
        this.remove(entry, 'watchdog', false); continue
      }
      if (entry.ordinal !== null) continue // Start deadline/scope callback do not cut off started audio.
      const invalid = this.invalidPending(entry.options)
      if (invalid || context.state !== 'running' || this.muted || this.volume === 0) {
        this.remove(entry, invalid ?? (this.muted || this.volume === 0 ? 'mute' : 'audio_locked'), false); continue
      }
      if (entry.scheduled === null && this.clock.now() >= entry.dueMs) {
        if (!stream) this.schedule(entry)
        else if (stream.queued.length && (stream.final || stream.queuedSeconds >= stream.prebufferSeconds)) this.scheduleStream(entry)
        else if (stream.final) this.remove(entry, 'cancelled', false) // Final without audio: nothing to start.
      }
    }
    // If an observer was throttled, order all crossed sources by their audio
    // start times, NOT by reservation/Map order. Equal-time ties stay stable.
    const crossed = [...this.entries.values()]
      .filter(entry => entry.ordinal === null && entry.scheduled !== null && context.currentTime >= entry.scheduled)
      .sort((a, b) => a.scheduled! - b.scheduled!)
    for (const entry of crossed) {
      if (!this.entries.has(entry.options.id) || this.disposed || context.state !== 'running') continue
      // A delayed observer must not announce/duck for a source whose entire
      // silent buffer has already elapsed, even if onended has not run yet.
      if (context.currentTime >= (entry.stream ? entry.stream.endTime : entry.scheduled! + entry.buffer!.duration)) {
        this.remove(entry, 'expired', false); continue
      }
      // Repeat validation at first observed start, not merely at reservation/scheduling.
      const firstStartInvalid = this.invalidPending(entry.options)
      if (firstStartInvalid) { this.remove(entry, firstStartInvalid, false); continue }
      entry.ordinal = ++this.ordinal
      if (entry.stream) entry.watchdogMs = this.clock.now() + STREAM_WATCHDOG_MS
      this.lastActualSource = entry.options.source
      this.increment('started'); this.remix(); this.record('started', entry.options.source)
    }
    this.remix()
    // Diagnostic refresh only: all gain curves are AudioParam automation.
    // This also publishes audible/gain changes after the first-start ramp.
    if (this.listeners.size && this.clock.now() - this.lastNotificationMs >= 50) this.notify()
    if (this.entries.size) this.timer = this.clock.setTimeout(() => this.check(), CHECK_MS)
  }

  private schedule(entry: Entry): void {
    const context = this.context!
    const invalid = this.invalidPending(entry.options)
    if (invalid) { this.remove(entry, invalid, false); return }
    if ([...this.entries.values()].filter(item => item.scheduled !== null).length >= MAX_ACTIVE) {
      this.remove(entry, 'queue_full', false); return
    }
    try {
      this.ensureGraph()
      entry.source = context.createBufferSource(); entry.gain = context.createGain()
      entry.source.buffer = entry.buffer
      entry.gain.gain.setValueAtTime(0, context.currentTime)
      entry.source.connect(entry.gain); entry.gain.connect(this.master!)
      entry.source.onended = () => {
        if (!this.entries.has(entry.options.id)) return
        const finished = entry.ordinal !== null
        this.remove(entry, finished ? 'ended' : 'cancelled', finished)
        this.remix(); this.record(finished ? 'ended' : 'cancelled')
      }
      // Silence until observed start/revalidation. Reservations never duck anything.
      entry.scheduled = context.currentTime + 0.01
      entry.source.start(entry.scheduled)
      this.record('ready')
    } catch { this.remove(entry, 'invalid', false) }
  }

  private scheduleStream(entry: Entry): void {
    const context = this.context!
    if ([...this.entries.values()].filter(item => item.scheduled !== null).length >= MAX_ACTIVE) {
      this.remove(entry, 'queue_full', false); return
    }
    try {
      this.ensureGraph()
      entry.gain = context.createGain()
      entry.gain.gain.setValueAtTime(0, context.currentTime)
      entry.gain.connect(this.master!)
      entry.scheduled = context.currentTime + 0.01
      entry.stream!.endTime = entry.scheduled
      this.flush(entry)
      this.record('ready')
    } catch { this.remove(entry, 'invalid', false) }
  }

  /** Chunks are queued back-to-back on the audio clock; an underrun resumes at now (counted as a gap). */
  private flush(entry: Entry): void {
    const context = this.context!
    const stream = entry.stream!
    for (const buffer of stream.queued) {
      const source = context.createBufferSource()
      source.buffer = buffer
      source.connect(entry.gain!)
      const at = Math.max(stream.endTime, context.currentTime + 0.01)
      if (entry.ordinal !== null && at > stream.endTime + 0.001) stream.gaps++
      source.onended = () => {
        if (!this.entries.has(entry.options.id)) return
        stream.sources = stream.sources.filter(item => item !== source)
        source.disconnect()
        this.check()
      }
      source.start(at)
      stream.sources.push(source)
      stream.endTime = at + buffer.duration
    }
    stream.queued = []; stream.queuedSeconds = 0
  }

  private inGap(entry: Entry): boolean {
    return !!entry.stream && entry.ordinal !== null && !!this.context && this.context.currentTime > entry.stream.endTime + GAP_SECONDS
  }

  private ensureGraph(): void {
    if (this.master) return
    const context = this.context!
    this.master = context.createGain(); this.compressor = context.createDynamicsCompressor()
    this.master.gain.setValueAtTime(this.muted ? 0 : this.volume * HEADROOM, context.currentTime)
    this.compressor.threshold.setValueAtTime(-12, context.currentTime)
    this.compressor.knee.setValueAtTime(12, context.currentTime)
    this.compressor.ratio.setValueAtTime(4, context.currentTime)
    this.compressor.attack.setValueAtTime(0.003, context.currentTime)
    this.compressor.release.setValueAtTime(0.15, context.currentTime)
    this.master.connect(this.compressor); this.compressor.connect(context.destination)
  }

  private remix(): void {
    const started = [...this.entries.values()].filter(entry => entry.ordinal !== null)
    // A stream in a long underrun is silent: it must not keep the remaining voices ducked.
    const audible = started.filter(entry => !this.inGap(entry))
    const latest = Math.max(0, ...audible.map(entry => entry.ordinal!))
    for (const entry of started) {
      const gap = this.inGap(entry)
      if (entry.stream && gap !== entry.stream.inGap) {
        entry.stream.inGap = gap
        if (gap) this.record('underrun', entry.options.source)
      }
      const coefficient = gap ? 0 : entry.ordinal === latest ? 1 : 0.65 / (audible.length - 1)
      entry.coefficient = coefficient
      this.ramp(entry, entry.options.baseGain * coefficient)
    }
  }

  private ramp(entry: Entry, target: number): void {
    if (!entry.gain || !this.context || entry.envelope.to === target) return
    const time = this.context.currentTime
    const current = envelopeValue(entry.envelope, time)
    const parameter = entry.gain.gain
    if (typeof parameter.cancelAndHoldAtTime === 'function') parameter.cancelAndHoldAtTime(time)
    else parameter.cancelScheduledValues(time)
    // Holding/cancelling does not reliably provide a ramp anchor (especially
    // on the initial constant gain). Explicitly anchor at the observed time.
    parameter.setValueAtTime(current, time)
    const duration = entry.envelope.end !== 0 && target > entry.envelope.to ? RESTORE_SECONDS : ATTACK_SECONDS
    parameter.linearRampToValueAtTime(target, time + duration)
    entry.envelope = { from: current, to: target, start: time, end: time + duration }
  }

  private remove(entry: Entry, reason: AudioReason, finished: boolean): void {
    if (!this.entries.delete(entry.options.id)) return
    for (const source of [entry.source, ...(entry.stream?.sources ?? [])]) {
      if (!source) continue
      source.onended = null
      if (!finished) { try { source.stop() } catch { /* Already stopped. */ } }
      source.disconnect()
    }
    if (entry.stream) { entry.stream.sources = []; entry.stream.queued = [] }
    entry.gain?.disconnect()
    this.increment(finished ? 'finished' : 'cancelled')
    this.remix()
    this.record(reason)
    if (!this.entries.size) this.clearTimer()
  }

  private clearTimer(): void {
    if (this.timer !== null) { this.clock.clearTimeout(this.timer); this.timer = null }
  }
  private validVolume(volume: number): number {
    if (!Number.isFinite(volume) || volume < 0 || volume > 1) throw new Error('invalid_volume')
    return volume
  }
  private increment(key: keyof typeof this.counters): void {
    this.counters[key] = Math.min(Number.MAX_SAFE_INTEGER, this.counters[key] + 1)
  }
  private reject(reason: AudioReason): false { this.increment('rejected'); this.record(reason); return false }
  private record(reason: AudioReason, source: MixerAudioSource | null = null): void {
    this.reason = reason
    this.timeline.push(Object.freeze({ atMs: this.clock.now(), reason, startOrdinal: this.ordinal, source }))
    if (this.timeline.length > 200) this.timeline.shift()
    this.notify()
  }
  private notify(): void {
    this.lastNotificationMs = this.clock.now()
    for (const listener of this.listeners) { try { listener() } catch { /* Diagnostics must not break playback. */ } }
  }
}