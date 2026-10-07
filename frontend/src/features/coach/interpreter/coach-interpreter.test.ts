import { describe, expect, it } from 'vitest'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import type { HardwareSnapshot } from '@/features/hardware/model/types'
import type { CoachEvent } from '../model/contracts'
import { CoachInterpreter, exactRepTarget, type CountMode, type InterpreterOptions, type InterpreterResult } from './coach-interpreter'
import { CUE_SPECS, REQUIRED_LOCAL_CLIPS, cueClipId } from './local-cues'

type Plan = { targetReps?: number; targetMinReps?: number; targetMaxReps?: number; targetSeconds?: number; setType?: string; restSeconds?: number }
const exercise = (id: string, kind = 'machine', plan: Plan[] = [{ targetReps: 10 }, { targetReps: 10 }, { targetReps: 10 }]) =>
  ({ id, kind, plan: plan.map(item => ({ restSeconds: 60, weightLabel: '', ...item })) })
const baseSession = (exercises = [exercise('e1'), exercise('e2')]) => ({
  id: 'session-1', runId: 'run-1', dataSource: 'backend', view: 'exercise-setup', currentExerciseId: exercises[0].id,
  currentSetIndex: 0, exercises, completedSets: {}, restState: undefined,
}) as unknown as RuntimeWorkoutSession

class Harness {
  readonly interpreter: CoachInterpreter
  now = 1_000
  session: RuntimeWorkoutSession
  hardware: HardwareSnapshot | null = null
  receivedAt: number | null = null
  count: CountMode = 'every'
  emergency = false
  userId: string | null = 'u1'
  lifecycle: CoachEvent[] = []
  connected: boolean | undefined = undefined
  private emitted = 0

  constructor(options: InterpreterOptions = {}, session = baseSession()) {
    this.interpreter = new CoachInterpreter(options); this.session = session
  }

  step(advance = 100): InterpreterResult {
    this.now += advance
    return this.interpreter.step({ nowMs: this.now, userId: this.userId, session: this.session, hardware: this.hardware,
      hardwareReceivedAtMs: this.receivedAt, emergency: this.emergency, count: this.count, lifecycle: this.lifecycle,
      sourceConnected: this.connected })
  }

  hw(mode: string | null, reps: number, extra: { elapsed?: number; patch?: Record<string, unknown> } = {}): InterpreterResult {
    this.now += 100
    this.emitted += 100
    this.hardware = {
      emittedAt: new Date(1_700_000_000_000 + this.emitted).toISOString(), serviceMode: false, emulatorMode: false,
      selectedUserId: 'u1', safety: { state: 'enabled', requiresService: false }, machine: { safety: 'enabled', machineState: 'ready' },
      panel: { stopLatched: false }, motion: { repetitionCount: reps, controlMode: mode, moving: false },
      control: { mode, spotterActive: false, failureDetected: false, faultCode: null, isometricElapsedS: extra.elapsed },
      ...extra.patch,
    } as unknown as HardwareSnapshot
    this.receivedAt = this.now
    return this.step(0)
  }

  view(view: string, patch: Record<string, unknown> = {}): InterpreterResult {
    this.session = { ...this.session, view, ...patch } as RuntimeWorkoutSession
    return this.step()
  }

  enterSet(): InterpreterResult[] {
    return [this.view('exercise-setup'), this.view('exercise-session'), this.hw('start_hold', 0), this.hw('training', 0)]
  }

  reps(from: number, to: number): string[] {
    const out: string[] = []
    for (let rep = from; rep <= to; rep++) out.push(...kinds(this.hw('training', rep)))
    return out
  }
}
const kinds = (result: InterpreterResult) => result.cues.map(cue => cue.value === null ? cue.kind : `${cue.kind}:${cue.value}`)
const all = (results: InterpreterResult[]) => results.flatMap(kinds)
const skipsOf = (results: InterpreterResult[]) => results.flatMap(result => result.skips.map(item => `${item.triggerId}:${item.reason}`))
const lifecycleEvent = (id: string, kind: CoachEvent['kind'], createdAtMs: number, outcome: string | null, setOrdinal: number | null = 1,
  exerciseId = 'e1') => ({
  schemaVersion: 1, id, kind, phase: 'active-set', source: 'user_input', exerciseKind: 'machine', controlMode: null, progressUnit: 'reps',
  scope: { schemaVersion: 1, userId: 'u1', runId: 'run-1', exerciseId, setOrdinal, scopeEpoch: 1 },
  ordinal: 0, planRevision: 0, contextVersion: 0, createdAtMs, startDeadlineMs: createdAtMs + 20_000, factDependencies: [],
  facts: outcome ? [{ schemaVersion: 1, id: 'result.outcome', value: outcome, unit: 'text', source: 'user_input', confidence: 'confirmed',
    observedAtMs: createdAtMs, validUntilMs: createdAtMs + 1000, scopeEpoch: 1 }] : [],
}) as unknown as CoachEvent

