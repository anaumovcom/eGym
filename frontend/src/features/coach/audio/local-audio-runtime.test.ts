import { webcrypto } from 'node:crypto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAppStore } from '../../../stores/app-store'
import { useHardwareStore } from '../../../stores/hardware-store'
import { useRuntimeStore } from '../../../stores/runtime-store'
import { useStage4Store } from '../../../stores/stage4-store'
import type { RuntimeWorkoutSession } from '../../../entities/runtime/model/types'
import type { HardwareSnapshot } from '../../hardware/model/types'
import { DEFAULT_COACH_PREFERENCES, type CoachPreferences } from '../model/preferences'
import { FakeClock, FakeContext } from './audio-test-fakes'
import { LocalClipPreparer } from './fixture-pack-storage'
import { LocalCoachAudioManager } from './local-coach-audio-manager'
import { LocalAudioRuntime, localAudioRuntime, type LocalAudioRuntimeInputs } from './local-audio-runtime'
import { createTestClipBuffer } from './test-clips'

const prefs: CoachPreferences = { ...DEFAULT_COACH_PREFERENCES, enabled: true, consentVersion: 1, revision: 1 }
const runtimes: LocalAudioRuntime[] = []
const originalApp = useAppStore.getState(), originalHardware = useHardwareStore.getState()
const originalRuntime = useRuntimeStore.getState(), originalGeneral = useStage4Store.getState()
function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (error: Error) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
function session(view: RuntimeWorkoutSession['view'], dataSource: 'mock' | 'backend' = 'mock'): RuntimeWorkoutSession {
  // Minimal read-only boundary fixture; production reads only these fields.
  return { id: 'workout-a', view, dataSource, currentExerciseId: 'exercise-a', currentSetIndex: 0,
    exercises: [], workoutSummary: { outcome: 'partial' } } as unknown as RuntimeWorkoutSession
}
function hardware(patch: Record<string, unknown> = {}): HardwareSnapshot {
  return { safety: { state: 'enabled', requiresService: false }, machine: { machineState: 'ready', safety: 'enabled' },
    control: { mode: 'idle', spotterActive: false, failureDetected: false, faultCode: null },
    motion: { moving: false, controlMode: 'idle' }, panel: { stopLatched: false }, ...patch } as HardwareSnapshot
}
function setup(options: { realPreparer?: boolean; contextMissing?: boolean } = {}) {
  let inputs: LocalAudioRuntimeInputs = { userId: 'user-a', featureEnabled: true, hidden: false, emergency: false,
    session: null, hardware: null, general: { soundEnabled: true, voiceHintsEnabled: true, volume: 0.7 } }
  const subscriptions = new Set<() => void>()
  const context = new FakeContext(), clock = new FakeClock()
  const unlock = vi.fn(async () => true), contextGetter = vi.fn(() => options.contextMissing ? null : context.asAudioContext())
  const getPreferences = vi.fn(async (_userId: string, _signal: AbortSignal) => prefs)
  const prepare = vi.fn(async (id: 'test-sine' | 'test-chime') => createTestClipBuffer(context.asAudioContext(), id))
  const clear = vi.fn()
  const createPreparer = vi.fn(() => options.realPreparer ? new LocalClipPreparer(context.asAudioContext()) : {
    prepare, clear, snapshot: () => ({ entries: 2, bytes: 16000, inFlight: 0 }),
  })
  const createManager = vi.fn((audioContext: AudioContext, scope: Parameters<LocalCoachAudioManager['updateScope']>[0]) =>
    new LocalCoachAudioManager({ context: audioContext, scope, clock }))
  const runtime = new LocalAudioRuntime({ read: () => inputs,
    subscribeInputs: listener => { subscriptions.add(listener); return () => { subscriptions.delete(listener) } },
    context: contextGetter, unlock, getPreferences, createManager, createPreparer, now: clock.now })
  runtimes.push(runtime)
  const change = (patch: Partial<LocalAudioRuntimeInputs>) => { inputs = { ...inputs, ...patch }; subscriptions.forEach(listener => listener()) }
  return { runtime, change, context, clock, unlock, contextGetter, getPreferences, prepare, clear, createManager, createPreparer,
    inputs: () => inputs, subscriptions }
}
function ready() {
  const fixture = setup()
  fixture.runtime.setSavedCoachPreferences('user-a', prefs)
  return fixture
}
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => { throw new Error('network forbidden') }))
  vi.stubGlobal('crypto', { subtle: { digest: (algorithm: string, data: ArrayBuffer) => webcrypto.subtle.digest(algorithm, Buffer.from(new Uint8Array(data))) } })
})
afterEach(() => {
  runtimes.splice(0).forEach(runtime => runtime.dispose())
  useAppStore.setState(originalApp, true); useHardwareStore.setState(originalHardware, true)
  useRuntimeStore.setState(originalRuntime, true); useStage4Store.setState(originalGeneral, true)
  localAudioRuntime.invalidateSavedCoachPreferences()
  vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks()
})

