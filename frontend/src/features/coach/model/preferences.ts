import { DEFAULT_COACH_SETTINGS, type CoachSettings } from './contracts'

export const COACH_STYLES = ['companion', 'calm', 'strict', 'showman', 'stoic'] as const
export const COACH_HUMOR_LEVELS = ['off', 'light', 'often'] as const
export const COACH_HUMOR_KINDS = ['irony', 'absurd', 'wordplay', 'self'] as const
export const COACH_EXTRAS = ['callbacks', 'pop-culture', 'trivia', 'breathing'] as const
export type CoachStyle = typeof COACH_STYLES[number]
export type CoachHumorKind = typeof COACH_HUMOR_KINDS[number]
export type CoachExtra = typeof COACH_EXTRAS[number]
/** Same rule as the backend: letters separated by single spaces/hyphens, up to 24 chars. */
export const COACH_NICKNAME = /^(?:\p{L}+(?:[ -]\p{L}+)*)?$/u

export type CoachPreferences = CoachSettings & Readonly<{
  networkConsentVersion: null | 1; voiceVolume: number | null
  style: CoachStyle; humor: typeof COACH_HUMOR_LEVELS[number]; humorKinds: readonly CoachHumorKind[]
  /** Explicit 18+ dark-humor opt-in. */
  edgyOptIn: boolean; extras: readonly CoachExtra[]; address: 'ty' | 'vy'; nickname: string
  duringSets: boolean; duringRest: boolean
}>
export const DEFAULT_COACH_PREFERENCES: CoachPreferences = Object.freeze<CoachPreferences>({
  ...DEFAULT_COACH_SETTINGS, networkConsentVersion: null, voiceVolume: null,
  style: 'companion', humor: 'light', humorKinds: ['irony', 'self'], edgyOptIn: false, extras: [],
  address: 'ty', nickname: '', duringSets: true, duringRest: true,
})

function enumList(values: unknown, allowed: readonly string[]): boolean {
  return Array.isArray(values) && values.every(v => allowed.includes(v)) && new Set(values).size === values.length
}

export function preferencesValid(p: CoachPreferences): boolean {
  return p.schemaVersion === 1 && (p.consentVersion === null || p.consentVersion === 1) &&
    (p.networkConsentVersion === null || p.networkConsentVersion === 1) &&
    (!p.enabled || p.consentVersion === 1) &&
    (p.mode === 'local' || p.networkConsentVersion === 1) &&
    typeof p.budgetUsd === 'string' && /^\d{1,3}(\.\d{1,4})?$/.test(p.budgetUsd) &&
    Number(p.budgetUsd) > 0 && Number(p.budgetUsd) <= 2 &&
    (p.voiceVolume === null || (Number.isFinite(p.voiceVolume) && p.voiceVolume >= 0 && p.voiceVolume <= 1)) &&
    Number.isSafeInteger(p.revision) && p.revision >= 0 && typeof p.edgyOptIn === 'boolean' &&
    COACH_STYLES.includes(p.style) && COACH_HUMOR_LEVELS.includes(p.humor) &&
    enumList(p.humorKinds, COACH_HUMOR_KINDS) && enumList(p.extras, COACH_EXTRAS) &&
    (p.address === 'ty' || p.address === 'vy') &&
    typeof p.nickname === 'string' && p.nickname.length <= 24 && COACH_NICKNAME.test(p.nickname)
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