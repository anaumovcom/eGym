import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { CoachFrameError, decodeCoachFrame, pcmDurationMs } from '../audio/coach-frames'
import type { AudioReason, LocalAudioSnapshot, LocalCoachAudioManager, NetworkAudioSource } from '../audio/local-coach-audio-manager'
import { exactRepTarget, type SetTimerInput } from '../interpreter/coach-interpreter'
import { parseBudget, type BudgetState } from '../lib/diagnostics-api'
import { coachEventIds } from '../lib/event-ids'
import type { LifecycleContext, LifecycleRefs, LifecycleVersions } from '../lib/lifecycle-observer'
import { coachRunId, type CoachEvent, type CoachEventKind, type CoachPhase, type CoachScope, type CoachSpeechIdentity } from '../model/contracts'
import { preferencesValid, type CoachPreferences } from '../model/preferences'
import { matchesIdentity, planSignature, sameRun, sameScope, speechIdentity, speechSurvives, type SpeechContext } from './coach-scope-policy'
import type { LocalCompletion } from './local-completion'
import { OPPORTUNITY_STATES, transitionOpportunity, type OpportunityState } from './opportunity'
import { RepTracker, telemetryContext, type TelemetrySample } from './rep-tracker'

/** E10 live client: forwards a few semantic events over one WebSocket and plays the
 * backend's tagged PCM through the local mixer. The run token only travels in the
 * first `configure` message and in `X-Coach-Run-Token` headers, never in a URL. */
export type NetworkMixer = Pick<LocalCoachAudioManager, 'beginStream' | 'pushStream' | 'cancelStream' | 'snapshot'>
export type NetworkTick = Readonly<{
  nowMs: number; userId: string | null; saved: CoachPreferences | null; session: RuntimeWorkoutSession | null
  featureEnabled: boolean; phase: CoachPhase; scope: CoachScope | null; latched: boolean; gate: AudioReason | null
  reps: number | null; partialReps?: number | null; timer?: SetTimerInput | null; lifecycle: readonly CoachEvent[]; refs: (eventId: string) => LifecycleRefs | null
  mixer: () => NetworkMixer | null
  localCompletion?: (event: CoachEvent) => LocalCompletion | null
  /** V2: the machine's bar position/velocity sample of this tick (absent without hardware telemetry). */
  telemetry?: TelemetrySample | null
}>
export type NetworkState = 'off' | 'creating' | 'connecting' | 'ready' | 'retrying' | 'refused'
export type NetworkDecision = Readonly<{ atMs: number; triggerId: string | null; action: string; reason: string | null; text: string | null }>
export type NetworkUsage = Readonly<{ requests: number; settledMicros: number; pendingMicros: number; capMicros: number; limitKind: string
  /** V0 budget buckets and degradation tier of this workout's ledger. */
  budget: BudgetState | null }>
export type NetworkSnapshot = Readonly<{
  state: NetworkState; reason: string | null; mode: string | null; voiceId: string | null; text: boolean; voice: boolean
  /** Billing ledger of the current workout (not secret: the run token never leaves the client). */
  runId: string | null
  degraded: boolean; eventsSent: number; streams: number; spoken: number; failed: number
  decisions: readonly NetworkDecision[]; reasons: Readonly<Record<string, number>>; usage: NetworkUsage | null
  lastText: string | null; firstAudioMs: number | null
  /** firstAudioMs remains the server voice-only metric, NOT end-to-end latency. */
  firstAudioMsLabel: 'voice-only'; latencies: Readonly<Record<string, LatencySummary>>
  /** Server receipt-relative monotonic deltas; never added to browser durations. */
  serverTimings: Readonly<Record<string, LatencySummary>>
  telemetry: Readonly<{ classified: number; missingClassification: number; pendingClassification: number; retained: number }>
  opportunities?: Readonly<Record<OpportunityState, number>>
  scenario?: ScenarioView
}>
export type LatencySummary = Readonly<{ count: number; p50: number; p95: number }>
/** V1 workout scenario: three generated cards to choose from, then the chosen story's acts. */
export type ScenarioPhase = 'off' | 'waiting' | 'proposing' | 'choosing' | 'building' | 'ready' | 'skipped' | 'failed'
export type ScenarioCard = Readonly<{ archetype: string; title: string; tagline: string; tone: string }>
export type ScenarioAct = Readonly<{ act: number; title: string; exerciseIds: readonly string[] }>
export type ScenarioView = Readonly<{
  phase: ScenarioPhase; cards: readonly ScenarioCard[]; proposalsLeft: number; title: string | null; tagline: string | null
  archetype: string | null; acts: readonly ScenarioAct[]; counters: readonly Readonly<{ id: string; label: string; value?: number | null }>[]
  coHost: Readonly<{ role: string; name: string }> | null; error: string | null
}>
const SCENARIO_OFF: ScenarioView = Object.freeze({ phase: 'off', cards: [], proposalsLeft: 0, title: null, tagline: null, archetype: null,
  acts: [], counters: [], coHost: null, error: null })
/** The opening line waits for the choice at most this long; then the workout starts without a story. */
const SCENARIO_HOLD_MS = 150_000
const SCENARIO_STATE_WAIT_MS = 4_000
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
  nowMs: () => number
}>

type Classification = { source: string; voiceModel: string; textModel: string; connection: string }
type EventTelemetry = { classification: Classification | null; pending: Map<string, number>; measured: Set<string> }
type SentEvent = { identity: CoachSpeechIdentity; kind: CoachEventKind; context: SpeechContext; valid: boolean; claimed: boolean; summaryRemapped: boolean; confirmedResult: boolean; sentAtMs: number; telemetry: EventTelemetry; state: OpportunityState }
type Stream = { event: SentEvent; source: NetworkAudioSource; sampleRate: number; bytes: number; final: boolean; started: boolean; lastProgressAckMs?: number; firstPcm: boolean; ended: boolean; mixer: NetworkMixer }
type Run = { runId: string; token: string }
const OPEN = 1
const BACKOFF_MS = [1_000, 2_000, 4_000, 8_000, 16_000, 30_000]
const SOURCES = new Set(['realtime', 'tts', 'fish', 'fake'])
const FORWARDED: ReadonlySet<CoachEventKind> = new Set(['set_persisted', 'exercise_finalized', 'workout_finalized'])
const EXERCISE_KINDS = new Set(['machine', 'bodyweight', 'timed', 'stretch', 'group'])
const REST_EXTRA_MIN_ELAPSED_S = 15
const REST_EXTRA_MIN_LEFT_S = 40
// V2 #14: a pause between reps worth a word (bar still for this long after the first rep).
const SET_STALL_MS = 4_500
const SET_NO_REP_MS = 8_000
const SET_ADVICE_INTERVAL_MS = 15_000
const USAGE_EVERY_MS = 15_000
const PING_EVERY_MS = 20_000
// Provider PCM can arrive much faster than real-time. Per-frame ACKs can
// exceed the server's control-message rate limit and tear down audible speech.
const PLAYBACK_PROGRESS_ACK_MS = 500
const MAX_TIMING_MS = 86_400_000
const SERVER_STAGES = ['receive', 'textStart', 'textEnd', 'firstPcm', 'speechEnd', 'ackStart', 'ackEnd', 'ackCancel', 'textDuration'] as const
// Exact public IDs only: a regex accepting arbitrary model suffixes can leak PII/secrets.
const PUBLIC_TEXT_MODELS = new Set(['gpt-6-luna', 'gpt-4.1', 'gpt-4.1-mini', 'gpt-4o', 'gpt-4o-mini', 'fake-text'])
const PUBLIC_VOICE_MODELS: Readonly<Record<string, ReadonlySet<string>>> = {
  realtime: new Set(['gpt-realtime-2.1-mini', 'gpt-realtime', 'gpt-realtime-mini', 'gpt-4o-realtime-preview', 'gpt-4o-mini-realtime-preview']),
  tts: new Set(['gpt-4o-mini-tts', 'tts-1', 'tts-1-hd']), fake: new Set(['fake-voice']),
}
const CONNECTIONS = new Set(['cold', 'warm', 'unknown', 'not-applicable', 'fake'])
function summaries(groups: Map<string, number[]>): Readonly<Record<string, LatencySummary>> {
  return Object.freeze(Object.fromEntries([...groups].map(([key, samples]) => {
    const sorted = [...samples].sort((a, b) => a - b)
    return [key, Object.freeze({ count: sorted.length, p50: sorted[Math.ceil(sorted.length * .5) - 1], p95: sorted[Math.ceil(sorted.length * .95) - 1] })]
  })))
}

