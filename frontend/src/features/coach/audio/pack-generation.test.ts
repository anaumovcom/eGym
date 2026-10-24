import { afterEach, describe, expect, it, vi } from 'vitest'
import { generateCoachPack } from './pack-generation'

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

describe('explicit pack generation', () => {
  it('explains outdated database schema rather than claiming the server is unavailable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ detail: 'coach_schema_outdated' }, { status: 503 })))
    await expect(generateCoachPack('fish-streamer', 'alexey', '0.50', new AbortController().signal, vi.fn())).rejects.toThrow('База данных Coach требует обновления')
  })

  it('distinguishes server internal errors without exposing exception details', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ detail: 'coach_internal_error' }, { status: 500 })))
    await expect(generateCoachPack('fish-streamer', 'alexey', '0.50', new AbortController().signal, vi.fn())).rejects.toThrow('Ошибка сервера при подготовке фраз')
  })

  it('sends capped confirmation, polls progress, and keeps the run token out of URLs', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(Response.json({ state: 'queued', runId: 'run-1', runToken: 'secret-token', jobId: 'job-1' }))
      .mockResolvedValueOnce(Response.json({ state: 'completed', completed: 56, total: 56 }))
    vi.stubGlobal('fetch', fetch)
    const progress = vi.fn()
    await generateCoachPack('fish-streamer', 'alexey', '0.50', new AbortController().signal, progress)
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ userId: 'alexey', capUsd: '0.50', confirmPaid: true })
    expect(fetch.mock.calls[1][1].headers['X-Coach-Run-Token']).toBe('secret-token')
    expect(fetch.mock.calls.every(([url]) => !url.includes('secret-token'))).toBe(true)
    expect(progress).toHaveBeenCalledWith(56, 56)
  })

  it('requires operator login and never displays a provider error body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('secret provider key', { status: 403 })))
    await expect(generateCoachPack('ash', 'alexey', '1.00', new AbortController().signal, vi.fn())).rejects.toThrow('Доступ оператора Coach')
  })

  it('cancels a failed job and explains that generated clips are retained', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(Response.json({ state: 'queued', runId: 'run-1', runToken: 'token', jobId: 'job-1' }))
      .mockResolvedValueOnce(Response.json({ state: 'paused', completed: 3, total: 56 }))
      .mockResolvedValueOnce(Response.json({ state: 'cancelled' }))
    vi.stubGlobal('fetch', fetch)
    await expect(generateCoachPack('ash', 'alexey', '1.00', new AbortController().signal, vi.fn())).rejects.toThrow('Уже созданные фразы сохранены')
    expect(fetch.mock.calls[2][0]).toBe('/api/coach/runs/run-1/jobs/job-1/action')
    expect(JSON.parse(fetch.mock.calls[2][1].body)).toEqual({ action: 'cancel' })
  })
})