describe('read-only local audio runtime diagnostics and preferences', () => {
  it('has stable frozen initial snapshots, no context/network/unlock, and unknown unbound usage', () => {
    const f = setup(), listener = vi.fn()
    const initial = f.runtime.getSnapshot(), unsubscribe = f.runtime.subscribe(listener)
    expect(f.runtime.getSnapshot()).toBe(initial)
    expect(Object.isFrozen(initial)).toBe(true)
    expect(initial).toMatchObject({ audio: null, prepared: { entries: 0, bytes: 0, loading: false },
      reason: 'preferences_loading', preferencesReady: false, previewAllowed: false, paidRequests: 0,
      usage: { completeness: 'unavailable', tokens: null, costUsd: null, ledgerBound: false } })
    f.change({})
    expect(f.runtime.getSnapshot()).toBe(initial); expect(listener).not.toHaveBeenCalled()
    expect(f.contextGetter).not.toHaveBeenCalled(); expect(f.unlock).not.toHaveBeenCalled()
    expect(f.getPreferences).not.toHaveBeenCalled(); expect(fetch).not.toHaveBeenCalled()
    unsubscribe(); f.runtime.setSavedCoachPreferences('user-a', prefs)
    expect(listener).not.toHaveBeenCalled(); expect(f.contextGetter).not.toHaveBeenCalled()
  })

  it('hydrates only explicitly, coalesces/caches GET, and copies saved preferences, not drafts', async () => {
    const f = setup(), response = deferred<CoachPreferences>()
    f.getPreferences.mockReturnValueOnce(response.promise)
    const first = f.runtime.refreshSavedPreferences(), second = f.runtime.refreshSavedPreferences()
    expect(first).toBe(second); expect(f.getPreferences).toHaveBeenCalledTimes(1)
    expect(f.runtime.getSnapshot().preferencesLoading).toBe(true)
    response.resolve(prefs); await first
    expect(f.runtime.getSnapshot()).toMatchObject({ preferencesReady: true, preferencesLoading: false, previewAllowed: true })
    await f.runtime.refreshSavedPreferences()
    expect(f.getPreferences).toHaveBeenCalledTimes(1)
    const mutable = { ...prefs, revision: 2 }
    f.runtime.setSavedCoachPreferences('user-a', mutable); mutable.enabled = false
    expect(f.runtime.getSnapshot().previewAllowed).toBe(true)
    f.runtime.setSavedCoachPreferences('other', { ...prefs, enabled: false })
    f.runtime.setSavedCoachPreferences('user-a', { ...prefs, enabled: false, revision: 0 })
    expect(f.runtime.getSnapshot().previewAllowed).toBe(true)
    expect(f.unlock).not.toHaveBeenCalled(); expect(fetch).not.toHaveBeenCalled()
  })

  it('aborts and rejects stale A→B→A hydration, including APIs ignoring AbortSignal', async () => {
    const f = setup(), a = deferred<CoachPreferences>(), b = deferred<CoachPreferences>()
    f.getPreferences.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise)
    const taskA = f.runtime.refreshSavedPreferences()
    const signalA = f.getPreferences.mock.calls[0][1]
    f.change({ userId: 'user-b' })
    expect(signalA.aborted).toBe(true)
    expect(f.runtime.getSnapshot()).toMatchObject({ userId: 'user-b', preferencesReady: false })
    const taskB = f.runtime.refreshSavedPreferences()
    f.change({ userId: 'user-a' }); a.resolve(prefs); b.resolve(prefs)
    await Promise.all([taskA, taskB])
    expect(f.runtime.getSnapshot()).toMatchObject({ userId: 'user-a', preferencesReady: false, preferencesLoading: false })
    f.runtime.setSavedCoachPreferences('user-a', prefs)
    expect(f.runtime.getSnapshot().previewAllowed).toBe(true)
  })

  it('supports effect AbortSignal, retries after abort/failure, and saved notification supersedes pending GET', async () => {
    const f = setup(), late = deferred<CoachPreferences>(), controller = new AbortController()
    f.getPreferences.mockReturnValueOnce(late.promise)
    const request = f.runtime.refreshSavedPreferences(controller.signal)
    controller.abort()
    expect(f.getPreferences.mock.calls[0][1].aborted).toBe(true)
    expect(f.runtime.getSnapshot().preferencesLoading).toBe(false)
    f.getPreferences.mockRejectedValueOnce(new Error('private error not exposed'))
    await f.runtime.refreshSavedPreferences()
    expect(f.runtime.getSnapshot().reason).toBe('preferences_unavailable')
    f.runtime.setSavedCoachPreferences('user-a', { ...prefs, revision: 3 })
    late.resolve({ ...prefs, enabled: false }); await request
    expect(f.runtime.getSnapshot().previewAllowed).toBe(true)
    f.runtime.invalidateSavedCoachPreferences('other')
    expect(f.runtime.getSnapshot().preferencesReady).toBe(true)
    f.runtime.invalidateSavedCoachPreferences('user-a')
    expect(f.runtime.getSnapshot().preferencesReady).toBe(false)
  })
})

