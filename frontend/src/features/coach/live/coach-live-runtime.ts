import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import { useStage4Store } from '@/stores/stage4-store'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import type { HardwareSnapshot } from '@/features/hardware/model/types'
import { localAudioRuntime } from '../audio/local-audio-runtime'
import { LocalCoachAudioManager, type AudioReason, type LocalAudioSnapshot } from '../audio/local-coach-audio-manager'
import { peekSharedAudioContext, unlockSharedAudioContext } from '../audio/shared-audio-context'
import { CoachInterpreter, type InterpreterSnapshot, type LocalCue } from '../interpreter/coach-interpreter'
import { coachLifecycle, isCoachFoundationEnabled } from '../lib/runtime-observation'
import type { CoachEvent, CoachScope } from '../model/contracts'
import { effectiveCoachState, type CoachPreferences, type GeneralCoachAudio } from '../model/preferences'
import { coachRepBeep, playCue, type ClipSource, type CueManager, type RepBeepArbiter } from './local-cue-player'
import { coachPackClient } from '../audio/pack-client'

export type LiveInputs = Readonly<{
  userId: string | null; featureEnabled: boolean; hidden: boolean; emergency: boolean
  session: RuntimeWorkoutSession | null; hardware: HardwareSnapshot | null; connected: boolean
  general: GeneralCoachAudio; saved: CoachPreferences | null
}>
export type LiveReason = AudioReason | 'admitted' | 'idle'
export type LiveRuntimeSnapshot = Readonly<{
  active: boolean; reason: LiveReason; interpreter: InterpreterSnapshot | null; audio: LocalAudioSnapshot | null
  lastCue: Readonly<{ triggerId: string; kind: string; clipId: string | null; reason: LiveReason }> | null
  counters: Readonly<{ cues: number; admitted: number; missingClip: number; suppressed: number; skips: number }>
}>
type Manager = CueManager & Pick<LocalCoachAudioManager, 'updateScope' | 'setVolume' | 'subscribe' | 'dispose'>
export type LiveRuntimeDependencies = Readonly<{
  read: () => LiveInputs
  subscribeInputs: (listener: () => void) => () => void
  lifecycle: () => readonly CoachEvent[]
  context: () => AudioContext | null
  createManager: (context: AudioContext, scope: CoachScope) => Manager
  clips: () => ClipSource
  beep: RepBeepArbiter
  now: () => number
  setInterval: (callback: () => void, ms: number) => unknown
  clearInterval: (handle: unknown) => void
  allowEmulator: boolean
}>

