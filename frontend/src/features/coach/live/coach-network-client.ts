import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { CoachFrameError, decodeCoachFrame, pcmDurationMs } from '../audio/coach-frames'
import type { AudioReason, LocalAudioSnapshot, LocalCoachAudioManager, NetworkAudioSource } from '../audio/local-coach-audio-manager'
import { exactRepTarget } from '../interpreter/coach-interpreter'
import type { LifecycleRefs } from '../lib/lifecycle-observer'
import type { CoachEvent, CoachEventKind, CoachPhase, CoachScope } from '../model/contracts'
import { preferencesValid, type CoachPreferences } from '../model/preferences'

/** E10 live client: forwards a few semantic events over one WebSocket and plays the
 * backend's tagged PCM through the local mixer. The run token only travels in the
 * first `configure` message and in `X-Coach-Run-Token` headers, never in a URL. */
export type NetworkMixer = Pick<LocalCoachAudioManager, 'beginStream' | 'pushStream' | 'cancelStream' | 'snapshot'>
export type NetworkTick = Readonly<{
  nowMs: number; userId: string | null; saved: CoachPreferences | null; session: RuntimeWorkoutSession | null
  featureEnabled: boolean; phase: CoachPhase; scope: CoachScope | null; latched: boolean; gate: AudioReason | null
  reps: number | null; lifecycle: readonly CoachEvent[]; refs: (eventId: string) => LifecycleRefs | null
  mixer: () => NetworkMixer | null
}>
export type NetworkState = 'off' | 'creating' | 'connecting' | 'ready' | 'retrying' | 'refused'
export type NetworkDecision = Readonly<{ atMs: number; triggerId: string | null; action: string; reason: string | null; text: string | null }>
export type NetworkUsage = Readonly<{ requests: number; settledMicros: number; pendingMicros: number; capMicros: number; limitKind: string }>
export type NetworkSnapshot = Readonly<{
  state: NetworkState; reason: string | null; mode: string | null; voiceId: string | null; text: boolean; voice: boolean
  degraded: boolean; eventsSent: number; streams: number; spoken: number; failed: number
  decisions: readonly NetworkDecision[]; reasons: Readonly<Record<string, number>>; usage: NetworkUsage | null
  lastText: string | null; firstAudioMs: number | null
}>
export interface SocketLike {
  binaryType: string; readonly readyState: number
  send(data: string): void; close(code?: number): void
  onopen: ((event: unknown) => void) | null; onclose: ((event: unknown) => void) | null
  onerror: ((event: unknown) => void) | null; onmessage: ((event: { data: unknown }) => void) | null
}
export type NetworkDependencies = Readonly<{
  fetch: (url: string, init: RequestInit) => Promise<Response>
  socket: (url: string) => SocketLike
  storage: Pick<Storage, 'getItem' | 'setItem' | 'removeItem'> | null
  origin: () => { protocol: string; host: string }
  setTimeout: (callback: () => void, ms: number) => unknown
  clearTimeout: (handle: unknown) => void
  ownerId: () => string
}>

type Stream = { scope: CoachScope; source: NetworkAudioSource; sampleRate: number; bytes: number; final: boolean; started: boolean; mixer: NetworkMixer }
type Run = { runId: string; token: string }
const OPEN = 1
const BACKOFF_MS = [1_000, 2_000, 4_000, 8_000, 16_000, 30_000]
const SOURCES = new Set(['realtime', 'tts', 'fake'])
const FORWARDED: ReadonlySet<CoachEventKind> = new Set(['set_persisted', 'exercise_finalized', 'workout_finalized'])
const EXERCISE_KINDS = new Set(['machine', 'bodyweight', 'timed', 'stretch', 'group'])
const REST_EXTRA_MIN_ELAPSED_S = 15
const REST_EXTRA_MIN_LEFT_S = 40
const USAGE_EVERY_MS = 15_000
const PING_EVERY_MS = 20_000

function defaults(): NetworkDependencies {
  return {
    fetch: (url, init) => fetch(url, init),
    socket: url => new WebSocket(url) as unknown as SocketLike,
    storage: typeof sessionStorage === 'undefined' ? null : sessionStorage,
    origin: () => ({ protocol: location.protocol, host: location.host }),
    setTimeout: (callback, ms) => setTimeout(callback, ms),
    clearTimeout: handle => clearTimeout(handle as ReturnType<typeof setTimeout>),
    // getRandomValues also works on plain-HTTP LAN kiosks, unlike randomUUID.
    ownerId: () => `tab-${Array.from(crypto.getRandomValues(new Uint8Array(12)), byte => byte.toString(16).padStart(2, '0')).join('')}`,
  }
}

