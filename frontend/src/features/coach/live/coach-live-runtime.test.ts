import { afterEach, describe, expect, it } from 'vitest'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import type { HardwareSnapshot } from '@/features/hardware/model/types'
import { FakeClock, FakeContext } from '../audio/audio-test-fakes'
import { LocalCoachAudioManager } from '../audio/local-coach-audio-manager'
import { createTestClipBuffer } from '../audio/test-clips'
import { REQUIRED_LOCAL_CLIPS } from '../interpreter/local-cues'
import type { CoachEvent } from '../model/contracts'
import { DEFAULT_COACH_PREFERENCES, type CoachPreferences } from '../model/preferences'
import { CoachLiveRuntime, type LiveInputs, type LiveRuntimeDependencies } from './coach-live-runtime'
import type { NetworkTick } from './coach-network-client'
import { RepBeepArbiter, type ClipSource } from './local-cue-player'

const saved: CoachPreferences = { ...DEFAULT_COACH_PREFERENCES, enabled: true, consentVersion: 1, count: 'every' }
const exercise = (id: string, sets = 2) => ({ id, kind: 'machine', plan: Array.from({ length: sets }, () => ({ targetReps: 3, restSeconds: 30, weightLabel: '' })) })
const session = () => ({ id: 's', runId: 'run-1', dataSource: 'backend', view: 'exercise-setup', currentExerciseId: 'e1', currentSetIndex: 0,
  exercises: [exercise('e1'), exercise('e2', 1)], completedSets: {} }) as unknown as RuntimeWorkoutSession

class Fixture {
  readonly clock = new FakeClock()
  readonly context = new FakeContext()
  readonly beep = new RepBeepArbiter(() => this.clock.now())
  inputs: LiveInputs
  lifecycle: CoachEvent[] = []
  managers: LocalCoachAudioManager[] = []
  available = new Set<string>(REQUIRED_LOCAL_CLIPS)
  private listener: (() => void) | null = null
  private emitted = 0
  readonly runtime: CoachLiveRuntime

  constructor(network: LiveRuntimeDependencies['network'] = null) {
    this.clock.time = 1000
    this.inputs = { userId: 'u1', featureEnabled: true, hidden: false, emergency: false, session: session(), hardware: null, connected: true,
      general: { soundEnabled: true, voiceHintsEnabled: true, volume: 0.7 }, saved }
    const buffer = createTestClipBuffer(this.context.asAudioContext())
    const clips: ClipSource = { get: id => this.available.has(id) ? buffer : null }
    this.runtime = new CoachLiveRuntime({
      read: () => this.inputs, subscribeInputs: listener => { this.listener = listener; return () => { this.listener = null } },
      lifecycle: () => this.lifecycle, context: () => this.context.asAudioContext(),
      createManager: (context, scope) => {
        const manager = new LocalCoachAudioManager({ context, scope, clock: this.clock }); this.managers.push(manager); return manager
      },
      clips: () => clips, beep: this.beep, now: () => this.clock.now(),
      setInterval: () => 1, clearInterval: () => undefined, allowEmulator: false, network,
    })
  }

  change(patch: Partial<LiveInputs>) { this.inputs = { ...this.inputs, ...patch }; this.clock.advance(100, this.context); this.listener?.() }
  view(view: string, patch: Record<string, unknown> = {}) { this.change({ session: { ...this.inputs.session!, view, ...patch } as RuntimeWorkoutSession }) }
  hw(mode: string, reps: number) {
    this.emitted += 100
    this.change({ hardware: { emittedAt: new Date(1_700_000_000_000 + this.emitted).toISOString(), serviceMode: false, emulatorMode: false,
      selectedUserId: 'u1', safety: { state: 'enabled' }, panel: { stopLatched: false }, motion: { repetitionCount: reps, controlMode: mode },
      control: { mode, spotterActive: false, failureDetected: false, faultCode: null } } as unknown as HardwareSnapshot })
  }
  get started() { return this.managers.reduce((sum, manager) => sum + manager.snapshot().counters.started, 0) }
}

const fixtures: Fixture[] = []
const make = () => { const f = new Fixture(); fixtures.push(f); f.runtime.start(); return f }
afterEach(() => { fixtures.splice(0).forEach(f => f.runtime.dispose()) })