const defaults: LiveRuntimeDependencies = {
  read: () => {
    const app = useAppStore.getState(), general = useStage4Store.getState().settingsSaved, hardware = useHardwareStore.getState()
    return { userId: app.selectedUserId, emergency: app.emergencyStopActive, featureEnabled: isCoachFoundationEnabled(),
      hidden: typeof document !== 'undefined' && document.hidden, session: useRuntimeStore.getState().session,
      hardware: hardware.snapshot, connected: hardware.connectionStatus === 'connected', saved: localAudioRuntime.getSavedPreferences(),
      general: { soundEnabled: general.soundEnabled === true, voiceHintsEnabled: general.voiceHintsEnabled === true,
        volume: Number(String(general.signalVolume).replace('%', '')) / 100 } }
  },
  subscribeInputs: listener => {
    const unsubscribes = [useAppStore.subscribe(listener), useHardwareStore.subscribe(listener), useRuntimeStore.subscribe(listener),
      useStage4Store.subscribe(listener), localAudioRuntime.subscribe(listener)]
    if (typeof document !== 'undefined') document.addEventListener('visibilitychange', listener)
    return () => { unsubscribes.forEach(item => item()); if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', listener) }
  },
  lifecycle: () => coachLifecycle.snapshot(),
  context: peekSharedAudioContext,
  createManager: (context, scope) => new LocalCoachAudioManager({ context, scope }),
  clips: () => coachPackClient.clipsFor(localAudioRuntime.getSavedPreferences()?.voiceProfile),
  beep: coachRepBeep,
  now: () => performance.now(),
  setInterval: (callback, ms) => globalThis.setInterval(callback, ms),
  clearInterval: handle => globalThis.clearInterval(handle as ReturnType<typeof setInterval>),
  allowEmulator: import.meta.env.VITE_COACH_ALLOW_EMULATOR === 'true',
}

/** E06 live local cue path: interpreter → prepared clip → local mixer.
 * The interpreter runs even while muted so unmuting never replays old events.
 * No network, provider, ledger or hardware command access.
 */
export class CoachLiveRuntime {
  private readonly deps: LiveRuntimeDependencies
  private interpreter: CoachInterpreter
  private readonly listeners = new Set<() => void>()
  private unsubscribe: (() => void) | null = null
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
    this.interval = this.deps.setInterval(this.tick, 200)
    this.tick()
  }

  dispose(): void {
    this.unsubscribe?.(); this.unsubscribe = null
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
    if (!inputs.featureEnabled) { this.removeUnlock(); this.disposeManager('disabled'); this.reason = 'disabled'; this.publish(false); return }
    if (inputs.hardware !== this.hardware) { this.hardware = inputs.hardware; this.hardwareAtMs = inputs.hardware ? now : null }
    const identity = JSON.stringify([inputs.userId, inputs.session?.runId ?? inputs.session?.id ?? null])
    if (identity !== this.identity) {
      this.identity = identity
      this.interpreter = new CoachInterpreter({ allowEmulator: this.deps.allowEmulator })
      this.disposeManager('scope_changed'); this.deps.beep.clear()
    }
    const result = this.interpreter.step({ nowMs: now, userId: inputs.userId, session: inputs.session, hardware: this.hardware,
      hardwareReceivedAtMs: this.hardwareAtMs, sourceConnected: inputs.connected, emergency: inputs.emergency,
      count: inputs.saved?.count ?? 'off', lifecycle: this.deps.lifecycle() })
    this.counters.skips += result.skips.length
    const gate = this.gate(inputs)
    if (result.scope) this.manager?.updateScope(result.scope)
    if (result.latched) this.manager?.cancelAll('safety')
    else if (gate) this.manager?.cancelAll(gate === 'audio_locked' ? 'audio_locked' : gate)
    if (gate === 'audio_locked' && result.scope) this.armUnlock(); else this.removeUnlock()
    for (const cue of result.cues) this.play(cue, inputs, gate, now)
    if (!result.cues.length && gate) this.reason = gate
    this.publish(!gate)
  }

  private play(cue: LocalCue, inputs: LiveInputs, gate: AudioReason | null, now: number): void {
    this.counters.cues++
    if (gate) { this.counters.suppressed++; this.record(cue, gate); return }
    const context = this.deps.context()
    if (!context || context.state !== 'running') { this.counters.suppressed++; this.record(cue, 'audio_locked'); return }
    if (!this.manager) {
      this.manager = this.deps.createManager(context, cue.scope)
      this.managerUnsubscribe = this.manager.subscribe(() => this.publish(this.snapshotValue.active))
    }
    const effective = effectiveCoachState(inputs.saved, inputs.general, inputs.featureEnabled)
    this.manager.setVolume(effective.volume, !effective.audioEnabled)
    const scope = cue.scope
    const outcome = playCue(this.manager, this.deps.clips(), cue, now, () => {
      const current = this.interpreter.snapshot()
      return current.scope?.scopeEpoch === scope.scopeEpoch && current.scope.runId === scope.runId &&
        (cue.priority === 'safety' || (!current.latches.length && !current.pain)) && !this.gate(this.deps.read())
    })
    if (outcome.admitted) {
      this.counters.admitted++
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
    this.manager?.cancelAll(reason); this.manager?.dispose(); this.manager = null
  }

  private makeSnapshot(active: boolean): LiveRuntimeSnapshot {
    return Object.freeze({ active, reason: this.reason, interpreter: this.unsubscribe ? this.interpreter.snapshot() : null,
      audio: this.manager?.snapshot() ?? null, lastCue: this.lastCue, counters: Object.freeze({ ...this.counters }) })
  }

  private publish(active: boolean): void {
    this.snapshotValue = this.makeSnapshot(active)
    for (const listener of this.listeners) { try { listener() } catch { /* Diagnostics never break cues. */ } }
  }
}

export const coachLiveRuntime = new CoachLiveRuntime()

/** Idempotent; a no-op unless VITE_COACH_ENABLED=true. */
export function startCoachLiveRuntime(): void {
  if (isCoachFoundationEnabled()) coachLiveRuntime.start()
}
