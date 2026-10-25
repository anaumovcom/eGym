import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import { useStage4Store } from '@/stores/stage4-store'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import type { HardwareSnapshot } from '@/features/hardware/model/types'
import { localAudioRuntime } from '../audio/local-audio-runtime'
import { LocalCoachAudioManager, type AudioReason, type LocalAudioSnapshot } from '../audio/local-coach-audio-manager'
import { peekSharedAudioContext, unlockSharedAudioContext } from '../audio/shared-audio-context'
import { CoachInterpreter, type InterpreterSnapshot, type LocalCue, type SetTimerInput } from '../interpreter/coach-interpreter'
import { coachLifecycle, coachSetTimer, isCoachFoundationEnabled, setLifecycleVersionReader } from '../lib/runtime-observation'
import { coachRunId, type CoachEvent, type CoachScope } from '../model/contracts'
import { effectiveCoachState, type CoachPreferences, type GeneralCoachAudio } from '../model/preferences'
import { coachRepBeep, playCue, type ClipSource, type CueManager, type RepBeepArbiter } from './local-cue-player'
import { coachPackClient, coachPackSlot, type PackSlot } from '../audio/pack-client'
import type { LifecycleRefs } from '../lib/lifecycle-observer'
import { CoachNetworkClient, type NetworkSnapshot } from './coach-network-client'
import { LocalCompletions } from './local-completion'

export type LiveInputs = Readonly<{
  userId: string | null; featureEnabled: boolean; hidden: boolean; emergency: boolean
  session: RuntimeWorkoutSession | null; hardware: HardwareSnapshot | null; connected: boolean
  general: GeneralCoachAudio; saved: CoachPreferences | null; timer?: SetTimerInput | null
}>
export type LiveReason = AudioReason | 'admitted' | 'idle' | 'live_priority' | 'completion_coalesced'
export type LiveRuntimeSnapshot = Readonly<{
  active: boolean; reason: LiveReason; interpreter: InterpreterSnapshot | null; audio: LocalAudioSnapshot | null
  lastCue: Readonly<{ triggerId: string; kind: string; clipId: string | null; reason: LiveReason }> | null
  counters: Readonly<{ cues: number; admitted: number; missingClip: number; suppressed: number; skips: number }>
  network: NetworkSnapshot | null
}>
type Manager = CueManager & Pick<LocalCoachAudioManager, 'updateScope' | 'setVolume' | 'subscribe' | 'dispose' | 'beginStream' | 'pushStream' | 'cancelStream'>
export type NetworkPort = Pick<CoachNetworkClient, 'tick' | 'observe' | 'dispose' | 'getSnapshot' | 'subscribe'>
export type LiveRuntimeDependencies = Readonly<{
  read: () => LiveInputs
  subscribeInputs: (listener: () => void) => () => void
  lifecycle: () => readonly CoachEvent[]
  lifecycleRefs: (eventId: string) => LifecycleRefs | null
  network: NetworkPort | null
  context: () => AudioContext | null
  createManager: (context: AudioContext, scope: CoachScope) => Manager
  clips: () => ClipSource
  /** Loads the published voice pack (cache or free GET); once per voice while audio runs. */
  restorePack: (slot: PackSlot) => void
  beep: RepBeepArbiter
  now: () => number
  setInterval: (callback: () => void, ms: number) => unknown
  clearInterval: (handle: unknown) => void
  allowEmulator: boolean
}>

