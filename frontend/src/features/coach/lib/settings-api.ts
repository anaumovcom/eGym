import { coachVoice } from '../model/contracts'
import { preferencesValid, type CoachPreferences } from '../model/preferences'

export type CoachApiErrorCode = 'revision_conflict' | 'unauthorized' | 'rate_limited' | 'unavailable' | 'invalid_response' | 'request_failed' | 'aborted'
export class CoachApiError extends Error {
  readonly code: CoachApiErrorCode
  constructor(code: CoachApiErrorCode) { super(code); this.code = code; this.name = 'CoachApiError' }
}
export type OperatorSession = Readonly<{ authorized: boolean; setupAvailable: boolean }>
export type DailyUsage = Readonly<{ requests: number; settledMicros: number; pendingMicros: number; totalMicros: number }>
export type CredentialStatus = Readonly<{
  configured: boolean; credentialVersion: number; source: 'server-vault'; storageAvailable: boolean
  lastCheckStatus: 'not_checked' | 'auth_ok_models_not_verified' | 'auth_failed' | 'provider_unavailable' |
    'never' | 'unchecked' | 'ok' | 'valid' | 'invalid' | 'failed' | 'unavailable' | null
}>
type JsonObject = Record<string, unknown>
function object(value: unknown): JsonObject {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new CoachApiError('invalid_response')
  return value as JsonObject
}
function preferences(value: unknown): CoachPreferences {
  const p = object(value)
  if (typeof p.enabled !== 'boolean' || typeof p.historyConsent !== 'boolean' || typeof p.duringSets !== 'boolean' ||
      typeof p.duringRest !== 'boolean' || !['local', 'hybrid', 'text-only'].includes(String(p.mode)) ||
      !['quiet', 'companion', 'talkative'].includes(String(p.density)) || !['every', 'last-three', 'milestones', 'off'].includes(String(p.count)) ||
      !(p.voiceProfile === null || typeof p.voiceProfile === 'string') ||
      !(p.voiceVolume === null || typeof p.voiceVolume === 'number') || !preferencesValid(p as CoachPreferences)) throw new CoachApiError('invalid_response')
  // Pick only the public contract: never retain unknown server/provider fields.
  return { schemaVersion: 1, enabled: p.enabled, consentVersion: p.consentVersion as null | 1,
    mode: p.mode as CoachPreferences['mode'], density: p.density as CoachPreferences['density'], count: p.count as CoachPreferences['count'],
    voiceProfile: coachVoice(p.voiceProfile), historyConsent: p.historyConsent, revision: p.revision as number, budgetUsd: p.budgetUsd as string,
    networkConsentVersion: p.networkConsentVersion as null | 1, voiceVolume: p.voiceVolume as number | null,
    style: p.style as CoachPreferences['style'], humor: p.humor as CoachPreferences['humor'],
    humorKinds: [...p.humorKinds as CoachPreferences['humorKinds']], edgyOptIn: p.edgyOptIn as boolean,
    extras: [...p.extras as CoachPreferences['extras']], address: p.address as CoachPreferences['address'],
    nickname: p.nickname as string, duringSets: p.duringSets, duringRest: p.duringRest }
}
function session(value: unknown): OperatorSession {
  const s = object(value)
  if (typeof s.authorized !== 'boolean' || typeof s.setupAvailable !== 'boolean') throw new CoachApiError('invalid_response')
  return { authorized: s.authorized, setupAvailable: s.setupAvailable }
}
function status(value: unknown): CredentialStatus {
  const s = object(value)
  if (typeof s.configured !== 'boolean' || typeof s.storageAvailable !== 'boolean' || s.source !== 'server-vault' ||
      !Number.isSafeInteger(s.credentialVersion) || Number(s.credentialVersion) < 0 ||
      ![null, 'not_checked', 'auth_ok_models_not_verified', 'auth_failed', 'provider_unavailable', 'never', 'unchecked', 'ok', 'valid', 'invalid', 'failed', 'unavailable'].includes(s.lastCheckStatus as string | null)) throw new CoachApiError('invalid_response')
  return { configured: s.configured, credentialVersion: s.credentialVersion as number, source: 'server-vault',
    storageAvailable: s.storageAvailable, lastCheckStatus: s.lastCheckStatus as CredentialStatus['lastCheckStatus'] }
}
async function request(path: string, method: string, signal: AbortSignal, body?: unknown): Promise<unknown> {
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal.addEventListener('abort', abort, { once: true })
  if (signal.aborted) abort()
  const timeout = setTimeout(abort, 15_000)
  try {
    if (signal.aborted) throw new CoachApiError('aborted')
    const response = await fetch(`/api/coach/${path}`, { method, credentials: 'include', signal: controller.signal,
      headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
    if (controller.signal.aborted) throw new CoachApiError(signal.aborted ? 'aborted' : 'unavailable')
    if (!response.ok) {
      // Do not read error bodies: they can contain provider secrets or request echoes.
      throw new CoachApiError(response.status === 409 ? 'revision_conflict' : response.status === 401 || response.status === 403 ? 'unauthorized' :
        response.status === 429 ? 'rate_limited' : response.status === 404 || response.status === 503 ? 'unavailable' : 'request_failed')
    }
    if (response.status === 204) return null
    const value: unknown = await response.json()
    if (controller.signal.aborted) throw new CoachApiError(signal.aborted ? 'aborted' : 'unavailable')
    return value
  } catch (error) {
    if (signal.aborted) throw new CoachApiError('aborted')
    if (controller.signal.aborted) throw new CoachApiError('unavailable')
    if (error instanceof CoachApiError) throw error
    throw new CoachApiError('request_failed')
  } finally {
    clearTimeout(timeout)
    signal.removeEventListener('abort', abort)
  }
}
function userPath(userId: string) {
  if (!/^[a-zA-Z0-9_-]{1,128}$/.test(userId)) throw new CoachApiError('request_failed')
  return `users/${encodeURIComponent(userId)}/settings`
}
export const coachSettingsApi = {
  get: async (userId: string, signal: AbortSignal) => preferences(await request(userPath(userId), 'GET', signal)),
  save: async (userId: string, settings: CoachPreferences, expectedRevision: number, signal: AbortSignal) => {
    if (!preferencesValid(settings)) throw new CoachApiError('request_failed')
    const saved = preferences(await request(userPath(userId), 'PUT', signal, { schemaVersion: 1, expectedRevision, settings }))
    if (saved.revision !== expectedRevision + 1) throw new CoachApiError('invalid_response')
    return saved
  },
  session: async (signal: AbortSignal) => session(await request('operator/session', 'GET', signal)),
  login: async (password: string, signal: AbortSignal) => {
    const s = object(await request('operator/session', 'POST', signal, { schemaVersion: 1, password }))
    if (s.authorized !== true) throw new CoachApiError('invalid_response')
    return { authorized: true, setupAvailable: true } as const
  },
  logout: async (signal: AbortSignal) => { await request('operator/session', 'DELETE', signal) },
  credentials: async (signal: AbortSignal) => status(await request('credentials', 'GET', signal)),
  putCredential: async (key: string, expectedVersion: number, signal: AbortSignal) => status(await request('credentials', 'PUT', signal, { schemaVersion: 1, key, expectedVersion })),
  deleteCredential: async (expectedVersion: number, signal: AbortSignal) => status(await request('credentials', 'DELETE', signal, { schemaVersion: 1, expectedVersion })),
  checkCredential: async (signal: AbortSignal) => status(await request('credentials/check', 'POST', signal)),
  /** Paid requests actually sent since `sinceMs` (local midnight) across all runs. */
  dailyUsage: async (sinceMs: number, signal: AbortSignal): Promise<DailyUsage> => {
    const u = object(await request(`usage/today?since=${encodeURIComponent((sinceMs / 1000).toFixed(3))}`, 'GET', signal))
    const fields = [u.requests, u.settledMicros, u.pendingMicros, u.totalMicros]
    if (!fields.every(value => Number.isSafeInteger(value) && Number(value) >= 0)) throw new CoachApiError('invalid_response')
    return { requests: u.requests as number, settledMicros: u.settledMicros as number, pendingMicros: u.pendingMicros as number, totalMicros: u.totalMicros as number }
  },
}
export function coachErrorMessage(error: unknown): string {
  const code = error instanceof CoachApiError ? error.code : 'request_failed'
  return code === 'revision_conflict' ? 'Настройки изменились на сервере. Загрузите актуальную версию; черновик сохранён на экране.' :
    code === 'unauthorized' ? 'Сессия оператора истекла или доступ запрещён. Войдите снова.' :
    code === 'rate_limited' ? 'Слишком много попыток входа. Подождите минуту и попробуйте снова.' :
    code === 'unavailable' ? 'Сервер Coach недоступен. Настройте операторский доступ и server vault на сервере.' :
    'Не удалось выполнить запрос Coach. Секретные данные не отображаются.'
}