const object = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null
const str = (value: unknown, max = 200): string | null => typeof value === 'string' && value.length <= max ? value : null
const num = (value: unknown): number | null => typeof value === 'number' && Number.isFinite(value) ? value : null

export function networkEligible(input: Pick<NetworkTick, 'featureEnabled' | 'userId' | 'saved' | 'session'>): boolean {
  const saved = input.saved
  return input.featureEnabled && !!input.userId && !!input.session && input.session.dataSource === 'backend' && !!saved &&
    preferencesValid(saved) && saved.enabled && saved.consentVersion === 1 && saved.networkConsentVersion === 1 && saved.mode !== 'local'
}

export class CoachNetworkClient {
  private readonly deps: NetworkDependencies
  private readonly owner: string
  private key = ''
  private run: Run | null = null
  private socket: SocketLike | null = null
  private state: NetworkState = 'off'
  private reason: string | null = null
  private attempt = 0
  private retryHandle: unknown = null
  private connecting = false
  private refusedRevision: number | null = null
  private boundWorkout: number | null = null
  private configured: { mode: string | null; voiceId: string | null; text: boolean; voice: boolean; degraded: boolean } | null = null
  private last: NetworkTick | null = null
  private sequence = 0
  private sentKeys = new Set<string>()
  private forwarded = new Set<string>()
  private latched: boolean | null = null
  private streams = new Map<string, Stream>()
  private counters = { eventsSent: 0, streams: 0, spoken: 0, failed: 0 }
  private decisions: NetworkDecision[] = []
  private reasons: Record<string, number> = {}
  private usage: NetworkUsage | null = null
  private usageAt = -Infinity
  private usageBusy = false
  private pingAt = 0
  private lastText: string | null = null
  private firstAudioMs: number | null = null
  private snap: NetworkSnapshot | null = null
  private readonly listeners = new Set<() => void>()
  private disposed = false

  constructor(deps: Partial<NetworkDependencies> = {}) {
    this.deps = { ...defaults(), ...deps }
    this.owner = this.deps.ownerId().slice(0, 120)
  }

  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  getSnapshot = (): NetworkSnapshot => this.snap ??= Object.freeze({
    state: this.state, reason: this.reason, mode: this.configured?.mode ?? null, voiceId: this.configured?.voiceId ?? null,
    text: this.configured?.text ?? false, voice: this.configured?.voice ?? false, degraded: this.configured?.degraded ?? false,
    ...this.counters, decisions: Object.freeze([...this.decisions]), reasons: Object.freeze({ ...this.reasons }),
    usage: this.usage, lastText: this.lastText, firstAudioMs: this.firstAudioMs,
  })

  /** Called on every runtime tick (input change or 250 ms timer). */
  tick(input: NetworkTick): void {
    if (this.disposed) return
    this.last = input
    if (!networkEligible(input)) { this.stop('off', null); return }
    const saved = input.saved!, session = input.session!
    const key = JSON.stringify([input.userId, session.runId ?? session.id])
    if (key !== this.key) {
      this.stop('off', null)
      this.key = key
      this.sentKeys = new Set(); this.forwarded = new Set(input.lifecycle.map(event => event.id)); this.latched = null
      this.run = this.loadRun(); this.boundWorkout = null; this.attempt = 0; this.refusedRevision = null
    }
    if (this.state === 'refused' && this.refusedRevision !== saved.revision) { this.refusedRevision = null; this.setState('off', null) }
    if (!this.socket && !this.connecting && this.retryHandle === null && this.state !== 'refused') void this.connect()
    if (this.state !== 'ready') { for (const event of input.lifecycle) this.forwarded.add(event.id); return }
    this.maybeBind(session)
    this.events(input, saved, session)
    if (input.nowMs - this.pingAt >= PING_EVERY_MS) { this.pingAt = input.nowMs; this.send({ type: 'ping' }) }
    if (input.nowMs - this.usageAt >= USAGE_EVERY_MS) { this.usageAt = input.nowMs; void this.pollUsage() }
  }

