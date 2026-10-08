import { describe, expect, it, vi } from 'vitest'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { FakeClock, FakeContext } from '../audio/audio-test-fakes'
import { encodeCoachFrame } from '../audio/coach-frames'
import { LocalCoachAudioManager } from '../audio/local-coach-audio-manager'
import { CoachLifecycleObserver } from '../lib/lifecycle-observer'
import type { CoachAudio, CoachEvent, CoachPhase, CoachScope } from '../model/contracts'
import { DEFAULT_COACH_PREFERENCES, type CoachPreferences } from '../model/preferences'
import { CoachNetworkClient, redactedNetworkReport, type NetworkTick, type SocketLike } from './coach-network-client'

const RATE = 8000
const saved: CoachPreferences = { ...DEFAULT_COACH_PREFERENCES, enabled: true, consentVersion: 1, networkConsentVersion: 1, mode: 'hybrid', revision: 3 }
const scope = (patch: Partial<CoachScope> = {}): CoachScope => ({ schemaVersion: 1, userId: 'u1', runId: 'run-1', exerciseId: 'e1', setOrdinal: 1, scopeEpoch: 3, ...patch })
const plan = (reps: number) => ({ targetReps: reps, restSeconds: 90, weightLabel: '' })
const session = (patch: Record<string, unknown> = {}) => ({ id: 'run-1', dataSource: 'backend', view: 'exercise-setup', currentExerciseId: 'e1',
  currentSetIndex: 0, completedSets: {}, exercises: [{ id: 'e1', name: 'Жим ногами', kind: 'machine', plan: [plan(10), plan(10)] },
    { id: 'e2', name: 'Тяга', kind: 'machine', plan: [plan(10)] }], ...patch }) as unknown as RuntimeWorkoutSession

class FakeSocket implements SocketLike {
  binaryType = ''
  readyState = 0
  sent: Record<string, unknown>[] = []
  onopen: ((event: unknown) => void) | null = null
  onclose: ((event: unknown) => void) | null = null
  onerror: ((event: unknown) => void) | null = null
  onmessage: ((event: { data: unknown }) => void) | null = null
  readonly url: string
  constructor(url: string) { this.url = url }
  send(data: string) { this.sent.push(JSON.parse(data)) }
  close() { this.readyState = 3 }
  open() { this.readyState = 1; this.onopen?.({}) }
  push(message: unknown) {
    const data = message instanceof Uint8Array ? message.buffer.slice(message.byteOffset, message.byteOffset + message.byteLength) : JSON.stringify(message)
    this.onmessage?.({ data })
  }
  serverClose() { this.readyState = 3; this.onclose?.({}) }
  types() { return this.sent.map(item => item.type) }
  events() { return this.sent.filter(item => item.type === 'event') as Array<{ event: CoachEvent; refs?: unknown; context?: Record<string, number> }> }
}

class Fixture {
  readonly sockets: FakeSocket[] = []
  readonly timers: Array<() => void> = []
  readonly storage = new Map<string, string>()
  readonly context = new FakeContext()
  readonly clock = new FakeClock()
  readonly manager: LocalCoachAudioManager
  runs = 0
  requests: Array<{ url: string; init: RequestInit }> = []
  readonly client: CoachNetworkClient
  input: NetworkTick
  refs: Record<string, object> = {}

  constructor() {
    this.manager = new LocalCoachAudioManager({ context: this.context.asAudioContext(), clock: this.clock, scope: scope() })
    this.client = new CoachNetworkClient({
      fetch: vi.fn(async (url: string, init: RequestInit) => {
        this.requests.push({ url, init })
        if (url === '/api/coach/runs') { this.runs++; return new Response(JSON.stringify({ runId: `run-${this.runs}`, runToken: `secret-${this.runs}` })) }
        if (url.endsWith('/usage')) return new Response(JSON.stringify({ requests: 2, settledMicros: 1200, pendingMicros: 0, capMicros: 2_000_000, limitKind: 'strict-reservations' }))
        if (url.endsWith('/memory')) return new Response(JSON.stringify({ cleared: 1, persistentMemory: false }))
        return new Response('{}')
      }),
      socket: url => { const socket = new FakeSocket(url); this.sockets.push(socket); return socket },
      storage: { getItem: key => this.storage.get(key) ?? null, setItem: (key, value) => { this.storage.set(key, value) }, removeItem: key => { this.storage.delete(key) } },
      origin: () => ({ protocol: 'http:', host: 'localhost:5173' }),
      setTimeout: callback => { this.timers.push(callback); return this.timers.length },
      clearTimeout: () => undefined,
      ownerId: () => 'tab-test',
    })
    this.input = { nowMs: 1000, userId: 'u1', saved, session: session(), featureEnabled: true, phase: 'setup', scope: scope(), latched: false,
      gate: null, reps: null, lifecycle: [], refs: id => this.refs[id] ?? null, mixer: () => this.manager }
  }

