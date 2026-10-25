import { describe, expect, it, vi } from 'vitest'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { FakeClock, FakeContext } from '../audio/audio-test-fakes'
import { encodeCoachFrame } from '../audio/coach-frames'
import { LocalCoachAudioManager } from '../audio/local-coach-audio-manager'
import { verifyLocalBuffer } from '../audio/local-buffers'
import { CoachLifecycleObserver } from '../lib/lifecycle-observer'
import type { CoachAudio, CoachEvent, CoachPhase, CoachScope } from '../model/contracts'
import { DEFAULT_COACH_PREFERENCES, type CoachPreferences } from '../model/preferences'
import { CoachNetworkClient, redactedNetworkReport, type NetworkTick, type SocketLike } from './coach-network-client'
import { CoachLiveRuntime, type LiveInputs } from './coach-live-runtime'
import { RepBeepArbiter } from './local-cue-player'
import { speechIdentity } from './coach-scope-policy'

const RATE = 8000
const unknownGroup = (kind = 'workout_started') => `${kind}:unknown:voiceModel=unknown:textModel=unknown:connection=unknown`
const metadata = { source: 'realtime', voiceModel: 'gpt-realtime-2.1-mini', textModel: 'gpt-6-luna', connectionClass: 'warm' }
const knownGroup = (kind = 'workout_started', connection = 'warm') => `${kind}:realtime:voiceModel=gpt-realtime-2.1-mini:textModel=gpt-6-luna:connection=${connection}`
const saved: CoachPreferences = { ...DEFAULT_COACH_PREFERENCES, enabled: true, consentVersion: 1, networkConsentVersion: 1, mode: 'hybrid', revision: 3,
  scenarioPicker: false }
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
  events() { return this.sent.filter(item => item.type === 'event') as Array<{ event: CoachEvent; refs?: unknown; context?: Record<string, unknown> }> }
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
      nowMs: () => this.clock.now(),
    })
    this.input = { nowMs: 1000, userId: 'u1', saved, session: session(), featureEnabled: true, phase: 'setup', scope: scope(), latched: false,
      gate: null, reps: null, lifecycle: [], refs: id => this.refs[id] ?? null, mixer: () => this.manager }
    this.clock.time = this.input.nowMs
  }

  tick(patch: Partial<NetworkTick> = {}) {
    this.input = { ...this.input, nowMs: this.input.nowMs + 100, ...patch }
    this.clock.advance(Math.max(0, this.input.nowMs - this.clock.now()), this.context)
    this.client.tick(this.input)
  }
  speech(gid = 'g1', event = this.socket.events().at(-1)!.event, patch: Record<string, unknown> = {}) {
    this.socket.push({ type: 'speech_start', eventId: event.id, identity: speechIdentity(event), generationId: gid,
      validForMs: 10_000, sampleRate: RATE, source: 'realtime', ...patch })
  }
  lifecycle(id: string, kind: CoachEvent['kind'], phase: CoachPhase): CoachEvent {
    const context = this.socket.sent.filter(item => item.type === 'context').at(-1)!
    return { ...lifecycleEvent(id, kind, phase), planRevision: context.planRevision as number,
      contextVersion: context.contextVersion as number, createdAtMs: this.input.nowMs + 1 }
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
  contextVersion: 0, createdAtMs: 1150, startDeadlineMs: 21_150, facts: [], factDependencies: [] })

function frame(gid: string, sequence: number, seconds: number, final: boolean, frameScope = scope()) {
  const pcm = new Uint8Array(Math.round(seconds * RATE) * 2)
  const meta: CoachAudio = { schemaVersion: 1, utteranceId: gid, generationId: gid, scope: frameScope, sequence, source: 'realtime',
    codec: 'pcm_s16le', sampleRate: RATE, channels: 1, byteLength: pcm.length, durationMs: pcm.length / 2 / RATE * 1000, final }
  return encodeCoachFrame(meta, pcm)
}