type SessionExercise = RuntimeWorkoutSession['exercises'][number]
type SetPlan = SessionExercise['plan'][number]
/** Loaded definition identity only. Never forward guide text or assume a cable/handle variant.
 * The display label is declared ordinary weight, not measured/applied motor telemetry. */
export function exerciseIdentity(session: RuntimeWorkoutSession, exercise: SessionExercise): Record<string, string> {
  if (session.dataSource !== 'backend' || typeof exercise.slug !== 'string'
    || exercise.details?.slug !== exercise.slug || exercise.summary?.slug !== exercise.slug
    || !/^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/.test(exercise.slug) || exercise.slug.length > 100) return {}
  const mode = exercise.loadSettings.mode
  return { exerciseSlug: exercise.slug, variant: exercise.slug,
    ...(mode === 'constant' || mode === 'Обычный вес' ? { controlMode: 'constant' } : {}) }
}
function whole(value: number | null | undefined): number | undefined {
  return typeof value === 'number' && Number.isInteger(value) && value > 0 ? value : undefined
}
/** Rep goal of a set for pacing: the exact target, else the top of the range. Failure sets have none. */
function repGoal(plan: SetPlan | undefined): number | null {
  if (!plan || plan.setType === 'failure') return null
  return exactRepTarget(plan) ?? whole(plan.targetMaxReps) ?? null
}
/** Plan facts the backend coach may voice when introducing an exercise. */
function exerciseContext(session: RuntimeWorkoutSession, exercise: SessionExercise): Record<string, unknown> {
  const first = exercise.plan[0]
  const exact = whole(exactRepTarget(first)) ?? whole(first?.targetSeconds)
  const low = whole(first?.targetMinReps), high = whole(first?.targetMaxReps)
  const weight = first?.recommendedWeightKg
  return { ...exerciseIdentity(session, exercise), exerciseName: exercise.name.slice(0, 120), exerciseIndex: session.exercises.indexOf(exercise) + 1,
    exerciseCount: session.exercises.length, totalSets: exercise.plan.length,
    ...(exact ? { targetReps: exact } : low && high ? { targetMin: low, targetMax: high } : {}),
    ...(typeof weight === 'number' && Number.isFinite(weight) && weight > 0 ? { weightKg: weight } : {}) }
}
/** Name of the following exercise, only once the last planned set of the current one is done. */
function nextExercise(session: RuntimeWorkoutSession, exerciseId: string | null, setOrdinal: number | null): Record<string, string> {
  const index = session.exercises.findIndex(item => item.id === exerciseId)
  const next = index >= 0 && setOrdinal !== null && setOrdinal >= session.exercises[index].plan.length ? session.exercises[index + 1] : undefined
  return next ? { nextExerciseName: next.name.slice(0, 120) } : {}
}

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
    nowMs: () => performance.now(),
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
  private readonly nextEventId = coachEventIds('net')
  private sentKeys = new Set<string>()
  private forwarded = new Set<string>()
  private inSet: { key: string; startedAt: number; reps: number | null; repAt: number; partial: number | null } | null = null
  private latched: boolean | null = null
  private streams = new Map<string, Stream>()
  private localStarted = new Set<string>() // Bounded, fail closed; IDs never leave the browser.
  // No eviction/replay: capacity fails closed until a new user/run. Invalid entries
  // remain tombstones so returning to a previous phase or unmuting cannot resurrect them.
  private registry = new Map<string, SentEvent>()
  private generations = new Set<string>()
  private planRevision = 0
  private contextVersion = 0
  private planKey: string | null = null
  private contextKey = ''
  private context: SpeechContext | null = null
  private history: Array<{ atMs: number; context: SpeechContext }> = []
  private clockAnchor = 0
  private latencySamples = new Map<string, number[]>()
  private serverSamples = new Map<string, number[]>()
  // Terminal audio cannot restart; these records are for late metadata only.
  private terminalStreams = new Map<string, Pick<Stream, 'event' | 'source' | 'ended'>>()
  private classified = 0
  private missingClassification = 0
  private counters = { eventsSent: 0, streams: 0, spoken: 0, failed: 0 }
  private opportunityCounts = Object.fromEntries(OPPORTUNITY_STATES.map(state => [state, 0])) as Record<OpportunityState, number>
  private decisions: NetworkDecision[] = []
  private reasons: Record<string, number> = {}
  private usage: NetworkUsage | null = null
  private usageAt = -Infinity
  private usageBusy = false
  private pingAt = 0
  private lastText: string | null = null
  private textEvent: SentEvent | null = null
  private firstAudioMs: number | null = null
  private snap: NetworkSnapshot | null = null
  private scenario: ScenarioView = SCENARIO_OFF
  private readonly repTracker = new RepTracker()
  private scenarioSince = 0
  private scenarioProposed = false
  private readonly listeners = new Set<() => void>()
  private disposed = false

  constructor(deps: Partial<NetworkDependencies> = {}) {
    this.deps = { ...defaults(), ...deps }
    this.owner = this.deps.ownerId().slice(0, 120)
  }

  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  /** Synchronous capture-time read; rejects an unobserved plan/owner/settings
   * change instead of stamping the last tick's revision onto new workout data. */
  captureVersions(current: LifecycleContext, session: RuntimeWorkoutSession | null, saved: CoachPreferences | null): LifecycleVersions | null {
    const context = this.context, scope = context?.scope
    if (this.disposed || !this.key || !context || context.blocked || !scope || !session || !saved ||
      !this.last || !networkEligible({ ...this.last, userId: current.userId, session, saved }) ||
      this.last.session?.id !== session.id || this.last.session.view !== session.view || this.last.saved?.revision !== saved.revision ||
      scope.userId !== current.userId || scope.runId !== current.runId || scope.exerciseId !== current.exerciseId ||
      scope.setOrdinal !== current.setOrdinal || session.currentExerciseId !== scope.exerciseId ||
      session.currentSetIndex + 1 !== scope.setOrdinal || planSignature(session, saved.mode) !== this.planKey) return null
    return Object.freeze({ scope, phase: context.phase, planRevision: context.planRevision, contextVersion: context.contextVersion })
  }
  getSnapshot = (): NetworkSnapshot => this.snap ??= Object.freeze({
    state: this.state, reason: this.reason, mode: this.configured?.mode ?? null, voiceId: this.configured?.voiceId ?? null,
    runId: this.run?.runId ?? null,
    text: this.configured?.text ?? false, voice: this.configured?.voice ?? false, degraded: this.configured?.degraded ?? false,
    ...this.counters, decisions: Object.freeze([...this.decisions]), reasons: Object.freeze({ ...this.reasons }),
    usage: this.usage, lastText: this.lastText, firstAudioMs: this.firstAudioMs,
    firstAudioMsLabel: 'voice-only', latencies: summaries(this.latencySamples), serverTimings: summaries(this.serverSamples),
    opportunities: Object.freeze({ ...this.opportunityCounts }),
    scenario: this.scenario,
    telemetry: Object.freeze({ classified: this.classified, missingClassification: this.missingClassification,
      pendingClassification: [...this.registry.values()].filter(event => event.telemetry.pending.size > 0).length, retained: this.terminalStreams.size }),
  })

  /** Called on every runtime tick (input change or 250 ms timer). */
  tick(input: NetworkTick): void {
    if (this.disposed) return
    this.last = input
    this.clockAnchor = this.deps.nowMs()
    if (!networkEligible(input)) { this.stop('off', null); return }
    const saved = input.saved!, session = input.session!
    const key = JSON.stringify([input.userId, coachRunId(session)])
    if (key !== this.key) {
      this.stop('off', null)
      this.key = key
      this.sentKeys = new Set(); this.forwarded = new Set(input.lifecycle.map(event => event.id)); this.latched = null; this.inSet = null
      this.run = this.loadRun(); this.boundWorkout = null; this.attempt = 0; this.refusedRevision = null
      this.registry.clear(); this.generations.clear(); this.history = []; this.context = null; this.contextKey = ''; this.planKey = null
      this.localStarted.clear()
      this.scenario = SCENARIO_OFF; this.scenarioProposed = false
      this.repTracker.clear()
    }
    this.updateContext(input)
    if (this.state === 'refused' && this.refusedRevision !== saved.revision) { this.refusedRevision = null; this.setState('off', null) }
    if (!this.socket && !this.connecting && this.retryHandle === null && this.state !== 'refused') void this.connect()
    if (this.state !== 'ready') { for (const event of input.lifecycle) this.forwarded.add(event.id); return }
    this.maybeBind(session)
    // Audio may have started between runtime ticks. ACK that start BEFORE the
    // new context, so the server also preserves it across a parameter edit.
    const activeMixer = this.streams.values().next().value?.mixer
    if (activeMixer) this.observe(activeMixer.snapshot())
    this.sendContext()
    this.events(input, saved, session)
    if (input.nowMs - this.pingAt >= PING_EVERY_MS) { this.pingAt = input.nowMs; this.send({ type: 'ping' }) }
    if (input.nowMs - this.usageAt >= USAGE_EVERY_MS) { this.usageAt = input.nowMs; void this.pollUsage() }
  }

  /** Mixer observation → playback acknowledgements for session memory and pacing. */
  observe(audio: LocalAudioSnapshot | null): void {
    for (const item of audio?.utterances ?? []) {
      if (item.state !== 'started' || !['local', 'cache'].includes(item.source) || this.localStarted.has(item.id)) continue
      if (this.localStarted.size >= 1024) break
      this.localStarted.add(item.id) // Do not replay offline observations after reconnect.
      const duration = item.bufferDurationMs, playback = item.localPlayback
      if (this.state !== 'ready' || !this.last || this.last.gate || this.last.latched || !this.last.scope ||
        !sameRun(item.scope, this.last.scope) || !playback || typeof duration !== 'number' ||
        !Number.isFinite(duration) || duration <= 0 || duration > 60_000) continue
      this.send({ type: 'localPlayback', kind: playback.kind, action: playback.action, durationMs: duration })
    }
    for (const [id, stream] of this.streams) {
      const item = audio?.utterances.find(entry => entry.id === id)
      if (item?.state === 'started' && !stream.started) {
        if (!stream.event.valid) { this.failStream(id, stream); continue }
        stream.started = true
        stream.lastProgressAckMs = this.now()
        this.transition(stream.event, 'started')
        this.measure('eventToPlaybackStart', stream, (item.startedAtMs ?? this.now()) - stream.event.identity.createdAtMs)
        this.send({ type: 'playback_started', generationId: id, identity: stream.event.identity, ...(stream.final ? { durationMs: Math.round(pcmDurationMs(stream.bytes, stream.sampleRate)) } : {}) })
        this.changed()
      } else if (!item) {
        this.streams.delete(id)
        stream.event.valid = false
        const receipt = audio?.terminal?.find(item => item.id === id)
        const ended = stream.started && receipt?.finished
        this.transition(stream.event, ended ? 'completed' : stream.started ? 'interrupted' : this.now() > stream.event.identity.startDeadlineMs ? 'expired' : 'rejected')
        if (ended) { this.counters.spoken++; this.send({ type: 'playback_completed', generationId: id, identity: stream.event.identity,
          durationMs: Math.round(pcmDurationMs(stream.bytes, stream.sampleRate)) }) }
        else { this.counters.failed++
          this.note(receipt?.reason ?? 'playback_failed', { triggerId: null, action: stream.started ? 'interrupted' : 'rejected', text: null })
          this.send({ type: 'playback_failed', generationId: id, identity: stream.event.identity,
          durationMs: Math.round(pcmDurationMs(stream.bytes, stream.sampleRate)) }) }
        this.measureEvent(ended ? 'eventToCompleted' : 'eventToFailed', stream.event, this.now() - stream.event.identity.createdAtMs)
        this.retainTerminal(id, stream)
        this.changed()
      }
    }
  }

  /** V1: ask the coach for three scenario cards (again: a regeneration, at most three times). */
  proposeScenarios(): void {
    const session = this.last?.session
    if (!session || this.state !== 'ready' || !['waiting', 'choosing', 'failed', 'off'].includes(this.scenario.phase)) return
    // The slug and each set's exact rep goal let the coach prepare plan-only lines (set start/finish, «what it works»).
    const plan = session.exercises.slice(0, 24).map(exercise => {
      const slug = exerciseIdentity(session, exercise).exerciseSlug
      return { id: exercise.id, name: exercise.name.slice(0, 120), sets: Math.max(1, Math.min(50, exercise.plan.length)),
        kind: exercise.kind, ...(slug ? { slug } : {}),
        ...(exercise.plan.length <= 50 ? { targets: exercise.plan.map(set => whole(exactRepTarget(set)) ?? null) } : {}) }
    })
    if (!plan.length) return
    this.scenarioProposed = true
    this.setScenario({ phase: 'proposing', error: null })
    this.send({ type: 'scenario_propose', plan })
  }
  selectScenario(index: number): void {
    if (this.scenario.phase !== 'choosing' || !Number.isInteger(index) || index < 0 || index >= this.scenario.cards.length) return
    const card = this.scenario.cards[index]
    this.setScenario({ phase: 'building', title: card.title, tagline: card.tagline, archetype: card.archetype, error: null })
    this.send({ type: 'scenario_select', index })
  }
  skipScenario(): void {
    if (this.scenario.phase === 'ready' || this.scenario.phase === 'skipped') return
    this.setScenario({ phase: 'skipped', cards: [] })
    this.send({ type: 'scenario_skip' })
    if (this.last) this.tick({ ...this.last, nowMs: this.now() })
  }

  private setScenario(patch: Partial<ScenarioView>): void {
    if (patch.phase && patch.phase !== this.scenario.phase) this.scenarioSince = this.now()
    this.scenario = Object.freeze({ ...this.scenario, ...patch })
    this.changed()
  }

  /** The opening waits while a story is being offered, chosen or written (bounded by SCENARIO_HOLD_MS). */
  private scenarioHolds(input: NetworkTick): boolean {
    const saved = input.saved
    if (!saved?.scenarioPicker) return false
    const phase = this.scenario.phase
    if (phase === 'off') {
      this.setScenario({ phase: 'waiting' })
      return true
    }
    if (phase === 'waiting' && this.now() - this.scenarioSince >= SCENARIO_STATE_WAIT_MS && !this.scenarioProposed) this.proposeScenarios()
    if (['waiting', 'proposing', 'choosing', 'building'].includes(phase)) {
      if (this.now() - this.scenarioSince < SCENARIO_HOLD_MS) return true
      this.skipScenario()
    }
    return false
  }

  private receiveScenario(message: Record<string, unknown>): void {
    if (message.type === 'scenarios') {
      const error = str(message.error, 60)
      if (error) { this.setScenario({ phase: this.scenario.phase === 'proposing' ? 'failed' : this.scenario.phase, error }); return }
      const cards = Array.isArray(message.cards) ? message.cards.slice(0, 3).flatMap(raw => {
        const card = object(raw)
        const archetype = str(card?.archetype, 24), title = str(card?.title, 60), tagline = str(card?.tagline, 160), tone = str(card?.tone, 60)
        return archetype && title && tagline && tone ? [{ archetype, title, tagline, tone }] : []
      }) : []
      if (cards.length !== 3) { this.setScenario({ phase: 'failed', error: 'invalid_scenarios' }); return }
      this.setScenario({ phase: 'choosing', cards, proposalsLeft: Math.max(0, Math.min(3, num(message.proposalsLeft) ?? 0)), error: null })
      return
    }
    const state = str(message.state, 16)
    if (state === 'none') {
      if (['off', 'waiting'].includes(this.scenario.phase) && this.last?.saved?.scenarioPicker && !this.scenarioProposed) {
        const session = this.last.session
        const fresh = !!session && !Object.values(session.completedSets).some(list => list.length > 0)
        if (fresh) this.proposeScenarios(); else this.setScenario({ phase: 'skipped' })
      }
      return
    }
    if (state === 'building') { this.setScenario({ phase: 'building', title: str(message.title, 60) ?? this.scenario.title }); return }
    if (state === 'skipped') { this.setScenario({ phase: 'skipped', cards: [] }); return }
    if (state === 'failed') { this.setScenario({ phase: 'failed', error: str(message.reason, 60) ?? 'failed' }); return }
    if (state !== 'ready') return
    const acts = Array.isArray(message.acts) ? message.acts.slice(0, 3).flatMap(raw => {
      const act = object(raw), number = num(act?.act), title = str(act?.title, 80)
      const ids = Array.isArray(act?.exerciseIds) ? act.exerciseIds.filter((id): id is string => typeof id === 'string' && id.length <= 160).slice(0, 24) : []
      return number && title ? [{ act: number, title, exerciseIds: ids }] : []
    }) : []
    const counters = Array.isArray(message.counters) ? message.counters.slice(0, 2).flatMap(raw => {
      const counter = object(raw), id = str(counter?.id, 8), label = str(counter?.label, 60)
      return id && label ? [{ id, label, value: num(counter?.value) }] : []
    }) : []
    const co = object(message.coHost), role = str(co?.role, 80), name = str(co?.name, 60)
    this.setScenario({ phase: 'ready', cards: [], title: str(message.title, 60), tagline: str(message.tagline, 160),
      archetype: str(message.archetype, 24), acts, counters, coHost: role && name ? { role, name } : null, error: null })
    if (this.last) this.tick({ ...this.last, nowMs: this.now() })
  }

  /** V4: server-computed story counters (glory, donations, boss health) after each saved set. */
  private receiveCounters(message: Record<string, unknown>): void {
    if (this.scenario.phase !== 'ready' || !Array.isArray(message.counters)) return
    const counters = message.counters.slice(0, 3).flatMap(raw => {
      const counter = object(raw), id = str(counter?.id, 8), label = str(counter?.label, 60), value = num(counter?.value)
      return id && label && value !== null && value >= 0 ? [{ id, label, value }] : []
    })
    this.setScenario({ counters })
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
        if (!response.ok) {
          let reason = response.status === 404 || response.status === 403 ? 'run_unavailable' : 'run_create_failed'
          // Never expose arbitrary response details (which may contain private
          // data). This exact public code distinguishes capacity from networking.
          if (response.status === 429) {
            try { if (object(await response.json())?.detail === 'active_runs_full') reason = 'active_runs_full' } catch { /* non-JSON proxy response */ }
          }
          if (key === this.key && !this.disposed) this.retry(reason)
          return
        }
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
    const input = this.last
    if (!input?.session) return
    // Billing ledger IDs and browser runtime IDs are intentionally different.
    // Capture the binding before onopen, never adopt a later user's session.
    const runtimeRunId = coachRunId(input.session), key = this.key
    const origin = this.deps.origin()
    const scheme = origin.protocol === 'https:' ? 'wss' : 'ws'
    this.setState('connecting', null)
    let socket: SocketLike
    try { socket = this.deps.socket(`${scheme}://${origin.host}/api/coach/runs/${encodeURIComponent(run.runId)}/live`) } catch { this.retry('socket'); return }
    socket.binaryType = 'arraybuffer'
    this.socket = socket
    socket.onopen = () => {
      if (this.socket === socket && this.key === key)
        socket.send(JSON.stringify({ type: 'configure', runToken: run.token, ownerId: this.owner, runtimeRunId }))
    }
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
      if (!this.disposed && this.last) this.tick({ ...this.last, nowMs: this.now() })
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
    if ([...this.streams.values()].some(stream => stream.started))
      this.note(this.reason ?? 'closed', { triggerId: null, action: 'interrupted', text: null })
    for (const event of this.registry.values()) {
      event.valid = false
      this.transition(event, event.state === 'started' ? 'interrupted' : 'rejected')
    }
    this.clearText()
    this.sentContextKey = ''
    for (const [id, stream] of [...this.streams]) this.failStream(id, stream)
    this.streams.clear()
    for (const stream of this.terminalStreams.values()) this.classifyUnknown(stream.event, stream.source)
    this.terminalStreams.clear()
    for (const event of this.registry.values()) if (event.telemetry.pending.size) this.classifyUnknown(event)
    this.changed()
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
      let budget: BudgetState | null = null
      try { budget = parseBudget(body.budget) } catch { budget = null }
      this.usage = Object.freeze({ requests: num(body.requests) ?? 0, settledMicros: num(body.settledMicros) ?? 0,
        pendingMicros: num(body.pendingMicros) ?? 0, capMicros: num(body.capMicros) ?? 0, limitKind: str(body.limitKind, 60) ?? '', budget })
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
      case 'configured': {
        const legacyReason = str(message.degraded, 80)
        const degraded = message.degraded === true || !!legacyReason
        const rawReason = str(message.degradedReason, 80) ?? legacyReason
        const reason = rawReason && ['credential_unavailable', 'voice_unavailable', 'voice_fallback', 'provider_unavailable'].includes(rawReason)
          ? rawReason : 'degraded'
        this.configured = { mode: str(message.mode, 20), voiceId: str(message.voiceId, 40), text: message.text === true,
          voice: message.voice === true, degraded }
        this.attempt = 0
        this.setState('ready', degraded ? reason : null)
        if (this.last) this.tick({ ...this.last, nowMs: this.now() })
        break
      }
      case 'scenarios': case 'scenario': this.receiveScenario(message); break
      case 'scenario_state': this.receiveCounters(message); break
      case 'speech_start': this.speechStart(message); break
      case 'speech_end': this.speechEnd(message); break
      case 'decision': {
        const text = message.action === 'text' ? str(message.text, 600) : null
        if (message.action === 'text') {
          const identity = object(message.identity), id = str(identity?.eventId, 120)
          const event = id ? this.registry.get(id) : undefined
          if (!text || !event || event.claimed || !event.valid || this.context?.blocked ||
            this.now() > event.identity.startDeadlineMs || !matchesIdentity(identity, event.identity) ||
            (message.eventId !== undefined && message.eventId !== id)) { this.count('stale_text'); break }
          event.claimed = true
          this.transition(event, 'ready') // Text display is not audible completion.
          this.lastText = text; this.textEvent = event
          this.classifyUnknown(event)
        }
        if (message.action === 'silence') {
          const id = str(message.eventId, 120), event = id ? this.registry.get(id) : undefined
          if (event) { event.valid = false; this.transition(event, message.reason === 'expired' ? 'expired' : 'rejected') }
        }
        this.note(str(message.reason, 80), { triggerId: str(message.triggerId, 10), action: str(message.action, 20) ?? 'silence', text })
        break
      }
      case 'event_rejected': {
        const id = str(message.eventId, 120), event = id ? this.registry.get(id) : undefined
        if (event) { event.valid = false; this.transition(event, message.reason === 'expired' ? 'expired' : 'rejected') }
        this.note(str(message.reason, 80), { triggerId: null, action: 'rejected', text: null }); break
      }
      case 'error': {
        const reason = str(message.reason, 80) ?? 'error'
        if (reason === 'run_not_found' || reason === 'run_not_live' || reason === 'run_closed') {
          this.dropStreams(); this.run = null; this.saveRun(null)
          // Do not accept fresh events/decisions on a server-closed run while
          // waiting for its transport close callback (which may never arrive).
          const socket = this.socket; this.socket = null; this.configured = null
          try { socket?.close(1000) } catch { /* already closed */ }
          this.retry(reason)
        }
        if (reason === 'local_mode' || reason === 'coach_disabled') { this.dropStreams(); this.refusedRevision = this.last?.saved?.revision ?? null; this.setState('refused', reason) }
        else this.reason = reason
        this.count(reason)
        break
      }
      default: break
    }
  }

  private speechStart(message: Record<string, unknown>): void {
    const gid = str(message.generationId, 120), source = str(message.source, 20)
    const sampleRate = num(message.sampleRate)
    const input = this.last
    if (!gid || !source || !SOURCES.has(source) || !sampleRate || !input) return
    const identity = object(message.identity), eventId = str(identity?.eventId, 120)
    const event = eventId ? this.registry.get(eventId) : undefined
    if (!event || !matchesIdentity(identity, event.identity) || (message.eventId !== undefined && message.eventId !== eventId)) {
      this.count('identity_mismatch'); return
    }
    if (this.generations.has(gid) || event.claimed || this.generations.size >= 1024) { this.count('duplicate'); return }
    this.generations.add(gid); event.claimed = true
    this.transition(event, 'ready')
    this.counters.streams++
    const scope = event.identity.scope, mixer = this.context?.blocked ? null : input.mixer()
    if (!event.valid || this.now() > event.identity.startDeadlineMs || !mixer || !mixer.beginStream({ id: gid, generationId: gid, scope, source: source as NetworkAudioSource,
      sampleRate, startDeadlineMs: event.identity.startDeadlineMs, baseGain: 1, prebufferMs: 200,
      revalidate: () => event.valid && !this.context?.blocked,
      allowScopeTransition: (original, current) => event.valid && sameScope(original, event.identity.scope) &&
        !!event.context.scope && sameScope(current, event.context.scope) })) {
      event.valid = false
      this.transition(event, this.now() > event.identity.startDeadlineMs ? 'expired' : 'rejected')
      this.counters.failed++
      this.measureEvent('eventToFailed', event, this.now() - event.identity.createdAtMs)
      this.retainTerminal(gid, { event, source: source as NetworkAudioSource, ended: false })
      this.count(mixer ? mixer.snapshot().reason : input.gate ?? 'unavailable')
      this.send({ type: 'cancel' }); this.send({ type: 'playback_failed', generationId: gid, identity: event.identity })
      return
    }
    this.streams.set(gid, { event, source: source as NetworkAudioSource, sampleRate, bytes: 0, final: false, started: false, firstPcm: false, ended: false, mixer })
    this.changed()
  }

  private frame(bytes: Uint8Array): void {
    let frame: ReturnType<typeof decodeCoachFrame>
    try { frame = decodeCoachFrame(bytes) } catch (error) { this.count(error instanceof CoachFrameError ? error.message : 'frame'); return }
    const id = frame.metadata.generationId, stream = this.streams.get(id)
    if (!stream) return
    if (!stream.event.valid || !sameScope(frame.metadata.scope, stream.event.identity.scope) || frame.metadata.utteranceId !== id ||
      !stream.mixer.pushStream(frame.metadata, frame.pcm)) {
      // The mixer may already have reported the removal through observe().
      if (this.streams.delete(id)) {
        stream.event.valid = false
        this.transition(stream.event, stream.started ? 'interrupted' : 'rejected')
        stream.mixer.cancelStream(id, 'stale')
        this.counters.failed++
        this.measureEvent('eventToFailed', stream.event, this.now() - stream.event.identity.createdAtMs)
        this.retainTerminal(id, stream)
        this.send({ type: 'cancel' }); this.send({ type: 'playback_failed', generationId: id, identity: stream.event.identity })
        this.changed()
      }
      return
    }
    stream.bytes += frame.pcm.length
    if (!stream.firstPcm && frame.pcm.length) {
      stream.firstPcm = true
      this.measure('firstAcceptedPcmMs', stream, this.now() - stream.event.identity.createdAtMs)
    }
    if (frame.metadata.final) stream.final = true
    if (stream.started && (stream.final || this.now() - (stream.lastProgressAckMs ?? -Infinity) >= PLAYBACK_PROGRESS_ACK_MS)) {
      stream.lastProgressAckMs = this.now()
      this.send({ type: 'playback_started', generationId: id,
        identity: stream.event.identity, durationMs: Math.round(pcmDurationMs(stream.bytes, stream.sampleRate)) })
    }
  }

  private speechEnd(message: Record<string, unknown>): void {
    const gid = str(message.generationId, 120)
    const active = gid ? this.streams.get(gid) : undefined
    const stream = active ?? (gid ? this.terminalStreams.get(gid) : undefined)
    if (!stream || stream.ended) return
    stream.ended = true
    const source = typeof message.source === 'string' && SOURCES.has(message.source) && message.source === stream.source ? message.source : 'unknown'
    const voiceModel = typeof message.voiceModel === 'string' && PUBLIC_VOICE_MODELS[source]?.has(message.voiceModel) ? message.voiceModel : 'unknown'
    const textModel = typeof message.textModel === 'string' && PUBLIC_TEXT_MODELS.has(message.textModel) ? message.textModel : 'unknown'
    const connection = typeof message.connectionClass === 'string' && CONNECTIONS.has(message.connectionClass) ? message.connectionClass : 'unknown'
    this.classify(stream.event, { source, voiceModel, textModel, connection })
    const timings = object(message.timingsMs)
    for (const stage of SERVER_STAGES) {
      const value = num(timings?.[stage])
      if (value !== null && value >= 0 && value <= MAX_TIMING_MS) this.sample(this.serverSamples, `${stage}:${this.group(stream.event)}`, value)
    }
    if (gid) this.terminalStreams.delete(gid)
    const first = num(message.firstAudioMs)
    if (first !== null && first >= 0 && first <= MAX_TIMING_MS) this.firstAudioMs = Math.round(first)
    if (message.status !== 'complete') this.count(str(message.reason, 80) ?? str(message.status, 40) ?? 'incomplete')
    this.usageAt = -Infinity // The header's spend follows each paid line instead of waiting for the next 15 s poll.
    if (gid && active && message.status !== 'complete' && !active.final) {
      this.note(str(message.reason, 80) ?? 'provider_error', { triggerId: null, action: active.started ? 'interrupted' : 'rejected', text: null })
      this.failStream(gid, active)
    }
    this.changed()
  }

  // ---------- outbound ----------

  private quiet(input: NetworkTick): boolean {
    // Text-only never needs the mixer, so its permanent `mute` gate is not a reason to stay silent.
    return input.latched || ['disabled', 'paused-set', 'suspended'].includes(input.phase) ||
      (input.gate !== null && !(input.saved?.mode === 'text-only' && input.gate === 'mute'))
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
      const localCompletion = input.localCompletion?.(event)
      const metrics = event.kind === 'set_persisted'
        ? telemetryContext(this.repTracker.finishedSet(`${event.scope.exerciseId}:${event.scope.setOrdinal}`, input.nowMs)) : {}
      this.forward(event, refs, { ...this.restContext(session, event.scope.exerciseId, event.scope.setOrdinal),
        ...(localCompletion ? { localCompletion } : {}), ...(Object.keys(metrics).length ? { setMetrics: metrics } : {}) })
    }
    if (!scope || quiet) return
    const exercise = session.exercises.find(item => item.id === session.currentExerciseId)
    const progress = Object.values(session.completedSets).some(list => list.length > 0)
    if (!this.sentKeys.has('workout') && !progress && (input.phase === 'setup' || input.phase === 'waiting-start') &&
      this.scenarioHolds(input)) return
    if (!this.sentKeys.has('workout')) {
      this.sentKeys.add('workout')
      if (exercise) this.sentKeys.add(`exercise:${exercise.id}`) // The opening already covers the first exercise.
      if (!progress && (input.phase === 'setup' || input.phase === 'waiting-start')) this.emit('workout_started', scope, input, input.phase,
        { exerciseCount: session.exercises.length, ...(exercise ? exerciseContext(session, exercise) : {}) })
      return
    }
    if (!exercise) return
    const exerciseKey = `exercise:${exercise.id}`
    if (!this.sentKeys.has(exerciseKey) && (input.phase === 'setup' || input.phase === 'waiting-start')) {
      this.sentKeys.add(exerciseKey)
      if (!(session.completedSets[exercise.id]?.length)) {
        this.emit('exercise_ready', scope, input, input.phase, exerciseContext(session, exercise))
        return
      }
    }
    const setKey = `${exercise.id}:${scope.setOrdinal}`
    if (input.phase === 'active-set' && saved.duringSets && exercise.kind === 'machine') this.inSetEvents(input, session, exercise, scope, setKey)
    else if (input.phase === 'active-set' && saved.duringSets && exercise.kind === 'timed') this.timedSetEvents(input, session, exercise, scope, setKey)
    else if (this.inSet) this.inSet.repAt = input.nowMs // a pause is not a stall
    const rest = session.restState
    if (input.phase === 'rest' && saved.duringRest && rest && !rest.timerPaused && !this.sentKeys.has(`rest:${setKey}`)) {
      const elapsed = rest.totalSeconds - rest.remainingSeconds
      if (elapsed >= REST_EXTRA_MIN_ELAPSED_S && rest.remainingSeconds >= REST_EXTRA_MIN_LEFT_S) {
        this.sentKeys.add(`rest:${setKey}`)
        this.emit('rest_long_opportunity', scope, input, 'rest', { ...exerciseIdentity(session, exercise), restMs: rest.totalSeconds * 1000, restElapsedMs: elapsed * 1000,
          exerciseName: exercise.name.slice(0, 120), totalSets: exercise.plan.length, ...nextExercise(session, exercise.id, scope.setOrdinal) })
      }
    }
  }

  /** A few in-set moments per set (start, partial rep, half, final reps, stall); the backend Director paces them. */
  private inSetEvents(input: NetworkTick, session: RuntimeWorkoutSession, exercise: SessionExercise, scope: CoachScope, setKey: string): void {
    const now = input.nowMs, reps = input.reps, partial = input.partialReps ?? null
    if (this.inSet?.key !== setKey) this.inSet = { key: setKey, startedAt: now, reps, repAt: now, partial }
    const track = this.inSet
    this.repTracker.begin(setKey, now, reps)
    this.repTracker.sample(input.telemetry)
    this.repTracker.rep(reps, now)
    const metrics = this.repTracker.snapshot(now)
    if (reps !== track.reps) { track.reps = reps; track.repAt = now }
    const partialRose = partial !== null && track.partial !== null && partial > track.partial
    track.partial = partial
    if (reps === null) return
    const plan = exercise.plan[session.currentSetIndex], target = repGoal(plan), exact = exactRepTarget(plan)
    const left = target === null ? null : target - reps
    const elapsed = now - track.startedAt
    const adviceSlot = Math.min(4, Math.floor(elapsed / SET_ADVICE_INTERVAL_MS))
    const drop = metrics.velocityDropPct ?? 0
    const telemetry = !!input.telemetry
    const paused = telemetry ? metrics.stillMs >= SET_STALL_MS : now - track.repAt >= SET_NO_REP_MS
    const moments: Array<[CoachEventKind, string, boolean]> = [
      ['rep_completed', 'partial', partialRose],
      ['set_activated', 'start', reps >= 1 && reps <= 2 && (left === null || left >= 3)],
      // V2: what the machine measured — fading speed, the descent/ascent tempo, a long pause.
      ['rep_milestone', 'velocity-hard', drop >= 30 && (left === null || left >= 1)],
      ['rep_milestone', 'velocity', drop >= 15 && (left === null || left >= 1)],
      ['last_rep_pending', 'finish', target !== null && target >= 5 && left !== null && left >= 1 && left <= 2],
      ['rep_milestone', 'tempo', reps >= 4 && metrics.avgEccentricS !== null && metrics.avgConcentricS !== null && (left === null || left >= 2)],
      ['rep_milestone', 'half', target !== null && target >= 8 && reps >= Math.ceil(target / 2) && left !== null && left >= 3],
      ['rep_milestone', 'stall', reps >= 1 && (left === null || left >= 1) && paused],
      // Retry with a new useful opportunity after an early moment lost to cooldown/busy.
      // The Director still enforces density, topic memory, opt-in and the paid budget.
      ['rep_milestone', `support-${adviceSlot}`, adviceSlot >= 1 && reps >= 1 && (left === null || left >= 3)],
    ]
    const moment = moments.find(([, name, due]) => due && !this.sentKeys.has(`${name}:${setKey}`))
    if (!moment) return
    this.sentKeys.add(`${moment[1]}:${setKey}`)
    if (moment[1] === 'velocity-hard') this.sentKeys.add(`velocity:${setKey}`)
    if (adviceSlot >= 1) this.sentKeys.add(`support-${adviceSlot}:${setKey}`)
    const names: Readonly<Record<string, string>> = { 'velocity-hard': 'velocity_drop_hard', velocity: 'velocity_drop' }
    const name = moment[1].startsWith('support-') ? 'support' : names[moment[1]] ?? moment[1]
    this.emit(moment[0], scope, input, 'active-set', { ...exerciseIdentity(session, exercise), phaseElapsedMs: Math.round(elapsed), moment: name,
      exerciseName: exercise.name.slice(0, 120), totalSets: exercise.plan.length, ...(exact !== null ? { targetReps: exact } : {}),
      ...(['velocity_drop', 'velocity_drop_hard', 'tempo', 'stall'].includes(name) ? { telemetry: telemetryContext(metrics) } : {}) }, 'reps')
  }

  /** Timed sets: start, half and the final stretch by the screen's clock; only while it runs. */
  private timedSetEvents(input: NetworkTick, session: RuntimeWorkoutSession, exercise: SessionExercise, scope: CoachScope, setKey: string): void {
    const timer = input.timer, target = whole(exercise.plan[session.currentSetIndex]?.targetSeconds)
    if (!timer || !timer.running || !target || timer.exerciseId !== exercise.id || timer.setOrdinal !== scope.setOrdinal) return
    const elapsed = timer.elapsedS, left = target - elapsed
    const adviceSlot = Math.min(4, Math.floor(elapsed * 1000 / SET_ADVICE_INTERVAL_MS))
    const moments: Array<[CoachEventKind, string, boolean]> = [
      ['set_activated', 'start', elapsed >= 3 && left >= 20],
      ['rep_milestone', 'half', target >= 40 && elapsed >= target / 2 && left >= 15],
      ['last_rep_pending', 'finish', target >= 30 && left <= 15 && left >= 6],
      ['rep_milestone', `support-${adviceSlot}`, adviceSlot >= 1 && left >= 15],
    ]
    const moment = moments.find(([, name, due]) => due && !this.sentKeys.has(`${name}:${setKey}`))
    if (!moment) return
    this.sentKeys.add(`${moment[1]}:${setKey}`)
    if (adviceSlot >= 1) this.sentKeys.add(`support-${adviceSlot}:${setKey}`)
    this.emit(moment[0], scope, input, 'active-set', { phaseElapsedMs: Math.round(elapsed * 1000), moment: moment[1].startsWith('support-') ? 'support' : moment[1],
      exerciseName: exercise.name.slice(0, 120), totalSets: exercise.plan.length, targetSeconds: target }, 'seconds')
  }

  private restContext(session: RuntimeWorkoutSession, exerciseId: string | null, setOrdinal: number | null): Record<string, unknown> {
    const next = nextExercise(session, exerciseId, setOrdinal)
    const rest = session.restState
    if (rest) return { restMs: rest.totalSeconds * 1000, restElapsedMs: Math.max(0, rest.totalSeconds - rest.remainingSeconds) * 1000, ...next }
    const plan = session.exercises.find(item => item.id === exerciseId)?.plan[(setOrdinal ?? 1) - 1]
    return plan && Number.isFinite(plan.restSeconds) && plan.restSeconds > 0 ? { restMs: plan.restSeconds * 1000, restElapsedMs: 0, ...next } : next
  }

  private emit(kind: CoachEventKind, scope: CoachScope, input: NetworkTick, phase: CoachPhase, context: Record<string, unknown> = {},
    progressUnit: 'reps' | 'seconds' | null = null): void {
    const session = input.session!
    const exerciseKind = session.exercises.find(item => item.id === scope.exerciseId)?.kind
    const now = Math.max(0, input.nowMs)
    const event: CoachEvent = { schemaVersion: 1, id: this.nextEventId(), scope, kind, phase, source: 'runtime_ack',
      exerciseKind: exerciseKind && EXERCISE_KINDS.has(exerciseKind) ? exerciseKind as CoachEvent['exerciseKind'] : null,
      controlMode: null, progressUnit, ordinal: 0, planRevision: this.planRevision, contextVersion: this.contextVersion, createdAtMs: now,
      // Rest/setup lines are authored with variants (~10–17 s); in-set moments stay short-lived.
      startDeadlineMs: now + (kind === 'rest_long_opportunity' || kind === 'exercise_ready' || kind === 'workout_started' ? 35_000 : 20_000),
      facts: [], factDependencies: [] }
    const setId = kind === 'rest_long_opportunity' ? session.restState?.completedSet?.backendSetId : undefined
    this.forward(event, setId && Number.isSafeInteger(setId) && setId > 0 ? { backendSetId: setId } : null, context)
  }

  private forward(event: CoachEvent, refs: LifecycleRefs | null, context: Record<string, unknown>): void {
    if (this.registry.has(event.id) || this.registry.size >= 1024 || !this.context) { this.count('event_capacity'); return }
    const ref = event.kind === 'set_persisted' ? refs?.backendSetId : event.kind === 'exercise_finalized' ? refs?.backendExerciseId :
      event.kind === 'workout_finalized' ? refs?.backendWorkoutId : undefined
    const confirmedResult = Number.isInteger(ref) && ref! > 0
    const captureAllowed = event.kind === 'set_persisted' ? ['active-set', 'finalizing-set'].includes(event.phase) :
      event.kind === 'exercise_finalized' ? ['active-set', 'finalizing-set', 'exercise-summary'].includes(event.phase) :
        event.kind !== 'workout_finalized' || event.phase === 'workout-summary'
    const identity = speechIdentity(event)
    // Versions are captured before any await, never inferred at publication.
    // Legacy/local-only zero versions and evicted provenance fail closed.
    const originIndex = this.history.findIndex(item => item.context.planRevision === event.planRevision &&
      item.context.contextVersion === event.contextVersion && item.atMs <= event.createdAtMs)
    const origin = this.history[originIndex]?.context
    const originMatches = !!origin?.scope && (sameScope(origin.scope, event.scope) ||
      (event.kind === 'workout_finalized' && event.scope.exerciseId === null && event.scope.setOrdinal === null &&
        sameRun(origin.scope, event.scope) && origin.scope.scopeEpoch === event.scope.scopeEpoch))
    const entry: SentEvent = { identity, kind: event.kind, claimed: false, summaryRemapped: false, confirmedResult, sentAtMs: this.now(), valid: !!origin && !!origin.scope &&
      captureAllowed && (!FORWARDED.has(event.kind) || confirmedResult) && originMatches && !origin.blocked && origin.phase === event.phase && this.now() <= event.startDeadlineMs,
      // Validation cursor is a browser context, NOT a replacement event/frame scope.
      context: origin ?? this.context, telemetry: { classification: null, pending: new Map(), measured: new Set() }, state: 'pending' }
    this.opportunityCounts.pending++
    if (entry.valid) for (const item of this.history.slice(originIndex)) this.advanceEvent(entry, item.context, false)
    if (entry.valid) this.advanceEvent(entry, this.context, false)
    this.registry.set(event.id, entry)
    if (!entry.valid) { this.transition(entry, this.now() > event.startDeadlineMs ? 'expired' : 'rejected'); this.count('stale_event'); return }
    this.transition(entry, 'preparing')
    this.counters.eventsSent++
    this.measureEvent('eventToSend', entry, entry.sentAtMs - event.createdAtMs)
    this.send({ type: 'event', event, elapsedAtSendMs: Math.min(86_400_000, Math.max(0, entry.sentAtMs - event.createdAtMs)), ...(refs ? { refs } : {}), context })
    this.changed()
  }

  private send(message: Record<string, unknown>): void {
    const socket = this.socket
    if (!socket || socket.readyState !== OPEN) return
    try { socket.send(JSON.stringify(message)) } catch { /* close handler reconnects */ }
  }

  // ---------- diagnostics ----------

  private now(): number { return (this.last?.nowMs ?? 0) + Math.max(0, this.deps.nowMs() - this.clockAnchor) }

  private sentContextKey = ''
  private sendContext(): void {
    if (!this.context || this.sentContextKey === this.contextKey) return
    this.send({ type: 'context', ...this.context })
    this.sentContextKey = this.contextKey
  }

  private updateContext(input: NetworkTick): void {
    const signature = planSignature(input.session!, input.saved!.mode)
    if (signature !== this.planKey || !this.context) { this.planKey = signature; this.planRevision++ }
    const blocked = this.quiet(input) || signature === null || !input.scope
    const key = JSON.stringify([input.scope, input.phase, blocked, input.gate, this.planRevision])
    if (key !== this.contextKey) {
      this.contextKey = key
      this.context = Object.freeze({ scope: input.scope ? Object.freeze({ ...input.scope }) : null,
        phase: input.phase, blocked, planRevision: this.planRevision, contextVersion: ++this.contextVersion })
      this.history.push({ atMs: input.nowMs, context: this.context })
      if (this.history.length > 1024) this.history.shift()
      for (const event of this.registry.values()) {
        const stream = [...this.streams.values()].find(item => item.event === event)
        // Mixer may have crossed its start since the last runtime observation.
        const started = stream?.started || stream?.mixer.snapshot().utterances.some(item => item.state === 'started' &&
          !!item.stream && this.streams.get(item.stream.generationId) === stream) || false
        this.advanceEvent(event, this.context, started)
      }
      if (this.textEvent && !this.textEvent.valid) this.clearText()
      this.changed()
    }
    for (const [id, stream] of this.streams) {
      const started = stream.started || stream.mixer.snapshot().utterances.some(item => item.id === id && item.state === 'started')
      if (!started && input.nowMs > stream.event.identity.startDeadlineMs) stream.event.valid = false
      if (!stream.event.valid) this.failStream(id, stream)
    }
    for (const event of this.registry.values()) if (!event.claimed && (!event.valid || input.nowMs > event.identity.startDeadlineMs)) {
      event.valid = false
      this.transition(event, input.nowMs > event.identity.startDeadlineMs ? 'expired' : 'rejected')
      if (event.telemetry.pending.size) this.classifyUnknown(event)
    }
  }

  private advanceEvent(event: SentEvent, next: SpeechContext, started: boolean): void {
    if (!event.valid) return
    const exact = !!event.context.scope && !!next.scope && sameScope(event.context.scope, next.scope) && event.context.phase === next.phase
    const remap = !exact && event.context.phase === next.phase
    if (!speechSurvives(event.kind, event.context, next, started, event.confirmedResult) ||
      (started && this.last?.saved?.mode === 'text-only') || (!started && remap && event.summaryRemapped)) {
      event.valid = false
      if (started) {
        const reason = this.last?.latched ? 'safety' : this.last?.gate ??
          (next.phase === 'paused-set' ? 'paused-set' : next.planRevision !== event.context.planRevision ? 'plan_changed' :
            !event.context.scope || !next.scope || !sameRun(event.context.scope, next.scope) ? 'owner_mismatch' : 'scope_changed')
        this.note(reason, { triggerId: null, action: 'interrupted', text: null })
      }
      if (started && event.state === 'ready') this.transition(event, 'started')
      this.transition(event, started ? 'interrupted' : 'rejected')
    }
    else { if (remap && !started) event.summaryRemapped = true; event.context = next }
  }

  private failStream(id: string, stream: Stream): void {
    if (!this.streams.delete(id)) return
    stream.event.valid = false
    this.transition(stream.event, stream.started ? 'interrupted' : this.now() > stream.event.identity.startDeadlineMs ? 'expired' : 'rejected')
    stream.mixer.cancelStream(id, 'scope_changed')
    this.counters.failed++
    this.measureEvent('eventToFailed', stream.event, this.now() - stream.event.identity.createdAtMs)
    this.retainTerminal(id, stream)
    this.send({ type: 'playback_failed', generationId: id, identity: stream.event.identity })
    this.changed()
  }

  private measure(metric: string, stream: Stream, value: number): void {
    this.measureEvent(metric, stream.event, value)
  }

  private measureEvent(metric: string, event: SentEvent, value: number): void {
    if (!Number.isFinite(value) || event.telemetry.measured.has(metric)) return
    event.telemetry.measured.add(metric)
    value = Math.min(MAX_TIMING_MS, Math.max(0, Math.round(value)))
    if (event.telemetry.classification) this.sample(this.latencySamples, `${metric}:${this.group(event)}`, value)
    else event.telemetry.pending.set(metric, value)
    this.changed()
  }

  private group(event: SentEvent): string {
    const c = event.telemetry.classification!
    return `${event.kind}:${c.source}:voiceModel=${c.voiceModel}:textModel=${c.textModel}:connection=${c.connection}`
  }

  private sample(groups: Map<string, number[]>, key: string, value: number): void {
    // Both group cardinality and samples/group are bounded, even across workouts.
    if (!groups.has(key) && groups.size >= 512) groups.delete(groups.keys().next().value!)
    const samples = groups.get(key) ?? []
    samples.push(value)
    if (samples.length > 128) samples.shift()
    groups.set(key, samples)
  }

  private classify(event: SentEvent, classification: Classification): void {
    if (event.telemetry.classification) return
    event.telemetry.classification = classification
    if ([classification.voiceModel, classification.textModel, classification.source, classification.connection].includes('unknown')) this.missingClassification++
    else this.classified++
    for (const [metric, value] of event.telemetry.pending) this.sample(this.latencySamples, `${metric}:${this.group(event)}`, value)
    event.telemetry.pending.clear()
    this.changed()
  }

  private classifyUnknown(event: SentEvent, source = 'unknown'): void {
    this.classify(event, { source, voiceModel: 'unknown', textModel: 'unknown', connection: 'unknown' })
  }

  private retainTerminal(id: string, stream: Pick<Stream, 'event' | 'source' | 'ended'>): void {
    if (stream.ended) return
    this.terminalStreams.set(id, { event: stream.event, source: stream.source, ended: false })
    if (this.terminalStreams.size > 32) {
      const oldest = this.terminalStreams.keys().next().value!
      const evicted = this.terminalStreams.get(oldest)!
      this.classifyUnknown(evicted.event, evicted.source)
      this.terminalStreams.delete(oldest)
    }
    this.changed()
  }

  private clearText(): void {
    this.lastText = null; this.textEvent = null
    this.decisions = this.decisions.map(item => item.text ? Object.freeze({ ...item, text: null }) : item)
  }

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

  private transition(event: SentEvent, target: OpportunityState): void {
    const next = transitionOpportunity(event.state, target)
    if (next !== event.state) { event.state = next; this.opportunityCounts[next]++; this.changed() }
  }
}