describe('explicit test-tone preparation and gesture previews', () => {
  it('clears a failed preparation batch before a slow sibling can repopulate its cache', async () => {
    const f = setup({ realPreparer: true })
    f.runtime.setSavedCoachPreferences('user-a', prefs)
    const failure = deferred<AudioBuffer>(), slow = deferred<AudioBuffer>()
    f.context.decodeAudioData.mockReturnValueOnce(failure.promise).mockReturnValueOnce(slow.promise)
    const preparation = f.runtime.prepareTestClips()
    await vi.waitFor(() => expect(f.context.decodeAudioData).toHaveBeenCalledTimes(2))
    failure.reject(new Error('bad decode'))
    expect(await preparation).toBe(false)
    expect(f.runtime.getSnapshot().prepared).toEqual({ entries: 0, bytes: 0, loading: false })
    slow.resolve(f.context.createBuffer(1, 2000, 8000))
    expect(await f.runtime.prepareTestClips()).toBe(true)
    expect(f.runtime.getSnapshot().prepared).toEqual({ entries: 2, bytes: 16000, loading: false })
    expect(f.context.decodeAudioData).toHaveBeenCalledTimes(4)
  })

  it('retains one bounded preparer across stop/retry and releases it on disposal', async () => {
    const f = ready()
    await f.runtime.prepareTestClips()
    f.runtime.stopPreview()
    await f.runtime.prepareTestClips()
    expect(f.createPreparer).toHaveBeenCalledTimes(1)
    f.runtime.dispose()
    expect(f.clear).toHaveBeenCalled()
    expect(f.runtime.getSnapshot().prepared).toEqual({ entries: 0, bytes: 0, loading: false })
  })

  it('an obsolete preparation completion cannot install buffers or clear a newer loading task', async () => {
    const f = ready(), old = deferred<AudioBuffer>(), current = deferred<AudioBuffer>()
    f.prepare.mockReturnValueOnce(old.promise).mockReturnValueOnce(old.promise)
      .mockReturnValueOnce(current.promise).mockReturnValueOnce(current.promise)
    const first = f.runtime.prepareTestClips()
    f.runtime.stopPreview()
    const second = f.runtime.prepareTestClips()
    old.resolve(createTestClipBuffer(f.context.asAudioContext()))
    expect(await first).toBe(false)
    expect(f.runtime.getSnapshot().prepared).toEqual({ entries: 0, bytes: 0, loading: true })
    current.resolve(createTestClipBuffer(f.context.asAudioContext()))
    expect(await second).toBe(true)
    expect(f.runtime.getSnapshot().prepared).toEqual({ entries: 2, bytes: 16000, loading: false })
    expect(f.createPreparer).toHaveBeenCalledTimes(1)
  })

  it('unlocks synchronously before any await, prepares once, and schedules a real manager overlap of three TEST tones', async () => {
    const f = ready(), unlock = deferred<boolean>()
    f.unlock.mockReturnValueOnce(unlock.promise)
    const playback = f.runtime.playPreview('overlap')
    expect(f.unlock).toHaveBeenCalledTimes(1); expect(f.prepare).not.toHaveBeenCalled()
    unlock.resolve(true); expect(await playback).toBe(true)
    expect(f.prepare).toHaveBeenCalledTimes(2)
    expect(f.runtime.getSnapshot().prepared).toEqual({ entries: 2, bytes: 16000, loading: false })
    f.clock.advance(180, f.context)
    const audio = f.runtime.getSnapshot().audio!
    expect(audio.active).toBe(3); expect(audio.startOrdinal).toBe(3)
    expect(audio.utterances.map(item => item.coefficient)).toEqual([0.325, 0.325, 1])
    expect(audio.utterances.map(item => item.scope.runId)).toEqual(['local-preview-0', 'local-preview-0', 'local-preview-0'])
    expect(f.context.sources.every(source => source.buffer?.duration === 0.25)).toBe(true)
    expect(audio.volume).toBe(0.7); expect(audio.lastActualSource).toBe('local')
    f.context.sources.forEach(source => source.end())
    expect(await f.runtime.playPreview('single')).toBe(true)
    expect(f.prepare).toHaveBeenCalledTimes(2); expect(f.createManager).toHaveBeenCalledTimes(1)
    expect(fetch).not.toHaveBeenCalled(); expect(f.getPreferences).not.toHaveBeenCalled()
  })

  it('explicit prepare verifies real fixed fixture SHA256 without unlock, playback, or settings requests', async () => {
    const f = setup({ realPreparer: true })
    f.runtime.setSavedCoachPreferences('user-a', prefs)
    const first = f.runtime.prepareTestClips(), second = f.runtime.prepareTestClips()
    expect(await first).toBe(true); expect(await second).toBe(true)
    expect(f.context.decodeAudioData).toHaveBeenCalledTimes(2)
    expect(f.runtime.getSnapshot().prepared).toEqual({ entries: 2, bytes: 16000, loading: false })
    expect(f.unlock).not.toHaveBeenCalled(); expect(f.createManager).not.toHaveBeenCalled()
    expect(f.context.sources).toHaveLength(0); expect(fetch).not.toHaveBeenCalled()
  })

  it('never proceeds when unlock fails or context unavailable; catches unlock/decode errors without error text', async () => {
    const f = ready()
    f.unlock.mockResolvedValueOnce(false)
    expect(await f.runtime.playPreview('single')).toBe(false)
    expect(f.runtime.getSnapshot().reason).toBe('audio_locked'); expect(f.prepare).not.toHaveBeenCalled()
    f.unlock.mockImplementationOnce(() => { throw new Error('private unlock') })
    expect(await f.runtime.playPreview('single')).toBe(false)
    expect(f.runtime.getSnapshot().reason).toBe('unavailable')
    f.prepare.mockRejectedValueOnce(new Error('private decode'))
    expect(await f.runtime.playPreview('single')).toBe(false)
    expect(f.runtime.getSnapshot().reason).toBe('decode_failed')
    const missing = setup({ contextMissing: true }); missing.runtime.setSavedCoachPreferences('user-a', prefs)
    expect(await missing.runtime.prepareTestClips()).toBe(false)
    expect(missing.runtime.getSnapshot().reason).toBe('unavailable')
  })

  it.each(['stop', 'hidden', 'user', 'mute', 'voice', 'mode', 'run', 'exercise', 'config', 'emergency', 'dispose'] as const)(
    'invalidates pending decode immediately on %s and ignores late completions', async boundary => {
      const f = ready(), decoded = deferred<AudioBuffer>()
      f.prepare.mockImplementation(() => decoded.promise)
      const playback = f.runtime.playPreview('single')
      await Promise.resolve(); await Promise.resolve()
      expect(f.runtime.getSnapshot().prepared.loading).toBe(true)
      switch (boundary) {
        case 'stop': f.runtime.stopPreview(); break
        case 'hidden': f.change({ hidden: true }); f.change({ hidden: false }); break
        case 'user': f.change({ userId: 'user-b' }); f.change({ userId: 'user-a' }); f.runtime.setSavedCoachPreferences('user-a', prefs); break
        case 'mute': f.change({ general: { ...f.inputs().general, soundEnabled: false } }); f.change({ general: f.inputs().general }); break
        case 'voice': f.runtime.setSavedCoachPreferences('user-a', { ...prefs, revision: 2, voiceProfile: 'cedar' }); break
        case 'mode': f.runtime.setSavedCoachPreferences('user-a', { ...prefs, revision: 2, mode: 'text-only', networkConsentVersion: 1 }); break
        case 'run': f.change({ session: session('workout-summary') }); break
        case 'exercise': f.change({ session: { ...session('workout-summary'), currentExerciseId: 'exercise-b' } }); break
        case 'config': f.change({ hardware: hardware({ control: { mode: 'idle', config: { loadKg: 5 } } }) }); break
        case 'emergency': f.change({ emergency: true }); f.change({ emergency: false }); break
        case 'dispose': f.runtime.dispose(); break
      }
      expect(f.runtime.getSnapshot().prepared.loading).toBe(false)
      decoded.resolve(createTestClipBuffer(f.context.asAudioContext()))
      expect(await playback).toBe(false)
      expect(f.createManager).not.toHaveBeenCalled(); expect(f.context.sources).toHaveLength(0)
      expect(f.runtime.getSnapshot().prepared.entries).toBe(0)
    })

  it('guards A→B→A during unlock and never automatically resumes after mute or visibility recovery', async () => {
    const f = ready(), unlock = deferred<boolean>()
    f.unlock.mockReturnValueOnce(unlock.promise)
    const playback = f.runtime.playPreview('single')
    f.change({ userId: 'user-b' }); f.change({ userId: 'user-a' }); f.runtime.setSavedCoachPreferences('user-a', prefs)
    unlock.resolve(true); expect(await playback).toBe(false)
    expect(f.prepare).not.toHaveBeenCalled()
    f.change({ hidden: true }); f.change({ hidden: false })
    expect(f.unlock).toHaveBeenCalledTimes(1); expect(f.context.sources).toHaveLength(0)
  })

  it.each(['hidden', 'emergency', 'hardware', 'runtime', 'sound'] as const)('rechecks %s after async unlock before decode', async boundary => {
    const f = ready(), unlock = deferred<boolean>()
    f.unlock.mockReturnValueOnce(unlock.promise)
    const playback = f.runtime.playPreview('single')
    if (boundary === 'hidden') f.change({ hidden: true })
    if (boundary === 'emergency') f.change({ emergency: true })
    if (boundary === 'hardware') f.change({ hardware: hardware({ control: { mode: 'training' } }) })
    if (boundary === 'runtime') f.change({ session: session('exercise-setup') })
    if (boundary === 'sound') f.change({ general: { ...f.inputs().general, voiceHintsEnabled: false } })
    unlock.resolve(true)
    expect(await playback).toBe(false); expect(f.prepare).not.toHaveBeenCalled()
    expect(f.context.sources).toHaveLength(0)
  })
})