describe('CoachNetworkClient', () => {
  it.each([
    [JSON.stringify({ detail: 'active_runs_full' }), 'active_runs_full'],
    [JSON.stringify({ detail: 'private-sentinel' }), 'run_create_failed'],
    ['<html>private-sentinel</html>', 'run_create_failed'],
  ])('reports only allowlisted capacity errors and retries creation (%s)', async (body, reason) => {
    const f = new Fixture(), timers: Array<() => void> = [], sockets: FakeSocket[] = []
    const request = vi.fn().mockResolvedValueOnce(new Response(body, { status: 429 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ runId: 'billing-retry', runToken: 'secret-retry' })))
    const client = new CoachNetworkClient({ fetch: request, storage: null,
      socket: url => { const socket = new FakeSocket(url); sockets.push(socket); return socket },
      setTimeout: callback => { timers.push(callback); return timers.length }, clearTimeout: () => undefined,
      origin: () => ({ protocol: 'http:', host: 'localhost:5173' }), nowMs: () => f.clock.now(), ownerId: () => 'tab-retry' })
    try {
      client.tick(f.input)
      await vi.waitFor(() => expect(client.getSnapshot()).toMatchObject({ state: 'retrying', reason }))
      expect(redactedNetworkReport(client.getSnapshot())).toContain(reason)
      expect(redactedNetworkReport(client.getSnapshot())).not.toContain('private-sentinel')
      expect(sockets).toHaveLength(0)
      timers.shift()!()
      await vi.waitFor(() => expect(sockets).toHaveLength(1))
      expect(request).toHaveBeenCalledTimes(2)
      expect(client.getSnapshot().state).toBe('connecting')
    } finally { client.dispose(); f.client.dispose(); f.manager.dispose() }
  })

  it.each(['rest_long_opportunity', 'set_persisted'] as const)('does not collide with retained %s IDs after a reload on the same billing run', async kind => {
    const first = new Fixture(), reloaded = new Fixture()
    const seen = new Set<string>()
    try {
      // A page is reopened during a later rest: same runtime and billing run,
      // but a genuinely new opportunity, not a replay of the previous set.
      for (const [index, f] of [first, reloaded].entries()) {
        if (index) for (const [key, value] of first.storage) f.storage.set(key, value)
        const restScope = scope({ setOrdinal: index + 1 })
        f.manager.updateScope(restScope)
        f.input = { ...f.input, phase: kind === 'set_persisted' ? 'active-set' : 'rest', scope: restScope,
          session: session({ view: kind === 'set_persisted' ? 'exercise-session' : 'rest', currentSetIndex: index,
          completedSets: { e1: [{ reps: 10 }] },
          restState: { totalSeconds: 90, remainingSeconds: kind === 'set_persisted' ? 90 : 70, timerPaused: false } }) }
        await f.connect()
        if (kind === 'set_persisted') {
          const current = { ...restScope, mock: false }
          const observer = new CoachLifecycleObserver({ enabled: () => true, current: () => current,
            clock: { nowMs: () => f.clock.now() }, versions: value => f.client.captureVersions(value, f.input.session, saved) })
          const capture = observer.capture('machine')!
          expect(capture.versions).not.toBeNull()
          expect(observer.publish(capture, kind, { backendSetId: index + 10, actualValue: 10 })).toBe(true)
          const result = observer.snapshot()[0]
          f.refs[result.id] = observer.refs(result.id)!
          f.tick({ phase: 'rest', lifecycle: [result] })
        } else f.tick()
        const event = f.socket.events().at(-1)!.event
        expect(event.kind).toBe(kind)
        expect(seen.has(event.id)).toBe(false)
        seen.add(event.id)
        f.speech(`rest-${index}`, event)
        f.socket.push(frame(`rest-${index}`, 0, .3, true, restScope))
        f.clock.advance(50, f.context); f.client.observe(f.manager.snapshot())
        for (const source of f.context.sources) source.end()
        f.client.observe(f.manager.snapshot())
        expect(f.client.getSnapshot()).toMatchObject({ spoken: 1, failed: 0 })
        f.client.dispose()
      }
      expect(reloaded.runs).toBe(0)
      expect(reloaded.socket.url).toBe(first.socket.url)
    } finally {
      first.client.dispose(); first.manager.dispose(); reloaded.client.dispose(); reloaded.manager.dispose()
    }
  })

  it.each(['weight', 'reps'] as const)('keeps started speech and its original identity through a %s edit', async field => {
    const f = new Fixture(); await f.connect()
    const event = f.socket.events().at(-1)!.event
    f.speech(); f.socket.push(frame('g1', 0, 2, false))
    f.clock.advance(50, f.context)
    // No observe yet: the audio clock has started, but the client has not ACKed it.
    expect(f.manager.snapshot().active).toBe(1)
    const edited = session()
    edited.exercises[0] = { ...edited.exercises[0],
      loadSettings: { ...edited.exercises[0].loadSettings, [field]: field === 'weight' ? 30 : 12 },
      plan: edited.exercises[0].plan.map(p => ({ ...p,
        ...(field === 'reps' ? { targetReps: 12 } : { weightLabel: '30 кг', recommendedWeightKg: 30 }) })) }
    f.tick({ session: edited })
    expect(f.socket.sent.filter(item => item.type === 'context').at(-1)!.planRevision).toBeGreaterThan(event.planRevision)
    const ackIndex = f.socket.sent.findIndex(item => item.type === 'playback_started')
    const editIndex = f.socket.sent.findIndex(item => item.type === 'context' && Number(item.planRevision) > event.planRevision)
    expect(ackIndex).toBeGreaterThanOrEqual(0)
    expect(ackIndex).toBeLessThan(editIndex)
    expect(f.manager.snapshot().utterances).toContainEqual(expect.objectContaining({ id: 'g1', state: 'started' }))
    f.client.observe(f.manager.snapshot())
    f.socket.push(frame('g1', 1, .2, true))
    f.clock.advance(2300, f.context)
    for (const source of f.context.sources) source.end()
    f.client.observe(f.manager.snapshot())
    expect(f.client.getSnapshot()).toMatchObject({ spoken: 1, failed: 0 })
    expect(f.socket.sent.filter(item => item.type === 'playback_completed')).toEqual([
      expect.objectContaining({ generationId: 'g1', identity: speechIdentity(event) }),
    ])
    expect(f.socket.types()).not.toContain('playback_failed')
    f.client.dispose(); f.manager.dispose()
  })

  it('invalidates speech that has not started when parameters change, without resurrection', async () => {
    const f = new Fixture(); await f.connect(); f.speech()
    f.tick({ session: session({ exercises: [{ ...session().exercises[0], plan: [plan(12)] }] }) })
    f.socket.push(frame('g1', 0, 2, true))
    f.client.observe(f.manager.snapshot())
    expect(f.manager.snapshot().active).toBe(0)
    expect(f.socket.types()).toContain('playback_failed')
    f.client.dispose(); f.manager.dispose()
  })

  it.each([
    ['paused-set', { phase: 'paused-set' }],
    ['safety', { latched: true }],
    ['hidden', { gate: 'hidden' }],
  ] as Array<[string, Partial<NetworkTick>]>)('records the precise %s cause of a started speech interruption', async (reason, patch) => {
    const f = new Fixture(); await f.connect(); f.speech()
    f.socket.push(frame('g1', 0, 2, false)); f.clock.advance(50, f.context)
    f.client.observe(f.manager.snapshot()); f.tick(patch)
    expect(f.client.getSnapshot().decisions).toContainEqual(expect.objectContaining({ action: 'interrupted', reason }))
    const report = JSON.parse(redactedNetworkReport(f.client.getSnapshot()))
    expect(report.decisions).toContainEqual({ action: 'interrupted', reason })
    f.client.dispose(); f.manager.dispose()
  })

  it('retains the mixer cancellation reason even after a later scope diagnostic overwrites its status', async () => {
    const f = new Fixture(); await f.connect(); f.speech()
    f.socket.push(frame('g1', 0, 2, false)); f.clock.advance(50, f.context)
    f.client.observe(f.manager.snapshot())
    f.manager.cancelAll('safety')
    f.manager.updateScope(scope())
    expect(f.manager.snapshot().reason).toBe('scope_changed')
    f.client.observe(f.manager.snapshot())
    expect(JSON.parse(redactedNetworkReport(f.client.getSnapshot())).decisions).toContainEqual({ action: 'interrupted', reason: 'safety' })
    f.client.dispose(); f.manager.dispose()
  })

  it('keeps actual live speech through bar movement and the transition to training', async () => {
    const f = new Fixture()
    const localBuffer = verifyLocalBuffer(f.context.asAudioContext(), f.context.createBuffer(1, RATE, RATE))
    let inputs: LiveInputs = { userId: 'u1', saved, session: session(), featureEnabled: true, hidden: false, emergency: false,
      hardware: null, connected: true, general: { soundEnabled: true, voiceHintsEnabled: true, volume: 1 } }
    const runtime = new CoachLiveRuntime({ read: () => inputs, subscribeInputs: () => () => undefined,
      lifecycle: () => [], lifecycleRefs: () => null, network: f.client, context: () => f.context.asAudioContext(),
      createManager: (_context, current) => { f.manager.updateScope(current); return f.manager },
      clips: () => ({ get: () => localBuffer }), restorePack: () => undefined,
      beep: new RepBeepArbiter(() => f.clock.now()), now: () => f.clock.now(), setInterval: () => 1, clearInterval: () => undefined })
    try {
      runtime.start()
      await vi.waitFor(() => expect(f.sockets).toHaveLength(1))
      f.socket.open()
      f.socket.push({ type: 'configured', mode: 'hybrid', text: true, voice: true, degraded: false })
      const event = f.socket.events()[0].event
      f.speech('moving-voice', event)
      f.socket.push(frame('moving-voice', 0, 2, false, event.scope))
      f.clock.advance(50, f.context)
      expect(f.manager.snapshot().active).toBe(1)
      inputs = { ...inputs, session: session({ view: 'exercise-session' }) }
      runtime.tick()
      for (const [index, mode] of ['start_hold', 'moving', 'training', 'training'].entries()) {
        inputs = { ...inputs, hardware: { emittedAt: new Date(1_700_000_000_000 + index * 100).toISOString(),
          selectedUserId: 'u1', serviceMode: false, emulatorMode: false, safety: { state: 'enabled' }, panel: { stopLatched: false },
          motion: { moving: mode !== 'start_hold', controlMode: mode, repetitionCount: index === 3 ? 1 : 0 },
          control: { mode, spotterActive: false, failureDetected: false, faultCode: null } } as LiveInputs['hardware'] }
        f.clock.advance(100, f.context); runtime.tick()
        expect(f.manager.snapshot().utterances.some(item => item.id === 'moving-voice' && item.state === 'started'), mode).toBe(true)
      }
      f.socket.push(frame('moving-voice', 1, .2, true, event.scope))
      expect(f.client.getSnapshot().failed).toBe(0)
      inputs = { ...inputs, emergency: true }; runtime.tick()
      expect(f.manager.snapshot().utterances.some(item => item.id === 'moving-voice')).toBe(false)
    } finally { runtime.dispose(); f.manager.dispose() }
  })

  it('does not close audible speech when provider PCM bursts above the control-message limit', async () => {
    const f = new Fixture(); await f.connect()
    const socket = f.socket
    let controls = 0
    const send = socket.send.bind(socket)
    socket.send = data => {
      send(data)
      // Mirror the production WS protection, counting client control messages,
      // not the server's outbound binary audio frames.
      if (++controls > 40) {
        socket.push({ type: 'error', reason: 'rate_limited' })
        socket.serverClose()
      }
    }
    f.speech()
    socket.push(frame('g1', 0, .3, false))
    f.clock.advance(30, f.context); f.client.observe(f.manager.snapshot())
    expect(f.manager.snapshot().active).toBe(1)
    // Six seconds of audio delivered in one fast network burst, AFTER start.
    for (let sequence = 1; sequence <= 60; sequence++) socket.push(frame('g1', sequence, .1, false))
    socket.push(frame('g1', 61, 0, true))
    expect(controls).toBe(2) // Immediate start + final duration, not 62 messages.
    expect(socket.sent.filter(item => item.type === 'playback_started').at(-1)).toMatchObject({ durationMs: 6300 })
    expect(f.client.getSnapshot()).toMatchObject({ state: 'ready', failed: 0 })
    expect(f.manager.snapshot().active).toBe(1)
    f.clock.advance(6400, f.context)
    for (const source of f.context.sources) source.end()
    f.client.observe(f.manager.snapshot())
    expect(f.client.getSnapshot()).toMatchObject({ spoken: 1, failed: 0 })
    expect(socket.types()).toContain('playback_completed')
    f.client.dispose(); f.manager.dispose()
  })

  it('bounds streaming progress ACKs by wall time and always reports the final duration', async () => {
    const f = new Fixture(); await f.connect()
    f.speech(); f.socket.push(frame('g1', 0, .3, false))
    f.clock.advance(30, f.context); f.client.observe(f.manager.snapshot())
    for (let sequence = 1; sequence <= 10; sequence++) {
      f.clock.advance(100, f.context)
      f.socket.push(frame('g1', sequence, .1, false))
    }
    expect(f.socket.sent.filter(item => item.type === 'playback_started')).toHaveLength(3)
    f.socket.push(frame('g1', 11, .1, true))
    expect(f.socket.sent.filter(item => item.type === 'playback_started')).toHaveLength(4)
    expect(f.socket.sent.filter(item => item.type === 'playback_started').at(-1)).toMatchObject({ durationMs: 1400 })
    f.client.dispose(); f.manager.dispose()
  })

  it('reports actual local buffer duration once, without identifiers and without serializing latest-start audio', async () => {
    const f = new Fixture(); await f.connect()
    const buffer = verifyLocalBuffer(f.context.asAudioContext(), f.context.createBuffer(1, 6000, RATE))
    expect(f.manager.playLocal({ id: 'private-cue-id', scope: scope(), source: 'local', buffer,
      startDeadlineMs: f.clock.now() + 5000, baseGain: 1, revalidate: () => true,
      localPlayback: { kind: 'count', action: 'count' } })).toBe(true)
    f.clock.advance(20, f.context)
    const audio = f.manager.snapshot()
    expect(audio.utterances[0].bufferDurationMs).toBe(750)
    f.client.observe(audio); f.client.observe(audio)
    expect(f.socket.sent.filter(item => item.type === 'localPlayback')).toEqual([
      { type: 'localPlayback', kind: 'count', action: 'count', durationMs: 750 },
    ])
    f.speech(); f.socket.push(frame('g1', 0, .3, true))
    f.clock.advance(20, f.context); f.client.observe(f.manager.snapshot())
    expect(f.manager.snapshot().active).toBe(2)
    expect(f.manager.snapshot().foreground).toBe('g1')
    f.client.dispose(); f.manager.dispose()
  })

  it.each([null, undefined, Number.NaN, -1, 60_001])('never fabricates local duration from %s', async duration => {
    const f = new Fixture(); await f.connect()
    const audio = { ...f.manager.snapshot(), utterances: [{ id: 'local', scope: scope(), source: 'local' as const,
      state: 'started' as const, startOrdinal: 1, baseGain: 1, coefficient: 1, gain: 1, targetGain: 1,
      scheduledStartTime: 0, stream: null, bufferDurationMs: duration,
      localPlayback: { kind: 'count' as const, action: 'count' as const } }] }
    f.client.observe(audio)
    expect(f.socket.types()).not.toContain('localPlayback')
    f.client.dispose(); f.manager.dispose()
  })

  it('does not replay an offline local start after reconnect or report a scheduled clip', async () => {
    const f = new Fixture(); await f.connect()
    const buffer = verifyLocalBuffer(f.context.asAudioContext(), f.context.createBuffer(1, RATE, RATE))
    f.manager.playLocal({ id: 'offline', scope: scope(), source: 'local', buffer,
      startDeadlineMs: f.clock.now() + 5000, baseGain: 1, delayMs: 100, revalidate: () => true,
      localPlayback: { kind: 'cue', action: 'support' } })
    f.client.observe(f.manager.snapshot())
    expect(f.socket.types()).not.toContain('localPlayback')
    f.socket.serverClose()
    f.clock.advance(120, f.context); f.client.observe(f.manager.snapshot())
    f.socket.push({ type: 'configured', mode: 'hybrid', text: true, voice: true })
    f.client.observe(f.manager.snapshot())
    expect(f.socket.types()).not.toContain('localPlayback')
    f.client.dispose(); f.manager.dispose()
  })

  it('tracks explicit states and actual streamed duration without a second start or false completion', async () => {
    const f = new Fixture(); await f.connect()
    const original = f.socket.events().at(-1)!.event
    expect(f.client.getSnapshot().opportunities).toMatchObject({ pending: 1, preparing: 1, ready: 0 })
    f.speech()
    expect(f.client.getSnapshot().opportunities?.ready).toBe(1)
    f.socket.push(frame('g1', 0, .3, false))
    f.clock.advance(100, f.context); f.client.observe(f.manager.snapshot())
    expect(f.client.getSnapshot().opportunities?.started).toBe(1)
    f.socket.push(frame('g1', 1, .6, true))
    expect(f.socket.sent.filter(item => item.type === 'playback_started').at(-1)).toMatchObject({ durationMs: 900 })
    f.client.observe(f.manager.snapshot())
    expect(f.client.getSnapshot().opportunities?.started).toBe(1)
    f.manager.cancelAll('mute'); f.client.observe(f.manager.snapshot())
    expect(f.client.getSnapshot().opportunities).toMatchObject({ interrupted: 1, completed: 0 })
    f.speech('g2', original)
    expect(f.client.getSnapshot().opportunities?.started).toBe(1)
    expect(f.socket.types()).not.toContain('playback_completed')
    f.client.dispose(); f.manager.dispose()
  })

  it.each(['expired', 'budget', 'pipeline_busy', 'validation_failed', 'no_useful_content'])
  ('terminates one %s opportunity explicitly without retry/regeneration', async reason => {
    const f = new Fixture(); await f.connect()
    const original = f.socket.events().at(-1)!.event
    f.socket.push({ type: 'decision', eventId: original.id, action: 'silence', reason })
    f.socket.push({ type: 'decision', eventId: original.id, action: 'silence', reason })
    f.tick()
    expect(f.socket.events()).toHaveLength(1)
    expect(f.client.getSnapshot().opportunities?.[reason === 'expired' ? 'expired' : 'rejected']).toBe(1)
    f.speech('late', original)
    expect(f.manager.snapshot().utterances).toHaveLength(0)
    f.client.dispose(); f.manager.dispose()
  })

  it('forwards only the supplied bounded local meanings alongside the original saved-event identity', async () => {
    const f = new Fixture(); await f.connect()
    f.tick({ phase: 'active-set' })
    const result = f.lifecycle('saved-local', 'set_persisted', 'active-set')
    f.refs[result.id] = { backendSetId: 7 }
    f.tick({ phase: 'rest', lifecycle: [result], localCompletion: () => ({ cueIds: ['set-end'], acknowledged: ['set_closed'] }) })
    const sent = f.socket.events().at(-1)!
    expect(sent.event).toEqual(result)
    expect(sent.context?.localCompletion).toEqual({ cueIds: ['set-end'], acknowledged: ['set_closed'] })
    f.client.dispose(); f.manager.dispose()
  })

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
    expect(f.socket.sent[0]).toEqual({ type: 'configure', runToken: 'secret-1', ownerId: 'tab-test', runtimeRunId: 'run-1' })
    expect(f.socket.binaryType).toBe('arraybuffer')
    expect(f.client.getSnapshot()).toMatchObject({ state: 'ready', voiceId: 'ash', voice: true })
    expect(f.socket.events().map(item => item.event.kind)).toEqual(['workout_started'])
    f.tick(); f.tick()
    expect(f.socket.events()).toHaveLength(1)
  })

  it('binds a distinct runtime ID without changing ledger URLs or event/PCM scope', async () => {
    const f = new Fixture()
    f.runs = 40 // Deliberately prevent the sandbox's accidental ledger/runtime equality.
    await f.connect()
    expect(f.socket.url).toContain('/runs/run-41/live')
    expect(f.socket.sent[0]).toMatchObject({ runtimeRunId: 'run-1', runToken: 'secret-41' })
    const event = f.socket.events()[0].event
    expect(event.scope).toEqual(scope())
    f.speech(); f.socket.push(frame('g1', 0, .3, true))
    expect(f.manager.snapshot().utterances[0].scope).toEqual(scope())
    f.clock.advance(20, f.context); f.client.observe(f.manager.snapshot())
    expect(f.socket.sent.find(item => item.type === 'playback_started')).toMatchObject({ identity: { scope: scope() } })
    f.client.dispose(); f.manager.dispose()
  })

  it('sends catalog identity on the very first setup without a second competing intro', async () => {
    const f = new Fixture()
    const current = session()
    f.input.session = session({ exercises: [
      { ...current.exercises[0], slug: 'machine-pulldown', details: { slug: 'machine-pulldown' },
        summary: { slug: 'machine-pulldown' }, loadSettings: { mode: 'constant' } }, current.exercises[1],
    ] })
    await f.connect()
    const first = f.socket.events()[0]
    expect(first.context).toMatchObject({ exerciseSlug: 'machine-pulldown', variant: 'machine-pulldown',
      exerciseIndex: 1, totalSets: 2 })
    f.tick(); f.tick()
    expect(f.socket.events()).toHaveLength(1)
    f.client.dispose(); f.manager.dispose()
  })

  it('never configures a stale socket after a user/runtime switch', async () => {
    const f = new Fixture()
    f.tick()
    await vi.waitFor(() => expect(f.sockets).toHaveLength(1))
    const old = f.socket
    f.tick({ userId: 'u2', session: session({ id: 'runtime-2' }), scope: scope({ userId: 'u2', runId: 'runtime-2' }) })
    await vi.waitFor(() => expect(f.sockets).toHaveLength(2))
    old.open(); f.socket.open()
    expect(old.sent).toHaveLength(0)
    expect(f.socket.sent[0]).toMatchObject({ runtimeRunId: 'runtime-2', runToken: 'secret-2' })
    f.client.dispose(); f.manager.dispose()
  })

  it.each([
    { degraded: true, degradedReason: 'voice_unavailable', reason: 'voice_unavailable' },
    { degraded: 'credential_unavailable', reason: 'credential_unavailable' },
    { degraded: true, degradedReason: 'private-provider-message', reason: 'degraded' },
  ])('reports unavailable live voice honestly: $reason', async ({ reason, ...configured }) => {
    const f = new Fixture(); await f.connect({ voice: false, ...configured })
    expect(f.client.getSnapshot()).toMatchObject({ state: 'ready', voice: false, degraded: true, reason })
    expect(JSON.parse(redactedNetworkReport(f.client.getSnapshot())).reason).toBe(reason)
    f.client.dispose(); f.manager.dispose()
  })

  it('forwards the next exercise, the half-target milestone and one long-rest opportunity', async () => {
    const f = new Fixture()
    await f.connect()
    f.tick({ phase: 'active-set', session: session({ view: 'exercise-session' }), reps: 4 })
    f.tick({ phase: 'active-set', reps: 5 })
    f.tick({ phase: 'active-set', reps: 6 })
    const rest = { mode: 'between-sets', totalSeconds: 90, remainingSeconds: 80, timerPaused: false, completedSet: { backendSetId: 91 } }
    f.tick({ phase: 'rest', session: session({ view: 'rest', restState: rest }) })
    f.tick({ phase: 'rest', session: session({ view: 'rest', restState: { ...rest, remainingSeconds: 70 } }) })
    f.tick({ phase: 'rest', session: session({ view: 'rest', restState: { ...rest, remainingSeconds: 60 } }) })
    f.tick({ phase: 'setup', scope: scope({ exerciseId: 'e2', setOrdinal: 1, scopeEpoch: 9 }),
      session: session({ currentExerciseId: 'e2', completedSets: { e1: [{}] } }) })
    const sent = f.socket.events()
    expect(sent.map(item => item.event.kind)).toEqual(['workout_started', 'rep_milestone', 'rest_long_opportunity', 'exercise_ready'])
    expect(sent[0].context).toEqual({ exerciseCount: 2, exerciseName: 'Жим ногами', exerciseIndex: 1, totalSets: 2, targetReps: 10 })
    expect(sent[1].context).toEqual({ phaseElapsedMs: 100, moment: 'half', exerciseName: 'Жим ногами', totalSets: 2, targetReps: 10 })
    expect(sent[2].context).toEqual({ restMs: 90_000, restElapsedMs: 20_000, exerciseName: 'Жим ногами', totalSets: 2 })
    expect(sent[2].refs).toEqual({ backendSetId: 91 })
    expect(sent[3].context).toEqual({ exerciseName: 'Тяга', exerciseIndex: 2, exerciseCount: 2, totalSets: 1, targetReps: 10 })
    expect(sent[0].event.scope).toEqual(scope())
    expect(sent[3].event.scope).toEqual(scope({ exerciseId: 'e2', setOrdinal: 1, scopeEpoch: 9 }))
  })

  it('comments a set at its start, on a partial rep, near the end and on a stall — once each', async () => {
    const f = new Fixture()
    await f.connect()
    const active = { phase: 'active-set' as const, session: session({ view: 'exercise-session' }) }
    f.tick({ ...active, reps: 0, partialReps: 0 })
    f.tick({ ...active, reps: 1, partialReps: 0 })
    f.tick({ ...active, reps: 2, partialReps: 0 })
    f.tick({ ...active, reps: 2, partialReps: 1 })
    f.tick({ ...active, reps: 3, partialReps: 2 })
    f.tick({ ...active, reps: 8, partialReps: 2 })
    f.tick({ ...active, reps: 9, partialReps: 2 })
    f.tick({ ...active, nowMs: f.input.nowMs + 9_000, reps: 9, partialReps: 2 })
    f.tick({ ...active, reps: 9, partialReps: 2 })
    const sent = f.socket.events().slice(1)
    expect(sent.map(item => [item.event.kind, item.context?.moment])).toEqual([
      ['set_activated', 'start'], ['rep_completed', 'partial'], ['last_rep_pending', 'finish'], ['rep_milestone', 'stall']])
    expect(sent.every(item => item.event.phase === 'active-set')).toBe(true)
    expect(sent[3].context?.phaseElapsedMs).toBeGreaterThan(9_000)
    f.tick({ ...active, reps: 1, partialReps: 0, saved: { ...saved, duringSets: false } })
    expect(f.socket.events()).toHaveLength(sent.length + 1)
  })

  it('paces range sets by the top of the range without claiming an exact target', async () => {
    const f = new Fixture()
    await f.connect()
    const range = { targetReps: 10, targetMinReps: 8, targetMaxReps: 10, setType: 'warmup', restSeconds: 60, weightLabel: '' }
    const active = { phase: 'active-set' as const, session: session({ view: 'exercise-session',
      exercises: [{ id: 'e1', name: 'Жим ногами', kind: 'machine', plan: [range, range] }] }) }
    for (const reps of [0, 1, 5, 8]) f.tick({ ...active, reps, partialReps: 0 })
    const sent = f.socket.events().slice(1)
    expect(sent.map(item => item.context?.moment)).toEqual(['start', 'half', 'finish'])
    expect(sent.every(item => !('targetReps' in (item.context ?? {})))).toBe(true)
  })

  it('comments a timed set by its clock: start, half and the final seconds', async () => {
    const f = new Fixture()
    await f.connect()
    const timed = session({ view: 'exercise-session', exercises: [{ id: 'e1', name: 'Шаффл', kind: 'timed', plan: [
      { targetSeconds: 120, restSeconds: 60, weightLabel: '' }] }] })
    const clock = (elapsedS: number, running = true) => f.tick({ phase: 'active-set', session: timed, reps: null,
      timer: { exerciseId: 'e1', setOrdinal: 1, elapsedS, running } })
    for (const s of [1, 4, 30, 61, 62, 100, 106, 107]) clock(s)
    clock(110, false)
    const sent = f.socket.events().slice(1)
    expect(sent.map(item => [item.event.kind, item.context?.moment, item.event.progressUnit])).toEqual([
      ['set_activated', 'start', 'seconds'], ['rep_milestone', 'support', 'seconds'],
      ['rep_milestone', 'half', 'seconds'], ['last_rep_pending', 'finish', 'seconds']])
    expect(sent[0].context).toMatchObject({ targetSeconds: 120, phaseElapsedMs: 4000 })
    expect(sent[0].event.exerciseKind).toBe('timed')
  })

  it('offers bounded regular advice even without a new rep milestone, never during pauses or after opt-out', async () => {
    const f = new Fixture()
    await f.connect()
    const failure = { ...plan(10), setType: 'failure' }
    const active = { phase: 'active-set' as const, session: session({ view: 'exercise-session',
      exercises: [{ id: 'e1', name: 'Жим ногами', kind: 'machine', plan: [failure] }] }) }
    f.tick({ ...active, reps: 1 })
    const start = f.input.nowMs
    for (const [elapsed, reps] of [[15_000, 2], [16_000, 3], [30_000, 4], [45_000, 5], [60_000, 6], [75_000, 7]]) {
      f.tick({ ...active, nowMs: start + elapsed, reps })
    }
    const advice = f.socket.events().filter(item => item.context?.moment === 'support')
    expect(advice.map(item => item.context?.phaseElapsedMs)).toEqual([15_000, 30_000, 45_000, 60_000])
    expect(advice.every(item => item.event.phase === 'active-set' && !('targetReps' in item.context!))).toBe(true)
    const count = f.socket.events().length
    f.tick({ ...active, phase: 'paused-set', nowMs: start + 90_000 })
    f.tick({ ...active, saved: { ...saved, duringSets: false }, nowMs: start + 105_000 })
    expect(f.socket.events()).toHaveLength(count)
  })

  it('forwards persisted lifecycle events with backend refs, never replaying older ones', async () => {
    const f = new Fixture()
    f.input = { ...f.input, lifecycle: [lifecycleEvent('old', 'set_persisted', 'finalizing-set')] }
    f.refs = { old: { backendSetId: 1 }, l2: { backendSetId: 7 } }
    await f.connect()
    const stopped = lifecycleEvent('l1', 'set_stopped', 'finalizing-set')
    f.tick({ phase: 'finalizing-set' })
    const persisted = f.lifecycle('l2', 'set_persisted', 'finalizing-set')
    f.tick({ phase: 'finalizing-set', lifecycle: [lifecycleEvent('old', 'set_persisted', 'finalizing-set'), stopped, persisted] })
    const sent = f.socket.events().filter(item => item.event.kind === 'set_persisted')
    expect(sent).toHaveLength(1)
    expect(sent[0]).toMatchObject({ event: { id: 'l2' }, refs: { backendSetId: 7 }, context: { restMs: 90_000, restElapsedMs: 0 } })
    expect(sent[0].context).not.toHaveProperty('nextExerciseName')
    f.tick({ scope: scope({ setOrdinal: 2 }) })
    const last = { ...f.lifecycle('l3', 'set_persisted', 'finalizing-set'), scope: scope({ setOrdinal: 2 }) }
    f.refs.l3 = { backendSetId: 8 }
    f.tick({ lifecycle: [last] })
    expect(f.socket.events().at(-1)).toMatchObject({ event: { id: 'l3' }, context: { nextExerciseName: 'Тяга' } })
  })

  it('streams speech with immutable source identity and scope and acknowledges playback', async () => {
    const f = new Fixture()
    await f.connect()
    const identity = speechIdentity(f.socket.events()[0].event)
    f.speech()
    f.socket.push(frame('g1', 0, 0.3, false))
    f.socket.push(frame('g1', 1, 0.1, true))
    f.socket.push({ type: 'speech_end', generationId: 'g1', status: 'complete', frames: 2, firstAudioMs: 420 })
    f.clock.advance(50, f.context)
    f.client.observe(f.manager.snapshot())
    const started = f.socket.sent.find(item => item.type === 'playback_started')
    expect(started).toEqual({ type: 'playback_started', generationId: 'g1', identity, durationMs: 400 })
    for (const source of f.context.sources) source.end()
    f.client.observe(f.manager.snapshot())
    expect(f.socket.sent.at(-1)).toEqual({ type: 'playback_completed', generationId: 'g1', identity, durationMs: 400 })
    expect(f.client.getSnapshot()).toMatchObject({ streams: 1, spoken: 1, failed: 0, firstAudioMs: 420 })
  })

  it('refuses speech while gated and asks the server to cancel', async () => {
    const f = new Fixture()
    await f.connect()
    f.tick({ gate: 'hidden' })
    f.speech('g2')
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
    f.socket.push({ type: 'decision', eventId: f.socket.events()[0].event.id, identity: speechIdentity(f.socket.events()[0].event), triggerId: 'T01', action: 'text', reason: null, text: 'Начинаем.' })
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
    f.socket.push({ type: 'decision', eventId: f.socket.events()[0].event.id, identity: speechIdentity(f.socket.events()[0].event), triggerId: 'T01', action: 'text', reason: null, text: 'секретный текст' })
    const report = redactedNetworkReport(f.client.getSnapshot())
    expect(report).not.toMatch(/secret|секретный|run-1|u1/)
    expect(JSON.parse(report)).toMatchObject({ state: 'ready', voiceId: 'ash', usage: { requests: 2 } })
  })
})