const REPORT_REASONS = new Set(('ready disabled audio_locked safety hardware_active runtime_session mute hidden no_user preferences_loading ' +
  'preferences_unavailable no_consent unavailable decode_failed cancelled scope_changed missing_clip admitted idle stale_source mock_source ' +
  'owner_mismatch expired no_source pipeline_busy provider_unavailable stale_run local_mode coach_disabled run_not_found run_not_live run_closed ' +
  'budget degraded credential_unavailable voice_unavailable voice_fallback no_useful_content validation_failed closed network run_unavailable run_create_failed active_runs_full invalid_response socket error ' +
  'queue_full queue_preempted invalid_local_completion provider_timeout provider_error rate_limited plan_changed paused-set ' +
  'playback_failed scope_changed watchdog stale invalid disposed audio_overrun first_audio_timeout internal_error facts_changed ' +
  'identity_mismatch duplicate event_capacity stale_event stale_text incomplete complete failed frame sequence_gap invalid_frame').split(' '))
for (const reason of ('insufficient_facts restricted_content provider_incomplete provider_refusal provider_malformed usage_unsettled ' +
  'cooldown density_cap topic_repeat no_window facts number claim comparison language length schema injection question shouting name ' +
  'unreviewed_tip tip_repeat fact_repeat humor_streak diversity context_reordered invalid_context invalid_event invalid_elapsed').split(' ')) REPORT_REASONS.add(reason)
