import type { RuntimeExercisePlan, RuntimeSetPlan, RuntimeView, RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import type { HardwareSnapshot } from '@/features/hardware/model/types'
import type { CoachEvent, CoachPhase, CoachReason, CoachScope, CoachSettings } from '../model/contracts'
import { CUE_SPECS, cueClipId, type CueKind } from './local-cues'

export type CountMode = CoachSettings['count']
export type InterpreterSkipReason = CoachReason | 'no_source' | 'ambiguous_target' | 'count_off' | 'jump' | 'save_delayed' | 'unsupported'
export type LocalCue = Readonly<{
  id: string; key: string; triggerId: string; kind: CueKind; clipId: string | null
  priority: 'safety' | 'ordinary'; scope: CoachScope; atMs: number; deadlineMs: number; value: number | null
}>
export type InterpreterSkip = Readonly<{ triggerId: string; reason: InterpreterSkipReason; atMs: number }>
export type InterpreterInput = Readonly<{
  nowMs: number; userId: string | null; session: RuntimeWorkoutSession | null
  hardware: HardwareSnapshot | null; hardwareReceivedAtMs: number | null
  emergency: boolean; count: CountMode; lifecycle: readonly CoachEvent[]
  /** Live socket state. The backend broadcasts only on change, so while connected an
   * unchanged snapshot stays current; without it freshness falls back to snapshot age. */
  sourceConnected?: boolean
}>
export type InterpreterOptions = Readonly<{
  freshnessMs?: number; restMarks?: readonly (10 | 5 | 0)[]; allowEmulator?: boolean
  lifecycleMaxAgeMs?: number; saveDelayMs?: number
}>
export type InterpreterResult = Readonly<{
  phase: CoachPhase; scope: CoachScope | null; cues: readonly LocalCue[]; skips: readonly InterpreterSkip[]
  scopeChanged: boolean; safetyRising: boolean; latched: boolean
}>
export type InterpreterSnapshot = Readonly<{
  phase: CoachPhase; scope: CoachScope | null; fresh: boolean; latches: readonly string[]; pain: boolean
  baseline: number | null; consumed: number; lastCue: LocalCue | null; skips: readonly InterpreterSkip[]
}>

type SetTrack = {
  enteredByTransition: boolean; observedInactive: boolean; started: boolean; activeSeen: boolean
  baseline: number | null; needsBaseline: boolean; inPause: boolean; pauseEpisodes: number
  lastElapsed: number | null; lastPhase: CoachPhase; noSourceReported: boolean
}

const ACTIVE_MODES = ['training', 'isometric', 'fixed_hold'] as const
const HOLD_MODES = ['isometric', 'fixed_hold'] as const
const CONTROL_MODES = ['post', 'homing', 'moving', 'weightless', 'start_hold', 'training', 'fixed_hold', 'isometric', 'paused', 'parked', 'idle', 'estop', 'fault', 'emergency_stop', 'failure', 'spotter']
const SAFETY_MODES = ['estop', 'emergency_stop', 'fault', 'failure', 'spotter']
const MAX_CONSUMED = 4096
const MAX_SEEN_LIFECYCLE = 1024
const MAX_SKIPS = 50

/** Exact (min = max) plan target; ranges and failure sets have none. */
export function exactRepTarget(plan: RuntimeSetPlan | undefined): number | null {
  if (!plan || plan.setType === 'failure') return null
  const min = plan.targetMinReps, max = plan.targetMaxReps
  if (min != null || max != null) {
    if (min == null || max == null || min !== max) return null
    return Number.isInteger(min) && min > 0 ? min : null
  }
  return Number.isInteger(plan.targetReps) && plan.targetReps! > 0 ? plan.targetReps! : null
}

/** Pure E06 interpreter. Owns no timers, network, audio or hardware command access.
 * Every cue is keyed by canonical identity and consumed once per user/run.
 */
export class CoachInterpreter {
  private readonly options: Required<InterpreterOptions>
  private identity = ''
  private scopeKey = ''
  private epoch = 0
  private view: RuntimeView | null = null
  private consumed = new Set<string>()
  private seenLifecycle = new Set<string>()
  private readonly latches = new Map<string, boolean>()
  private tracks = new Map<string, SetTrack>()
  private pendingSaves = new Map<string, number>()
  private hardware: HardwareSnapshot | null = null
  private hardwareAtMs: number | null = null
  private lastEmittedMs = -Infinity
  private latched = false
  private painCounts = new Map<string, number>()
  private painLatched = false
  private restRemaining: number | null = null
  private restKey = ''
  private sequence = 0
  private phase: CoachPhase = 'disabled'
  private scope: CoachScope | null = null
  private fresh = false
  private lastCue: LocalCue | null = null
  private skips: InterpreterSkip[] = []
  private lastSafetyCueMs = -Infinity
  private lastSkip = ''

  constructor(options: InterpreterOptions = {}) {
    this.options = { freshnessMs: options.freshnessMs ?? 1000, restMarks: options.restMarks ?? [10, 0],
      allowEmulator: options.allowEmulator ?? false, lifecycleMaxAgeMs: options.lifecycleMaxAgeMs ?? 5000,
      saveDelayMs: options.saveDelayMs ?? 5000 }
  }

  step(input: InterpreterInput): InterpreterResult {
    const cues: LocalCue[] = [], skips: InterpreterSkip[] = []
    const now = input.nowMs
    const session = input.session
    const runId = session ? session.runId ?? session.id : null
    const identity = JSON.stringify([input.userId, runId])
    if (identity !== this.identity) {
      this.identity = identity
      this.consumed = new Set(); this.seenLifecycle = new Set(); this.tracks = new Map(); this.pendingSaves = new Map()
      this.painCounts = new Map(); this.painLatched = false; this.restKey = ''; this.restRemaining = null; this.view = null
    }
    // A disconnect invalidates the last snapshot until a new one arrives after reconnect.
    if (input.sourceConnected === false) this.hardwareAtMs = null
    this.acceptHardware(input)
    const hw = this.hardware
    this.fresh = !!hw && this.hardwareAtMs !== null && now >= this.hardwareAtMs &&
      (input.sourceConnected === true || now - this.hardwareAtMs <= this.options.freshnessMs)
    const wasLatched = this.latched
    this.latched = input.emergency || [...this.latches].some(([key, value]) => value && !key.startsWith('active'))
    const exercise = session?.exercises.find(item => item.id === session.currentExerciseId) ?? null
    const setOrdinal = session ? session.currentSetIndex + 1 : null
    const nextScopeKey = JSON.stringify([identity, exercise?.id ?? null, setOrdinal, session?.view ?? null])
    const scopeChanged = nextScopeKey !== this.scopeKey
    const previousView = this.view
    if (scopeChanged) { this.scopeKey = nextScopeKey; this.epoch++ }
    this.view = session?.view ?? null
    this.scope = input.userId && session ? Object.freeze({ schemaVersion: 1 as const, userId: input.userId, runId: runId!,
      exerciseId: exercise?.id ?? null, setOrdinal, scopeEpoch: this.epoch }) : null
    const scope = this.scope
    const skip = (triggerId: string, reason: InterpreterSkipReason) => {
      // One primary reason per change, never the same message on every tick.
      const signature = `${triggerId}:${reason}`
      if (signature === this.lastSkip) return
      this.lastSkip = signature
      skips.push(Object.freeze({ triggerId, reason, atMs: now }))
    }
    const emit = (kind: CueKind, keyScope: readonly unknown[], ordinal: number, value: number | null = null) => {
      const spec = CUE_SPECS[kind]
      const key = JSON.stringify([...keyScope, kind, ordinal])
      if (this.consumed.has(key)) return
      if (this.consumed.size >= MAX_CONSUMED) { skip(spec.triggerId, 'queue_full'); return }
      this.consumed.add(key)
      if (!scope) return
      const cue: LocalCue = Object.freeze({ id: `cue-${++this.sequence}`, key, triggerId: spec.triggerId, kind,
        clipId: cueClipId(kind, value), priority: spec.priority, scope, atMs: now, deadlineMs: now + spec.deadlineMs, value })
      cues.push(cue); this.lastCue = cue
    }
    // Consumption without a cue: suppressed opportunities are never replayed later.
    const consume = (kind: CueKind, keyScope: readonly unknown[], ordinal: number) => {
      const key = JSON.stringify([...keyScope, kind, ordinal])
      if (this.consumed.size < MAX_CONSUMED) this.consumed.add(key)
    }

    let phase: CoachPhase
    let gate: InterpreterSkipReason | null = null
    if (!input.userId || !session || !exercise || !scope) { phase = 'disabled'; gate = 'disabled' }
    else if (session.dataSource !== 'backend') { phase = 'disabled'; gate = 'mock_source' }
    else {
      const setKey = [input.userId, runId, exercise.id, setOrdinal] as const
      const exerciseKey = [input.userId, runId, exercise.id, null] as const
      this.updatePain(session, exercise, exerciseKey, previousView !== null, emit)
      const safetyRising = this.latched && !wasLatched
      if (safetyRising && now - this.lastSafetyCueMs >= 30_000) {
        this.lastSafetyCueMs = now
        emit('safety-stop', [input.userId, runId, null, null], this.sequence + 1)
      }
      if (this.latched || this.painLatched) { phase = 'suspended'; gate = 'safety' }
      else phase = this.uiPhase(session.view)
      this.consumeLifecycle(input, emit, skip, gate)
      if (session.view === 'exercise-session') {
        phase = this.setPhase(input, session, exercise, setKey, previousView, gate, emit, consume, skip) ?? phase
      }
      if (session.view === 'rest') this.restMarks(session, exercise, setKey, previousView, gate, emit, consume)
      else { this.restKey = ''; this.restRemaining = null }
      for (const [key, at] of this.pendingSaves) {
        if (now - at > this.options.saveDelayMs) { this.pendingSaves.delete(key); skip('T36', 'save_delayed') }
      }
    }
    this.phase = phase
    if (gate && gate !== 'safety' && gate !== 'disabled') skip('T64', gate)
    for (const item of skips) { this.skips.push(item); if (this.skips.length > MAX_SKIPS) this.skips.shift() }
    return Object.freeze({ phase, scope, cues: Object.freeze(cues), skips: Object.freeze(skips), scopeChanged,
      safetyRising: this.latched && !wasLatched, latched: this.latched || this.painLatched })
  }

  snapshot(): InterpreterSnapshot {
    const track = this.scope ? this.tracks.get(JSON.stringify([this.scope.userId, this.scope.runId, this.scope.exerciseId, this.scope.setOrdinal])) : undefined
    return Object.freeze({ phase: this.phase, scope: this.scope, fresh: this.fresh,
      latches: Object.freeze([...this.latches].filter(([key, value]) => value && !key.startsWith('active')).map(([key]) => key)),
      pain: this.painLatched, baseline: track?.baseline ?? null, consumed: this.consumed.size, lastCue: this.lastCue,
      skips: Object.freeze([...this.skips]) })
  }

  private acceptHardware(input: InterpreterInput): void {
    const next = input.hardware
    if (!next || next === this.hardware || input.hardwareReceivedAtMs === null || !Number.isFinite(input.hardwareReceivedAtMs)) return
    const emitted = Date.parse(next.emittedAt)
    // Out-of-order telemetry never regresses counters or clears latches.
    if (Number.isFinite(emitted) && emitted < this.lastEmittedMs) return
    if (Number.isFinite(emitted)) this.lastEmittedMs = emitted
    this.hardware = next; this.hardwareAtMs = input.hardwareReceivedAtMs
    const set = (key: string, value: unknown) => { if (typeof value === 'boolean') this.latches.set(key, value) }
    const mode = (key: string, value: unknown, blocked: readonly string[], known: readonly string[]) => {
      if (typeof value === 'string' && known.includes(value)) this.latches.set(key, blocked.includes(value))
    }
    const states = ['enabled', 'disabled', 'emergency_stop']
    mode('emergency', next.safety?.state, ['emergency_stop'], states)
    mode('machineEmergency', next.machine?.safety, ['emergency_stop'], states)
    mode('blocked', next.machine?.machineState, ['blocked'], ['ready', 'warning', 'blocked'])
    set('requiresService', next.safety?.requiresService)
    set('panelStop', next.panel?.stopLatched)
    set('spotter', next.control?.spotterActive)
    set('failure', next.control?.failureDetected)
    mode('controlSafety', next.control?.mode, SAFETY_MODES, CONTROL_MODES)
    mode('motionSafety', next.motion?.controlMode, SAFETY_MODES, CONTROL_MODES)
    if (next.control && (next.control.faultCode === null || typeof next.control.faultCode === 'string')) this.latches.set('faultCode', !!next.control.faultCode)
  }

  private uiPhase(view: RuntimeView): CoachPhase {
    return view === 'rest' ? 'rest' : view === 'exercise-summary' ? 'exercise-summary' : view === 'workout-summary' ? 'workout-summary'
      : view === 'exercise-session' ? 'waiting-start' : 'setup'
  }

  private hardwareGate(input: InterpreterInput): InterpreterSkipReason | null {
    const hw = this.hardware
    if (!hw) return 'no_source'
    if (hw.serviceMode || (hw.emulatorMode && !this.options.allowEmulator)) return 'mock_source'
    if (hw.selectedUserId && hw.selectedUserId !== input.userId) return 'owner_mismatch'
    if (!this.fresh) return 'stale_source'
    return null
  }

  private setPhase(input: InterpreterInput, session: RuntimeWorkoutSession, exercise: RuntimeExercisePlan, setKey: readonly unknown[],
    previousView: RuntimeView | null, gate: InterpreterSkipReason | null,
    emit: (kind: CueKind, keyScope: readonly unknown[], ordinal: number, value?: number | null) => void,
    consume: (kind: CueKind, keyScope: readonly unknown[], ordinal: number) => void,
    skip: (triggerId: string, reason: InterpreterSkipReason) => void): CoachPhase | null {
    const trackKey = JSON.stringify(setKey)
    let track = this.tracks.get(trackKey)
    if (!track) {
      track = { enteredByTransition: previousView !== null && previousView !== 'exercise-session', observedInactive: false,
        started: false, activeSeen: false, baseline: null, needsBaseline: true, inPause: false, pauseEpisodes: 0,
        lastElapsed: null, lastPhase: 'waiting-start', noSourceReported: false }
      this.tracks.set(trackKey, track)
    }
    const plan = exercise.plan[session.currentSetIndex] ?? exercise.plan[exercise.plan.length - 1]
    if (exercise.kind !== 'machine') {
      // Another device's bar counter is never this exercise's progress.
      if (!track.started) {
        track.started = true
        if (exercise.kind === 'timed') skip('T27', 'no_source')
        else if (gate) consume('start', setKey, 0)
        else if (track.enteredByTransition) emit('start', setKey, 0)
      }
      if (!track.noSourceReported) { track.noSourceReported = true; skip('T14', 'no_source') }
      return gate ? null : 'active-set'
    }
    const hwGate = this.hardwareGate(input)
    const hw = this.hardware
    if (hwGate || !hw) {
      track.needsBaseline = true // Reconnect re-baselines; no burst of old numbers.
      if (hwGate !== 'no_source' || track.activeSeen) skip('T14', hwGate ?? 'no_source')
      return gate ? null : track.activeSeen ? track.lastPhase : 'waiting-start'
    }
    const mode = hw.control?.mode ?? hw.motion?.controlMode ?? null
    const active = (ACTIVE_MODES as readonly string[]).includes(mode ?? '')
    const hold = (HOLD_MODES as readonly string[]).includes(mode ?? '')
    const paused = mode === 'paused'
    const reps = Number.isInteger(hw.motion?.repetitionCount) && hw.motion.repetitionCount >= 0 ? hw.motion.repetitionCount : null
    if (!active && !paused) track.observedInactive = true
    if (gate) { track.needsBaseline = true; return null }
    let phase: CoachPhase = active ? 'active-set' : paused && track.activeSeen ? 'paused-set' : 'waiting-start'
    if (active) {
      const firstActive = !track.activeSeen
      track.activeSeen = true
      if (firstActive && !track.started) {
        track.started = true
        const kind = hold ? 'hold-start' : 'start'
        // Observed transition and no counted progress since this set was first seen.
        if ((track.observedInactive || track.enteredByTransition) && (hold || track.baseline === null || reps === track.baseline || reps === 0)) emit(kind, setKey, 0)
        else consume(kind, setKey, 0)
      }
      if (track.inPause) { track.inPause = false; emit('resume', setKey, track.pauseEpisodes) }
    } else if (paused && track.activeSeen && !track.inPause) {
      track.inPause = true; track.pauseEpisodes++
      if (track.pauseEpisodes <= 3) emit('pause', setKey, track.pauseEpisodes)
    }
    if (reps !== null) {
      if (track.needsBaseline || track.baseline === null) { track.baseline = reps; track.needsBaseline = false }
      else if (reps < track.baseline) track.baseline = reps
      else if (reps > track.baseline) {
        const jump = reps > track.baseline + 1
        track.baseline = reps
        if (active && !hold) this.countCues(input.count, plan, reps, jump, setKey, emit, consume, skip)
        else if (!active) skip('T14', 'no_window')
      }
    }
    if (hold && active) this.holdMarks(input.count, plan, hw.control?.isometricElapsedS, track, setKey, emit, skip)
    track.lastPhase = phase
    return phase
  }

  private countCues(count: CountMode, plan: RuntimeSetPlan | undefined, reps: number, jump: boolean, setKey: readonly unknown[],
    emit: (kind: CueKind, keyScope: readonly unknown[], ordinal: number, value?: number | null) => void,
    consume: (kind: CueKind, keyScope: readonly unknown[], ordinal: number) => void,
    skip: (triggerId: string, reason: InterpreterSkipReason) => void): void {
    const target = exactRepTarget(plan)
    const milestone: CueKind | null = target === null ? null
      : reps === target ? 'target'
        : target > 6 && reps === target - 3 ? 'three-left'
          : target > 6 && reps === Math.ceil(target / 2) ? 'half' : null
    if (count === 'off') { consume('count', setKey, reps); skip('T14', 'count_off'); return }
    if (jump) {
      // Only the current milestone survives a counter jump; never old numbers.
      consume('count', setKey, reps); skip('T14', 'jump')
      if (count === 'milestones' && milestone) emit(milestone, setKey, 0)
      return
    }
    if (count === 'every') { emit('count', setKey, reps, reps); return }
    if (target === null) { skip('T16', 'ambiguous_target'); consume('count', setKey, reps); return }
    if (count === 'last-three') {
      if (reps > target - 3 && reps <= target) emit('count', setKey, reps, reps)
      else if (milestone === 'half' && target >= 8) emit('half', setKey, 0)
      else consume('count', setKey, reps)
      return
    }
    if (milestone) emit(milestone, setKey, 0)
  }

  private holdMarks(count: CountMode, plan: RuntimeSetPlan | undefined, elapsedValue: number | undefined, track: SetTrack,
    setKey: readonly unknown[], emit: (kind: CueKind, keyScope: readonly unknown[], ordinal: number, value?: number | null) => void,
    skip: (triggerId: string, reason: InterpreterSkipReason) => void): void {
    const target = plan?.targetSeconds
    if (!Number.isFinite(elapsedValue) || !Number.isFinite(target) || target! <= 0) {
      if (!track.noSourceReported) { track.noSourceReported = true; skip('T28', 'no_source') }
      return
    }
    const elapsed = elapsedValue!, previous = track.lastElapsed
    track.lastElapsed = elapsed
    // Marks require an observed running timer: crossing between two increasing readings.
    if (previous === null || elapsed <= previous || count === 'off') return
    const crossed = (mark: number) => previous < mark && elapsed >= mark
    if (target! >= 20 && crossed(target! / 2)) emit('time-half', setKey, 0)
    if (target! >= 20 && crossed(target! - 10)) emit('ten-left', setKey, 0)
    for (const left of [3, 2, 1]) if (target! > left && crossed(target! - left)) emit('countdown', setKey, left, left)
  }

  private restMarks(session: RuntimeWorkoutSession, exercise: RuntimeExercisePlan, setKey: readonly unknown[], previousView: RuntimeView | null,
    gate: InterpreterSkipReason | null, emit: (kind: CueKind, keyScope: readonly unknown[], ordinal: number) => void,
    consume: (kind: CueKind, keyScope: readonly unknown[], ordinal: number) => void): void {
    const rest = session.restState
    if (!rest) return
    const key = JSON.stringify(setKey)
    const entered = key !== this.restKey
    if (entered) {
      this.restKey = key; this.restRemaining = null
      const lastNext = rest.mode === 'between-sets' && session.currentSetIndex + 2 === exercise.plan.length
      if (lastNext && previousView !== null && previousView !== 'rest' && !gate) emit('last-set-next', setKey, 0)
      else if (lastNext) consume('last-set-next', setKey, 0)
    }
    const remaining = rest.remainingSeconds, previous = this.restRemaining
    this.restRemaining = remaining
    if (previous === null || rest.timerPaused || !(remaining < previous)) return
    const marks: Array<[10 | 5 | 0, CueKind]> = [[10, 'rest-ten'], [5, 'rest-five'], [0, 'rest-ready']]
    for (const [mark, kind] of marks) {
      if (!this.options.restMarks.includes(mark) || !(previous > mark && remaining <= mark)) continue
      if (gate) consume(kind, setKey, 0)
      else if (remaining === mark || mark === 0) emit(kind, setKey, 0)
      else consume(kind, setKey, 0) // Large timer edits skip stale marks.
    }
  }

  private updatePain(session: RuntimeWorkoutSession, exercise: RuntimeExercisePlan, exerciseKey: readonly unknown[], observed: boolean,
    emit: (kind: CueKind, keyScope: readonly unknown[], ordinal: number) => void): void {
    const count = (session.completedSets[exercise.id] ?? []).filter(item => item.pain === true).length
    const key = JSON.stringify(exerciseKey)
    const previous = this.painCounts.get(key)
    this.painCounts.set(key, count)
    if ([...this.painCounts.keys()].length > 256) this.painCounts.delete(this.painCounts.keys().next().value!)
    this.painLatched = count > 0
    if (observed && previous !== undefined && count > previous) emit('pain-stop', exerciseKey, count)
  }

  private consumeLifecycle(input: InterpreterInput, emit: (kind: CueKind, keyScope: readonly unknown[], ordinal: number) => void,
    skip: (triggerId: string, reason: InterpreterSkipReason) => void, gate: InterpreterSkipReason | null): void {
    const scope = this.scope
    for (const event of input.lifecycle) {
      if (this.seenLifecycle.has(event.id)) continue
      if (this.seenLifecycle.size >= MAX_SEEN_LIFECYCLE) return
      this.seenLifecycle.add(event.id)
      if (!scope || event.scope.userId !== scope.userId || event.scope.runId !== scope.runId) continue
      const keyScope = [event.scope.userId, event.scope.runId, event.scope.exerciseId, event.kind.startsWith('set_') ? event.scope.setOrdinal : null]
      const saveKey = JSON.stringify(keyScope)
      if (event.kind === 'set_persisted') { this.pendingSaves.delete(saveKey); continue }
      const outcome = event.facts.find(fact => fact.id === 'result.outcome')?.value
      const stale = input.nowMs - event.createdAtMs > this.options.lifecycleMaxAgeMs || event.createdAtMs > input.nowMs
      let kind: CueKind | null = null
      if (event.kind === 'set_stopped') {
        if (!stale) this.pendingSaves.set(saveKey, event.createdAtMs)
        kind = outcome === 'skipped' ? 'set-skipped' : outcome === 'partial' || outcome === 'aborted' ? 'set-partial' : outcome === 'completed' ? 'set-end' : null
      } else if (event.kind === 'exercise_finalized') {
        kind = outcome === 'skipped' ? 'exercise-skipped' : outcome === 'completed' ? 'exercise-done' : outcome ? 'exercise-partial' : null
      } else if (event.kind === 'workout_finalized') {
        kind = outcome === 'completed' ? 'workout-done' : outcome ? 'workout-partial' : null
      }
      if (!kind) continue
      if (stale) { skip(CUE_SPECS[kind].triggerId, 'expired'); continue }
      if (gate) { skip(CUE_SPECS[kind].triggerId, gate); continue }
      if (event.kind === 'set_stopped' && event.scope.exerciseId !== scope.exerciseId) { skip(CUE_SPECS[kind].triggerId, 'scope_changed'); continue }
      emit(kind, keyScope, 0)
    }
  }
}