const defaults: LiveRuntimeDependencies = {
  read: () => {
    const app = useAppStore.getState(), general = useStage4Store.getState().settingsSaved, hardware = useHardwareStore.getState()
    const clock = coachSetTimer.get()
    const timer = clock ? { exerciseId: clock.exerciseId, setOrdinal: clock.setOrdinal, running: clock.startedAtMs !== null,
      elapsedS: (clock.elapsedMs + (clock.startedAtMs !== null ? Math.max(0, Date.now() - clock.startedAtMs) : 0)) / 1000 } : null
    return { userId: app.selectedUserId, emergency: app.emergencyStopActive, featureEnabled: isCoachFoundationEnabled(),
      hidden: typeof document !== 'undefined' && document.hidden, session: useRuntimeStore.getState().session, timer,
      hardware: hardware.snapshot, connected: hardware.connectionStatus === 'connected', saved: localAudioRuntime.getSavedPreferences(),
      general: { soundEnabled: general.soundEnabled === true, voiceHintsEnabled: general.voiceHintsEnabled === true,
        volume: Number(String(general.signalVolume).replace('%', '')) / 100 } }
  },
  subscribeInputs: listener => {
    const unsubscribes = [useAppStore.subscribe(listener), useHardwareStore.subscribe(listener), useRuntimeStore.subscribe(listener),
      useStage4Store.subscribe(listener), localAudioRuntime.subscribe(listener), coachSetTimer.subscribe(listener)]
    if (typeof document !== 'undefined') document.addEventListener('visibilitychange', listener)
    return () => { unsubscribes.forEach(item => item()); if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', listener) }
  },
  lifecycle: () => coachLifecycle.snapshot(),
  lifecycleRefs: id => coachLifecycle.refs(id),
  network: null,
  context: peekSharedAudioContext,
  createManager: (context, scope) => new LocalCoachAudioManager({ context, scope }),
  clips: () => coachPackClient.clipsFor(coachPackSlot(localAudioRuntime.getSavedPreferences())),
  restorePack: slot => { void coachPackClient.restore(slot, { downloadPrepared: true }) },
  beep: coachRepBeep,
  now: () => performance.now(),
  setInterval: (callback, ms) => globalThis.setInterval(callback, ms),
  clearInterval: handle => globalThis.clearInterval(handle as ReturnType<typeof setInterval>),
  allowEmulator: import.meta.env.VITE_COACH_ALLOW_EMULATOR === 'true',
}

/** E06 live local cue path: interpreter → prepared clip → local mixer.
 * The interpreter runs even while muted so unmuting never replays old events.
 * E10: an optional network port forwards semantic events and streams backend speech
 * into the same mixer. No provider keys or hardware command access here.
 */
export class CoachLiveRuntime {
  private readonly deps: LiveRuntimeDependencies
  private interpreter: CoachInterpreter
  private readonly listeners = new Set<() => void>()
  private unsubscribe: (() => void) | null = null
  private networkUnsubscribe: (() => void) | null = null
  private interval: unknown = null
  private manager: Manager | null = null
  private managerUnsubscribe: (() => void) | null = null
  private hardware: HardwareSnapshot | null = null
  private hardwareAtMs: number | null = null
  private identity = ''
  private reason: LiveReason = 'idle'
  private lastCue: LiveRuntimeSnapshot['lastCue'] = null
  private counters = { cues: 0, admitted: 0, missingClip: 0, suppressed: 0, skips: 0 }
  private snapshotValue: LiveRuntimeSnapshot
  private unlockListener: (() => void) | null = null
  private ticking = false
  private restoredSlot: PackSlot | null = null
  private completions = new LocalCompletions()

  constructor(dependencies: Partial<LiveRuntimeDependencies> = {}) {
    this.deps = { ...defaults, ...dependencies }
    this.interpreter = new CoachInterpreter({ allowEmulator: this.deps.allowEmulator })
    this.snapshotValue = this.makeSnapshot(false)
  }

  readonly subscribe = (listener: () => void): (() => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  readonly getSnapshot = (): LiveRuntimeSnapshot => this.snapshotValue

  start(): void {
    if (this.unsubscribe) return
    this.unsubscribe = this.deps.subscribeInputs(this.tick)
    this.networkUnsubscribe = this.deps.network?.subscribe(() => this.publish(this.snapshotValue.active)) ?? null
    this.interval = this.deps.setInterval(this.tick, 200)
    this.tick()
  }

  dispose(): void {
    this.unsubscribe?.(); this.unsubscribe = null
    this.networkUnsubscribe?.(); this.networkUnsubscribe = null
    this.deps.network?.dispose()
    if (this.interval !== null) this.deps.clearInterval(this.interval)
    this.interval = null
    this.removeUnlock(); this.disposeManager('disposed'); this.publish(false); this.listeners.clear()
  }

  readonly tick = (): void => {
    if (this.ticking) return // Store updates during cancellation must not re-enter.
    this.ticking = true
    try { this.run() } finally { this.ticking = false }
  }

  private run(): void {
    const inputs = this.deps.read(), now = this.deps.now()
    if (!inputs.featureEnabled) {
      this.stopNetwork(inputs, now)
      this.removeUnlock(); this.disposeManager('disabled'); this.reason = 'disabled'; this.publish(false); return
    }
    if (inputs.hardware !== this.hardware) { this.hardware = inputs.hardware; this.hardwareAtMs = inputs.hardware ? now : null }
    const identity = JSON.stringify([inputs.userId, inputs.session ? coachRunId(inputs.session) : null])
    if (identity !== this.identity) {
      this.identity = identity
      this.interpreter = new CoachInterpreter({ allowEmulator: this.deps.allowEmulator })
      this.completions.clear()
      this.disposeManager('scope_changed'); this.deps.beep.clear()
    }
    const lifecycle = this.deps.lifecycle()
    const result = this.interpreter.step({ nowMs: now, userId: inputs.userId, session: inputs.session, hardware: this.hardware,
      hardwareReceivedAtMs: this.hardwareAtMs, sourceConnected: inputs.connected, emergency: inputs.emergency, timer: inputs.timer ?? null,
      count: inputs.saved?.count ?? 'off', lifecycle })
    this.counters.skips += result.skips.length
    const gate = this.gate(inputs)
    const slot = coachPackSlot(inputs.saved)
    // Decoding needs the running (user-unlocked) context; the cues below find no clips until it finishes.
    if (!gate && slot && slot !== this.restoredSlot) { this.restoredSlot = slot; this.deps.restorePack(slot) }
    if (result.scope) this.manager?.updateScope(result.scope)
    if (result.latched) this.manager?.cancelAll('safety')
    else if (gate) this.manager?.cancelAll(gate === 'audio_locked' ? 'audio_locked' : gate)
    if (gate === 'audio_locked' && result.scope) this.armUnlock(); else this.removeUnlock()
    // Every completion is local-first, independent of readiness, budget or live voice.
    const setCompleted = result.cues.some(cue => cue.kind === 'set-end' || cue.kind === 'set-partial' || cue.kind === 'set-skipped')
    for (const cue of result.cues) {
      if (!gate && cue.kind === 'last-set-next' && setCompleted) {
        this.counters.cues++; this.counters.suppressed++; this.record(cue, 'completion_coalesced')
      } else this.play(cue, inputs, gate, now)
    }
    this.deps.network?.tick({ nowMs: now, userId: inputs.userId, saved: inputs.saved, session: inputs.session, featureEnabled: true,
      phase: result.phase, scope: result.scope, latched: result.latched, gate, reps: this.interpreter.snapshot().baseline,
      partialReps: this.hardware?.motion?.partialReps ?? null, timer: inputs.timer ?? null, lifecycle, refs: this.deps.lifecycleRefs,
      telemetry: this.telemetry(now),
      localCompletion: event => this.completions.forEvent(event), mixer: () => this.networkMixer() })
    if (!result.cues.length && gate) this.reason = gate
    if (this.manager) this.deps.network?.observe(this.manager.snapshot())
    this.publish(!gate)
  }

  /** V2: the bar sample the rep tracker needs; only real (fresh) machine control telemetry. */
  private telemetry(now: number) {
    const control = this.hardware?.control
    if (!control || this.hardwareAtMs === null || now - this.hardwareAtMs > 1_000 || !Number.isFinite(control.velocityMmPerSec)) return null
    return { atMs: this.hardwareAtMs, positionMm: control.positionMm, velocityMmPerSec: control.velocityMmPerSec,
      loadDirection: control.loadDirection === 'up' ? 'up' as const : 'down' as const }
  }

  private stopNetwork(inputs: LiveInputs, now: number): void {
    this.deps.network?.tick({ nowMs: now, userId: inputs.userId, saved: inputs.saved, session: inputs.session, featureEnabled: false,
      phase: 'disabled', scope: null, latched: false, gate: 'disabled', reps: null, partialReps: null, lifecycle: [], refs: () => null, mixer: () => null })
  }

  /** Network speech joins the same mixer; created lazily like local cues, with the current scope. */
  private networkMixer(): Manager | null {
    const inputs = this.deps.read(), scope = this.interpreter.snapshot().scope
    if (!scope || this.gate(inputs)) return null
    return this.ensureManager(inputs, scope)
  }

  private ensureManager(inputs: LiveInputs, scope: CoachScope): Manager | null {
    const context = this.deps.context()
    if (!context || context.state !== 'running') return null
    if (!this.manager) {
      this.manager = this.deps.createManager(context, scope)
      const manager = this.manager
      this.managerUnsubscribe = manager.subscribe(() => {
        this.deps.network?.observe(manager.snapshot())
        this.publish(this.snapshotValue.active)
      })
    }
    const effective = effectiveCoachState(inputs.saved, inputs.general, inputs.featureEnabled)
    this.manager.setVolume(effective.volume, !effective.audioEnabled)
    return this.manager
  }

  private play(cue: LocalCue, inputs: LiveInputs, gate: AudioReason | null, now: number): void {
    this.counters.cues++
    if (gate) { this.counters.suppressed++; this.record(cue, gate); return }
    if (!this.ensureManager(inputs, cue.scope)) { this.counters.suppressed++; this.record(cue, 'audio_locked'); return }
    const manager = this.manager!
    const scope = cue.scope
    const outcome = playCue(manager, this.deps.clips(), cue, now, () => {
      const current = this.interpreter.snapshot()
      return current.scope?.scopeEpoch === scope.scopeEpoch && current.scope.runId === scope.runId &&
        (cue.priority === 'safety' || (!current.latches.length && !current.pain)) && !this.gate(this.deps.read())
    })
    if (outcome.admitted) {
      this.counters.admitted++
      this.completions.note(cue)
      if (cue.kind === 'count' && cue.value !== null) this.deps.beep.noteVoiceCount(cue.value)
    } else if (outcome.reason === 'missing_clip') this.counters.missingClip++
    else this.counters.suppressed++
    this.record(cue, outcome.reason)
  }

  private gate(inputs: LiveInputs): AudioReason | null {
    if (inputs.hidden) return 'hidden'
    const saved = inputs.saved
    if (!saved || !saved.enabled) return 'disabled'
    if (saved.consentVersion !== 1) return 'no_consent'
    if (!effectiveCoachState(saved, inputs.general, inputs.featureEnabled).audioEnabled) return 'mute'
    const context = this.deps.context()
    if (context?.state === 'closed') return 'unavailable'
    if (!context || context.state !== 'running') return 'audio_locked'
    return null
  }

  private record(cue: LocalCue, reason: LiveReason): void {
    this.reason = reason
    this.lastCue = Object.freeze({ triggerId: cue.triggerId, kind: cue.kind, clipId: cue.clipId, reason })
  }

  /** Unlock only from a trusted user gesture, never from a timer or store update. */
  private armUnlock(): void {
    if (this.unlockListener || typeof document === 'undefined') return
    const listener = () => { this.removeUnlock(); void unlockSharedAudioContext().then(() => this.tick()) }
    document.addEventListener('pointerdown', listener, { capture: true, once: true })
    document.addEventListener('keydown', listener, { capture: true, once: true })
    this.unlockListener = listener
  }

  private removeUnlock(): void {
    if (!this.unlockListener || typeof document === 'undefined') return
    document.removeEventListener('pointerdown', this.unlockListener, { capture: true })
    document.removeEventListener('keydown', this.unlockListener, { capture: true })
    this.unlockListener = null
  }

  private disposeManager(reason: AudioReason): void {
    this.managerUnsubscribe?.(); this.managerUnsubscribe = null
    const had = !!this.manager
    this.manager?.cancelAll(reason); this.manager?.dispose(); this.manager = null
    if (had) this.deps.network?.observe(null)
  }

  private makeSnapshot(active: boolean): LiveRuntimeSnapshot {
    return Object.freeze({ active, reason: this.reason, interpreter: this.unsubscribe ? this.interpreter.snapshot() : null,
      audio: this.manager?.snapshot() ?? null, lastCue: this.lastCue, counters: Object.freeze({ ...this.counters }),
      network: this.deps.network?.getSnapshot() ?? null })
  }

  private publish(active: boolean): void {
    this.snapshotValue = this.makeSnapshot(active)
    for (const listener of this.listeners) { try { listener() } catch { /* Diagnostics never break cues. */ } }
  }
}

export const coachNetworkClient = new CoachNetworkClient()
setLifecycleVersionReader(current => coachNetworkClient.captureVersions(current, useRuntimeStore.getState().session,
  localAudioRuntime.getSavedPreferences()))
export const coachLiveRuntime = new CoachLiveRuntime({ network: coachNetworkClient })

/** Idempotent; a no-op unless VITE_COACH_ENABLED=true. */
export function startCoachLiveRuntime(): void {
  if (isCoachFoundationEnabled()) coachLiveRuntime.start()
}
