import { LocalAudioRuntime, type LocalAudioRuntimeInputs } from '../src/features/coach/audio/local-audio-runtime'
import { LocalCoachAudioManager, type LocalAudioSnapshot } from '../src/features/coach/audio/local-coach-audio-manager'
import { LocalClipPreparer } from '../src/features/coach/audio/fixture-pack-storage'
import { DEFAULT_COACH_PREFERENCES } from '../src/features/coach/model/preferences'
export type { LocalAudioRuntimeSnapshot } from '../src/features/coach/audio/local-audio-runtime'

let context: AudioContext | null = null
let inputs: LocalAudioRuntimeInputs = {
  userId: 'e05-fixture', featureEnabled: true, hidden: false, emergency: false,
  session: null, hardware: null,
  general: { soundEnabled: true, voiceHintsEnabled: true, volume: 1 },
}
const listeners = new Set<() => void>()
export const activations: { active: boolean; trusted: boolean; before: string | null; after?: string }[] = []
let trusted = false
export function markTrusted(event: { isTrusted: boolean }) { trusted = event.isTrusted }
export function changeInputs(patch: Partial<LocalAudioRuntimeInputs>) {
  inputs = { ...inputs, ...patch }; listeners.forEach(listener => listener())
}
export const localAudioRuntime = new LocalAudioRuntime({
  read: () => inputs,
  subscribeInputs: listener => { listeners.add(listener); return () => { listeners.delete(listener) } },
  unlock: () => {
    const record = { active: navigator.userActivation.isActive, trusted, before: context?.state ?? null, after: '' }
    activations.push(record)
    context ??= new AudioContext()
    const current = context
    return current.resume().then(() => { record.after = current.state; return current.state === 'running' })
  },
  context: () => context,
  createManager: (audio, scope) => new LocalCoachAudioManager({ context: audio, scope }),
  createPreparer: audio => new LocalClipPreparer(audio),
  getPreferences: async () => ({ ...DEFAULT_COACH_PREFERENCES, enabled: true, consentVersion: 1, mode: 'local' }),
  now: () => performance.now(),
})
export const contextState = () => context?.state ?? null
export const history: LocalAudioSnapshot[] = []
localAudioRuntime.subscribe(() => { const audio = localAudioRuntime.getSnapshot().audio; if (audio) history.push(audio) })