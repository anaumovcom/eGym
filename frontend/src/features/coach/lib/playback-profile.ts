import { DEFAULT_COACH_PREFERENCES, preferencesValid, type CoachPreferences } from '../model/preferences'
import { COACH_VOICES } from '../model/contracts'
import { CoachApiError, coachSettingsApi } from './settings-api'

// Device-only, per-user knobs. Never store prompts, names, histories, keys, run tokens or network consent.
const fields = ['standardPack', 'enabled', 'consentVersion', 'count', 'duringSets', 'duringRest', 'revision',
  'voiceProfile', 'voiceModel', 'fishVoiceId', 'persona', 'voiceVolume'] as const
const key = (user: string) => `egym:coach-playback:1:${user}`

export function rememberPlaybackProfile(user: string, p: CoachPreferences) {
  if ((cached(user)?.revision ?? -1) > p.revision) return
  try { localStorage.setItem(key(user), JSON.stringify(Object.fromEntries(fields.map(field => [field, p[field]])))) } catch { /* Storage is optional. */ }
}
function cached(user: string): CoachPreferences | null {
  try {
    const raw = JSON.parse(localStorage.getItem(key(user)) ?? 'null')
    if (!raw || !fields.every(field => Object.hasOwn(raw, field)) || !COACH_VOICES.includes(raw.voiceProfile) ||
        !['every', 'last-three', 'milestones', 'off'].includes(raw.count) ||
        !['enabled', 'standardPack', 'duringSets', 'duringRest'].every(f => typeof raw[f] === 'boolean')) return null
    const prefs = { ...DEFAULT_COACH_PREFERENCES, ...Object.fromEntries(fields.map(field => [field, raw[field]])) }
    return preferencesValid(prefs) ? prefs : null
  } catch { return null }
}
export async function loadPlaybackProfile(user: string, signal: AbortSignal) {
  try {
    const value = await coachSettingsApi.get(user, signal)
    if (!signal.aborted) rememberPlaybackProfile(user, value)
    return { value, offline: false }
  } catch (error) {
    if (!signal.aborted && error instanceof CoachApiError) {
      if (error.code === 'offline' || error.code === 'unavailable') {
        const value = cached(user)
        if (value) return { value, offline: true }
      } else if (error.code !== 'aborted') {
        try { localStorage.removeItem(key(user)) } catch { /* Fail closed. */ }
      }
    }
    throw error
  }
}