describe('runtime and hardware admission/cancellation', () => {
  it.each(['photo-progress', 'exercise-setup', 'exercise-session', 'rest', 'exercise-summary'] as const)(
    'blocks every unfinished %s session regardless of route or backend/mock source', async view => {
      for (const source of ['mock', 'backend'] as const) {
        const f = ready(); f.change({ session: session(view, source) })
        expect(f.runtime.getSnapshot()).toMatchObject({ reason: 'runtime_session', previewAllowed: false })
        expect(await f.runtime.playPreview('single')).toBe(false)
        expect(f.unlock).not.toHaveBeenCalled(); expect(f.contextGetter).not.toHaveBeenCalled()
      }
    })

  it.each(['completed', 'partial', 'aborted'] as const)('allows terminal workout summary %s only, without using backendSaved as a training status', async outcome => {
    const f = ready(), closed = session('workout-summary')
    closed.workoutSummary.outcome = outcome; closed.backendWorkoutSaved = false
    f.change({ session: closed }); expect(f.runtime.getSnapshot().previewAllowed).toBe(true)
    expect(await f.runtime.playPreview('single')).toBe(true)
    f.change({ session: { ...closed, view: 'exercise-session', backendWorkoutSaved: true } })
    expect(f.runtime.getSnapshot().reason).toBe('runtime_session')
    expect(f.context.sources[0].stop).toHaveBeenCalled()
  })

  it.each(['training', 'isometric', 'fixed_hold', 'moving'])('blocks actual control %s even with no session or closed summary', async mode => {
    const f = ready(); f.change({ hardware: hardware({ control: { mode } }) })
    expect(f.runtime.getSnapshot().reason).toBe('hardware_active')
    expect(await f.runtime.playPreview('single')).toBe(false)
    f.change({ session: session('workout-summary') })
    expect(await f.runtime.playPreview('single')).toBe(false)
    expect(f.unlock).not.toHaveBeenCalled()
    f.change({ hardware: hardware() }); expect(f.runtime.getSnapshot().previewAllowed).toBe(true)
  })

  it.each([
    { safety: { state: 'emergency_stop' } }, { machine: { machineState: 'blocked' } },
    { control: { mode: 'fault' } }, { control: { mode: 'estop' } }, { control: { faultCode: 'E99' } },
    { motion: { moving: false, controlMode: 'fault' } }, { motion: { moving: false, controlMode: 'estop' } },
    { motion: { moving: false, controlMode: 'failure' } }, { motion: { moving: false, controlMode: 'spotter' } },
    { control: { spotterActive: true } }, { control: { failureDetected: true } },
    { panel: { stopLatched: true } }, { safety: { requiresService: true } },
  ])('latches explicit safety %j through missing telemetry until corresponding usable false', async patch => {
    const f = ready(); expect(await f.runtime.playPreview('overlap')).toBe(true)
    f.clock.advance(180, f.context)
    f.change({ hardware: hardware(patch) })
    expect(f.runtime.getSnapshot().reason).toBe('safety')
    expect(f.context.sources.every(source => source.stop.mock.calls.length > 0)).toBe(true)
    f.change({ hardware: null })
    expect(f.runtime.getSnapshot().reason).toBe('safety')
    f.change({ hardware: {} as HardwareSnapshot })
    expect(f.runtime.getSnapshot().reason).toBe('safety')
    expect(await f.runtime.playPreview('single')).toBe(false)
    f.change({ hardware: hardware() })
    expect(f.runtime.getSnapshot().previewAllowed).toBe(true)
    expect(f.unlock).toHaveBeenCalledTimes(1) // Recovery does not autoplay.
    expect(f.runtime.getSnapshot().audio?.active).toBe(0)
  })

  it('does not clear safety on user/run changes and allows idle service/emulator for fixtures only', () => {
    const f = ready(); f.change({ hardware: hardware({ control: { failureDetected: true } }) })
    f.change({ hardware: null, userId: 'user-b', session: session('workout-summary') })
    f.runtime.setSavedCoachPreferences('user-b', prefs)
    expect(f.runtime.getSnapshot().reason).toBe('safety')
    f.change({ hardware: hardware({ emulatorMode: true, serviceMode: true }) })
    expect(f.runtime.getSnapshot().previewAllowed).toBe(true)
    f.change({ hardware: hardware({ emulatorMode: true, serviceMode: true, motion: { moving: true } }) })
    expect(f.runtime.getSnapshot().reason).toBe('hardware_active')
  })

  it('unknown/missing modes and unrelated explicit false flags cannot clear corresponding safety latches', () => {
    const f = ready()
    f.change({ hardware: hardware({ control: { mode: 'fault', spotterActive: true, failureDetected: true } }) })
    f.change({ hardware: hardware({ control: { mode: 'unusable-mode', spotterActive: false } }) })
    expect(f.runtime.getSnapshot().reason).toBe('safety')
    f.change({ hardware: hardware({ control: { mode: 'idle', spotterActive: false } }) })
    expect(f.runtime.getSnapshot().reason).toBe('safety') // failure still latched
    f.change({ hardware: hardware({ control: { failureDetected: false } }) })
    expect(f.runtime.getSnapshot().previewAllowed).toBe(true)
  })

  it('requires actual selected user, feature flag, consent/enabled saved state and effective saved sound', async () => {
    const f = ready()
    for (const patch of [{ userId: null }, { featureEnabled: false }, { hidden: true }, { emergency: true }]) {
      const before = f.inputs(); f.change(patch)
      expect(await f.runtime.playPreview('single')).toBe(false); f.change(before)
      f.runtime.setSavedCoachPreferences('user-a', prefs)
    }
    for (const general of [{ soundEnabled: false }, { voiceHintsEnabled: false }, { volume: 0 }]) {
      f.change({ general: { soundEnabled: true, voiceHintsEnabled: true, volume: 0.7, ...general } })
      expect(await f.runtime.playPreview('single')).toBe(false)
    }
    f.change({ general: { soundEnabled: true, voiceHintsEnabled: true, volume: 0.7 } })
    for (const patch of [{ enabled: false }, { voiceVolume: 0 }, { mode: 'text-only' as const, networkConsentVersion: 1 as const }]) {
      f.runtime.setSavedCoachPreferences('user-a', { ...prefs, ...patch })
      expect(await f.runtime.playPreview('single')).toBe(false)
    }
    expect(f.unlock).not.toHaveBeenCalled(); expect(fetch).not.toHaveBeenCalled()
  })

  it('preserves lifetime ID budget across stop/mute/voice toggles; recreates only for new user/run', async () => {
    const f = ready(); await f.runtime.playPreview('single')
    const manager = f.createManager.mock.results[0].value as LocalCoachAudioManager
    f.runtime.stopPreview()
    f.change({ general: { ...f.inputs().general, soundEnabled: false } })
    f.change({ general: { ...f.inputs().general, soundEnabled: true } })
    f.runtime.setSavedCoachPreferences('user-a', { ...prefs, revision: 2, voiceProfile: 'cedar' })
    await f.runtime.playPreview('single')
    expect(f.createManager).toHaveBeenCalledTimes(1)
    expect(manager.snapshot().counters.enqueued).toBe(2)
    f.change({ session: session('workout-summary') }); await f.runtime.playPreview('single')
    expect(manager.snapshot().disposed).toBe(true); expect(f.createManager).toHaveBeenCalledTimes(2)
    f.change({ userId: 'user-b' }); f.runtime.setSavedCoachPreferences('user-b', prefs)
    await f.runtime.playPreview('single'); expect(f.createManager).toHaveBeenCalledTimes(3)
  })

  it('uses canonical runId, not session id, and retires the old manager on a new run', async () => {
    const f = ready(), closed = { ...session('workout-summary'), runId: 'run-a' }
    f.change({ session: closed }); await f.runtime.playPreview('single')
    const old = f.createManager.mock.results[0].value as LocalCoachAudioManager
    expect(old.snapshot().utterances[0].scope.runId).toBe('run-a')
    f.change({ session: { ...closed, runId: 'run-b' } }); await f.runtime.playPreview('single')
    expect(old.snapshot().disposed).toBe(true)
    expect(f.runtime.getSnapshot().audio!.utterances[0].scope.runId).toBe('run-b')
  })

  it('never publishes user A audio diagnostics under user B during synchronous cancellation', async () => {
    const f = ready(); await f.runtime.playPreview('single'); f.clock.advance(20, f.context)
    const seen: ReturnType<LocalAudioRuntime['getSnapshot']>[] = []
    f.runtime.subscribe(() => { seen.push(f.runtime.getSnapshot()) })
    f.change({ userId: 'user-b' })
    expect(seen.length).toBeGreaterThan(0)
    expect(seen.every(snapshot => snapshot.userId === 'user-b' && snapshot.audio === null && !snapshot.preferencesReady)).toBe(true)
  })

  it('same-exercise set transitions preserve started but cancel pending using updateScope; exercise boundaries cancel all', async () => {
    const f = ready(), closed = session('workout-summary')
    f.change({ session: closed }); await f.runtime.playPreview('overlap')
    f.clock.advance(20, f.context)
    expect(f.runtime.getSnapshot().audio).toMatchObject({ active: 1, pending: 2 })
    f.change({ session: { ...closed, currentSetIndex: 1 } })
    expect(f.runtime.getSnapshot().audio).toMatchObject({ active: 1, pending: 0 })
    expect(f.context.sources[0].stop).not.toHaveBeenCalled()
    f.change({ session: { ...closed, currentSetIndex: 1, currentExerciseId: 'exercise-b' } })
    expect(f.runtime.getSnapshot().audio?.active).toBe(0)
    expect(f.context.sources[0].stop).toHaveBeenCalled(); expect(f.createManager).toHaveBeenCalledTimes(1)
  })

  it('disposes subscriptions/sources idempotently without shared-context ownership or automatic resume', async () => {
    const f = ready(); await f.runtime.playPreview('overlap'); f.clock.advance(180, f.context)
    const listener = vi.fn(); f.runtime.subscribe(listener)
    f.runtime.dispose(); f.runtime.dispose()
    expect(f.subscriptions.size).toBe(0); expect(f.clock.pendingTimers).toBe(0)
    expect(f.runtime.getSnapshot()).toMatchObject({ reason: 'disposed', previewAllowed: false, audio: null })
    expect(f.context.close).not.toHaveBeenCalled(); expect(f.context.suspend).not.toHaveBeenCalled(); expect(f.context.resume).not.toHaveBeenCalled()
    const calls = listener.mock.calls.length
    f.change({ hidden: true }); f.runtime.stopPreview(); expect(await f.runtime.playPreview('single')).toBe(false)
    expect(listener).toHaveBeenCalledTimes(calls)
  })
})

