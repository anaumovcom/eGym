import { DEFAULT_COACH_SETTINGS, type CoachSettings } from './contracts'

export type CoachPreferences = CoachSettings & Readonly<{
  networkConsentVersion: null | 1; voiceVolume: number | null
  style: 'companion' | 'calm'; humor: 'off' | 'light' | 'often'; edgyOptIn: false
  duringSets: boolean; duringRest: boolean
}>
export const DEFAULT_COACH_PREFERENCES: CoachPreferences = Object.freeze({
  ...DEFAULT_COACH_SETTINGS, networkConsentVersion: null, voiceVolume: null,
  style: 'companion', humor: 'light', edgyOptIn: false, duringSets: true, duringRest: true,
})

export function preferencesValid(p: CoachPreferences): boolean {
  return p.schemaVersion === 1 && (p.consentVersion === null || p.consentVersion === 1) &&
    (p.networkConsentVersion === null || p.networkConsentVersion === 1) &&
    (!p.enabled || p.consentVersion === 1) &&
    (p.mode === 'local' || p.networkConsentVersion === 1) &&
    typeof p.budgetUsd === 'string' && /^\d{1,3}(\.\d{1,4})?$/.test(p.budgetUsd) &&
    Number(p.budgetUsd) > 0 && Number(p.budgetUsd) <= 2 &&
    (p.voiceVolume === null || (Number.isFinite(p.voiceVolume) && p.voiceVolume >= 0 && p.voiceVolume <= 1)) &&
    Number.isSafeInteger(p.revision) && p.revision >= 0 && p.edgyOptIn === false
}

export type GeneralCoachAudio = Readonly<{ soundEnabled: boolean; voiceHintsEnabled: boolean; volume: number }>
/** Admission only; this does not imply provider, pack, ledger or playback readiness. */
export function effectiveCoachState(saved: CoachPreferences | null, general: GeneralCoachAudio, featureEnabled: boolean) {
  const volume = Math.min(1, Math.max(0, Number.isFinite(general.volume) ? general.volume : 0))
  const allowed = featureEnabled && !!saved && preferencesValid(saved) && saved.enabled && saved.consentVersion === 1
  const textEnabled = allowed && saved?.mode === 'text-only'
  const voiceVolume = saved?.voiceVolume ?? volume
  const audioEnabled = allowed && saved?.mode !== 'text-only' && general.soundEnabled && general.voiceHintsEnabled && volume > 0 && voiceVolume > 0
  return { textEnabled, audioEnabled, volume: audioEnabled ? voiceVolume : 0, paidProductionReady: false as const }
}