  tick(patch: Partial<NetworkTick> = {}) {
    this.input = { ...this.input, nowMs: this.input.nowMs + 100, ...patch }
    this.client.tick(this.input)
  }
  get socket() { return this.sockets.at(-1)! }
  async connect(configured: Record<string, unknown> = {}) {
    this.tick()
    await vi.waitFor(() => expect(this.sockets.length).toBeGreaterThan(0))
    this.socket.open()
    this.socket.push({ type: 'configured', generation: 1, mode: 'hybrid', voiceId: 'ash', text: true, voice: true, degraded: false, ...configured })
  }
}

const lifecycleEvent = (id: string, kind: CoachEvent['kind'], phase: CoachPhase): CoachEvent => ({ schemaVersion: 1, id, kind, phase,
  scope: scope(), source: 'runtime_ack', exerciseKind: 'machine', controlMode: null, progressUnit: 'reps', ordinal: 0, planRevision: 0,
  contextVersion: 0, createdAtMs: 1, startDeadlineMs: 2, facts: [], factDependencies: [] })

function frame(gid: string, sequence: number, seconds: number, final: boolean, frameScope = scope({ scopeEpoch: 1 })) {
  const pcm = new Uint8Array(Math.round(seconds * RATE) * 2)
  const meta: CoachAudio = { schemaVersion: 1, utteranceId: gid, generationId: gid, scope: frameScope, sequence, source: 'realtime',
    codec: 'pcm_s16le', sampleRate: RATE, channels: 1, byteLength: pcm.length, durationMs: pcm.length / 2 / RATE * 1000, final }
  return encodeCoachFrame(meta, pcm)
}