  /** Mixer observation → playback acknowledgements for session memory and pacing. */
  observe(audio: LocalAudioSnapshot | null): void {
    for (const [id, stream] of this.streams) {
      const item = audio?.utterances.find(entry => entry.id === id)
      if (item?.state === 'started' && !stream.started) {
        stream.started = true
        this.send({ type: 'playback_started', generationId: id, ...(stream.final ? { durationMs: Math.round(pcmDurationMs(stream.bytes, stream.sampleRate)) } : {}) })
      } else if (!item) {
        this.streams.delete(id)
        if (stream.started) { this.counters.spoken++; this.send({ type: 'playback_completed', generationId: id }) }
        else { this.counters.failed++; this.send({ type: 'playback_failed', generationId: id }) }
        this.changed()
      }
    }
  }

  async forgetMemory(signal?: AbortSignal): Promise<number | null> {
    const userId = this.last?.userId
    if (!userId || !/^[a-zA-Z0-9_-]{1,120}$/.test(userId)) return null
    try {
      const response = await this.deps.fetch(`/api/coach/users/${encodeURIComponent(userId)}/memory`, {
        method: 'DELETE', credentials: 'include', headers: { Accept: 'application/json' }, signal })
      if (!response.ok) return null
      return num(object(await response.json())?.cleared)
    } catch { return null }
  }

  dispose(): void { this.stop('off', null); this.disposed = true; this.listeners.clear() }

  // ---------- connection ----------

  private storageKey(): string { return `coach-run:${this.key}` }
  private loadRun(): Run | null {
    try {
      const value = object(JSON.parse(this.deps.storage?.getItem(this.storageKey()) ?? 'null'))
      const runId = str(value?.runId, 64), token = str(value?.token, 128)
      return runId && token ? { runId, token } : null
    } catch { return null }
  }
  private saveRun(run: Run | null): void {
    try {
      // Same-tab only (sessionStorage): a reload keeps one ledger per workout instead of a fresh cap.
      if (run) this.deps.storage?.setItem(this.storageKey(), JSON.stringify(run))
      else this.deps.storage?.removeItem(this.storageKey())
    } catch { /* storage unavailable: memory only */ }
  }

  private async connect(): Promise<void> {
    const input = this.last
    if (!input?.saved || !input.userId) return
    const key = this.key
    this.connecting = true
    try {
      if (!this.run) {
        this.setState('creating', null)
        const response = await this.deps.fetch('/api/coach/runs', { method: 'POST', credentials: 'include',
          headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
          body: JSON.stringify({ schemaVersion: 1, userId: input.userId, ledger: 'workout', capUsd: input.saved.budgetUsd }) })
        if (key !== this.key || this.disposed) return
        if (!response.ok) { this.retry(response.status === 404 || response.status === 403 ? 'run_unavailable' : 'run_create_failed'); return }
        const body = object(await response.json())
        const runId = str(body?.runId, 64), token = str(body?.runToken, 128)
        if (key !== this.key || this.disposed) return
        if (!runId || !token) { this.retry('invalid_response'); return }
        this.run = { runId, token }; this.saveRun(this.run)
      }
      this.open(this.run)
    } catch {
      if (key === this.key && !this.disposed) this.retry('network')
    } finally { this.connecting = false }
  }

  private open(run: Run): void {
    const origin = this.deps.origin()
    const scheme = origin.protocol === 'https:' ? 'wss' : 'ws'
    this.setState('connecting', null)
    let socket: SocketLike
    try { socket = this.deps.socket(`${scheme}://${origin.host}/api/coach/runs/${encodeURIComponent(run.runId)}/live`) } catch { this.retry('socket'); return }
    socket.binaryType = 'arraybuffer'
    this.socket = socket
    socket.onopen = () => { if (this.socket === socket) socket.send(JSON.stringify({ type: 'configure', runToken: run.token, ownerId: this.owner })) }
    socket.onmessage = message => { if (this.socket === socket) this.receive(message.data) }
    socket.onerror = () => undefined
    socket.onclose = () => {
      if (this.socket !== socket) return
      this.socket = null; this.configured = null; this.dropStreams()
      if (this.state !== 'refused' && this.state !== 'off') this.retry(this.reason ?? 'closed')
    }
  }

  private retry(reason: string): void {
    if (this.disposed || this.retryHandle !== null) return
    const delay = reason === 'owner_mismatch' ? 16_000 : BACKOFF_MS[Math.min(this.attempt, BACKOFF_MS.length - 1)]
    this.attempt++
    this.setState('retrying', reason)
    this.retryHandle = this.deps.setTimeout(() => {
      this.retryHandle = null
      if (!this.disposed && this.last) this.tick(this.last)
    }, delay)
  }

