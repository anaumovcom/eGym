import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CalibrationSessionPayload, CalibrationSpec, CalibrationState } from '@/features/motor/api/motor-api'
import { apiGet, apiPost } from '@/shared/api/client'
import { useCalibrationRun } from './use-calibration-run'

vi.mock('@/shared/api/client', async () => ({
  ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'),
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}))

const spec: CalibrationSpec = {
  code: 'S9', group: 'S', groupTitle: 'Статика', title: 'Масштаб силы', description: 'Эталонный груз.',
  priority: 'critical', priorityReason: 'Определяет силу, соответствующую заданному весу.',
  steps: [], durationS: 150, requires: [], produces: ['left.n_per_raw'], inputs: ['referenceKg'],
  implemented: true, runnable: true, status: 'missing', measuredAt: null,
}

const runningSession: CalibrationSessionPayload = {
  id: 'S9-1', code: 'S9', title: 'Масштаб силы', status: 'running', reason: null,
  startedAt: '2026-01-01T10:00:00Z', finishedAt: null, elapsedS: 1, progress: 0.1, currentStage: 'S9',
  note: '', deadManHeld: true, stages: [], changes: [], hasChanges: false, savedVersion: null,
  log: { t: [], xL: [], xR: [], vL: [], vR: [], fL: [], fR: [] },
}

function okPreconditions() {
  return [
    { id: 'service', label: 'Сервисный режим включён', ok: true, detail: null },
    { id: 'stops', label: 'Гриф на нижних упорах', ok: true, detail: null },
  ]
}

function middlePreconditions() {
  return [...okPreconditions(), { id: 'middleZone', label: 'Рабочая зона middle задана', ok: true, detail: null }]
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((yes) => { resolve = yes })
  return { promise, resolve }
}

let state: CalibrationState
let client: QueryClient

function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  state = { session: null, preconditions: okPreconditions(), profileVersion: 3 }
  vi.mocked(apiGet).mockReset()
  vi.mocked(apiPost).mockReset()
  vi.mocked(apiGet).mockImplementation(async <T,>(path: string): Promise<T> => {
    if (path.startsWith('/api/motor/calibration/session')) return state as T
    if (path.startsWith('/api/motor/calibration/runs')) return [] as T
    if (path.startsWith('/api/motor/calibrations')) return [spec] as T
    if (path.startsWith('/api/motor/parameters')) return { version: null, runtimeVersion: null, groups: [] } as T
    throw new Error(`Unexpected GET ${path}`)
  })
  vi.mocked(apiPost).mockImplementation(async <T,>(path: string): Promise<T> => {
    if (path.endsWith('/keepalive')) return { running: true } as T
    if (path.endsWith('/start')) { state = { ...state, session: runningSession }; return state as T }
    if (path.endsWith('/abort')) {
      state = { ...state, session: { ...runningSession, status: 'aborted' as const, reason: 'прервано оператором' } }
      return { session: state.session } as T
    }
    throw new Error(`Unexpected POST ${path}`)
  })
})

afterEach(() => { cleanup(); client.clear(); vi.restoreAllMocks() })