describe('local cue catalog', () => {
  it('maps every cue to a stable clip id and lists required clips', () => {
    expect(cueClipId('count', 7)).toBe('count-7')
    expect(cueClipId('count', 101)).toBeNull()
    expect(cueClipId('countdown', 2)).toBe('countdown-2')
    expect(cueClipId('set-end', null)).toBe('set-end')
    expect(REQUIRED_LOCAL_CLIPS).toContain('count-30')
    expect(REQUIRED_LOCAL_CLIPS).not.toContain('count-31')
    expect(new Set(REQUIRED_LOCAL_CLIPS).size).toBe(REQUIRED_LOCAL_CLIPS.length)
    expect(CUE_SPECS['safety-stop'].priority).toBe('safety')
  })

  it('has exact targets only for exact non-failure plans', () => {
    expect(exactRepTarget({ targetReps: 10, restSeconds: 0, weightLabel: '' })).toBe(10)
    expect(exactRepTarget({ targetMinReps: 8, targetMaxReps: 12, restSeconds: 0, weightLabel: '' })).toBeNull()
    expect(exactRepTarget({ targetMinReps: 8, targetMaxReps: 8, restSeconds: 0, weightLabel: '' })).toBe(8)
    expect(exactRepTarget({ targetReps: 10, setType: 'failure', restSeconds: 0, weightLabel: '' } as never)).toBeNull()
    expect(exactRepTarget(undefined)).toBeNull()
  })
})

