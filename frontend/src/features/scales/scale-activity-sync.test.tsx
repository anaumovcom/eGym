import { StrictMode } from 'react'
import { act, cleanup, render } from '@testing-library/react'
import { MemoryRouter, useNavigate, type NavigateFunction } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useRuntimeStore } from '@/stores/runtime-store'
import { useAppStore } from '@/stores/app-store'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import type { ScaleActivity } from './api'
import { ScaleActivitySync } from './scale-activity-sync'

let fetchMock: ReturnType<typeof vi.fn>
let navigate: NavigateFunction
function Navigation() { navigate = useNavigate(); return null }
function renderSync(path = '/dashboard', strict = false) {
  const content = <MemoryRouter initialEntries={[path]}><ScaleActivitySync /><Navigation /></MemoryRouter>
  return render(strict ? <StrictMode>{content}</StrictMode> : content)
}
const payloads = (): ScaleActivity[] => fetchMock.mock.calls.map(([, init]) => JSON.parse(String(init.body)))
const phases = () => payloads().map(item => item.phase)
function setView(view: RuntimeWorkoutSession['view']) {
  // Only the view is read by this observer; no workout actions/hardware commands are needed.
  act(() => useRuntimeStore.setState({ session: { view } as RuntimeWorkoutSession }))
}
beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-18T12:00:00Z'))
  sessionStorage.clear()
  useRuntimeStore.setState({ session: null, sessionSignature: null })
  useAppStore.setState({ selectedUserId: 'alexey' })
  fetchMock = vi.fn().mockImplementation(async () => new Response('{}', { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('ScaleActivitySync leases', () => {
  it.each([
    ['/dashboard', 'idle'], ['/progress?tab=photo', 'idle'], ['/profile', 'idle'],
    ['/exercise-summary', 'idle'], ['/workout-summary', 'idle'],
    ['/exercise-setup', 'setup'], ['/exercise-session', 'exercise'], ['/rest', 'rest'],
    ['/motor-calibration', 'setup'], ['/modbus', 'setup'], ['/modbus-debug', 'setup'],
    ['/settings/service/modbus', 'setup'], ['/exercise-setup/', 'setup'],
  ])('reports %s immediately as %s', (path, phase) => {
    renderSync(path)
    expect(phases()).toEqual([phase])
    expect(fetchMock).toHaveBeenCalledWith('/api/scales/activity', expect.objectContaining({ method: 'PUT' }))
    expect(payloads()[0].clientId).toMatch(/^[\da-f]{8}-[\da-f]{4}-4[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/i)
    expect(payloads()[0].sequence).toBeGreaterThanOrEqual(0)
    expect(Number.isInteger(payloads()[0].sequence)).toBe(true)
  })

  it('heartbeats every 5 seconds, transitions immediately, and never toggles persistent search', async () => {
    renderSync()
    await act(async () => { await vi.advanceTimersByTimeAsync(4999) })
    expect(phases()).toEqual(['idle'])
    await act(async () => { await vi.advanceTimersByTimeAsync(1) })
    for (const path of ['/exercise-setup', '/exercise-session', '/rest', '/progress', '/motor-calibration', '/workout-summary']) {
      act(() => navigate(path))
    }
    expect(phases()).toEqual(['idle', 'idle', 'setup', 'exercise', 'rest', 'idle', 'setup', 'idle'])
    expect(fetchMock.mock.calls.every(([url]) => url === '/api/scales/activity')).toBe(true)
    const sequences = payloads().map(item => item.sequence)
    expect(sequences.every((value, index) => index === 0 || value > sequences[index - 1])).toBe(true)
  })

  it('covers pending runtime transitions only on workout routes; dashboard/progress/summaries release stale sessions', () => {
    renderSync('/exercise-setup')
    const selectedUser = useAppStore.getState().selectedUserId
    setView('exercise-session')
    setView('rest')
    expect(phases()).toEqual(['setup', 'exercise', 'rest'])
    const session = useRuntimeStore.getState().session
    for (const path of ['/dashboard', '/progress', '/exercise-summary', '/workout-summary']) {
      act(() => navigate(path))
      expect(payloads().at(-1)?.phase).toBe('idle')
    }
    expect(useRuntimeStore.getState().session).toBe(session)
    expect(useAppStore.getState().selectedUserId).toBe(selectedUser)
    act(() => navigate('/motor-calibration'))
    expect(payloads().at(-1)?.phase).toBe('setup')
  })

  it('keeps the route paused when runtime view is already a summary or absent', () => {
    renderSync('/exercise-session')
    setView('exercise-summary')
    expect(phases()).toEqual(['exercise'])
    act(() => navigate('/rest'))
    expect(payloads().at(-1)?.phase).toBe('rest')
  })

  it('does not wait for hung requests and does not let late responses overwrite newer status', async () => {
    let resolveFirst: ((value: Response) => void) | undefined
    fetchMock.mockImplementationOnce(() => new Promise<Response>(resolve => { resolveFirst = resolve }))
    renderSync('/exercise-session')
    act(() => navigate('/progress'))
    expect(phases()).toEqual(['exercise', 'idle'])
    await act(async () => { resolveFirst?.(new Response('{"paused":true}', { headers: { 'Content-Type': 'application/json' } })) })
    expect(phases()).toEqual(['exercise', 'idle'])
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(phases()).toEqual(['exercise', 'idle', 'idle'])
  })

  it('treats offline/unsupported API errors as non-fatal and reasserts the phase after reconnect', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('offline'))
    fetchMock.mockResolvedValueOnce(new Response('{"detail":"unavailable"}', { status: 503, headers: { 'Content-Type': 'application/json' } }))
    renderSync('/rest')
    await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
    expect(phases()).toEqual(['rest', 'rest', 'rest'])
  })

  it('cleans up the heartbeat, releases idle and retains identity/monotonic sequence through StrictMode and remount', async () => {
    const first = renderSync('/exercise-session', true)
    expect(phases()).toEqual(['exercise', 'idle', 'exercise'])
    await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
    expect(phases()).toEqual(['exercise', 'idle', 'exercise', 'exercise'])
    first.unmount()
    expect(payloads().at(-1)?.phase).toBe('idle')
    const count = payloads().length
    await act(async () => { await vi.advanceTimersByTimeAsync(30000) })
    expect(payloads()).toHaveLength(count)
    vi.setSystemTime(new Date('2026-10-17T12:00:00Z'))
    renderSync('/rest')
    expect(new Set(payloads().map(item => item.clientId)).size).toBe(1)
    const sequences = payloads().map(item => item.sequence)
    expect(sequences.every((value, index) => index === 0 || value > sequences[index - 1])).toBe(true)
  })

  it('reuses the tab identity stored before a remount and supports disabled sessionStorage', () => {
    const id = 'adf29e27-0a59-4924-b3d0-14aa09762188'
    sessionStorage.setItem('egym-scales-client-id', id)
    const first = renderSync()
    expect(payloads()[0].clientId).toBe(id)
    first.unmount()
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('denied') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('denied') })
    expect(() => renderSync('/rest')).not.toThrow()
    expect(payloads().at(-1)?.phase).toBe('rest')
  })
})