describe('useCalibrationRun', () => {
  it('gates canStart on enabled', async () => {
    const view = renderHook(({ enabled }) => useCalibrationRun({ code: 'S9', spec, enabled }), {
      wrapper, initialProps: { enabled: true },
    })
    await waitFor(() => expect(view.result.current.canStart).toBe(true))
    view.rerender({ enabled: false })
    await waitFor(() => expect(view.result.current.canStart).toBe(false))
  })

  it('requires non-empty preconditions that all pass', async () => {
    state = { ...state, preconditions: [{ id: 'service', label: 'Сервисный режим включён', ok: false, detail: null }] }
    const view = renderHook(() => useCalibrationRun({ code: 'S9', spec, enabled: true }), { wrapper })
    await waitFor(() => expect(view.result.current.state.data?.preconditions).toHaveLength(1))
    expect(view.result.current.canStart).toBe(false)

    state = { ...state, preconditions: [] }
    view.unmount()
    const empty = renderHook(() => useCalibrationRun({ code: 'S9', spec, enabled: true }), { wrapper })
    await waitFor(() => expect(empty.result.current.state.data?.preconditions).toEqual([]))
    expect(empty.result.current.canStart).toBe(false)
  })

  it('posts start exactly once on rapid double clicks', async () => {
    const view = renderHook(() => useCalibrationRun({ code: 'S9', spec, enabled: true }), { wrapper })
    await waitFor(() => expect(view.result.current.canStart).toBe(true))
    act(() => {
      void view.result.current.start(20)
      void view.result.current.start(20)
    })
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/start', { code: 'S9', referenceKg: 20 }))
    const starts = vi.mocked(apiPost).mock.calls.filter(([path]) => path.endsWith('/start'))
    expect(starts).toHaveLength(1)
  })

  it('does not take over heartbeat or reply of a foreign running session', async () => {
    state = { ...state, session: { ...runningSession, id: 'WIZARD-9', code: 'WIZARD' } }
    const view = renderHook(() => useCalibrationRun({ code: 'S9', spec, enabled: true }), { wrapper })
    await waitFor(() => expect(view.result.current.running).toBe(true))
    expect(view.result.current.ownsRun).toBe(false)
    await act(async () => { await view.result.current.reply('любой вопрос', 5) })
    expect(apiPost).not.toHaveBeenCalledWith('/api/motor/calibration/reply', expect.anything())
    expect(apiPost).not.toHaveBeenCalledWith('/api/motor/calibration/keepalive', expect.anything())
  })

  it('aborts only its own late session id after unmount', async () => {
    const startCall = deferred<CalibrationState>()
    vi.mocked(apiPost).mockImplementation(async <T,>(path: string): Promise<T> => {
      if (path.endsWith('/start')) return startCall.promise as Promise<T>
      if (path.endsWith('/abort')) return { session: null } as T
      if (path.endsWith('/keepalive')) return { running: true } as T
      throw new Error(path)
    })
    const view = renderHook(() => useCalibrationRun({ code: 'S9', spec, enabled: true }), { wrapper })
    await waitFor(() => expect(view.result.current.canStart).toBe(true))
    act(() => { void view.result.current.start() })
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/start', { code: 'S9' }))
    view.unmount()
    await act(async () => { startCall.resolve({ ...state, session: runningSession }) })
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/abort', { sessionId: 'S9-1' }))
  })

  it('passes workingZone to session/start and requires a valid middle zone', async () => {
    state = { ...state, preconditions: middlePreconditions(), workingZone: { lowMm: 10, highMm: 20 } }
    const view = renderHook(() => useCalibrationRun({ code: 'S9', spec, enabled: true, workingZone: 'middle' }), { wrapper })
    await waitFor(() => expect(view.result.current.canStart).toBe(true))
    expect(apiGet).toHaveBeenCalledWith('/api/motor/calibration/session?code=S9&workingZone=middle')
    act(() => { void view.result.current.start() })
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/start', { code: 'S9', workingZone: 'middle' }))
  })

  it('rejects an invalid middle zone even with a middleZone precondition', async () => {
    state = { ...state, preconditions: middlePreconditions(), workingZone: { lowMm: 20, highMm: 10 } }
    const view = renderHook(() => useCalibrationRun({ code: 'S9', spec, enabled: true, workingZone: 'middle' }), { wrapper })
    await waitFor(() => expect(view.result.current.state.data?.workingZone).toEqual({ lowMm: 20, highMm: 10 }))
    expect(view.result.current.canStart).toBe(false)
  })

  it('surfaces the server refusal to evict an unsaved result without posting start', async () => {
    const view = renderHook(() => useCalibrationRun({ code: 'S9', spec, enabled: true }), { wrapper })
    await waitFor(() => expect(view.result.current.canStart).toBe(true))
    state = {
      ...state,
      session: { ...runningSession, status: 'done' as const, finishedAt: '2026-01-01T10:02:00Z', hasChanges: true },
    }
    act(() => { void view.result.current.start() })
    await waitFor(() => expect(view.result.current.error).toContain('сохраните или отклоните'))
    expect(apiPost).not.toHaveBeenCalledWith('/api/motor/calibration/start', expect.anything())
  })

  it('aborts with the sessionId on STOP and clears ownership', async () => {
    const view = renderHook(() => useCalibrationRun({ code: 'S9', spec, enabled: true }), { wrapper })
    await waitFor(() => expect(view.result.current.canStart).toBe(true))
    act(() => { void view.result.current.start() })
    await waitFor(() => expect(view.result.current.running).toBe(true))
    expect(view.result.current.ownsRun).toBe(true)
    await act(async () => { await view.result.current.stop() })
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/abort', { sessionId: 'S9-1' }))
    expect(view.result.current.ownsRun).toBe(false)
  })
})