  private stop(state: NetworkState, reason: string | null): void {
    if (this.retryHandle !== null) { this.deps.clearTimeout(this.retryHandle); this.retryHandle = null }
    const socket = this.socket
    this.socket = null
    if (socket) { try { socket.close(1000) } catch { /* already closed */ } }
    this.dropStreams()
    this.configured = null
    if (state === 'off') this.key = ''
    this.setState(state, reason)
  }

  private dropStreams(): void {
    for (const [id, stream] of this.streams) stream.mixer.cancelStream(id, 'cancelled')
    this.streams.clear()
  }

  private maybeBind(session: RuntimeWorkoutSession): void {
    const workoutId = session.backendWorkoutSessionId
    const run = this.run
    if (!run || !Number.isInteger(workoutId) || workoutId! <= 0 || this.boundWorkout === workoutId) return
    this.boundWorkout = workoutId!
    void this.deps.fetch(`/api/coach/runs/${encodeURIComponent(run.runId)}/bind`, { method: 'POST', credentials: 'include',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json', 'X-Coach-Run-Token': run.token },
      body: JSON.stringify({ schemaVersion: 1, workoutSessionId: workoutId }) }).catch(() => undefined)
  }

  private async pollUsage(): Promise<void> {
    const run = this.run
    if (!run || this.usageBusy) return
    this.usageBusy = true
    try {
      const response = await this.deps.fetch(`/api/coach/runs/${encodeURIComponent(run.runId)}/usage`, { method: 'GET', credentials: 'include',
        headers: { Accept: 'application/json', 'X-Coach-Run-Token': run.token } })
      if (!response.ok) return
      const body = object(await response.json())
      if (!body || this.run !== run) return
      this.usage = Object.freeze({ requests: num(body.requests) ?? 0, settledMicros: num(body.settledMicros) ?? 0,
        pendingMicros: num(body.pendingMicros) ?? 0, capMicros: num(body.capMicros) ?? 0, limitKind: str(body.limitKind, 60) ?? '' })
      this.changed()
    } catch { /* usage is diagnostics only */ } finally { this.usageBusy = false }
  }

  // ---------- inbound ----------

  private receive(data: unknown): void {
    if (data instanceof ArrayBuffer) { this.frame(new Uint8Array(data)); return }
    if (typeof data !== 'string' || data.length > 16_384) return
    let message: Record<string, unknown> | null
    try { message = object(JSON.parse(data)) } catch { return }
    if (!message) return
    switch (message.type) {
      case 'configured':
        this.configured = { mode: str(message.mode, 20), voiceId: str(message.voiceId, 40), text: message.text === true,
          voice: message.voice === true, degraded: message.degraded === true }
        this.attempt = 0
        this.setState('ready', this.configured.degraded ? 'degraded' : null)
        if (this.last) this.tick(this.last)
        break
      case 'speech_start': this.speechStart(message); break
      case 'speech_end': this.speechEnd(message); break
      case 'decision': {
        const text = message.action === 'text' ? str(message.text, 600) : null
        if (text) this.lastText = text
        this.note(str(message.reason, 80), { triggerId: str(message.triggerId, 10), action: str(message.action, 20) ?? 'silence', text })
        break
      }
      case 'event_rejected': this.note(str(message.reason, 80), { triggerId: null, action: 'rejected', text: null }); break
      case 'error': {
        const reason = str(message.reason, 80) ?? 'error'
        if (reason === 'run_not_found' || reason === 'run_not_live' || reason === 'run_closed') { this.run = null; this.saveRun(null) }
        if (reason === 'local_mode' || reason === 'coach_disabled') { this.refusedRevision = this.last?.saved?.revision ?? null; this.setState('refused', reason) }
        else this.reason = reason
        this.count(reason)
        break
      }
      default: break
    }
  }

  private speechStart(message: Record<string, unknown>): void {
    const gid = str(message.generationId, 120), source = str(message.source, 20)
    const sampleRate = num(message.sampleRate), validFor = num(message.validForMs)
    const input = this.last
    if (!gid || !source || !SOURCES.has(source) || !sampleRate || validFor === null || !input) return
    this.counters.streams++
    const scope = input.scope, mixer = this.quiet(input) ? null : input.mixer()
    // The server's event scope epoch belongs to an earlier view; the stream adopts the
    // scope that is current now and is invalidated by the mixer on the next change.
    if (!scope || !mixer || !mixer.beginStream({ id: gid, generationId: gid, scope, source: source as NetworkAudioSource,
      sampleRate, startDeadlineMs: input.nowMs + Math.max(0, validFor), baseGain: 1, prebufferMs: 200,
      revalidate: () => !!this.last && !this.quiet(this.last) && this.last.scope?.scopeEpoch === scope.scopeEpoch })) {
      this.counters.failed++
      this.count(mixer ? mixer.snapshot().reason : input.gate ?? 'unavailable')
      this.send({ type: 'cancel' }); this.send({ type: 'playback_failed', generationId: gid })
      return
    }
    this.streams.set(gid, { scope, source: source as NetworkAudioSource, sampleRate, bytes: 0, final: false, started: false, mixer })
    this.changed()
  }

