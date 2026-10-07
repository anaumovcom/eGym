import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import { useStage4Store } from '@/stores/stage4-store'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import type { HardwareSnapshot } from '@/features/hardware/model/types'
import { coachSettingsApi } from '../lib/settings-api'
import type { CoachScope } from '../model/contracts'
import { effectiveCoachState, preferencesValid, type CoachPreferences } from '../model/preferences'
import { LocalClipPreparer } from './fixture-pack-storage'
import { LocalCoachAudioManager, type AudioReason, type LocalAudioSnapshot } from './local-coach-audio-manager'
import { getSharedAudioContext, unlockSharedAudioContext } from './shared-audio-context'

export type LocalAudioRuntimeInputs = Readonly<{
  userId: string | null; featureEnabled: boolean; hidden: boolean; emergency: boolean
  session: RuntimeWorkoutSession | null; hardware: HardwareSnapshot | null
  general: Readonly<{ soundEnabled: boolean; voiceHintsEnabled: boolean; volume: number }>
}>
export type LocalAudioRuntimeReason = AudioReason | 'no_user' | 'preferences_loading' | 'preferences_unavailable' | 'runtime_session' | 'hardware_active'
export type LocalAudioRuntimeSnapshot = Readonly<{
  userId: string | null; audio: LocalAudioSnapshot | null
  prepared: Readonly<{ entries: number; bytes: number; loading: boolean }>
  reason: LocalAudioRuntimeReason; previewAllowed: boolean
  preferencesReady: boolean; preferencesLoading: boolean
  paidRequests: 0; usage: Readonly<{ completeness: 'unavailable'; tokens: null; costUsd: null; ledgerBound: false }>
}>
type Manager = Pick<LocalCoachAudioManager, 'playLocal' | 'cancelAll' | 'updateScope' | 'setVolume' | 'subscribe' | 'snapshot' | 'dispose'>
type Preparer = Pick<LocalClipPreparer, 'prepare' | 'clear' | 'snapshot'>
export type LocalAudioRuntimeDependencies = Readonly<{
  read: () => LocalAudioRuntimeInputs
  subscribeInputs: (listener: () => void) => () => void
  unlock: () => Promise<boolean>
  context: () => AudioContext | null
  createManager: (context: AudioContext, scope: CoachScope) => Manager
  createPreparer: (context: AudioContext) => Preparer
  getPreferences: (userId: string, signal: AbortSignal) => Promise<CoachPreferences>
  now: () => number
}>
const usage = Object.freeze({ completeness: 'unavailable' as const, tokens: null, costUsd: null, ledgerBound: false as const })
const controlModes = ['post', 'homing', 'moving', 'weightless', 'start_hold', 'training', 'fixed_hold', 'isometric', 'paused', 'parked', 'idle', 'estop', 'fault', 'emergency_stop', 'failure', 'spotter'] as const
const defaultDependencies: LocalAudioRuntimeDependencies = {
  read: () => {
    const app = useAppStore.getState(), general = useStage4Store.getState().settingsSaved
    return { userId: app.selectedUserId, emergency: app.emergencyStopActive,
      featureEnabled: import.meta.env.VITE_COACH_ENABLED === 'true', hidden: typeof document !== 'undefined' && document.hidden,
      session: useRuntimeStore.getState().session, hardware: useHardwareStore.getState().snapshot,
      general: { soundEnabled: general.soundEnabled === true, voiceHintsEnabled: general.voiceHintsEnabled === true,
        volume: Number(String(general.signalVolume).replace('%', '')) / 100 } }
  },
  subscribeInputs: listener => {
    const unsubscribes = [useAppStore.subscribe(listener), useHardwareStore.subscribe(listener),
      useRuntimeStore.subscribe(listener), useStage4Store.subscribe(listener)]
    if (typeof document !== 'undefined') document.addEventListener('visibilitychange', listener)
    return () => { unsubscribes.forEach(unsubscribe => unsubscribe()); if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', listener) }
  },
  unlock: unlockSharedAudioContext, context: getSharedAudioContext,
  createManager: (context, scope) => new LocalCoachAudioManager({ context, scope }),
  createPreparer: context => new LocalClipPreparer(context), getPreferences: coachSettingsApi.get,
  now: () => performance.now(),
}

/** Read-only E05 fixture integration. Never a training/provider/ledger service.
 * Construction, subscription and snapshots do not construct/resume AudioContext.
 * UI must hydrate on selected-user mount (NOT diagnostics opening) and notify
 * successful settings GET/PUT with setSavedCoachPreferences. No draft updates.
 */
export class LocalAudioRuntime {
  private readonly deps: LocalAudioRuntimeDependencies
  private inputs: LocalAudioRuntimeInputs
  private readonly listeners = new Set<() => void>()
  private readonly latches = new Map<string, boolean>()
  private readonly unsubscribeInputs: () => void
  private unsubscribeManager: (() => void) | null = null
  private manager: Manager | null = null
  private preparer: Preparer | null = null
  private saved: CoachPreferences | null = null
  private preferencesLoading = false
  private preferencesFailed = false
  private preferencesEpoch = 0
  private preferencesRequest: { controller: AbortController; promise: Promise<void> } | null = null
  private prepareTask: Promise<boolean> | null = null
  private buffers: Readonly<{ single: AudioBuffer; chime: AudioBuffer }> | null = null
  private audio: LocalAudioSnapshot | null = null
  private prepared: LocalAudioRuntimeSnapshot['prepared'] = Object.freeze({ entries: 0, bytes: 0, loading: false })
  private generation = 0
  private scopeEpoch = 0
  private lifetime = 0
  private nextId = 0
  private disposed = false
  private actionReason: AudioReason = 'ready'
  private signature = ''
  private scope: CoachScope
  private snapshotValue: LocalAudioRuntimeSnapshot

  constructor(dependencies: Partial<LocalAudioRuntimeDependencies> = {}) {
    this.deps = { ...defaultDependencies, ...dependencies }
    this.inputs = this.deps.read()
    this.scope = this.makeScope()
    this.updateHardwareLatches()
    this.signature = this.configurationSignature()
    this.snapshotValue = this.makeSnapshot()
    this.unsubscribeInputs = this.deps.subscribeInputs(this.sync)
  }

  readonly subscribe = (listener: () => void): (() => void) => {
    if (this.disposed) return () => {}
    this.listeners.add(listener)
    return () => { this.listeners.delete(listener) }
  }
  readonly getSnapshot = (): LocalAudioRuntimeSnapshot => this.snapshotValue
  /** Saved (never draft) preferences of the currently selected user, or null. */
  readonly getSavedPreferences = (): CoachPreferences | null => this.saved

  /** Cached GET only. No settings request is made by snapshot/preview/preparation.
   * Abort is optional for a parent effect; stale/aborted results never install.
   */
  readonly refreshSavedPreferences = (signal?: AbortSignal): Promise<void> => {
    this.sync()
    if (this.disposed || !this.inputs.userId || !this.inputs.featureEnabled || signal?.aborted || this.saved) return Promise.resolve()
    if (this.preferencesRequest) return this.preferencesRequest.promise
    const userId = this.inputs.userId, epoch = ++this.preferencesEpoch
    const controller = new AbortController()
    const abort = () => {
      if (epoch === this.preferencesEpoch) { this.clearPreferencesRequest(); this.preferencesLoading = false; this.publish() }
      controller.abort()
    }
    signal?.addEventListener('abort', abort, { once: true })
    this.preferencesLoading = true; this.preferencesFailed = false; this.publish()
    const promise = (async () => {
      try {
        const prefs = await this.deps.getPreferences(userId, controller.signal)
        if (!controller.signal.aborted && epoch === this.preferencesEpoch && this.inputs.userId === userId && !this.disposed) this.setSavedCoachPreferences(userId, prefs)
      } catch {
        if (epoch === this.preferencesEpoch && !controller.signal.aborted && !this.disposed) this.preferencesFailed = true
      } finally {
        signal?.removeEventListener('abort', abort)
        if (epoch === this.preferencesEpoch && !this.disposed) { this.preferencesRequest = null; this.preferencesLoading = false; this.publish() }
      }
    })()
    this.preferencesRequest = { controller, promise }
    return promise
  }

  readonly setSavedCoachPreferences = (userId: string, prefs: CoachPreferences): void => {
    this.sync()
    if (this.disposed || this.inputs.userId !== userId || !preferencesValid(prefs)) return
    // Parent is responsible for its GET/PUT scope guard; revisions cannot regress.
    if (this.saved && prefs.revision < this.saved.revision) return
    this.clearPreferencesRequest()
    this.preferencesLoading = false; this.preferencesFailed = false
    const changed = JSON.stringify(this.saved) !== JSON.stringify(prefs)
    this.saved = Object.freeze({ ...prefs })
    if (changed) this.invalidateAudio('scope_changed')
    this.applyVolume(); this.publish()
  }

  readonly invalidateSavedCoachPreferences = (userId?: string): void => {
    this.sync()
    if (this.disposed || (userId !== undefined && userId !== this.inputs.userId)) return
    this.clearPreferencesRequest(); this.saved = null; this.preferencesLoading = false; this.preferencesFailed = false
    this.invalidateAudio('disabled'); this.applyVolume(); this.publish()
  }

  /** Explicit fixture preparation only; never unlocks/resumes or plays. */
  readonly prepareTestClips = async (): Promise<boolean> => {
    this.sync()
    if (this.disposed || this.gate()) return false
    if (this.buffers) return true
    if (this.prepareTask) return this.prepareTask
    const context = this.deps.context()
    if (!context || context.state === 'closed') { this.actionReason = 'unavailable'; this.publish(); return false }
    const preparer = this.preparer ??= this.deps.createPreparer(context)
    const generation = this.generation
    this.prepared = Object.freeze({ ...this.prepared, loading: true }); this.publish()
    const task = (async () => {
      try {
        const [single, chime] = await Promise.all([preparer.prepare('test-sine'), preparer.prepare('test-chime')])
        this.sync()
        if (this.disposed || generation !== this.generation || this.gate()) return false
        this.buffers = Object.freeze({ single, chime })
        const stats = preparer.snapshot()
        this.prepared = Object.freeze({ entries: stats.entries, bytes: stats.bytes, loading: false })
        this.actionReason = 'ready'; this.publish(); return true
      } catch {
        if (!this.disposed && generation === this.generation) {
          // Promise.all rejects before a sibling necessarily finishes. Retire
          // the whole batch so that sibling cannot refill a failed cache.
          this.invalidatePreparation(); this.actionReason = 'decode_failed'; this.publish()
        }
        return false
      } finally {
        if (!this.disposed && generation === this.generation) {
          this.prepareTask = null; this.prepared = Object.freeze({ ...this.prepared, loading: false }); this.publish()
        }
      }
    })()
    this.prepareTask = task
    return task
  }

  /** Call directly inside a trusted click/key handler. Unlock happens before
   * the FIRST await; effects and store subscriptions never call this method.
   */
  readonly playPreview = async (kind: 'single' | 'overlap'): Promise<boolean> => {
    this.sync()
    if (this.disposed || this.gate() || (kind !== 'single' && kind !== 'overlap')) return false
    const generation = this.generation
    // Do not insert an await before this trusted-activation call.
    try {
      const unlocked = this.deps.unlock()
      const ok = await unlocked
      this.sync()
      if (this.disposed || generation !== this.generation || this.gate()) return false
      if (!ok) { this.actionReason = 'audio_locked'; this.publish(); return false }
      if (!await this.prepareTestClips()) return false
      this.sync()
      if (this.disposed || generation !== this.generation || this.gate() || !this.buffers) return false
      const context = this.deps.context()
      if (!context || context.state !== 'running') { this.actionReason = 'audio_locked'; this.publish(); return false }
      if (!this.manager) {
        this.manager = this.deps.createManager(context, this.scope)
        this.unsubscribeManager = this.manager.subscribe(() => { this.audio = this.manager?.snapshot() ?? null; this.publish() })
        this.audio = this.manager.snapshot()
      }
      this.applyVolume()
      const scope = this.scope, deadline = this.deps.now() + 2000
      // Three verified 250ms tones overlap: starts at 0, 80, 160ms. TEST only.
      let admitted = true
      for (const [index, delayMs] of (kind === 'single' ? [0] : [0, 80, 160]).entries()) {
        const accepted = this.manager.playLocal({ id: `preview-${this.lifetime}-${++this.nextId}`, scope, source: 'local',
          buffer: index % 2 ? this.buffers.chime : this.buffers.single, startDeadlineMs: deadline, baseGain: 1, delayMs,
          revalidate: () => !this.disposed && generation === this.generation && !this.gate() })
        admitted = accepted && admitted
      }
      this.actionReason = admitted ? 'ready' : this.manager.snapshot().reason
      this.publish(); return admitted
    } catch {
      if (!this.disposed && generation === this.generation) { this.actionReason = 'unavailable'; this.publish() }
      return false
    }
  }

  readonly stopPreview = (): void => {
    if (this.disposed) return
    this.invalidateAudio('cancelled'); this.publish()
  }

  /** Tests/unmount owners only. Does not close or suspend the shared context. */
  readonly dispose = (): void => {
    if (this.disposed) return
    this.disposed = true; this.unsubscribeInputs(); this.clearPreferencesRequest()
    this.invalidateAudio('disposed'); this.unsubscribeManager?.(); this.manager?.dispose()
    this.manager = null; this.preparer = null; this.audio = null; this.preferencesLoading = false
    this.publish(); this.listeners.clear()
  }

  private readonly sync = (): void => {
    if (this.disposed) return
    const previous = this.inputs
    const oldGate = this.gate()
    this.inputs = this.deps.read()
    const userChanged = previous.userId !== this.inputs.userId
    const runChanged = previous.session?.id !== this.inputs.session?.id || previous.session?.runId !== this.inputs.session?.runId
    const scopeChanged = userChanged || runChanged || previous.session?.currentExerciseId !== this.inputs.session?.currentExerciseId ||
      previous.session?.currentSetIndex !== this.inputs.session?.currentSetIndex || previous.session?.view !== this.inputs.session?.view
    if (userChanged) {
      this.clearPreferencesRequest(); this.saved = null; this.preferencesLoading = false; this.preferencesFailed = false
    }
    this.updateHardwareLatches()
    const signature = this.configurationSignature()
    const configChanged = signature !== this.signature
    this.signature = signature
    if (userChanged || runChanged) {
      // Never publish the previous user's/run's diagnostic payload under the
      // new selected identity, even synchronously during cancelAll callbacks.
      this.unsubscribeManager?.(); this.unsubscribeManager = null
      this.audio = null
      this.invalidateAudio('scope_changed')
      this.manager?.dispose(); this.manager = null
      this.lifetime++
    } else if (configChanged || oldGate !== this.gate()) this.invalidateAudio(this.cancelReason())
    if (scopeChanged) {
      this.scopeEpoch++
      this.scope = this.makeScope()
      // Started audio survives a normal same-exercise set/rest boundary. Decode
      // completions and old pending sources are invalidated, not carried over.
      if (!userChanged && !runChanged && !configChanged && oldGate === this.gate()) this.invalidatePreparation()
      this.manager?.updateScope(this.scope)
    }
    this.applyVolume(); this.publish()
  }

  private updateHardwareLatches(): void {
    const h = this.inputs.hardware
    if (!h) return // Missing telemetry NEVER clears previously observed latches.
    const boolean = (key: string, value: unknown) => { if (typeof value === 'boolean') this.latches.set(key, value) }
    const mode = (key: string, value: unknown, blocked: readonly string[], known: readonly string[] = controlModes) => {
      if (typeof value === 'string' && known.includes(value)) this.latches.set(key, blocked.includes(value))
    }
    mode('emergency', h.safety?.state, ['emergency_stop'], ['enabled', 'disabled', 'emergency_stop'])
    mode('machineEmergency', h.machine?.safety, ['emergency_stop'], ['enabled', 'disabled', 'emergency_stop'])
    mode('blocked', h.machine?.machineState, ['blocked'], ['ready', 'warning', 'blocked'])
    boolean('requiresService', h.safety?.requiresService)
    boolean('panelStop', h.panel?.stopLatched)
    boolean('spotter', h.control?.spotterActive)
    boolean('failure', h.control?.failureDetected)
    mode('controlSafety', h.control?.mode, ['estop', 'emergency_stop', 'fault', 'failure', 'spotter'])
    mode('motionSafety', h.motion?.controlMode, ['estop', 'emergency_stop', 'fault', 'failure', 'spotter'])
    if (h.control?.faultCode === null || typeof h.control?.faultCode === 'string') boolean('faultCode', !!h.control.faultCode)
    mode('controlActive', h.control?.mode, ['training', 'isometric', 'fixed_hold', 'moving'])
    mode('motionActive', h.motion?.controlMode, ['training', 'isometric', 'fixed_hold', 'moving'])
    boolean('moving', h.motion?.moving)
    // serviceMode/emulatorMode are allowed for these local TEST fixtures only.
  }

  private gate(): LocalAudioRuntimeReason | null {
    if (this.disposed) return 'disposed'
    if (this.inputs.emergency || [...this.latches].some(([key, active]) => active && !['controlActive', 'motionActive', 'moving'].includes(key))) return 'safety'
    if (this.inputs.hidden) return 'hidden'
    if (['controlActive', 'motionActive', 'moving'].some(key => this.latches.get(key))) return 'hardware_active'
    const session = this.inputs.session
    // RuntimeWorkoutSession has no status flag. A workout-summary + terminal
    // workout outcome is the closed view; exercise-summary is NOT run closure.
    if (session && !(session.view === 'workout-summary' && ['completed', 'partial', 'aborted'].includes(session.workoutSummary?.outcome))) return 'runtime_session'
    if (!this.inputs.userId) return 'no_user'
    if (!this.inputs.featureEnabled) return 'disabled'
    if (!this.saved) return this.preferencesFailed ? 'preferences_unavailable' : 'preferences_loading'
    if (!this.saved.enabled) return 'disabled'
    if (this.saved.consentVersion !== 1) return 'no_consent'
    if (!effectiveCoachState(this.saved, this.inputs.general, this.inputs.featureEnabled).audioEnabled) return 'mute'
    return null
  }
  private cancelReason(): AudioReason {
    const reason = this.gate()
    return reason === 'safety' || reason === 'hardware_active' ? 'safety' : reason === 'hidden' ? 'hidden' : reason === 'mute' ? 'mute' : 'scope_changed'
  }
  private configurationSignature(): string {
    const session = this.inputs.session
    const exercise = session?.exercises.find(item => item.id === session.currentExerciseId)
    return JSON.stringify([this.inputs.featureEnabled, this.inputs.hidden, this.inputs.emergency, this.inputs.general,
      exercise?.plan, exercise?.loadSettings, this.inputs.hardware?.control?.config])
  }
  private makeScope(): CoachScope {
    const s = this.inputs.session
    return Object.freeze({ schemaVersion: 1, userId: this.inputs.userId ?? 'no-user',
      runId: s?.runId ?? s?.id ?? `local-preview-${this.lifetime}`, exerciseId: s?.currentExerciseId ?? 'test-preview',
      setOrdinal: s ? s.currentSetIndex + 1 : null, scopeEpoch: this.scopeEpoch })
  }
  private applyVolume(): void {
    if (!this.manager) return
    const effective = effectiveCoachState(this.saved, this.inputs.general, this.inputs.featureEnabled)
    const muted = !effective.audioEnabled || !!this.gate()
    if (this.audio?.volume !== effective.volume || this.audio?.muted !== muted) this.manager.setVolume(effective.volume, muted)
  }
  private clearPreferencesRequest(): void {
    this.preferencesEpoch++
    this.preferencesRequest?.controller.abort(); this.preferencesRequest = null
  }
  private invalidatePreparation(): void {
    this.generation++; this.prepareTask = null; this.buffers = null
    // Retain the owner: clear invalidates sharing/cache but cannot cancel a
    // native decode. Recreating it here would reset the outstanding-job cap.
    this.preparer?.clear()
    this.prepared = Object.freeze({ entries: 0, bytes: 0, loading: false })
  }
  private invalidateAudio(reason: AudioReason): void {
    this.invalidatePreparation(); this.actionReason = reason; this.manager?.cancelAll(reason)
  }
  private makeSnapshot(): LocalAudioRuntimeSnapshot {
    const gate = this.gate()
    return Object.freeze({ userId: this.inputs.userId, audio: this.audio, prepared: this.prepared,
      reason: gate ?? (this.audio?.reason === 'id_capacity' ? 'id_capacity' : this.actionReason), previewAllowed: !gate,
      preferencesReady: !!this.saved, preferencesLoading: this.preferencesLoading, paidRequests: 0, usage })
  }
  private publish(): void {
    const next = this.makeSnapshot(), previous = this.snapshotValue
    if (previous && next.userId === previous.userId && next.audio === previous.audio && next.reason === previous.reason &&
        next.previewAllowed === previous.previewAllowed && next.preferencesReady === previous.preferencesReady &&
        next.preferencesLoading === previous.preferencesLoading && next.prepared.entries === previous.prepared.entries &&
        next.prepared.bytes === previous.prepared.bytes && next.prepared.loading === previous.prepared.loading) return
    this.snapshotValue = next
    for (const listener of this.listeners) { try { listener() } catch { /* Diagnostics cannot break cancellation. */ } }
  }
}

export const localAudioRuntime = new LocalAudioRuntime()