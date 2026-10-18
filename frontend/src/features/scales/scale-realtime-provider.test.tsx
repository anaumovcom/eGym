import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { playExerciseEventSound } from '@/features/runtime/lib/exercise-event-sounds'
import { useAppStore } from '@/stores/app-store'
import { scaleKeys, scalesApi, type ScaleMeasurement, type ScaleStatus } from './api'
import { ScaleRealtimeProvider } from './scale-realtime-provider'

vi.mock('@/features/runtime/lib/exercise-event-sounds', () => ({ playExerciseEventSound: vi.fn() }))

class Socket {
  static instances: Socket[] = []
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  close = vi.fn()
  constructor(public url: string) { Socket.instances.push(this) }
  message(value: unknown) { this.onmessage?.({ data: JSON.stringify(value) }) }
}
const initial: ScaleStatus = { enabled: true, paused: false, pauseReason: null, bluetoothAvailable: true, scanning: true, scanningMode: 'active', measuring: false, deviceId: 'AA', lastSeen: null, lastMeasurement: null, devices: [], error: null, warning: null }
const now = Date.parse('2026-10-18T12:00:00Z')
const measurement = (id: number, patch: Partial<ScaleMeasurement> = {}): ScaleMeasurement => ({ id, userId: 'alexey', weightKg: 80.5, timestamp: new Date(now + 100).toISOString(), stable: true, deviceId: 'AA', impedanceOhm: null, ...patch })
let client: QueryClient
let rest: ScaleStatus
function renderObserver() { return render(<QueryClientProvider client={client}><ScaleRealtimeProvider /><div>Любой экран</div></QueryClientProvider>) }
async function flush(ms = 10) { await act(async () => { await vi.advanceTimersByTimeAsync(ms) }) }
async function send(item: ScaleMeasurement | null) { act(() => Socket.instances.at(-1)!.message({ ...initial, lastMeasurement: item })); await flush() }

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(now)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  rest = initial
  Socket.instances = []
  vi.stubGlobal('WebSocket', Socket)
  vi.spyOn(scalesApi, 'status').mockImplementation(async () => rest)
  vi.spyOn(scalesApi, 'history').mockResolvedValue({ measurements: [] })
  useAppStore.setState({ selectedUserId: 'alexey' })
})
afterEach(() => { cleanup(); client.clear(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.mocked(playExerciseEventSound).mockClear() })

describe('ScaleRealtimeProvider', () => {
  it.each([
    [81, '−0,5 кг', 'text-sky-200'],
    [80, '+0,5 кг', 'text-amber-200'],
    [80.5, 'Без изменений с прошлого замера', 'text-white/65'],
  ])('compares with the previous owner measurement (%s kg) with a directional indicator', async (weightKg, text, tone) => {
    vi.mocked(scalesApi.history).mockResolvedValue({ measurements: [
      measurement(2),
      measurement(7, { userId: 'elena', weightKg: 50, timestamp: '2026-10-18T11:59:00Z' }),
      measurement(1, { weightKg, timestamp: '2026-10-17T12:00:00Z' }),
      measurement(0, { weightKg: 99, timestamp: '2026-10-16T12:00:00Z' }),
    ] })
    renderObserver()
    await flush()
    await send(measurement(2))
    await flush()
    const indicator = screen.getByText(text)
    expect(indicator).toBeVisible()
    expect(indicator.closest('.border')).toHaveClass(tone)
    expect(screen.getByText(new RegExp(`Было ${String(weightKg).replace('.', ',')} кг`))).toBeVisible()
    expect(playExerciseEventSound).toHaveBeenCalledTimes(1)
  })

  it('labels a first measurement and handles unavailable comparison without inventing a delta', async () => {
    renderObserver()
    await flush()
    await send(measurement(1))
    await flush()
    expect(screen.getByText('Первое взвешивание')).toBeVisible()
    vi.mocked(scalesApi.history).mockRejectedValue(new Error('offline'))
    await send(measurement(2, { timestamp: new Date(now + 200).toISOString() }))
    await flush()
    expect(screen.getByText('Не удалось загрузить прошлый замер')).toBeVisible()
    expect(screen.queryByText('Первое взвешивание')).not.toBeInTheDocument()
  })

  it('ignores old initial history, notifies once globally for fresh ids and suppresses impedance/heartbeat/deletion', async () => {
    rest = { ...initial, lastMeasurement: measurement(10, { timestamp: '2026-10-17T12:00:00Z' }) }
    renderObserver()
    await flush()
    expect(screen.queryByText('Вес сохранён')).not.toBeInTheDocument()
    expect(playExerciseEventSound).not.toHaveBeenCalled()
    await send(measurement(11))
    expect(screen.getByText('Вес сохранён')).toBeVisible()
    expect(playExerciseEventSound).toHaveBeenCalledExactlyOnceWith('success')
    await send(measurement(11, { impedanceOhm: 510 }))
    await send(measurement(11))
    await send(measurement(9, { timestamp: new Date(now).toISOString() }))
    await send(null)
    await send(measurement(11))
    expect(playExerciseEventSound).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть уведомление' }))
    expect(screen.queryByText('Вес сохранён')).not.toBeInTheDocument()
    await send(measurement(12))
    expect(playExerciseEventSound).toHaveBeenCalledTimes(2)
    await flush(6000)
    expect(screen.queryByText('Вес сохранён')).not.toBeInTheDocument()
  })

  it('notifies for a genuinely fresh first REST measurement (including cached data)', async () => {
    rest = { ...initial, lastMeasurement: measurement(20, { timestamp: new Date(now).toISOString() }) }
    client.setQueryData(scaleKeys.status, rest)
    renderObserver()
    await flush()
    expect(screen.getByText('Вес сохранён')).toBeVisible()
    expect(playExerciseEventSound).toHaveBeenCalledExactlyOnceWith('success')
  })

  it('suppresses deletion fallback then notifies once for a reused id with a later timestamp', async () => {
    renderObserver()
    await flush()
    await send(measurement(11))
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть уведомление' }))

    // An unseen fallback is still newer than mount, but older than the deleted row.
    const fallback = measurement(10, { timestamp: new Date(now + 50).toISOString() })
    await send(null)
    await send(fallback)
    rest = { ...initial, lastMeasurement: fallback }
    await flush(5000)
    expect(screen.queryByText('Вес сохранён')).not.toBeInTheDocument()
    expect(playExerciseEventSound).toHaveBeenCalledTimes(1)

    const reused = measurement(11, { timestamp: new Date(now + 6000).toISOString() })
    await send(reused)
    expect(screen.getByText('Вес сохранён')).toBeVisible()
    expect(playExerciseEventSound).toHaveBeenCalledTimes(2)
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть уведомление' }))
    await send({ ...reused, impedanceOhm: 510 })
    await send(reused)
    rest = { ...initial, lastMeasurement: reused }
    await flush(5000)
    await send(measurement(11))
    expect(screen.queryByText('Вес сохранён')).not.toBeInTheDocument()
    expect(playExerciseEventSound).toHaveBeenCalledTimes(2)
  })

  it('invalidates the actual owner but only notifies the active profile, with no replay on switching', async () => {
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    renderObserver()
    await flush()
    await send(measurement(1, { userId: 'elena' }))
    for (const queryKey of [scaleKeys.history('elena'), scaleKeys.latest('elena'), ['progress-screen', 'elena'], ['user-profile-screen', 'elena']]) expect(invalidate).toHaveBeenCalledWith({ queryKey })
    expect(invalidate).not.toHaveBeenCalledWith({ queryKey: ['progress-screen', 'alexey'] })
    expect(playExerciseEventSound).not.toHaveBeenCalled()
    act(() => useAppStore.setState({ selectedUserId: 'elena' }))
    await send(measurement(1, { userId: 'elena' }))
    expect(playExerciseEventSound).not.toHaveBeenCalled()
    await send(measurement(2, { userId: 'elena' }))
    expect(screen.getByText('Вес сохранён')).toBeVisible()
    act(() => useAppStore.setState({ selectedUserId: 'alexey' }))
    expect(screen.queryByText('Вес сохранён')).not.toBeInTheDocument()
    expect(Socket.instances).toHaveLength(1)
  })

  it('keeps the watermark on reconnect, rejects old higher ids and polls fresh REST fallback', async () => {
    renderObserver()
    await flush()
    await send(measurement(20))
    fireEvent.click(screen.getByRole('button', { name: 'Закрыть уведомление' }))
    act(() => Socket.instances[0].onclose?.())
    await flush(2000)
    expect(Socket.instances).toHaveLength(2)
    await send(measurement(20))
    await send(measurement(21, { timestamp: '2026-10-17T12:00:00Z' }))
    expect(screen.queryByText('Вес сохранён')).not.toBeInTheDocument()
    rest = { ...initial, lastMeasurement: measurement(22) }
    await flush(5000)
    expect(screen.getByText('Вес сохранён')).toBeVisible()
    expect(playExerciseEventSound).toHaveBeenCalledTimes(2)
  })

  it('ignores malformed frames and cleans up reconnect/polling/socket handlers', async () => {
    const view = renderObserver()
    await flush()
    act(() => Socket.instances[0].message({ unexpected: true }))
    expect(client.getQueryData(scaleKeys.status)).toEqual(initial)
    const socket = Socket.instances[0]
    act(() => socket.onclose?.())
    view.unmount()
    expect(socket.close).toHaveBeenCalled()
    expect(socket.onmessage).toBeNull()
    expect(socket.onclose).toBeNull()
    expect(socket.onerror).toBeNull()
    const calls = vi.mocked(scalesApi.status).mock.calls.length
    await flush(30000)
    expect(Socket.instances).toHaveLength(1)
    expect(scalesApi.status).toHaveBeenCalledTimes(calls)
  })
})