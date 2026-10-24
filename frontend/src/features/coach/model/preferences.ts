import { DEFAULT_COACH_SETTINGS, type CoachSettings } from './contracts'

export const COACH_STYLES = ['companion', 'calm', 'strict', 'showman', 'stoic'] as const
export const COACH_HUMOR_LEVELS = ['off', 'light', 'often'] as const
export const COACH_HUMOR_KINDS = ['roast', 'irony', 'absurd', 'wordplay', 'self'] as const
/** Coach characters (backend services/coach/personas.py); each brings its own default Fish voice. */
export const COACH_PERSONAS = ['streamer', 'classic'] as const
export const COACH_EXTRAS = ['callbacks', 'pop-culture', 'trivia', 'breathing'] as const
export type CoachStyle = typeof COACH_STYLES[number]
export type CoachHumorKind = typeof COACH_HUMOR_KINDS[number]
export type CoachExtra = typeof COACH_EXTRAS[number]
/** Same rule as the backend: letters separated by single spaces/hyphens, up to 24 chars. */
export const COACH_NICKNAME = /^(?:\p{L}+(?:[ -]\p{L}+)*)?$/u
/** Enum settings mirrored from backend `CoachPreferences`; the first value of each list is not necessarily the default. */
/** fish.audio library voice ID; empty means the server default voice. */
export const FISH_VOICE_ID = /^(?:[a-f0-9]{32})?$/
export const COACH_CHOICES = {
  persona: COACH_PERSONAS,
  voiceModel: ['openai-realtime', 'openai-tts', 'fish-drama-3'],
  voiceEmotion: ['off', 'subtle', 'expressive'],
  voiceEnergy: ['auto', 'calm', 'warm', 'bright'],
  voicePace: ['auto', 'normal', 'brisk'],
  pauseGap: ['short', 'normal', 'long'],
  verbosity: ['short', 'normal', 'detailed'],
  praise: ['rare', 'normal', 'generous'],
  goal: ['none', 'strength', 'hypertrophy', 'endurance', 'health'],
  experience: ['beginner', 'intermediate', 'advanced'],
  userGender: ['unspecified', 'm', 'f'],
  coachGender: ['unspecified', 'm', 'f'],
} as const
export const COACH_SWITCHES = ['greeting', 'exerciseIntro', 'setFeedback', 'exerciseSummary', 'workoutSummary', 'comparisons',
  'sayNumbers', 'sayExerciseName', 'saySetProgress', 'sayWeight', 'slang', 'profanity'] as const
export type CoachChoice = keyof typeof COACH_CHOICES
export type CoachSwitch = typeof COACH_SWITCHES[number]
export type CoachTuning = Readonly<{ [K in CoachChoice]: typeof COACH_CHOICES[K][number] } & { [K in CoachSwitch]: boolean }>
export const DEFAULT_COACH_TUNING: CoachTuning = Object.freeze<CoachTuning>({
  persona: 'streamer', voiceModel: 'fish-drama-3', voiceEmotion: 'expressive', voiceEnergy: 'auto', voicePace: 'auto', pauseGap: 'normal', verbosity: 'normal', praise: 'normal', goal: 'none',
  experience: 'intermediate', userGender: 'unspecified', coachGender: 'unspecified',
  greeting: true, exerciseIntro: true, setFeedback: true, exerciseSummary: true, workoutSummary: true, comparisons: true,
  sayNumbers: true, sayExerciseName: true, saySetProgress: true, sayWeight: true, slang: false, profanity: true,
})

export type CoachPreferences = CoachSettings & CoachTuning & Readonly<{
  networkConsentVersion: null | 1; voiceVolume: number | null; fishVoiceId: string
  style: CoachStyle; humor: typeof COACH_HUMOR_LEVELS[number]; humorKinds: readonly CoachHumorKind[]
  /** Explicit 18+ dark-humor opt-in. */
  edgyOptIn: boolean; extras: readonly CoachExtra[]; address: 'ty' | 'vy'; nickname: string
  duringSets: boolean; duringRest: boolean; assistantContext: string
  memoryEnabled: boolean; crossWorkoutMemory: boolean
}>
export const DEFAULT_COACH_PREFERENCES: CoachPreferences = Object.freeze<CoachPreferences>({
  ...DEFAULT_COACH_SETTINGS, ...DEFAULT_COACH_TUNING, networkConsentVersion: null, voiceVolume: null, fishVoiceId: '',
  // Default roast set (user decision 24.10.2026): streamer character, swearing, teasing, dark humor.
  style: 'companion', humor: 'often', humorKinds: ['roast', 'irony', 'absurd'], edgyOptIn: true, extras: [],
  address: 'ty', nickname: '', duringSets: true, duringRest: true, assistantContext: '',
  memoryEnabled: true, crossWorkoutMemory: false,
})

function tuningValid(p: CoachTuning): boolean {
  return (Object.keys(COACH_CHOICES) as CoachChoice[]).every(key => (COACH_CHOICES[key] as readonly string[]).includes(p[key])) &&
    COACH_SWITCHES.every(key => typeof p[key] === 'boolean')
}

/** Picks only the tuning fields; missing ones (older server) fall back to defaults. */
export function pickTuning(source: Record<string, unknown>): CoachTuning {
  const out: Record<string, unknown> = {}
  for (const key of [...Object.keys(COACH_CHOICES), ...COACH_SWITCHES]) out[key] = source[key] ?? DEFAULT_COACH_TUNING[key as keyof CoachTuning]
  return out as CoachTuning
}

function enumList(values: unknown, allowed: readonly string[]): boolean {
  return Array.isArray(values) && values.every(v => allowed.includes(v)) && new Set(values).size === values.length
}

export function preferencesValid(p: CoachPreferences): boolean {
  return p.schemaVersion === 1 && (p.consentVersion === null || p.consentVersion === 1) &&
    typeof p.memoryEnabled === 'boolean' && typeof p.crossWorkoutMemory === 'boolean' &&
    (p.networkConsentVersion === null || p.networkConsentVersion === 1) &&
    (!p.enabled || p.consentVersion === 1) &&
    (p.mode === 'local' || p.networkConsentVersion === 1) &&
    typeof p.budgetUsd === 'string' && /^\d{1,3}(\.\d{1,4})?$/.test(p.budgetUsd) &&
    Number(p.budgetUsd) > 0 && Number(p.budgetUsd) <= 2 &&
    (p.voiceVolume === null || (Number.isFinite(p.voiceVolume) && p.voiceVolume >= 0 && p.voiceVolume <= 1)) &&
    typeof p.fishVoiceId === 'string' && FISH_VOICE_ID.test(p.fishVoiceId) &&
    typeof p.assistantContext === 'string' && p.assistantContext.length <= 500 &&
    Number.isSafeInteger(p.revision) && p.revision >= 0 && typeof p.edgyOptIn === 'boolean' &&
    COACH_STYLES.includes(p.style) && COACH_HUMOR_LEVELS.includes(p.humor) &&
    enumList(p.humorKinds, COACH_HUMOR_KINDS) && enumList(p.extras, COACH_EXTRAS) &&
    (p.address === 'ty' || p.address === 'vy') &&
    typeof p.nickname === 'string' && p.nickname.length <= 24 && COACH_NICKNAME.test(p.nickname) && tuningValid(p)
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