describe('CoachNetworkClient', () => {
  it('stays offline without network consent or in local mode', () => {
    for (const patch of [{ networkConsentVersion: null }, { mode: 'local' }, { enabled: false }] as const) {
      const f = new Fixture()
      f.tick({ saved: { ...saved, ...patch } as CoachPreferences })
      expect(f.requests).toHaveLength(0)
      expect(f.client.getSnapshot().state).toBe('off')
    }
    const f = new Fixture()
    f.tick({ session: session({ dataSource: 'mock' }) })
    expect(f.requests).toHaveLength(0)
  })

  it('creates a workout run, configures over the socket and never puts the token in the URL', async () => {
    const f = new Fixture()
    await f.connect()
    const create = f.requests.find(item => item.url === '/api/coach/runs')!
    expect(JSON.parse(String(create.init.body))).toEqual({ schemaVersion: 1, userId: 'u1', ledger: 'workout', capUsd: '2.00' })
    expect(f.socket.url).toBe('ws://localhost:5173/api/coach/runs/run-1/live')
    expect(f.socket.url).not.toContain('secret')
    expect(f.socket.sent[0]).toEqual({ type: 'configure', runToken: 'secret-1', ownerId: 'tab-test' })
    expect(f.socket.binaryType).toBe('arraybuffer')
    expect(f.client.getSnapshot()).toMatchObject({ state: 'ready', voiceId: 'ash', voice: true })
    expect(f.socket.events().map(item => item.event.kind)).toEqual(['workout_started'])
    f.tick(); f.tick()
    expect(f.socket.events()).toHaveLength(1)
  })

  it('forwards the next exercise, the half-target milestone and one long-rest opportunity', async () => {
    const f = new Fixture()
    await f.connect()
    f.tick({ phase: 'active-set', session: session({ view: 'exercise-session' }), reps: 4 })
    f.tick({ phase: 'active-set', reps: 5 })
    f.tick({ phase: 'active-set', reps: 6 })
    const rest = { mode: 'between-sets', totalSeconds: 90, remainingSeconds: 80, timerPaused: false }
    f.tick({ phase: 'rest', session: session({ view: 'rest', restState: rest }) })
    f.tick({ phase: 'rest', session: session({ view: 'rest', restState: { ...rest, remainingSeconds: 70 } }) })
    f.tick({ phase: 'rest', session: session({ view: 'rest', restState: { ...rest, remainingSeconds: 60 } }) })
    f.tick({ phase: 'setup', scope: scope({ exerciseId: 'e2', setOrdinal: 1, scopeEpoch: 9 }),
      session: session({ currentExerciseId: 'e2', completedSets: { e1: [{}] } }) })
    const sent = f.socket.events()
    expect(sent.map(item => item.event.kind)).toEqual(['workout_started', 'rep_milestone', 'rest_long_opportunity', 'exercise_ready'])
    expect(sent[2].context).toEqual({ restMs: 90_000, restElapsedMs: 20_000 })
    expect(sent[3].context).toEqual({ exerciseName: 'Тяга' })
    expect(sent[3].event.scope).toMatchObject({ exerciseId: 'e2', setOrdinal: null })
  })

  it('forwards persisted lifecycle events with backend refs, never replaying older ones', async () => {
    const f = new Fixture()
    f.input = { ...f.input, lifecycle: [lifecycleEvent('old', 'set_persisted', 'finalizing-set')] }
    f.refs = { old: { backendSetId: 1 }, l2: { backendSetId: 7 } }
    await f.connect()
    const stopped = lifecycleEvent('l1', 'set_stopped', 'finalizing-set')
    const persisted = lifecycleEvent('l2', 'set_persisted', 'finalizing-set')
    f.tick({ lifecycle: [lifecycleEvent('old', 'set_persisted', 'finalizing-set'), stopped, persisted] })
    const sent = f.socket.events().filter(item => item.event.kind === 'set_persisted')
    expect(sent).toHaveLength(1)
    expect(sent[0]).toMatchObject({ event: { id: 'l2' }, refs: { backendSetId: 7 }, context: { restMs: 90_000, restElapsedMs: 0 } })
  })

  it('streams speech into the mixer under the current scope and acknowledges playback', async () => {
    const f = new Fixture()
    await f.connect()
    f.socket.push({ type: 'speech_start', eventId: 'net-1', triggerId: 'T01', generationId: 'g1', text: 'Привет', validForMs: 10_000, sampleRate: RATE, source: 'realtime' })
    f.socket.push(frame('g1', 0, 0.3, false))
    f.socket.push(frame('g1', 1, 0.1, true))
    f.socket.push({ type: 'speech_end', generationId: 'g1', status: 'complete', frames: 2, firstAudioMs: 420 })
    f.clock.advance(50, f.context)
    f.client.observe(f.manager.snapshot())
    const started = f.socket.sent.find(item => item.type === 'playback_started')
    expect(started).toEqual({ type: 'playback_started', generationId: 'g1', durationMs: 400 })
    for (const source of f.context.sources) source.end()
    f.client.observe(f.manager.snapshot())
    expect(f.socket.sent.at(-1)).toEqual({ type: 'playback_completed', generationId: 'g1' })
    expect(f.client.getSnapshot()).toMatchObject({ streams: 1, spoken: 1, failed: 0, firstAudioMs: 420 })
  })

  it('refuses speech while gated and asks the server to cancel', async () => {
    const f = new Fixture()
    await f.connect()
    f.tick({ gate: 'hidden' })
    f.socket.push({ type: 'speech_start', generationId: 'g2', validForMs: 5000, sampleRate: RATE, source: 'realtime' })
    expect(f.socket.types().slice(-2)).toEqual(['cancel', 'playback_failed'])
    expect(f.manager.snapshot().utterances).toHaveLength(0)
  })

  it('reports safety latches and stays quiet while latched', async () => {
    const f = new Fixture()
    await f.connect()
    const before = f.socket.events().length
    f.tick({ latched: true, phase: 'suspended' })
    expect(f.socket.sent.filter(item => item.type === 'safety').at(-1)).toEqual({ type: 'safety', latched: true })
    f.tick({ latched: true, phase: 'setup', scope: scope({ exerciseId: 'e2' }), session: session({ currentExerciseId: 'e2' }) })
    expect(f.socket.events()).toHaveLength(before)
    f.tick({ latched: false })
    expect(f.socket.sent.filter(item => item.type === 'safety').at(-1)).toEqual({ type: 'safety', latched: false })
  })

  it('text-only mode still forwards events and records the returned text', async () => {
    const f = new Fixture()
    f.input = { ...f.input, saved: { ...saved, mode: 'text-only' }, gate: 'mute' }
    await f.connect({ mode: 'text-only', voice: false })
    expect(f.socket.events().map(item => item.event.kind)).toEqual(['workout_started'])
    f.socket.push({ type: 'decision', eventId: 'net-1', triggerId: 'T01', action: 'text', reason: null, text: 'Начинаем.' })
    expect(f.client.getSnapshot()).toMatchObject({ lastText: 'Начинаем.', decisions: [{ triggerId: 'T01', action: 'text' }] })
  })

  it('reconnects on stale_run with the same run and replaces a lost run', async () => {
    const f = new Fixture()
    await f.connect()
    f.socket.push({ type: 'error', reason: 'stale_run' })
    f.socket.serverClose()
    expect(f.client.getSnapshot()).toMatchObject({ state: 'retrying', reason: 'stale_run' })
    f.timers.shift()!()
    await vi.waitFor(() => expect(f.sockets).toHaveLength(2))
    expect(f.runs).toBe(1)
    f.socket.open()
    expect(f.socket.sent[0]).toMatchObject({ type: 'configure', runToken: 'secret-1' })
    f.socket.push({ type: 'error', reason: 'run_not_found' })
    f.socket.serverClose()
    f.timers.shift()!()
    await vi.waitFor(() => expect(f.sockets).toHaveLength(3))
    expect(f.runs).toBe(2)
    expect(f.socket.url).toContain('/run-2/live')
  })

  it('keeps the run for the same tab across a reload (sessionStorage) and stops on local_mode', async () => {
    const f = new Fixture()
    await f.connect()
    f.socket.push({ type: 'error', reason: 'local_mode' })
    f.socket.serverClose()
    expect(f.client.getSnapshot().state).toBe('refused')
    f.tick()
    expect(f.timers).toHaveLength(0)
    expect([...f.storage.values()][0]).toContain('run-1')
    f.tick({ saved: { ...saved, revision: 4 } })
    await vi.waitFor(() => expect(f.sockets).toHaveLength(2))
    expect(f.runs).toBe(1)
  })

  it('stops reconnecting when the server coach is disabled', async () => {
    const f = new Fixture()
    await f.connect()
    f.socket.push({ type: 'error', reason: 'coach_disabled' })
    f.socket.serverClose()
    expect(f.client.getSnapshot()).toMatchObject({ state: 'refused' })
    f.tick()
    expect(f.timers).toHaveLength(0)
    expect(f.sockets).toHaveLength(1)
  })

  it('polls usage, clears memory and exports a redacted report', async () => {
    const f = new Fixture()
    await f.connect()
    await vi.waitFor(() => expect(f.client.getSnapshot().usage).toMatchObject({ requests: 2, settledMicros: 1200 }))
    const usage = f.requests.find(item => item.url.endsWith('/usage'))!
    expect((usage.init.headers as Record<string, string>)['X-Coach-Run-Token']).toBe('secret-1')
    expect(await f.client.forgetMemory()).toBe(1)
    f.socket.push({ type: 'decision', eventId: 'net-1', triggerId: 'T01', action: 'text', reason: null, text: 'секретный текст' })
    const report = redactedNetworkReport(f.client.getSnapshot())
    expect(report).not.toMatch(/secret|секретный|run-1|u1/)
    expect(JSON.parse(report)).toMatchObject({ state: 'ready', voiceId: 'ash', usage: { requests: 2 } })
  })
})

describe('CoachLifecycleObserver refs', () => {
  it('keeps backend IDs beside the event for the live client', () => {
    const observer = new CoachLifecycleObserver({ enabled: () => true, clock: { nowMs: () => 10 },
      current: () => ({ userId: 'u1', runId: 'run-1', exerciseId: 'e1', setOrdinal: 1, scopeEpoch: 2, mock: false }) })
    const capture = observer.capture('machine')
    expect(observer.publish(capture, 'set_persisted', { outcome: 'completed', backendSetId: 42 })).toBe(true)
    const [event] = observer.snapshot()
    expect(observer.refs(event.id)).toEqual({ backendSetId: 42 })
    expect(JSON.stringify(event)).not.toContain('42')
    observer.clear()
    expect(observer.refs(event.id)).toBeNull()
  })
})
