import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { DEFAULT_COACH_PREFERENCES as defaults } from '../model/preferences'
import { CoachApiError, coachErrorMessage, coachSettingsApi as api } from './settings-api'

const fetchMock = vi.fn()
const credential = { configured: false, credentialVersion: 0, source: 'server-vault', storageAvailable: true, lastCheckStatus: null }
const signal = () => new AbortController().signal
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock) })
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })
const reply = (value: unknown) => ({ ok: true, status: 200, json: async () => value })
describe('Coach-only safe fetch', () => {
  it.each(['not_checked', 'auth_ok_models_not_verified', 'auth_failed', 'provider_unavailable'])('accepts real server credential status %s', async lastCheckStatus => {
    fetchMock.mockResolvedValue(reply({ ...credential, lastCheckStatus }))
    expect((await api.credentials(signal())).lastCheckStatus).toBe(lastCheckStatus)
  })
  it('uses fixed internal path, cookie credentials, JSON, signal; filters unknown fields', async () => {
    fetchMock.mockResolvedValue(reply({ ...defaults, secretEcho: 'must-not-retain' }))
    const abort = signal()
    expect(await api.get('actual-user', abort)).toEqual(defaults)
    expect(fetchMock).toHaveBeenCalledWith('/api/coach/users/actual-user/settings', expect.objectContaining({ credentials: 'include', signal: expect.any(AbortSignal), method: 'GET' }))
  })
  it.each(['../../credentials', 'https://example.org', 'user/path', '', 'user?query'])('rejects unsafe user paths %s without fetching', async id => {
    await expect(api.get(id, signal())).rejects.toMatchObject({ code: 'request_failed' })
    expect(fetchMock).not.toHaveBeenCalled()
  })
  it('saves explicit schema/revision and requires increment', async () => {
    fetchMock.mockResolvedValue(reply({ ...defaults, revision: 1 }))
    await api.save('A', defaults, 0, signal())
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ schemaVersion: 1, expectedRevision: 0, settings: defaults })
    fetchMock.mockResolvedValue(reply(defaults))
    await expect(api.save('A', defaults, 0, signal())).rejects.toMatchObject({ code: 'invalid_response' })
  })
  it.each([409, 401, 403, 404, 500, 503])('normalizes HTTP %s without reading provider body', async status => {
    const json = vi.fn().mockRejectedValue(new Error('provider-secret'))
    fetchMock.mockResolvedValue({ ok: false, status, json })
    await expect(api.get('A', signal())).rejects.toBeInstanceOf(CoachApiError)
    expect(json).not.toHaveBeenCalled()
  })
  it('normalizes network/JSON errors without retaining secret messages or causes', async () => {
    fetchMock.mockRejectedValue(new Error('secret-key'))
    try { await api.login('secret-password', signal()) } catch (error) {
      expect(String(error)).not.toContain('secret')
      expect((error as Error).cause).toBeUndefined()
      expect(coachErrorMessage(error)).not.toContain('secret')
    }
    fetchMock.mockResolvedValue({ ...reply(null), json: async () => { throw new Error('secret-json') } })
    await expect(api.credentials(signal())).rejects.toMatchObject({ code: 'request_failed' })
  })
  it.each([{ ...defaults, enabled: 'true' }, { ...defaults, voiceVolume: 2 }, { ...defaults, schemaVersion: 2 }, { ...defaults, edgyOptIn: true }])('validates external preferences %j', async bad => {
    fetchMock.mockResolvedValue(reply(bad))
    await expect(api.get('A', signal())).rejects.toMatchObject({ code: 'invalid_response' })
  })
  it('rejects late response when fetch ignores abort', async () => {
    const controller = new AbortController()
    fetchMock.mockImplementation(async () => { controller.abort(); return reply(defaults) })
    await expect(api.get('A', controller.signal)).rejects.toMatchObject({ code: 'aborted' })
  })
  it('bounds request time and normalizes timeout without provider errors', async () => {
    vi.useFakeTimers()
    fetchMock.mockImplementation((_path, init) => new Promise((_resolve, reject) => {
      init.signal.addEventListener('abort', () => reject(new Error('secret-timeout')), { once: true })
    }))
    const pending = expect(api.get('A', signal())).rejects.toMatchObject({ code: 'unavailable' })
    await vi.advanceTimersByTimeAsync(15_000)
    await pending
  })
  it('operator and vault protocol uses only transient secrets and no user/PIN', async () => {
    fetchMock.mockResolvedValueOnce(reply({ authorized: false, setupAvailable: true }))
      .mockResolvedValueOnce(reply({ authorized: true })).mockResolvedValueOnce(reply(credential))
      .mockResolvedValueOnce(reply({ ...credential, credentialVersion: 1 })).mockResolvedValueOnce(reply({ ...credential, credentialVersion: 1 }))
      .mockResolvedValueOnce(reply({ ...credential, credentialVersion: 2 })).mockResolvedValueOnce({ ok: true, status: 204 })
    const abort = signal()
    await api.session(abort); await api.login('operator-password', abort); await api.credentials(abort)
    await api.putCredential('provider-key', 0, abort); await api.checkCredential(abort); await api.deleteCredential(1, abort); await api.logout(abort)
    expect(fetchMock.mock.calls.map(([path, init]) => [path, init.method])).toEqual([
      ['/api/coach/operator/session', 'GET'], ['/api/coach/operator/session', 'POST'], ['/api/coach/credentials', 'GET'],
      ['/api/coach/credentials', 'PUT'], ['/api/coach/credentials/check', 'POST'], ['/api/coach/credentials', 'DELETE'], ['/api/coach/operator/session', 'DELETE'],
    ])
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ schemaVersion: 1, password: 'operator-password' })
    expect(JSON.parse(fetchMock.mock.calls[3][1].body)).toEqual({ schemaVersion: 1, key: 'provider-key', expectedVersion: 0 })
    expect(fetchMock.mock.calls[4][1]).not.toHaveProperty('body')
    expect(JSON.parse(fetchMock.mock.calls[5][1].body)).toEqual({ schemaVersion: 1, expectedVersion: 1 })
  })
})