describe('CoachInterpreter machine sets', () => {
  it('emits start once on an observed transition and every count once', () => {
    const h = new Harness()
    expect(all(h.enterSet())).toEqual(['start'])
    expect(h.reps(1, 3)).toEqual(['count:1', 'count:2', 'count:3'])
    expect(kinds(h.hw('training', 3))).toEqual([])
    expect(h.interpreter.snapshot().phase).toBe('active-set')
  })

  it('does not replay start or counts when attached mid-set', () => {
    const h = new Harness()
    h.session = { ...h.session, view: 'exercise-session' } as RuntimeWorkoutSession
    expect(kinds(h.hw('training', 4))).toEqual([])
    expect(h.reps(5, 5)).toEqual(['count:5'])
  })

  it('accepts a counter not reset between sets as baseline', () => {
    const h = new Harness()
    h.view('exercise-setup'); h.view('exercise-session')
    h.hw('start_hold', 10)
    expect(kinds(h.hw('training', 10))).toEqual(['start'])
    expect(kinds(h.hw('training', 0))).toEqual([])
    expect(h.reps(1, 1)).toEqual(['count:1'])
  })

  it('last-three counts only the final three of an exact target plus half', () => {
    const h = new Harness(); h.count = 'last-three'
    h.enterSet()
    expect(h.reps(1, 10)).toEqual(['half', 'count:8', 'count:9', 'count:10'])
  })

  it('last-three skips half for short targets', () => {
    const h = new Harness({}, baseSession([exercise('e1', 'machine', [{ targetReps: 6 }])])); h.count = 'last-three'
    h.enterSet()
    expect(h.reps(1, 6)).toEqual(['count:4', 'count:5', 'count:6'])
  })

  it('milestones emit half, three-left and target', () => {
    const h = new Harness(); h.count = 'milestones'
    h.enterSet()
    expect(h.reps(1, 11)).toEqual(['half', 'three-left', 'target'])
  })

  it('milestones only announce the target for short sets', () => {
    const h = new Harness({}, baseSession([exercise('e1', 'machine', [{ targetReps: 6 }])])); h.count = 'milestones'
    h.enterSet()
    expect(h.reps(1, 6)).toEqual(['target'])
  })

  it('ranges and failure sets never invent a target', () => {
    for (const plan of [{ targetMinReps: 8, targetMaxReps: 12 }, { targetReps: 10, setType: 'failure' }]) {
      const h = new Harness({}, baseSession([exercise('e1', 'machine', [plan])])); h.count = 'last-three'
      h.enterSet()
      const results = [1, 2, 3].map(rep => h.hw('training', rep))
      expect(all(results)).toEqual([])
      expect(skipsOf(results)).toContain('T16:ambiguous_target')
      const every = new Harness({}, baseSession([exercise('e1', 'machine', [plan])]))
      every.enterSet()
      expect(every.reps(1, 2)).toEqual(['count:1', 'count:2'])
      const milestones = new Harness({}, baseSession([exercise('e1', 'machine', [plan])])); milestones.count = 'milestones'
      milestones.enterSet()
      expect(milestones.reps(1, 12)).toEqual([])
    }
  })

  it('count off consumes silently and a later mode change never replays', () => {
    const h = new Harness(); h.count = 'off'
    h.enterSet()
    expect(h.reps(1, 3)).toEqual([])
    h.count = 'every'
    expect(h.reps(3, 4)).toEqual(['count:4'])
  })

  it('a counter jump keeps only the current milestone, never old numbers', () => {
    const h = new Harness(); h.enterSet(); h.reps(1, 2)
    const jump = h.hw('training', 6)
    expect(kinds(jump)).toEqual([])
    expect(skipsOf([jump])).toContain('T14:jump')
    expect(h.reps(7, 7)).toEqual(['count:7'])
    const m = new Harness(); m.count = 'milestones'; m.enterSet(); m.reps(1, 2)
    expect(kinds(m.hw('training', 7))).toEqual(['three-left'])
  })

  it('a counter decrease re-baselines without repeating numbers', () => {
    const h = new Harness(); h.enterSet(); h.reps(1, 3)
    expect(kinds(h.hw('training', 0))).toEqual([])
    expect(h.reps(1, 4)).toEqual(['count:4'])
  })

  it('pause and resume are announced once per episode and pause at most 3 times', () => {
    const h = new Harness(); h.enterSet()
    const out: string[] = []
    for (let i = 0; i < 4; i++) {
      out.push(...kinds(h.hw('paused', 0)), ...kinds(h.hw('paused', 0)), ...kinds(h.hw('training', 0)))
    }
    expect(out).toEqual(['pause', 'resume', 'pause', 'resume', 'pause', 'resume', 'resume'])
    expect(h.interpreter.snapshot().phase).toBe('active-set')
  })

  it('stale telemetry re-baselines; reconnect never bursts old numbers', () => {
    const h = new Harness(); h.enterSet(); h.reps(1, 3)
    const stale = h.step(1500)
    expect(skipsOf([stale])).toContain('T14:stale_source')
    expect(h.interpreter.snapshot().fresh).toBe(false)
    expect(kinds(h.hw('training', 6))).toEqual([])
    expect(h.reps(7, 7)).toEqual(['count:7'])
  })

  it('treats an unchanged snapshot as current while the socket is connected', () => {
    const h = new Harness(); h.connected = true; h.enterSet(); h.reps(1, 1)
    h.step(5000)
    expect(h.interpreter.snapshot().fresh).toBe(true)
    expect(h.reps(2, 2)).toEqual(['count:2'])
    h.connected = false; h.step()
    h.connected = true; h.step()
    expect(h.interpreter.snapshot().fresh).toBe(false)
    expect(kinds(h.hw('training', 5))).toEqual([])
    expect(h.reps(6, 6)).toEqual(['count:6'])
  })

  it('ignores out-of-order telemetry', () => {
    const h = new Harness(); h.enterSet(); h.reps(1, 2)
    const older = { ...h.hardware!, emittedAt: '2000-01-01T00:00:00.000Z', motion: { ...h.hardware!.motion, repetitionCount: 9 } } as HardwareSnapshot
    h.hardware = older; h.receivedAt = h.now + 100
    expect(kinds(h.step())).toEqual([])
    expect(h.reps(3, 3)).toEqual(['count:3'])
  })

  it('isometric holds emit hold-start, half, ten-left and countdown on a running timer only', () => {
    const h = new Harness({}, baseSession([exercise('e1', 'machine', [{ targetSeconds: 30 }])]))
    h.view('exercise-setup'); h.view('exercise-session'); h.hw('start_hold', 0)
    const out = [...kinds(h.hw('isometric', 0, { elapsed: 0 }))]
    for (let s = 1; s <= 30; s++) out.push(...kinds(h.hw('isometric', 0, { elapsed: s })))
    expect(out).toEqual(['hold-start', 'time-half', 'ten-left', 'countdown:3', 'countdown:2', 'countdown:1'])
    const frozen = new Harness({}, baseSession([exercise('e1', 'machine', [{ targetSeconds: 30 }])]))
    frozen.view('exercise-setup'); frozen.view('exercise-session')
    expect(kinds(frozen.hw('isometric', 0, { elapsed: 28 }))).toEqual(['hold-start'])
    expect(kinds(frozen.hw('isometric', 0, { elapsed: 28 }))).toEqual([])
  })
})