describe('default singleton store adapter', () => {
  it('observes app/runtime/hardware/saved-general and visibility without writes, requests, or context construction', () => {
    vi.stubEnv('VITE_COACH_ENABLED', 'true')
    const context = vi.fn(); vi.stubGlobal('AudioContext', context)
    useAppStore.setState({ selectedUserId: 'user-a', emergencyStopActive: false })
    useRuntimeStore.setState({ session: null }); useHardwareStore.setState({ snapshot: hardware() })
    useStage4Store.setState({ settingsSaved: { soundEnabled: true, voiceHintsEnabled: true, signalVolume: '70%' } })
    const runtime = new LocalAudioRuntime(); runtimes.push(runtime)
    runtime.setSavedCoachPreferences('user-a', prefs)
    expect(runtime.getSnapshot().previewAllowed).toBe(true)
    const initial = runtime.getSnapshot()
    const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
    document.dispatchEvent(new Event('visibilitychange'))
    expect(runtime.getSnapshot().reason).toBe('hidden')
    hidden.mockReturnValue(false); document.dispatchEvent(new Event('visibilitychange'))
    expect(runtime.getSnapshot().previewAllowed).toBe(true)
    const afterVisibility = runtime.getSnapshot()
    useStage4Store.setState({ settingsDraft: { soundEnabled: false } })
    expect(runtime.getSnapshot()).toBe(afterVisibility)
    expect(initial.audio).toBeNull()
    useStage4Store.setState({ settingsSaved: { soundEnabled: false, voiceHintsEnabled: true, signalVolume: '70%' } })
    expect(runtime.getSnapshot().reason).toBe('mute')
    useAppStore.setState({ emergencyStopActive: true }); expect(runtime.getSnapshot().reason).toBe('safety')
    useAppStore.setState({ emergencyStopActive: false })
    useHardwareStore.setState({ snapshot: hardware({ control: { spotterActive: true } }) })
    useHardwareStore.setState({ snapshot: null }); expect(runtime.getSnapshot().reason).toBe('safety')
    useHardwareStore.setState({ snapshot: hardware() })
    useRuntimeStore.setState({ session: session('rest') }); expect(runtime.getSnapshot().reason).toBe('runtime_session')
    useAppStore.setState({ selectedUserId: 'user-b' }); expect(runtime.getSnapshot().preferencesReady).toBe(false)
    expect(context).not.toHaveBeenCalled(); expect(fetch).not.toHaveBeenCalled()
    expect(useRuntimeStore.getState().session?.view).toBe('rest')
    expect(useStage4Store.getState().settingsDraft).toEqual({ soundEnabled: false })
  })
})