describe('immutable network speech regressions', () => {
  it.each([
    ['set_persisted', 'active-set', 'rest'],
    ['set_persisted', 'finalizing-set', 'rest'],
    ['exercise_finalized', 'active-set', 'exercise-summary'],
    ['exercise_finalized', 'finalizing-set', 'exercise-summary'],
    ['exercise_finalized', 'exercise-summary', 'exercise-summary'],
    ['workout_finalized', 'workout-summary', 'workout-summary'],
  ] as const)('forwards real %s capture in %s after save into %s', async (kind, phase, destination) => {
    const f = new Fixture(); await f.connect()
    f.tick({ phase, session: session({ view: phase === 'workout-summary' || phase === 'exercise-summary' ? phase : 'exercise-session' }) })
    const current = { userId: 'u1', runId: 'run-1', exerciseId: 'e1', setOrdinal: 1, scopeEpoch: 90, mock: false }
    const observer = new CoachLifecycleObserver({ enabled: () => true, current: () => current,
      clock: { nowMs: () => f.clock.now() }, versions: value => f.client.captureVersions(value, f.input.session, saved) })
    const capture = observer.capture('machine', kind === 'workout_finalized')!
    expect(capture.versions?.phase).toBe(phase)
    if (phase === 'active-set') f.tick({ phase: 'finalizing-set', scope: scope({ scopeEpoch: 4 }) })
    const targetScope = scope({ scopeEpoch: 5 })
    f.manager.updateScope(targetScope)
    f.tick({ phase: destination, scope: targetScope })
    // Publish after the async DB save and after the runtime transition was observed.
    expect(observer.publish(capture, kind, { backendSetId: 7, backendExerciseId: 8, backendWorkoutId: 9 })).toBe(true)
    const event = observer.snapshot()[0]
    f.refs[event.id] = observer.refs(event.id)!
    f.tick({ lifecycle: [event] })
    expect(f.socket.events().find(item => item.event.id === event.id)?.event).toEqual(event)
    expect(event.phase).toBe(phase)
    f.speech('confirmed', event); f.socket.push(frame('confirmed', 0, .3, true, event.scope))
    f.clock.advance(50, f.context); f.client.observe(f.manager.snapshot())
    expect(f.socket.sent.find(item => item.type === 'playback_started')?.identity).toEqual(speechIdentity(event))
  })

  it.each(['reverse', 'epoch', 'pause', 'gate', 'set', 'exercise', 'plan', 'run'] as const)(
    'never resurrects an active-set result after %s during the save', async change => {
      const f = new Fixture(); await f.connect(); f.tick({ phase: 'active-set' })
      const event = f.lifecycle('captured', 'set_persisted', 'active-set')
      f.tick({ phase: 'finalizing-set' })
      if (change === 'reverse') f.tick({ phase: 'active-set' })
      if (change === 'epoch') f.tick({ scope: scope({ scopeEpoch: 4 }) })
      if (change === 'pause') f.tick({ phase: 'paused-set' })
      if (change === 'gate') f.tick({ latched: true })
      if (change === 'set') f.tick({ scope: scope({ setOrdinal: 2 }) })
      if (change === 'exercise') f.tick({ scope: scope({ exerciseId: 'e2' }) })
      if (change === 'run') f.tick({ scope: scope({ runId: 'other' }) })
      if (change === 'plan') f.tick({ session: session({ exercises: [{ ...session().exercises[0], plan: [plan(12)] }] }) })
      f.tick({ phase: 'rest', scope: scope(), latched: false, session: session() })
      f.refs[event.id] = { backendSetId: 7 }
      f.tick({ lifecycle: [event] }); f.speech('stale', event)
      expect(f.socket.events().some(item => item.event.id === event.id)).toBe(false)
      expect(f.manager.snapshot().pending).toBe(0)
    })

  it('requires the kind-specific confirmed ref and rejects fabricated result capture phases', async () => {
    for (const phase of ['active-set', 'setup', 'rest'] as const) {
      const f = new Fixture(); await f.connect(); f.tick({ phase })
      const event = f.lifecycle('unconfirmed', 'set_persisted', phase)
      f.refs[event.id] = phase === 'active-set' ? { backendExerciseId: 8 } : { backendSetId: 7 }
      f.tick({ lifecycle: [event] })
      expect(f.socket.events().some(item => item.event.id === event.id)).toBe(false)
    }
  })

  it('allows one summary epoch remap, not an arbitrary second remap or a return', async () => {
    const f = new Fixture(); await f.connect(); f.tick({ phase: 'exercise-summary' })
    const event = f.lifecycle('summary', 'exercise_finalized', 'exercise-summary')
    f.refs[event.id] = { backendExerciseId: 8 }; f.tick({ lifecycle: [event] })
    f.tick({ scope: scope({ scopeEpoch: 4 }) }); f.tick({ scope: scope({ scopeEpoch: 5 }) })
    f.tick({ scope: scope() }); f.speech('stale-summary', event)
    expect(f.manager.snapshot().pending).toBe(0)
  })

  it.each([false, true])('retains capture-time provenance across an async save (plan change: %s)', async changePlan => {
    const f = new Fixture(); await f.connect(); f.tick({ phase: 'active-set', session: session({ view: 'exercise-session' }) })
    const current = { userId: 'u1', runId: 'run-1', exerciseId: 'e1', setOrdinal: 1, scopeEpoch: 90, mock: false }
    const observer = new CoachLifecycleObserver({ enabled: () => true, current: () => current,
      clock: { nowMs: () => f.clock.now() }, versions: value => f.client.captureVersions(value, f.input.session, f.input.saved) })
    const capture = observer.capture('machine')!
    const before = f.socket.sent.filter(item => item.type === 'context').at(-1)!
    expect(capture.versions).toMatchObject({ planRevision: before.planRevision, contextVersion: before.contextVersion })
    let finish!: () => void
    const save = new Promise<void>(resolve => { finish = resolve }).then(() => {
      expect(observer.publish(capture, 'set_persisted', { backendSetId: 7, actualValue: 10 })).toBe(true)
    })
    if (changePlan) f.tick({ session: session({ exercises: [{ ...session().exercises[0], plan: [plan(12)] }] }) })
    f.clock.advance(500, f.context); finish(); await save
    const event = observer.snapshot()[0]
    expect(event.createdAtMs).toBe(capture.createdAtMs)
    expect(event.phase).toBe('active-set')
    expect(event.startDeadlineMs).toBe(capture.createdAtMs + 20_000)
    expect(event.planRevision).toBe(before.planRevision)
    expect(event.contextVersion).toBe(before.contextVersion)
    expect(event.scope.scopeEpoch).toBe(3) // Network epoch, not the observer's independent epoch=90.
    expect(event.facts[0].scopeEpoch).toBe(event.scope.scopeEpoch)
    f.refs[event.id] = observer.refs(event.id)!
    f.tick({ nowMs: f.clock.now(), lifecycle: [event] })
    const sent = f.socket.events().find(item => item.event.id === event.id)
    if (changePlan) expect(sent).toBeUndefined()
    else {
      expect(sent).toBeDefined()
      expect(f.socket.sent.find(item => item.type === 'event' && (item.event as CoachEvent).id === event.id)?.elapsedAtSendMs).toBe(500)
      f.tick({ phase: 'finalizing-set', scope: scope({ scopeEpoch: 4 }) })
      const restScope = scope({ scopeEpoch: 5 }); f.manager.updateScope(restScope)
      f.tick({ scope: restScope, phase: 'rest' }); f.speech('saved', event)
      f.socket.push(frame('saved', 0, .3, true, event.scope)); f.clock.advance(50, f.context)
      f.client.observe(f.manager.snapshot())
      expect(f.socket.sent.find(item => item.type === 'playback_started')?.identity).toEqual(speechIdentity(event))
    }
  })

  it('fails closed without capture provenance, with unobserved edits, or incompatible capture phases', async () => {
    const f = new Fixture(); await f.connect()
    const current = { userId: 'u1', runId: 'run-1', exerciseId: 'e1', setOrdinal: 1, scopeEpoch: 3, mock: false }
    expect(f.client.captureVersions(current, f.input.session, f.input.saved)).not.toBeNull()
    const changed = session(); changed.exercises[0].plan[0].targetReps = 12
    expect(f.client.captureVersions(current, changed, saved)).toBeNull()
    expect(f.client.captureVersions(current, session({ view: 'rest' }), saved)).toBeNull()
    expect(f.client.captureVersions({ ...current, userId: 'other' }, f.input.session, saved)).toBeNull()
    f.refs.zero = { backendSetId: 7 }; f.refs.incompatible = { backendSetId: 8 }
    const incompatible = f.lifecycle('incompatible', 'set_persisted', 'finalizing-set') // Captured during setup, not finalizing.
    f.tick({ phase: 'finalizing-set', lifecycle: [lifecycleEvent('zero', 'set_persisted', 'finalizing-set'), incompatible] })
    expect(f.socket.events().map(item => item.event.kind)).toEqual(['workout_started'])
  })

  it.each(['missing', 'unknown', 'mismatch', 'expired', 'phase', 'plan', 'closed'] as const)('rejects %s text decisions without displaying them', async change => {
    const f = new Fixture(); f.input = { ...f.input, saved: { ...saved, mode: 'text-only' }, gate: 'mute' }
    await f.connect({ voice: false, mode: 'text-only' })
    const event = f.socket.events()[0].event
    let identity: unknown = speechIdentity(event)
    if (change === 'missing') identity = undefined
    if (change === 'unknown') identity = { ...speechIdentity(event), eventId: 'unsolicited' }
    if (change === 'mismatch') identity = { ...speechIdentity(event), planRevision: 999 }
    if (change === 'expired') f.clock.advance(20_001, f.context)
    if (change === 'phase') f.tick({ phase: 'waiting-start' })
    if (change === 'plan') f.tick({ session: session({ exercises: [{ ...session().exercises[0], plan: [plan(12)] }] }) })
    if (change === 'closed') f.socket.push({ type: 'error', reason: 'run_closed' })
    f.socket.push({ type: 'decision', identity, eventId: event.id, action: 'text', text: 'OLD', triggerId: 'T01' })
    expect(f.client.getSnapshot().lastText).toBeNull()
    expect(f.client.getSnapshot().decisions.some(item => item.text === 'OLD')).toBe(false)
  })

  it('clears previously accepted text on context invalidation and rejects duplicate decisions', async () => {
    const f = new Fixture(); await f.connect()
    const decision = { type: 'decision', eventId: f.socket.events()[0].event.id, identity: speechIdentity(f.socket.events()[0].event), action: 'text', text: 'Fresh' }
    f.socket.push(decision); f.socket.push(decision)
    expect(f.client.getSnapshot().lastText).toBe('Fresh')
    expect(f.client.getSnapshot().decisions).toHaveLength(1)
    f.tick({ phase: 'waiting-start' })
    expect(f.client.getSnapshot().lastText).toBeNull()
    expect(f.client.getSnapshot().decisions.every(item => item.text === null)).toBe(true)
  })

  it('records event/send/start/terminal latency separately with unknown model/connection labels', async () => {
    const f = new Fixture(); await f.connect(); f.speech()
    f.clock.advance(200, f.context); f.socket.push(frame('g1', 0, .3, true))
    f.clock.advance(50, f.context); f.client.observe(f.manager.snapshot())
    for (const source of f.context.sources) source.end()
    f.client.observe(f.manager.snapshot())
    expect(f.client.getSnapshot().latencies).toEqual({})
    f.socket.push({ type: 'speech_end', generationId: 'g1', status: 'complete' })
    const metrics = f.client.getSnapshot().latencies
    expect(metrics[`eventToSend:${unknownGroup()}`]).toEqual({ count: 1, p50: 0, p95: 0 })
    expect(metrics[`eventToCompleted:${unknownGroup()}`]).toEqual({ count: 1, p50: 250, p95: 250 })
    expect(Object.keys(metrics).every(key => key.endsWith('voiceModel=unknown:textModel=unknown:connection=unknown'))).toBe(true)
  })

  const transitions: Array<[string, Partial<NetworkTick>]> = [
    ['exercise', { scope: scope({ exerciseId: 'e2', scopeEpoch: 4 }), session: session({ currentExerciseId: 'e2' }) }],
    ['epoch', { scope: scope({ scopeEpoch: 4 }) }],
    ['set', { scope: scope({ setOrdinal: 2, scopeEpoch: 4 }) }],
    ['phase', { phase: 'waiting-start' }],
    ['pause', { phase: 'paused-set' }],
    ['hidden', { gate: 'hidden' }],
    ['mute', { gate: 'mute' }],
    ['safety', { latched: true }],
    ['plan', { session: session({ exercises: [{ ...session().exercises[0], plan: [plan(12)] }] }) }],
    ['mode', { saved: { ...saved, mode: 'text-only' } }],
    ['user', { userId: 'u2', scope: scope({ userId: 'u2' }) }],
    ['run', { session: session({ runId: 'run-2' }), scope: scope({ runId: 'run-2' }) }],
    ['session close', { session: null, scope: null }],
  ]

  it.each(transitions)('rejects late speech after %s, even after returning to the origin', async (_name, patch) => {
    const f = new Fixture(); await f.connect()
    const original = f.input, event = f.socket.events()[0].event
    f.tick(patch)
    f.tick({ ...original, nowMs: f.input.nowMs + 100 })
    f.speech('late', event)
    f.socket.push(frame('late', 0, .3, true))
    expect(f.manager.snapshot().utterances).toHaveLength(0)
    expect(f.socket.sent.filter(item => item.type === 'playback_started')).toHaveLength(0)
  })

  it.each(transitions)('proactively removes pending generations on %s', async (_name, patch) => {
    const f = new Fixture(); await f.connect(); f.speech()
    expect(f.manager.snapshot().pending).toBe(1)
    f.tick(patch)
    expect(f.manager.snapshot().utterances).toHaveLength(0)
    f.socket.push(frame('g1', 0, .3, true))
    expect(f.socket.sent.filter(item => item.type === 'playback_started')).toHaveLength(0)
  })

  it.each(transitions.filter(([name]) => !['exercise', 'epoch', 'set', 'phase', 'plan'].includes(name)))('interrupts already started speech on %s without completion', async (_name, patch) => {
    const f = new Fixture(); await f.connect(); f.speech()
    f.socket.push(frame('g1', 0, .5, false)); f.clock.advance(50, f.context)
    f.client.observe(f.manager.snapshot())
    expect(f.socket.sent.filter(item => item.type === 'playback_started')).toHaveLength(1)
    f.tick(patch)
    expect(f.manager.snapshot().utterances).toHaveLength(0)
    expect(f.socket.sent.filter(item => item.type === 'playback_completed')).toHaveLength(0)
  })

  it('keeps already started speech across ordinary transitions, including later original-scope frames', async () => {
    const f = new Fixture(); await f.connect(); const event = f.socket.events()[0].event; f.speech()
    f.socket.push(frame('g1', 0, .5, false)); f.clock.advance(50, f.context)
    // Do not call observe: tick must detect the mixer's already-observed start itself.
    const next = scope({ exerciseId: 'e2', scopeEpoch: 4 })
    f.manager.updateScope(next)
    f.tick({ phase: 'active-set', scope: next, session: session({ currentExerciseId: 'e2' }), reps: 0 })
    f.socket.push(frame('g1', 1, .2, true, event.scope))
    f.client.observe(f.manager.snapshot())
    expect(f.manager.snapshot().utterances[0].scope).toEqual(event.scope)
    // Immediate start before context + final-duration update, not a second start.
    const acknowledgements = f.socket.sent.filter(item => item.type === 'playback_started')
    expect(acknowledgements).toHaveLength(2)
    expect(acknowledgements[1]).toMatchObject({ identity: speechIdentity(event), durationMs: 700 })
    expect(f.socket.sent.find(item => item.type === 'playback_started')?.identity).toEqual(speechIdentity(event))
  })

  it.each(['set_persisted', 'exercise_finalized', 'workout_finalized'] as const)('allows only the explicit %s result handoff, preserving lifecycle versions and PCM scope', async kind => {
    const f = new Fixture(); await f.connect()
    const phase = kind === 'set_persisted' ? 'finalizing-set' : kind === 'exercise_finalized' ? 'exercise-summary' : 'workout-summary'
    f.tick({ phase })
    const event = f.lifecycle('result', kind, phase)
    f.refs.result = kind === 'set_persisted' ? { backendSetId: 7 } : kind === 'exercise_finalized' ? { backendExerciseId: 8 } : { backendWorkoutId: 9 }
    f.tick({ lifecycle: [event] })
    expect(f.socket.events().at(-1)!.event).toEqual(event)
    f.speech('result-audio', event)
    const next = scope({ scopeEpoch: 4 })
    // Production ordering: mixer receives the new scope before network.tick.
    f.manager.updateScope(next)
    expect(f.manager.snapshot().pending).toBe(1)
    f.tick({ nowMs: f.clock.now(), scope: next, phase: kind === 'set_persisted' ? 'rest' : phase })
    f.socket.push(frame('result-audio', 0, .3, true, event.scope))
    f.clock.advance(50, f.context); f.client.observe(f.manager.snapshot())
    expect(f.manager.snapshot().utterances[0].scope).toEqual(event.scope)
    expect(f.socket.sent.find(item => item.type === 'playback_started')?.identity).toEqual(speechIdentity(event))
    expect(event.planRevision).toBeGreaterThan(0); expect(event.contextVersion).toBeGreaterThan(0)
  })

  it('allows a persisted-set reply that first arrives after the approved rest transition, but not a second epoch', async () => {
    const f = new Fixture(); await f.connect(); f.tick({ phase: 'finalizing-set' })
    const event = f.lifecycle('result', 'set_persisted', 'finalizing-set')
    f.refs.result = { backendSetId: 7 }; f.tick({ lifecycle: [event] })
    const next = scope({ scopeEpoch: 4 }); f.manager.updateScope(next)
    f.tick({ scope: next, phase: 'rest' }); f.speech('after-rest', event)
    expect(f.manager.snapshot().pending).toBe(1)
    f.tick({ scope: scope({ scopeEpoch: 5 }) })
    expect(f.manager.snapshot().pending).toBe(0)
  })

  it('does not allow persisted results to cross exercise/set/plan changes or pauses before arrival', async () => {
    for (const patch of [{ scope: scope({ setOrdinal: 2, scopeEpoch: 4 }), phase: 'rest' },
      { scope: scope({ exerciseId: 'e2', scopeEpoch: 4 }), phase: 'rest' }, { phase: 'paused-set' }] as const) {
      const f = new Fixture(); await f.connect(); f.tick({ phase: 'finalizing-set' })
      const event = f.lifecycle('result', 'set_persisted', 'finalizing-set')
      f.refs.result = { backendSetId: 7 }; f.tick({ lifecycle: [event] }); f.tick(patch); f.speech('bad', event)
      expect(f.manager.snapshot().utterances).toHaveLength(0)
    }
  })

  it('preserves an observer workout-only scope through workout-summary and ACKs', async () => {
    const f = new Fixture(); await f.connect()
    f.tick({ phase: 'workout-summary' })
    const event = { ...f.lifecycle('workout-result', 'workout_finalized', 'workout-summary'),
      scope: scope({ exerciseId: null, setOrdinal: null }), createdAtMs: f.input.nowMs + 1 }
    f.refs[event.id] = { backendWorkoutId: 9 }
    f.tick({ phase: 'workout-summary', lifecycle: [event] })
    expect(f.socket.events().at(-1)!.event).toEqual(event)
    f.speech('workout', event); f.socket.push(frame('workout', 0, .3, true, event.scope))
    f.clock.advance(50, f.context); f.client.observe(f.manager.snapshot())
    expect(f.manager.snapshot().utterances[0].scope).toEqual(event.scope)
    expect(f.socket.sent.find(item => item.type === 'playback_started')?.identity).toEqual(speechIdentity(event))
  })

  it('rejects a lifecycle event first seen after a post-publication plan change', async () => {
    const f = new Fixture(); await f.connect(); f.tick({ phase: 'finalizing-set' })
    const event = f.lifecycle('old-result', 'set_persisted', 'finalizing-set')
    f.tick({ session: session({ exercises: [{ ...session().exercises[0], plan: [plan(12)] }] }) })
    f.refs[event.id] = { backendSetId: 7 }; f.tick({ lifecycle: [event] })
    expect(f.socket.events().some(item => item.event.id === event.id)).toBe(false)
    f.speech('late-result', event); expect(f.manager.snapshot().pending).toBe(0)
  })

  it('invalidates on server run closure and explicit client disposal', async () => {
    for (const dispose of [false, true]) {
      const f = new Fixture(); await f.connect(); const event = f.socket.events()[0].event; f.speech()
      if (dispose) f.client.dispose(); else f.socket.push({ type: 'error', reason: 'run_closed' })
      if (!dispose) {
        const count = f.socket.events().length
        f.tick({ phase: 'active-set', reps: 1 })
        expect(f.socket.events()).toHaveLength(count)
        expect(f.client.getSnapshot().state).toBe('retrying')
      }
      f.speech('late', event); f.socket.push(frame('g1', 0, .3, true))
      expect(f.manager.snapshot().pending).toBe(0)
      expect(f.socket.types()).not.toContain('playback_started')
    }
  })

  it('does not report an interrupted final stream as completed', async () => {
    const f = new Fixture(); await f.connect(); f.speech(); f.socket.push(frame('g1', 0, .5, true))
    f.clock.advance(50, f.context); f.client.observe(f.manager.snapshot())
    f.manager.cancelStream('g1', 'mute'); f.client.observe(f.manager.snapshot())
    expect(f.socket.sent.filter(item => item.type === 'playback_completed')).toHaveLength(0)
    expect(f.socket.sent.filter(item => item.type === 'playback_failed')).toHaveLength(1)
  })

  it('rejects unknown, absent and field-by-field mismatched identities without consuming the real event', async () => {
    const f = new Fixture(); await f.connect(); const event = f.socket.events()[0].event
    const identity = speechIdentity(event)
    const mismatches = [null, { ...identity, eventId: 'unknown' }, { ...identity, scope: scope({ setOrdinal: 2 }) },
      { ...identity, planRevision: 999 }, { ...identity, contextVersion: 999 }, { ...identity, createdAtMs: 0 },
      { ...identity, startDeadlineMs: 999999 }, { ...identity, factDependencies: ['invented'] }, { ...identity, schemaVersion: 2 }]
    for (const bad of mismatches) f.speech('bad', event, { identity: bad })
    f.speech('bad-event-id', event, { eventId: 'unknown' })
    expect(f.manager.snapshot().utterances).toHaveLength(0)
    f.speech('valid', event)
    expect(f.manager.snapshot().pending).toBe(1)
  })

  it.each(['wrong scope', 'reorder', 'wrong utterance'])('fails %s frames without scope rebinding or a start ACK', async kind => {
    const f = new Fixture(); await f.connect(); f.speech()
    if (kind === 'wrong utterance') {
      const pcm = new Uint8Array(4800)
      f.socket.push(encodeCoachFrame({ schemaVersion: 1, utteranceId: 'other', generationId: 'g1', scope: scope(), sequence: 0,
        source: 'realtime', codec: 'pcm_s16le', sampleRate: RATE, channels: 1, byteLength: pcm.length, durationMs: 300, final: true }, pcm))
    } else f.socket.push(frame('g1', kind === 'reorder' ? 1 : 0, .3, true, kind === 'wrong scope' ? scope({ scopeEpoch: 1 }) : scope()))
    f.socket.push(frame('g1', 0, .3, true))
    f.clock.advance(50, f.context); f.client.observe(f.manager.snapshot())
    expect(f.manager.snapshot().utterances).toHaveLength(0)
    expect(f.socket.sent.filter(item => item.type === 'playback_started')).toHaveLength(0)
    expect(f.socket.sent.filter(item => item.type === 'playback_failed')).toHaveLength(1)
  })

  it('ignores PCM/end before speech_start and duplicate speech/observations/ends without duplicate ACK effects', async () => {
    const f = new Fixture(); await f.connect()
    f.socket.push(frame('g1', 0, .3, true)); f.socket.push({ type: 'speech_end', generationId: 'g1', status: 'complete' })
    f.client.observe(f.manager.snapshot()); expect(f.socket.types()).not.toContain('playback_completed')
    f.speech(); f.speech(); f.socket.push(frame('g1', 0, .3, true)); f.clock.advance(50, f.context)
    for (let i = 0; i < 3; i++) f.client.observe(f.manager.snapshot())
    for (const source of f.context.sources) source.end()
    for (let i = 0; i < 3; i++) { f.client.observe(f.manager.snapshot()); f.speech(); f.socket.push({ type: 'speech_end', generationId: 'g1', status: 'complete' }) }
    expect(f.socket.sent.filter(item => item.type === 'playback_started')).toHaveLength(1)
    expect(f.socket.sent.filter(item => item.type === 'playback_completed')).toHaveLength(1)
    expect(f.client.getSnapshot().spoken).toBe(1)
  })

  it('uses the original browser deadline, never server clocks or receipt + validForMs', async () => {
    const f = new Fixture(); await f.connect(); const event = f.socket.events()[0].event
    f.tick({ nowMs: event.startDeadlineMs - 10 })
    f.speech('ttl', event, { validForMs: 999999999, createdAtMs: -9e12 })
    expect(f.manager.snapshot().pending).toBe(1)
    f.clock.advance(20, f.context)
    f.socket.push(frame('ttl', 0, .3, true)); f.client.observe(f.manager.snapshot())
    expect(f.manager.snapshot().utterances).toHaveLength(0)
    expect(f.socket.types()).not.toContain('playback_started')
    f.speech('ttl-retry', event)
    expect(f.manager.snapshot().utterances).toHaveLength(0)
  })

  it('rejects expired speech_start before the next tick and does not resurrect on reconnect', async () => {
    const f = new Fixture(); await f.connect(); const event = f.socket.events()[0].event
    f.clock.advance(20_001, f.context); f.speech('expired', event, { validForMs: 60_000 })
    expect(f.manager.snapshot().pending).toBe(0)
    f.socket.serverClose(); f.timers.shift()!()
    await vi.waitFor(() => expect(f.sockets).toHaveLength(2))
    f.socket.open(); f.socket.push({ type: 'configured', mode: 'hybrid', text: true, voice: true })
    f.speech('reconnected', event); expect(f.manager.snapshot().pending).toBe(0)
  })

  it('versions meaningful context and plan changes, not telemetry/progress or identical ticks', async () => {
    const f = new Fixture(); await f.connect()
    const first = f.socket.events()[0].event
    expect(first.planRevision).toBeGreaterThan(0); expect(first.contextVersion).toBeGreaterThan(0)
    const count = f.socket.sent.filter(item => item.type === 'context').length
    f.tick(); f.tick({ reps: 8, session: session({ completedSets: { e1: [{}] }, sessionState: { currentValue: 8 } }) })
    expect(f.socket.sent.filter(item => item.type === 'context')).toHaveLength(count)
    f.tick({ phase: 'active-set', reps: 1 })
    const active = f.socket.sent.filter(item => item.type === 'context').at(-1)!
    expect(active.planRevision).toBe(first.planRevision); expect(active.contextVersion).toBeGreaterThan(first.contextVersion)
    const changed = session(); changed.exercises[0].plan[0].recommendedWeightKg = 12
    f.tick({ session: changed })
    const revision = f.socket.sent.filter(item => item.type === 'context').at(-1)!
    expect(revision.planRevision).toBeGreaterThan(first.planRevision)
    f.tick({ gate: 'hidden' })
    expect(f.socket.sent.filter(item => item.type === 'context').at(-1)).toMatchObject({ blocked: true })
  })

  it('records bounded browser event-to-PCM/start percentiles and redacts IDs/text', async () => {
    const f = new Fixture(); await f.connect(); const event = f.socket.events()[0].event
    f.clock.advance(200, f.context); f.speech()
    f.clock.advance(100, f.context); f.socket.push(frame('g1', 0, .3, true))
    f.clock.advance(50, f.context); f.client.observe(f.manager.snapshot())
    f.socket.push({ type: 'speech_end', generationId: 'g1', status: 'complete' })
    const snapshot = f.client.getSnapshot()
    expect(snapshot.latencies[`firstAcceptedPcmMs:${unknownGroup()}`]).toEqual({ count: 1, p50: 300, p95: 300 })
    expect(snapshot.latencies[`eventToPlaybackStart:${unknownGroup()}`]).toEqual({ count: 1, p50: 310, p95: 310 })
    expect(snapshot.firstAudioMsLabel).toBe('voice-only')
    expect(redactedNetworkReport(snapshot)).not.toMatch(new RegExp(`${event.id}|g1|u1|run-1|identity|Привет`))
  })

  it('fails closed at 1024 retained sent events without evicting old identity tombstones', async () => {
    const f = new Fixture(); await f.connect(); f.tick({ phase: 'finalizing-set' })
    for (let i = 0; i < 1030; i++) {
      const event = { ...f.lifecycle(`result-${i}`, 'set_persisted', 'finalizing-set'),
        startDeadlineMs: f.input.nowMs + 20_000 }
      f.refs[event.id] = { backendSetId: i + 1 }; f.tick({ lifecycle: [event] })
    }
    expect(f.socket.events()).toHaveLength(1024)
    expect(f.client.getSnapshot().reasons.event_capacity).toBeGreaterThan(0)
  })

  it('bounds each latency group to 128 observations with nearest-rank p50/p95', async () => {
    const f = new Fixture(); await f.connect(); f.tick({ phase: 'finalizing-set' })
    for (let i = 0; i < 140; i++) {
      const event = { ...f.lifecycle(`latency-${i}`, 'set_persisted', 'finalizing-set'),
        startDeadlineMs: f.input.nowMs + 20_000 }
      f.refs[event.id] = { backendSetId: i + 1 }
      f.tick({ nowMs: f.clock.now() + 100, lifecycle: [event] })
      const gid = `audio-${i}`; f.speech(gid, event)
      f.socket.push({ type: 'speech_end', generationId: gid, status: 'complete', timingsMs: { firstPcm: i } })
      f.clock.advance(i, f.context); f.socket.push(frame(gid, 0, .3, true)); f.clock.advance(50, f.context)
      f.client.observe(f.manager.snapshot()); for (const source of f.context.sources) source.end()
      f.client.observe(f.manager.snapshot())
      // Keep input's browser timestamp aligned before constructing the next event.
      f.tick({ nowMs: f.clock.now() })
    }
    expect(f.client.getSnapshot().latencies[`firstAcceptedPcmMs:${unknownGroup('set_persisted')}`]).toEqual({ count: 128, p50: 174, p95: 232 })
    expect(f.client.getSnapshot().latencies[`eventToPlaybackStart:${unknownGroup('set_persisted')}`]).toEqual({ count: 128, p50: 184, p95: 242 })
    expect(f.client.getSnapshot().serverTimings[`firstPcm:${unknownGroup('set_persisted')}`]).toEqual({ count: 128, p50: 75, p95: 133 })
  })
})