describe('CoachLiveRuntime', () => {
  it('replays a whole workout through the local mixer with TEST clips', () => {
    const f = make()
    f.view('exercise-setup'); f.view('exercise-session'); f.hw('start_hold', 0); f.hw('training', 0)
    for (const rep of [1, 2, 3]) f.hw('training', rep)
    f.lifecycle = [{ schemaVersion: 1, id: 'l1', kind: 'set_stopped', phase: 'active-set', source: 'user_input', exerciseKind: 'machine',
      controlMode: null, progressUnit: 'reps', ordinal: 0, planRevision: 0, contextVersion: 0, createdAtMs: f.clock.now(), startDeadlineMs: 0,
      factDependencies: [], scope: { schemaVersion: 1, userId: 'u1', runId: 'run-1', exerciseId: 'e1', setOrdinal: 1, scopeEpoch: 1 },
      facts: [{ schemaVersion: 1, id: 'result.outcome', value: 'completed', unit: 'text', source: 'user_input', confidence: 'confirmed',
        observedAtMs: 0, validUntilMs: 0, scopeEpoch: 1 }] } as unknown as CoachEvent]
    f.view('rest', { restState: { mode: 'between-sets', totalSeconds: 30, remainingSeconds: 30, timerPaused: false } })
    for (let left = 29; left >= 0; left--) f.view('rest', { restState: { mode: 'between-sets', totalSeconds: 30, remainingSeconds: left, timerPaused: false } })
    f.clock.advance(2000, f.context)
    const snapshot = f.runtime.getSnapshot()
    // start, count 1..3, set-end, last-set-next, rest-ten, rest-ready
    expect(snapshot.counters.cues).toBe(8)
    expect(snapshot.counters.admitted).toBe(8)
    expect(snapshot.counters.missingClip).toBe(0)
    expect(f.started).toBe(8)
    expect(snapshot.interpreter?.phase).toBe('rest')
  })

  it('reports a missing clip and keeps the legacy beep as the fallback', () => {
    const f = make(); f.available.delete('count-2')
    f.view('exercise-setup'); f.view('exercise-session'); f.hw('start_hold', 0); f.hw('training', 0)
    f.hw('training', 1)
    expect(f.beep.shouldPlayLegacyBeep(1)).toBe(false)
    f.hw('training', 2)
    expect(f.runtime.getSnapshot().lastCue).toMatchObject({ clipId: 'count-2', reason: 'missing_clip' })
    expect(f.beep.shouldPlayLegacyBeep(2)).toBe(true)
    expect(f.runtime.getSnapshot().counters.missingClip).toBe(1)
  })

  it('keeps interpreting while muted and never replays on unmute', () => {
    const f = make()
    f.change({ general: { ...f.inputs.general, soundEnabled: false } })
    f.view('exercise-setup'); f.view('exercise-session'); f.hw('start_hold', 0); f.hw('training', 0); f.hw('training', 1)
    expect(f.runtime.getSnapshot().counters).toMatchObject({ cues: 2, admitted: 0, suppressed: 2 })
    expect(f.runtime.getSnapshot().reason).toBe('mute')
    f.change({ general: { ...f.inputs.general, soundEnabled: true } })
    f.hw('training', 2)
    expect(f.runtime.getSnapshot().counters).toMatchObject({ cues: 3, admitted: 1 })
  })

  it.each([
    ['no consent', { saved: { ...saved, consentVersion: null } }, 'no_consent'],
    ['disabled', { saved: { ...saved, enabled: false } }, 'disabled'],
    ['hidden', { hidden: true }, 'hidden'],
  ] as const)('%s gates audio', (_name, patch, reason) => {
    const f = make(); f.change(patch as Partial<LiveInputs>)
    f.view('exercise-setup'); f.view('exercise-session'); f.hw('start_hold', 0); f.hw('training', 0)
    expect(f.runtime.getSnapshot().counters.admitted).toBe(0)
    expect(f.runtime.getSnapshot().reason).toBe(reason)
  })

  it('a suspended context reports audio_locked and creates no manager', () => {
    const f = make(); f.context.setState('suspended')
    f.view('exercise-setup'); f.view('exercise-session'); f.hw('start_hold', 0); f.hw('training', 0)
    expect(f.managers).toHaveLength(0)
    expect(f.runtime.getSnapshot().reason).toBe('audio_locked')
  })

  it('emergency cancels ordinary speech and plays the safety cue', () => {
    const f = make()
    f.view('exercise-setup'); f.view('exercise-session'); f.hw('start_hold', 0); f.hw('training', 0)
    expect(f.managers[0].snapshot().pending + f.managers[0].snapshot().active).toBeGreaterThan(0)
    f.change({ emergency: true })
    expect(f.runtime.getSnapshot().lastCue).toMatchObject({ kind: 'safety-stop', reason: 'admitted' })
    expect(f.managers[0].snapshot().utterances.every(item => item.id === f.managers[0].snapshot().utterances.at(-1)!.id)).toBe(true)
  })

  it('passes interpreter state to the network port and shares the mixer', () => {
    const ticks: NetworkTick[] = []
    const observed: unknown[] = []
    const network = { tick: (input: NetworkTick) => { ticks.push(input) }, observe: (audio: unknown) => { observed.push(audio) },
      dispose: () => undefined, subscribe: () => () => undefined, getSnapshot: () => null as never }
    const f = new Fixture(network); fixtures.push(f); f.runtime.start()
    f.view('exercise-setup'); f.view('exercise-session'); f.hw('start_hold', 0); f.hw('training', 0); f.hw('training', 2)
    const last = ticks.at(-1)!
    expect(last).toMatchObject({ featureEnabled: true, phase: 'active-set', reps: 2, latched: false, gate: null, userId: 'u1' })
    expect(last.scope).toMatchObject({ runId: 'run-1', exerciseId: 'e1', setOrdinal: 1 })
    expect(last.mixer()).toBe(f.managers[0])
    expect(observed.length).toBeGreaterThan(0)
    f.change({ featureEnabled: false })
    expect(ticks.at(-1)).toMatchObject({ featureEnabled: false })
  })

  it('does nothing when the feature flag is off', () => {
    const f = make(); f.change({ featureEnabled: false })
    f.view('exercise-setup'); f.view('exercise-session'); f.hw('start_hold', 0); f.hw('training', 0)
    expect(f.runtime.getSnapshot()).toMatchObject({ active: false, reason: 'disabled' })
    expect(f.runtime.getSnapshot().counters.cues).toBe(0)
  })
})

describe('coach static boundaries', () => {
  it('coach sources never import motor/hardware command APIs', () => {
    const sources = import.meta.glob(['../**/*.ts', '../**/*.tsx', '!../**/*.test.ts', '!../**/*.test.tsx'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>
    expect(Object.keys(sources).length).toBeGreaterThan(10)
    for (const [path, text] of Object.entries(sources)) {
      expect(text, path).not.toMatch(/hardwareApi|hardware-api|runCommand|runHardwareCommand|sendCommand|\/hardware\/commands/)
    }
  })
})