  private frame(bytes: Uint8Array): void {
    let frame: ReturnType<typeof decodeCoachFrame>
    try { frame = decodeCoachFrame(bytes) } catch (error) { this.count(error instanceof CoachFrameError ? error.message : 'frame'); return }
    const id = frame.metadata.generationId, stream = this.streams.get(id)
    if (!stream) return
    if (!stream.mixer.pushStream({ ...frame.metadata, scope: stream.scope }, frame.pcm)) {
      // The mixer may already have reported the removal through observe().
      if (this.streams.delete(id)) {
        this.counters.failed++
        this.send({ type: 'cancel' }); this.send({ type: 'playback_failed', generationId: id })
        this.changed()
      }
      return
    }
    stream.bytes += frame.pcm.length
    if (frame.metadata.final) stream.final = true
  }

  private speechEnd(message: Record<string, unknown>): void {
    const gid = str(message.generationId, 120)
    const first = num(message.firstAudioMs)
    if (first !== null) this.firstAudioMs = Math.round(first)
    if (message.status !== 'complete') this.count(str(message.reason, 80) ?? str(message.status, 40) ?? 'incomplete')
    const stream = gid ? this.streams.get(gid) : undefined
    if (gid && stream && message.status !== 'complete' && !stream.final) stream.mixer.cancelStream(gid, 'cancelled')
    this.changed()
  }

  // ---------- outbound ----------

  private quiet(input: NetworkTick): boolean {
    // Text-only never needs the mixer, so its permanent `mute` gate is not a reason to stay silent.
    return input.latched || (input.gate !== null && !(input.saved?.mode === 'text-only' && input.gate === 'mute'))
  }

  private events(input: NetworkTick, saved: CoachPreferences, session: RuntimeWorkoutSession): void {
    if (this.latched !== input.latched) {
      this.latched = input.latched
      this.send({ type: 'safety', latched: input.latched })
    }
    const scope = input.scope
    const quiet = this.quiet(input)
    for (const event of input.lifecycle) {
      if (this.forwarded.has(event.id)) continue
      this.forwarded.add(event.id)
      if (quiet || !FORWARDED.has(event.kind) || event.scope.userId !== input.userId) continue
      const refs = input.refs(event.id)
      if (!refs) continue
      this.forward(event, refs, this.restContext(session, event.scope.exerciseId, event.scope.setOrdinal))
    }
    if (!scope || quiet) return
    const exercise = session.exercises.find(item => item.id === session.currentExerciseId)
    const progress = Object.values(session.completedSets).some(list => list.length > 0)
    if (!this.sentKeys.has('workout')) {
      this.sentKeys.add('workout')
      if (exercise) this.sentKeys.add(`exercise:${exercise.id}`) // The opening already covers the first exercise.
      if (!progress && (input.phase === 'setup' || input.phase === 'waiting-start')) this.emit('workout_started', { ...scope, setOrdinal: null, exerciseId: null }, input, 'setup')
      return
    }
    if (!exercise) return
    const exerciseKey = `exercise:${exercise.id}`
    if (!this.sentKeys.has(exerciseKey) && (input.phase === 'setup' || input.phase === 'waiting-start')) {
      this.sentKeys.add(exerciseKey)
      if (!(session.completedSets[exercise.id]?.length)) {
        this.emit('exercise_ready', { ...scope, setOrdinal: null }, input, 'setup', { exerciseName: exercise.name.slice(0, 120) })
        return
      }
    }
    const setKey = `${exercise.id}:${scope.setOrdinal}`
    if (input.phase === 'active-set' && saved.duringSets && exercise.kind === 'machine' && !this.sentKeys.has(`milestone:${setKey}`)) {
      const target = exactRepTarget(exercise.plan[session.currentSetIndex])
      const reps = input.reps
      if (target !== null && target >= 8 && reps !== null && reps >= Math.ceil(target / 2) && reps <= target - 2) {
        this.sentKeys.add(`milestone:${setKey}`)
        this.emit('rep_milestone', scope, input, 'active-set', { phaseElapsedMs: 0 }, 'reps')
      }
    }
    const rest = session.restState
    if (input.phase === 'rest' && saved.duringRest && rest && !rest.timerPaused && !this.sentKeys.has(`rest:${setKey}`)) {
      const elapsed = rest.totalSeconds - rest.remainingSeconds
      if (elapsed >= REST_EXTRA_MIN_ELAPSED_S && rest.remainingSeconds >= REST_EXTRA_MIN_LEFT_S) {
        this.sentKeys.add(`rest:${setKey}`)
        this.emit('rest_long_opportunity', scope, input, 'rest', { restMs: rest.totalSeconds * 1000, restElapsedMs: elapsed * 1000 })
      }
    }
  }