const reportReason = (value: string | null): string | null => {
  if (value === null) return null
  if (REPORT_REASONS.has(value)) return value
  // Do not hide a known validator reason, but never export arbitrary suffixes.
  const parts = value.split(':')
  return parts.length === 2 && parts[0] === 'validation_failed' && REPORT_REASONS.has(parts[1]) ? value : 'other'
}
/** Allowlisted diagnostics only — arbitrary server strings never enter the export. */
export function redactedNetworkReport(snapshot: NetworkSnapshot): string {
  const reasons: Record<string, number> = {}
  for (const [reason, count] of Object.entries(snapshot.reasons)) {
    const key = reportReason(reason)!
    reasons[key] = (reasons[key] ?? 0) + count
  }
  const voiceId = snapshot.voiceId && ['alloy', 'ash', 'ballad', 'coral', 'echo', 'fable', 'nova', 'onyx', 'sage', 'shimmer', 'verse', 'marin', 'cedar', 'fake'].includes(snapshot.voiceId) ? snapshot.voiceId : null
  const mode = snapshot.mode && ['local', 'hybrid', 'text-only'].includes(snapshot.mode) ? snapshot.mode : null
  const usage = snapshot.usage ? { ...snapshot.usage,
    limitKind: ['strict-reservations', 'strict', 'soft', 'daily', 'workout'].includes(snapshot.usage.limitKind) ? snapshot.usage.limitKind : 'unknown' } : null
  return JSON.stringify({ schemaVersion: 1, state: snapshot.state, reason: reportReason(snapshot.reason), mode, voiceId,
    degraded: snapshot.degraded, eventsSent: snapshot.eventsSent, streams: snapshot.streams, spoken: snapshot.spoken, failed: snapshot.failed,
    firstAudioMs: snapshot.firstAudioMs, firstAudioMsLabel: snapshot.firstAudioMsLabel, latencies: snapshot.latencies,
    serverTimings: snapshot.serverTimings, telemetry: snapshot.telemetry, opportunities: snapshot.opportunities, reasons, usage,
    decisions: snapshot.decisions.map(item => ({ action: ['text', 'silence', 'speak', 'rejected', 'skip', 'cancel', 'local', 'interrupted'].includes(item.action) ? item.action : 'other', reason: reportReason(item.reason) })) }, null, 2)
}