describe('CoachInterpreter sources and safety', () => {
  it('stays disabled for mock sessions and without a user', () => {
    const h = new Harness(); h.session = { ...h.session, dataSource: 'mock' } as RuntimeWorkoutSession
    expect(all(h.enterSet())).toEqual([])
    expect(h.interpreter.snapshot().phase).toBe('disabled')
    const n = new Harness(); n.userId = null
    expect(all(n.enterSet())).toEqual([])
  })

  it('rejects emulator, service mode and another owner unless explicitly allowed', () => {
    for (const patch of [{ emulatorMode: true }, { serviceMode: true }, { selectedUserId: 'u2' }]) {
      const h = new Harness()
      h.view('exercise-setup'); h.view('exercise-session')
      const results = [h.hw('training', 0, { patch }), h.hw('training', 1, { patch })]
      expect(all(results)).toEqual([])
      expect(skipsOf(results).some(item => /mock_source|owner_mismatch/.test(item))).toBe(true)
    }
    const allowed = new Harness({ allowEmulator: true })
    allowed.view('exercise-setup'); allowed.view('exercise-session'); allowed.hw('start_hold', 0, { patch: { emulatorMode: true } })
    expect(all([allowed.hw('training', 0, { patch: { emulatorMode: true } }), allowed.hw('training', 1, { patch: { emulatorMode: true } })]))
      .toEqual(['start', 'count:1'])
  })

  it('safety latch emits one safety cue, suspends and never replays progress', () => {
    const h = new Harness(); h.enterSet(); h.reps(1, 2)
    h.emergency = true
    const first = h.step()
    expect(kinds(first)).toEqual(['safety-stop'])
    expect(first.cues[0].priority).toBe('safety')
    expect(first.latched).toBe(true)
    expect(kinds(h.hw('training', 3))).toEqual([])
    expect(h.interpreter.snapshot().phase).toBe('suspended')
    h.emergency = false
    expect(kinds(h.hw('training', 4))).toEqual([])
    expect(h.reps(5, 5)).toEqual(['count:5'])
  })

  it.each([
    { safety: { state: 'emergency_stop', requiresService: false } }, { panel: { stopLatched: true } },
    { machine: { safety: 'enabled', machineState: 'blocked' } },
  ])('hardware latch %j suspends cues', patch => {
    const h = new Harness(); h.enterSet(); h.reps(1, 1)
    const latched = h.hw('training', 2, { patch })
    expect(kinds(latched)).toEqual(['safety-stop'])
    expect(h.interpreter.snapshot().latches.length).toBeGreaterThan(0)
  })

  it('pain stops the exercise and is cleared on the next exercise', () => {
    const h = new Harness(); h.enterSet(); h.reps(1, 1)
    const pain = h.view('exercise-summary', { completedSets: { e1: [{ setNumber: 1, pain: true }] } })
    expect(kinds(pain)).toEqual(['pain-stop'])
    expect(pain.latched).toBe(true)
    expect(kinds(h.view('exercise-summary'))).toEqual([])
    h.session = { ...h.session, currentExerciseId: 'e2' } as RuntimeWorkoutSession
    expect(all(h.enterSet())).toEqual(['start'])
  })
})