  private restContext(session: RuntimeWorkoutSession, exerciseId: string | null, setOrdinal: number | null): Record<string, number> {
    const rest = session.restState
    if (rest) return { restMs: rest.totalSeconds * 1000, restElapsedMs: Math.max(0, rest.totalSeconds - rest.remainingSeconds) * 1000 }
    const plan = session.exercises.find(item => item.id === exerciseId)?.plan[(setOrdinal ?? 1) - 1]
    return plan && Number.isFinite(plan.restSeconds) && plan.restSeconds > 0 ? { restMs: plan.restSeconds * 1000, restElapsedMs: 0 } : {}
  }

  private emit(kind: CoachEventKind, scope: CoachScope, input: NetworkTick, phase: CoachPhase, context: Record<string, unknown> = {},
    progressUnit: 'reps' | null = null): void {
    const session = input.session!
    const exerciseKind = session.exercises.find(item => item.id === scope.exerciseId)?.kind
    const now = Math.max(0, input.nowMs)
    const event: CoachEvent = { schemaVersion: 1, id: `net-${++this.sequence}`, scope, kind, phase, source: 'runtime_ack',
      exerciseKind: exerciseKind && EXERCISE_KINDS.has(exerciseKind) ? exerciseKind as CoachEvent['exerciseKind'] : null,
      controlMode: null, progressUnit, ordinal: 0, planRevision: 0, contextVersion: 0, createdAtMs: now, startDeadlineMs: now + 20_000,
      facts: [], factDependencies: [] }
    this.forward(event, null, context)
  }

  private forward(event: CoachEvent, refs: LifecycleRefs | null, context: Record<string, unknown>): void {
    this.counters.eventsSent++
    this.send({ type: 'event', event, ...(refs ? { refs } : {}), context })
    this.changed()
  }

  private send(message: Record<string, unknown>): void {
    const socket = this.socket
    if (!socket || socket.readyState !== OPEN) return
    try { socket.send(JSON.stringify(message)) } catch { /* close handler reconnects */ }
  }

  // ---------- diagnostics ----------

  private note(reason: string | null, decision: Omit<NetworkDecision, 'atMs' | 'reason'>): void {
    if (reason) this.count(reason, false)
    this.decisions.push(Object.freeze({ atMs: this.last?.nowMs ?? 0, reason, ...decision }))
    if (this.decisions.length > 30) this.decisions.shift()
    this.changed()
  }

  private count(reason: string, notify = true): void {
    const key = reason.split(':', 1)[0].slice(0, 60)
    if (key in this.reasons || Object.keys(this.reasons).length < 64) this.reasons[key] = (this.reasons[key] ?? 0) + 1
    if (notify) this.changed()
  }

  private setState(state: NetworkState, reason: string | null): void {
    if (this.state === state && this.reason === reason) return
    this.state = state; this.reason = reason
    this.changed()
  }

  private changed(): void {
    this.snap = null
    for (const listener of this.listeners) listener()
  }
}

/** Redacted diagnostics export: reasons, counters and usage only — no texts, IDs or tokens. */
export function redactedNetworkReport(snapshot: NetworkSnapshot): string {
  return JSON.stringify({ schemaVersion: 1, state: snapshot.state, reason: snapshot.reason, mode: snapshot.mode, voiceId: snapshot.voiceId,
    degraded: snapshot.degraded, eventsSent: snapshot.eventsSent, streams: snapshot.streams, spoken: snapshot.spoken, failed: snapshot.failed,
    firstAudioMs: snapshot.firstAudioMs, reasons: snapshot.reasons, usage: snapshot.usage,
    decisions: snapshot.decisions.map(item => ({ triggerId: item.triggerId, action: item.action, reason: item.reason })) }, null, 2)
}