describe('classified U01 telemetry', () => {
  it('defers browser samples and keeps server monotonic deltas separate, without duplicate samples', async () => {
    const f = new Fixture(); await f.connect(); f.speech()
    f.clock.advance(200, f.context); f.socket.push(frame('g1', 0, .3, true))
    f.clock.advance(50, f.context); f.client.observe(f.manager.snapshot())
    expect(f.client.getSnapshot()).toMatchObject({ latencies: {}, serverTimings: {}, telemetry: { pendingClassification: 1 } })
    const end = { type: 'speech_end', generationId: 'g1', status: 'complete', ...metadata, firstAudioMs: 40,
      timingsMs: { receive: 0, textStart: 10, textEnd: 80, textDuration: 70, firstPcm: 120, speechEnd: 180,
        ackStart: 190, ackEnd: 200, ackCancel: 210, secret: 123, absoluteClock: 99999 } }
    f.socket.push(end); f.socket.push(end)
    const s = f.client.getSnapshot(), group = knownGroup()
    expect(s.latencies[`eventToSend:${group}`]).toEqual({ count: 1, p50: 0, p95: 0 })
    expect(s.latencies[`firstAcceptedPcmMs:${group}`]).toEqual({ count: 1, p50: 200, p95: 200 })
    expect(s.latencies[`eventToPlaybackStart:${group}`]).toEqual({ count: 1, p50: 210, p95: 210 })
    expect(s.serverTimings[`textDuration:${group}`]).toEqual({ count: 1, p50: 70, p95: 70 })
    expect(Object.keys(s.serverTimings)).toHaveLength(9)
    expect(s.telemetry).toEqual({ classified: 1, missingClassification: 0, pendingClassification: 0, retained: 0 })
    expect(s.firstAudioMs).toBe(40)
    for (const source of f.context.sources) source.end()
    f.client.observe(f.manager.snapshot()); f.client.observe(f.manager.snapshot())
    expect(f.client.getSnapshot().latencies[`eventToCompleted:${group}`]?.count).toBe(1)
  })

  it('classifies naturally finished audio from late metadata without losing samples or restarting speech', async () => {
    const f = new Fixture(); await f.connect(); const event = f.socket.events()[0].event; f.speech()
    f.clock.advance(200, f.context); f.socket.push(frame('g1', 0, .3, true))
    f.clock.advance(50, f.context); f.client.observe(f.manager.snapshot())
    for (const source of f.context.sources) source.end()
    f.client.observe(f.manager.snapshot())
    expect(f.client.getSnapshot()).toMatchObject({ spoken: 1, failed: 0, latencies: {}, telemetry: { retained: 1 } })
    f.socket.push({ type: 'speech_end', generationId: 'g1', status: 'complete', ...metadata, connectionClass: 'cold', timingsMs: { speechEnd: 1234 } })
    const before = f.client.getSnapshot()
    expect(before.latencies[`eventToCompleted:${knownGroup('workout_started', 'cold')}`]).toEqual({ count: 1, p50: 250, p95: 250 })
    expect(before.telemetry.retained).toBe(0)
    f.speech('g1', event); f.socket.push(frame('g1', 1, .3, true)); f.client.observe(f.manager.snapshot())
    expect(f.manager.snapshot().active).toBe(0)
    expect(f.client.getSnapshot().spoken).toBe(1)
    expect(f.socket.sent.filter(item => item.type === 'playback_started')).toHaveLength(1)
  })

  it.each(['cold', 'warm', 'unknown', 'not-applicable', 'fake'])('keeps the authoritative %s connection class', async connectionClass => {
    const f = new Fixture(); await f.connect(); f.speech()
    f.socket.push({ type: 'speech_end', generationId: 'g1', status: 'complete', ...metadata, connectionClass })
    expect(f.client.getSnapshot().latencies[`eventToSend:${knownGroup('workout_started', connectionClass)}`]?.count).toBe(1)
    expect(f.client.getSnapshot().telemetry.missingClassification).toBe(connectionClass === 'unknown' ? 1 : 0)
  })

  it('does not infer cold/warm from arrival times and rejects private models, unknown stages and invalid durations', async () => {
    const f = new Fixture(); await f.connect(); f.speech()
    f.socket.push({ type: 'speech_end', generationId: 'g1', status: 'complete', source: 'realtime',
      voiceModel: 'gpt-realtime-secret-user@example.com', textModel: 'gpt-6-luna-secret-token', connectionClass: 'private-user',
      apiKey: 'secret-api-key', userId: 'private-user', text: 'private-text', firstAudioMs: -1,
      timingsMs: { receive: 0, textStart: -1, textEnd: '80', firstPcm: 86_400_001, speechEnd: null, apiKey: 12, textDuration: 7.25 } })
    const s = f.client.getSnapshot()
    expect(s.firstAudioMs).toBeNull()
    expect(Object.keys(s.serverTimings)).toHaveLength(2)
    expect(s.telemetry.missingClassification).toBe(1)
    expect(redactedNetworkReport(s)).not.toMatch(/secret|private|example|apiKey|userId/)
    expect(Object.keys(s.latencies)[0]).toContain('voiceModel=unknown:textModel=unknown:connection=unknown')
  })

  it('rejects a public voice model assigned to the wrong source', async () => {
    const f = new Fixture(); await f.connect(); f.speech('g1', undefined, { source: 'tts' })
    f.socket.push({ type: 'speech_end', generationId: 'g1', status: 'complete', ...metadata, source: 'tts' })
    expect(Object.keys(f.client.getSnapshot().latencies)[0]).toContain('tts:voiceModel=unknown:')
  })

  it('redacts arbitrary server reason/action/configuration strings as well as metadata secrets', async () => {
    const f = new Fixture(); await f.connect({ mode: 'secret-mode', voiceId: 'private-voice' })
    f.socket.push({ type: 'decision', reason: 'secret-user-id', action: 'private-token', text: 'private-text' })
    f.socket.push({ type: 'error', reason: 'secret-api-key' })
    const report = redactedNetworkReport(f.client.getSnapshot())
    expect(report).not.toMatch(/secret|private/)
    expect(JSON.parse(report)).toMatchObject({ mode: null, voiceId: null, reason: 'other', reasons: { other: 2 } })
  })

  it('retains only 32 terminal records, flushes evictions as unknown once and ignores late evicted metadata', async () => {
    const f = new Fixture(); await f.connect(); f.tick({ phase: 'finalizing-set' })
    for (let i = 0; i < 35; i++) {
      const event = { ...f.lifecycle(`bounded-${i}`, 'set_persisted', 'finalizing-set'), startDeadlineMs: f.input.nowMs + 20_000 }
      f.refs[event.id] = { backendSetId: i + 1 }; f.tick({ lifecycle: [event] }); f.speech(`bounded-${i}`, event)
      f.socket.push(frame(`bounded-${i}`, 0, .3, true)); f.clock.advance(50, f.context)
      f.client.observe(f.manager.snapshot()); for (const source of f.context.sources) source.end()
      f.client.observe(f.manager.snapshot()); f.tick({ nowMs: f.clock.now() })
    }
    const s = f.client.getSnapshot()
    expect(s.telemetry).toMatchObject({ retained: 32, missingClassification: 4 }) // opening event invalidated + 3 evictions
    const key = 'eventToCompleted:set_persisted:realtime:voiceModel=unknown:textModel=unknown:connection=unknown'
    expect(s.latencies[key]?.count).toBe(3)
    f.socket.push({ type: 'speech_end', generationId: 'bounded-0', status: 'complete', ...metadata })
    expect(f.client.getSnapshot()).toBe(s)
    f.socket.serverClose()
    expect(f.client.getSnapshot().telemetry).toMatchObject({ retained: 0, pendingClassification: 0 })
    expect(f.client.getSnapshot().latencies[key]?.count).toBe(35)
  })

  it('retains cancellation timing until classification and counts the failure only once', async () => {
    const f = new Fixture(); await f.connect(); f.speech()
    f.clock.advance(100, f.context); f.tick({ gate: 'mute', nowMs: f.clock.now() })
    expect(f.client.getSnapshot()).toMatchObject({ failed: 1, latencies: {}, telemetry: { retained: 1 } })
    f.socket.push({ type: 'speech_end', generationId: 'g1', status: 'cancelled', ...metadata, timingsMs: { ackCancel: 90 } })
    f.client.observe(f.manager.snapshot())
    const s = f.client.getSnapshot()
    expect(s.failed).toBe(1)
    expect(s.latencies[`eventToFailed:${knownGroup()}`]?.count).toBe(1)
    expect(s.serverTimings[`ackCancel:${knownGroup()}`]?.p95).toBe(90)
  })
})