describe('CoachInterpreter lifecycle and rest', () => {
  it('maps lifecycle outcomes once and reports expired and delayed saves', () => {
    const h = new Harness(); h.enterSet()
    h.lifecycle = [lifecycleEvent('l1', 'set_stopped', h.now, 'completed')]
    expect(kinds(h.step())).toEqual(['set-end'])
    expect(kinds(h.step())).toEqual([])
    const delayed = h.step(6000)
    expect(skipsOf([delayed])).toContain('T36:save_delayed')
    h.lifecycle = [...h.lifecycle, lifecycleEvent('l2', 'exercise_finalized', h.now - 10_000, 'completed', null)]
    expect(skipsOf([h.step()])).toContain(`${CUE_SPECS['exercise-done'].triggerId}:expired`)
    h.lifecycle = [...h.lifecycle, lifecycleEvent('l3', 'workout_finalized', h.now, 'partial', null)]
    expect(kinds(h.step())).toEqual(['workout-partial'])
  })

  it('a persisted save clears the delay and partial/skipped sets are distinct', () => {
    const h = new Harness(); h.enterSet()
    h.lifecycle = [lifecycleEvent('a', 'set_stopped', h.now, 'partial'), lifecycleEvent('b', 'set_persisted', h.now, null)]
    expect(kinds(h.step())).toEqual(['set-partial'])
    expect(skipsOf([h.step(6000)])).not.toContain('T36:save_delayed')
    const s = new Harness(); s.enterSet()
    s.lifecycle = [lifecycleEvent('c', 'set_stopped', s.now, 'skipped')]
    expect(kinds(s.step())).toEqual(['set-skipped'])
  })

  it('rest marks fire on real crossings only, not paused timers or large edits', () => {
    const h = new Harness(); h.enterSet()
    const rest = (remainingSeconds: number, timerPaused = false) =>
      h.view('rest', { restState: { mode: 'between-sets', totalSeconds: 60, remainingSeconds, timerPaused } })
    expect(kinds(rest(12))).toEqual([])
    expect([11, 10, 9].flatMap(value => kinds(rest(value)))).toEqual(['rest-ten'])
    expect(kinds(rest(1, true))).toEqual([])
    expect(kinds(rest(0, true))).toEqual([])
    const edit = new Harness(); edit.enterSet()
    edit.view('rest', { restState: { mode: 'between-sets', totalSeconds: 60, remainingSeconds: 30, timerPaused: false } })
    expect(kinds(edit.view('rest', { restState: { mode: 'between-sets', totalSeconds: 60, remainingSeconds: 4, timerPaused: false } }))).toEqual([])
    expect(kinds(edit.view('rest', { restState: { mode: 'between-sets', totalSeconds: 60, remainingSeconds: 0, timerPaused: false } }))).toEqual(['rest-ready'])
  })

  it('announces the last set on entering the rest before it', () => {
    const h = new Harness(); h.session = { ...h.session, currentSetIndex: 1 } as RuntimeWorkoutSession
    h.enterSet()
    expect(kinds(h.view('rest', { restState: { mode: 'between-sets', totalSeconds: 60, remainingSeconds: 60, timerPaused: false } })))
      .toEqual(['last-set-next'])
  })

  it('revisiting a set never repeats its start or counts', () => {
    const h = new Harness(); h.enterSet(); h.reps(1, 2)
    h.view('rest', { restState: { mode: 'between-sets', totalSeconds: 60, remainingSeconds: 60, timerPaused: false } })
    expect(all([h.view('exercise-session'), h.hw('start_hold', 0), h.hw('training', 0)])).toEqual([])
    expect(h.reps(1, 3)).toEqual(['count:3'])
  })

  it('a new run resets dedup while latches persist', () => {
    const h = new Harness(); h.enterSet()
    h.session = { ...h.session, runId: 'run-2', id: 'session-2' } as RuntimeWorkoutSession
    expect(all(h.enterSet())).toEqual(['start'])
  })
})

describe('CoachInterpreter non-machine exercises', () => {
  it('never uses bar counters for bodyweight and reports no source', () => {
    const h = new Harness({}, baseSession([exercise('e1', 'bodyweight')]))
    const results = [...h.enterSet(), h.hw('training', 1), h.hw('training', 2)]
    expect(all(results)).toEqual(['start'])
    expect(skipsOf(results)).toContain('T14:no_source')
  })

  it('timed exercises without a runtime timer source stay silent', () => {
    const h = new Harness({}, baseSession([exercise('e1', 'timed', [{ targetSeconds: 30 }])]))
    const results = h.enterSet()
    expect(all(results)).toEqual([])
    expect(skipsOf(results)).toContain('T27:no_source')
  })

  it('does not repeat an identical skip on every tick', () => {
    const h = new Harness(); h.view('exercise-setup'); h.view('exercise-session')
    h.hw('training', 0, { patch: { serviceMode: true } })
    const repeated = [h.step(), h.step(), h.step()]
    expect(skipsOf(repeated)).toEqual([])
  })
})
