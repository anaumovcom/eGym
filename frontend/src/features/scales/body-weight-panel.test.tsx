import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAppStore } from '@/stores/app-store'
import { scaleKeys, type ScaleMeasurement, type ScaleStatus } from './api'
import { BodyWeightPanel } from './body-weight-panel'

const measurement: ScaleMeasurement = { id: 11, userId: 'alexey', weightKg: 80.5, timestamp: '2026-10-18T10:00:00Z', stable: true, deviceId: 'AA', impedanceOhm: 510 }
const initial: ScaleStatus = { enabled: false, paused: false, pauseReason: null, bluetoothAvailable: true, scanning: false, scanningMode: null, measuring: false, deviceId: null, lastSeen: null, lastMeasurement: null, devices: [], error: null, warning: null }
let client: QueryClient
let status: ScaleStatus
let measurements: ScaleMeasurement[]
let latest: ScaleMeasurement | null
let failDelete: boolean
let finishDelete: (() => void) | undefined
let deferDelete: boolean
let fetchMock: ReturnType<typeof vi.fn>
const response = (data: unknown, code = 200) => new Response(JSON.stringify(data), { status: code, headers: { 'Content-Type': 'application/json' } })
function renderPanel() { return render(<QueryClientProvider client={client}><BodyWeightPanel userId="alexey" userName="Алексей" /></QueryClientProvider>) }
function settings() { fireEvent.click(screen.getByText('Настройки весов')) }
beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  status = { ...initial }
  measurements = []
  latest = null
  failDelete = false
  deferDelete = false
  finishDelete = undefined
  useAppStore.setState({ selectedUserId: 'alexey' })
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/scales/status') return response(status)
    if (url.startsWith('/api/scales/measurements/latest?')) return response(latest)
    if (url.startsWith('/api/scales/measurements?')) return response({ measurements })
    if (init?.method === 'DELETE') {
      if (deferDelete) await new Promise<void>(resolve => { finishDelete = resolve })
      if (failDelete) return response({ detail: 'offline' }, 503)
      measurements = measurements.filter(item => item.id !== 11)
      latest = measurements[0] ?? null
      status = { ...status, lastMeasurement: latest }
      return new Response(null, { status: 204 })
    }
    if (url === '/api/scales/settings') { status = { ...status, ...JSON.parse(String(init?.body)) }; return response(status) }
    if (url.startsWith('/api/scales/scan/')) { status = { ...status, enabled: url.endsWith('start'), scanning: url.endsWith('start') }; return response(status) }
    return response({ detail: 'offline' }, 503)
  })
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => { cleanup(); client.clear(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('BodyWeightPanel shared scales', () => {
  it.each([
    ['exercise', 'Поиск на паузе · упражнение'],
    ['setup', 'Поиск на паузе · настройка'],
    ['rest', 'Поиск на паузе · отдых'],
    [null, 'Поиск на паузе'],
    ['unknown', 'Поиск на паузе'],
  ])('shows paused discovery for %s without offering a measurement or changing settings', async (pauseReason, label) => {
    status = { ...initial, enabled: true, paused: true, pauseReason, measuring: true }
    renderPanel()
    expect(await screen.findByText(label)).toBeVisible()
    expect(screen.queryByText('Идёт измерение — стойте неподвижно')).not.toBeInTheDocument()
    settings()
    expect(screen.getByText(/работает автоматически вне тренировки/)).toBeVisible()
    expect(fetchMock.mock.calls.every(([, init]) => init?.method === 'GET')).toBe(true)
    act(() => client.setQueryData(scaleKeys.status, { ...status, enabled: false }))
    expect(await screen.findByText('Поиск весов выключен')).toBeVisible()
  })

  it('shows loading, honest empty states and collapsed settings without creating a socket', async () => {
    const socket = vi.fn()
    vi.stubGlobal('WebSocket', socket)
    renderPanel()
    expect(screen.getByText('Загрузка последнего измерения…')).toBeVisible()
    expect(await screen.findByText('Поиск весов выключен')).toBeVisible()
    expect(await screen.findByText('Сохранённых измерений пока нет.')).toBeVisible()
    expect(await screen.findByText('За выбранный период измерений нет.')).toBeVisible()
    expect(screen.getByText('Настройки весов').closest('details')).not.toHaveAttribute('open')
    expect(socket).not.toHaveBeenCalled()
  })
  it('selects only a device and uses the active profile without rebinding on a switch', async () => {
    status.devices = [{ deviceId: 'AA', name: 'Mi Body Composition', rssi: -60, lastSeen: measurement.timestamp }]
    renderPanel()
    await screen.findByText('Поиск весов выключен')
    settings()
    expect(screen.getByText(/активный профиль «Алексей»/)).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Выбрать весы' }))
    expect(await screen.findByRole('button', { name: 'Выбраны' })).toBeDisabled()
    expect(fetchMock).toHaveBeenCalledWith('/api/scales/settings', expect.objectContaining({ method: 'PUT', body: JSON.stringify({ enabled: true, deviceId: 'AA' }) }))
    act(() => useAppStore.setState({ selectedUserId: 'elena' }))
    expect(screen.getByText(/активный профиль «Елена»/)).toBeVisible()
    expect(fetchMock.mock.calls.filter(([url]) => url === '/api/scales/settings')).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: 'Сбросить выбор весов' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/scales/settings', expect.objectContaining({ body: JSON.stringify({ enabled: true, deviceId: null }) })))
  })
  it('enables/disables discovery and shows measuring/error states from the shared cache', async () => {
    renderPanel()
    await screen.findByText('Поиск весов выключен')
    settings()
    fireEvent.click(screen.getByRole('button', { name: 'Включить поиск' }))
    expect(await screen.findByText('Поиск весов')).toBeVisible()
    expect(fetchMock).toHaveBeenCalledWith('/api/scales/scan/start', expect.objectContaining({ method: 'POST', body: '{}' }))
    fireEvent.click(screen.getByRole('button', { name: 'Выключить поиск' }))
    expect(await screen.findByText('Поиск весов выключен')).toBeVisible()
    act(() => client.setQueryData(scaleKeys.status, { ...initial, enabled: true, measuring: true, error: 'Слабый сигнал' }))
    expect(await screen.findByText('Идёт измерение — стойте неподвижно')).toBeVisible()
    expect(screen.getByText('Слабый сигнал')).toBeVisible()
  })
  it('shows independent latest, chart, count/delta, history and period controls', async () => {
    latest = measurement
    measurements = [measurement, { ...measurement, id: 10, weightKg: 82, timestamp: '2026-10-17T10:00:00Z', impedanceOhm: null }]
    renderPanel()
    expect(await screen.findByRole('img', { name: 'Динамика веса тела' })).toBeVisible()
    expect(screen.getByText('-1,5 кг')).toBeVisible()
    expect(screen.getByText('2', { selector: 'p' })).toBeVisible()
    expect(within(screen.getAllByRole('listitem')[0]).getByText('80,5 кг')).toBeVisible()
    expect(screen.getByText('Импеданс: 510 Ом')).toBeVisible()
    measurements = []
    fireEvent.click(screen.getByRole('button', { name: '7 дней' }))
    expect(await screen.findByText('За выбранный период измерений нет.')).toBeVisible()
    expect(screen.getByText(/Последнее измерение:/)).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: '90 дней' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/scales/measurements?userId=alexey&days=90', expect.anything()))
    expect(screen.getByRole('button', { name: '90 дней' })).toHaveAttribute('aria-pressed', 'true')
  })
  it('confirms precise weight/time, cancels without DELETE, then deletes with owner/confirm and invalidates caches', async () => {
    latest = measurement
    measurements = [measurement]
    const invalidate = vi.spyOn(client, 'invalidateQueries')
    renderPanel()
    fireEvent.click(await screen.findByRole('button', { name: /^Удалить 80,5 кг/ }))
    expect(within(screen.getByRole('dialog')).getByText(/80,5 кг.*№11/)).toBeVisible()
    expect(screen.getByRole('dialog')).toHaveTextContent(new Date(measurement.timestamp).toLocaleTimeString('ru-RU'))
    fireEvent.click(screen.getByRole('button', { name: 'Отмена' }))
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === 'DELETE')).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: /^Удалить 80,5 кг/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Удалить измерение' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledWith('/api/scales/measurements/11?userId=alexey&confirm=true', expect.objectContaining({ method: 'DELETE' }))
    for (const queryKey of [scaleKeys.history('alexey'), scaleKeys.latest('alexey'), ['progress-screen', 'alexey'], ['user-profile-screen', 'alexey'], scaleKeys.status]) expect(invalidate).toHaveBeenCalledWith({ queryKey })
    expect(await screen.findByText('Сохранённых измерений пока нет.')).toBeVisible()
    expect(screen.queryByText('Вес сохранён')).not.toBeInTheDocument()
  })
  it('blocks duplicate deletion/close while pending and retains error/retry/cancel', async () => {
    measurements = [measurement]
    deferDelete = true
    failDelete = true
    renderPanel()
    fireEvent.click(await screen.findByRole('button', { name: /^Удалить 80,5 кг/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Удалить измерение' }))
    expect(await screen.findByRole('button', { name: 'Удаление…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Отмена' })).toBeDisabled()
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(screen.getByRole('dialog')).toBeVisible()
    await act(async () => finishDelete?.())
    expect(await screen.findByText('Не удалось удалить измерение: offline')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Удалить измерение' })).toBeEnabled()
    fireEvent.click(screen.getByRole('button', { name: 'Отмена' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByText('80,5 кг')).toBeVisible()
  })
})