describe('setup rejection report', () => {
  it.each(['insufficient_facts', 'provider_incomplete', 'usage_unsettled', 'cooldown', 'density_cap',
    'topic_repeat', 'no_window', 'validation_failed:unreviewed_tip', 'validation_failed:length'])('preserves the safe %s cause instead of other', async reason => {
    const f = new Fixture(); await f.connect()
    const sent = f.socket.events()[0]
    f.socket.push({ type: 'decision', eventId: sent.event.id, triggerId: 'T01', action: 'silence', reason })
    const report = JSON.parse(redactedNetworkReport(f.client.getSnapshot()))
    expect(report.decisions).toContainEqual({ action: 'silence', reason })
    expect(report.reasons[reason.split(':')[0]]).toBe(1)
    expect(report.opportunities.rejected).toBe(1)
    f.client.dispose(); f.manager.dispose()
  })

  it('does not export arbitrary validation suffixes or identifiers', async () => {
    const f = new Fixture(); await f.connect()
    f.socket.push({ type: 'decision', eventId: f.socket.events()[0].event.id, triggerId: 'T01',
      action: 'silence', reason: 'validation_failed:private-provider-payload' })
    const report = redactedNetworkReport(f.client.getSnapshot())
    expect(JSON.parse(report).decisions).toContainEqual({ action: 'silence', reason: 'other' })
    expect(report).not.toContain('private-provider-payload')
    expect(report).not.toContain('secret-1')
    f.client.dispose(); f.manager.dispose()
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

describe('CoachNetworkClient scenarios (V1)', () => {
  const cards = [{ archetype: 'race', title: 'Гонка героев', tagline: 'Заезд за заездом', tone: 'дерзко' },
    { archetype: 'rpg', title: 'Боссфайт', tagline: 'Победи босса', tone: 'эпично' },
    { archetype: 'space', title: 'Орбита', tagline: 'Старт к звёздам', tone: 'торжественно' }]

  it('holds the opening until a story is chosen, proposes the plan and opens with the chosen one', async () => {
    const f = new Fixture()
    f.input = { ...f.input, saved: { ...saved, scenarioPicker: true } }
    await f.connect()
    f.socket.push({ type: 'scenario', state: 'none' })
    f.tick()
    const propose = f.socket.sent.find(item => item.type === 'scenario_propose') as { plan: Array<Record<string, unknown>> }
    expect(propose.plan).toEqual([{ id: 'e1', name: 'Жим ногами', sets: 2, kind: 'machine' }, { id: 'e2', name: 'Тяга', sets: 1, kind: 'machine' }])
    expect(f.socket.events()).toHaveLength(0)
    expect(f.client.getSnapshot().scenario?.phase).toBe('proposing')
    f.socket.push({ type: 'scenarios', cards, proposalsLeft: 3 })
    expect(f.client.getSnapshot().scenario).toMatchObject({ phase: 'choosing', proposalsLeft: 3 })
    f.client.selectScenario(1)
    expect(f.socket.sent.at(-1)).toEqual({ type: 'scenario_select', index: 1 })
    f.tick()
    expect(f.socket.events()).toHaveLength(0)
    f.socket.push({ type: 'scenario', state: 'ready', title: 'Боссфайт', tagline: 'Победи босса', archetype: 'rpg',
      acts: [{ act: 1, title: 'Подземелье', exerciseIds: ['e1'] }, { act: 2, title: 'Босс', exerciseIds: ['e2'] }],
      counters: [{ id: 'c1', label: 'урон боссу' }], coHost: { role: 'летописец', name: 'Борис' } })
    f.tick()
    expect(f.client.getSnapshot().scenario).toMatchObject({ phase: 'ready', title: 'Боссфайт', coHost: { name: 'Борис' } })
    expect(f.socket.events().map(item => item.event.kind)).toEqual(['workout_started'])
  })

  it('skipping or a timeout releases the opening without a story', async () => {
    const f = new Fixture()
    f.input = { ...f.input, saved: { ...saved, scenarioPicker: true } }
    await f.connect()
    f.socket.push({ type: 'scenario', state: 'none' })
    f.tick()
    f.socket.push({ type: 'scenarios', error: 'budget' })
    expect(f.client.getSnapshot().scenario).toMatchObject({ phase: 'failed', error: 'budget' })
    f.client.skipScenario()
    expect(f.socket.sent.some(item => item.type === 'scenario_skip')).toBe(true)
    expect(f.socket.events().map(item => item.event.kind)).toEqual(['workout_started'])

    const g = new Fixture()
    g.input = { ...g.input, saved: { ...saved, scenarioPicker: true } }
    await g.connect()
    g.socket.push({ type: 'scenario', state: 'none' })
    g.tick()
    g.tick({ nowMs: g.input.nowMs + 160_000 })
    expect(g.client.getSnapshot().scenario?.phase).toBe('skipped')
    g.tick()
    expect(g.socket.events().map(item => item.event.kind)).toEqual(['workout_started'])
  })

  it('restores a chosen story after reconnecting and never offers one with the switch off', async () => {
    const f = new Fixture()
    f.input = { ...f.input, saved: { ...saved, scenarioPicker: true } }
    await f.connect()
    f.socket.push({ type: 'scenario', state: 'ready', title: 'Гонка героев', archetype: 'race', acts: [], counters: [] })
    f.tick()
    expect(f.socket.sent.some(item => item.type === 'scenario_propose')).toBe(false)
    expect(f.socket.events().map(item => item.event.kind)).toEqual(['workout_started'])
    const off = new Fixture()
    await off.connect()
    off.socket.push({ type: 'scenario', state: 'none' })
    off.tick()
    expect(off.socket.sent.some(item => item.type === 'scenario_propose')).toBe(false)
    expect(off.socket.events().map(item => item.event.kind)).toEqual(['workout_started'])
  })
})
