import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { machineScenarios } from '@/mocks/data'
import type { CalibrationSessionPayload, CalibrationSpec, CalibrationState, ParametersPayload } from '@/features/motor/api/motor-api'
import type { HardwareSnapshot } from '@/features/hardware/model/types'
import { MotorCalibrationScreen } from '@/screens/motor-calibration/motor-calibration-screen'
import { apiGet, apiPost, apiPut } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'

vi.mock('@/shared/api/client', async () => ({
  ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'),
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiPut: vi.fn(),
}))

const value = (v: number | boolean, provenance: 'default' | 'measured' = 'default') => ({ value: v, ci95: null, provenance, runId: null, measuredAt: null, points: null })

const catalog: CalibrationSpec[] = [
  { code: 'WIZARD', group: 'W', groupTitle: 'Мастер', title: 'Мастер первичной настройки', description: 'Последовательно выполняет B5, S3, C1.', steps: ['B5: направление', 'S3: окно', 'C1: устойчивость'], durationS: 240, requires: [], produces: ['left.coulomb_up_n'], implemented: true, runnable: true, status: 'missing', measuredAt: null },
  { code: 'B1', group: 'B', groupTitle: 'Привод и шина', title: 'Тайминг шины', description: 'Период цикла.', steps: [], durationS: null, requires: ['B0'], produces: [], implemented: false, runnable: false, status: 'planned', measuredAt: null },
  { code: 'S9', group: 'S', groupTitle: 'Статика', title: 'Масштаб силы', description: 'Эталонный груз.', steps: [], durationS: 150, requires: ['S3'], produces: ['left.n_per_raw'], inputs: ['referenceKg'], implemented: true, runnable: true, status: 'missing', measuredAt: null },
]

const parameters: ParametersPayload = {
  version: 3,
  runtimeVersion: 3,
  groups: [
    { id: 'statics', title: 'Вес и трение', description: 'Окно невесомости.', items: [
      { scope: 'side', key: 'coulomb_up_n', label: 'Трение вверх', description: 'Добавка к весу.', unit: 'Н', kind: 'float', editable: true, min: 0, max: 500, step: 1, producedBy: 'S3', restart: false, values: { left: value(49), right: value(50) } },
    ] },
    { id: 'behaviour', title: 'Поведение тренажёра', description: 'Коэффициенты.', items: [
      { scope: 'tunables', key: 'hold_k_fraction', label: 'Доля жёсткости удержания', description: 'Доля K_u.', unit: '×', kind: 'float', editable: true, min: 0.05, max: 0.6, step: 0.05, producedBy: null, restart: false, value: value(0.3) },
    ] },
  ],
}

const preconditions = (ok: boolean) => [
  { id: 'service', label: 'Сервисный режим включён', ok, detail: ok ? null : 'Настройки → Сервис' },
  { id: 'stops', label: 'Гриф на нижних упорах', ok: true, detail: 'Л 0.0 мм, П 0.0 мм' },
]

const baseSession: CalibrationSessionPayload = {
  id: 'WIZARD-1', code: 'WIZARD', title: 'Мастер первичной настройки', status: 'running', reason: null,
  startedAt: '2026-01-01T10:00:00Z', finishedAt: null, elapsedS: 42, progress: 0.4, currentStage: 'S3', note: 'трогание вверх 2/3', deadManHeld: true,
  stages: [
    { code: 'B5', title: 'Направление', status: 'done', progress: 1, note: '', reason: null, result: {} },
    { code: 'S3', title: 'Окно невесомости', status: 'running', progress: 0.3, note: 'трогание вверх 2/3', reason: null, result: null },
    { code: 'C1', title: 'Запас устойчивости', status: 'pending', progress: 0, note: '', reason: null, result: null },
  ],
  changes: [], hasChanges: false, savedVersion: null,
  log: { t: [0, 0.05, 0.1], xL: [0, 1, 2], xR: [0, 1, 2], vL: [0, 0, 0], vR: [0, 0, 0], fL: [60, 70, 80], fR: [60, 70, 80] },
}

let state: CalibrationState
let client: QueryClient

function snapshot(serviceMode: boolean): HardwareSnapshot {
  return {
    machine: machineScenarios.ready,
    serviceMode,
    safety: { state: 'enabled', label: '', message: '', requiresService: false, activeEventId: null },
    control: { mode: 'support', servo: { left: true, right: true }, positionMm: 0 },
  } as unknown as HardwareSnapshot
}

function renderScreen(path = '/motor-calibration') {
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><MotorCalibrationScreen /></MemoryRouter></QueryClientProvider>)
}

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
  useHardwareStore.setState({ snapshot: snapshot(true) })
  state = { session: null, preconditions: preconditions(true), profileVersion: 3 }
  vi.mocked(apiGet).mockReset()
  vi.mocked(apiPost).mockReset()
  vi.mocked(apiPut).mockReset()
  vi.mocked(apiGet).mockImplementation(async <T,>(path: string): Promise<T> => {
    if (path === '/api/motor/calibrations') return catalog as T
    if (path.startsWith('/api/motor/calibration/session')) return state as T
    if (path.startsWith('/api/motor/calibration/runs')) return [] as T
    if (path === '/api/motor/parameters') return parameters as T
    if (path.startsWith('/api/machine/status')) return machineScenarios.ready as T
    throw new Error(`Unexpected request ${path}`)
  })
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})

afterEach(() => { cleanup(); client.clear(); vi.restoreAllMocks() })

describe('MotorCalibrationScreen', () => {
  it('describes the selected calibration and blocks the hold button until preconditions pass', async () => {
    state = { ...state, preconditions: preconditions(false) }
    renderScreen()
    expect(await screen.findByText('Последовательно выполняет B5, S3, C1.')).toBeInTheDocument()
    expect(screen.getByText('S3: окно')).toBeInTheDocument()
    expect(await screen.findByText('Настройки → Сервис')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Нажмите и удерживайте/ })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: /Тайминг шины/ }))
    expect(await screen.findByText('Запуск этой калибровки из интерфейса пока не реализован.')).toBeInTheDocument()
  })

  it('starts on press, keeps the dead-man alive and aborts on release', async () => {
    vi.mocked(apiPost).mockImplementation(async <T,>(path: string): Promise<T> => {
      if (path.endsWith('/start')) { state = { ...state, session: baseSession }; return state as T }
      if (path.endsWith('/keepalive')) return { running: true } as T
      if (path.endsWith('/abort')) { state = { ...state, session: { ...baseSession, status: 'aborted', reason: 'прервано оператором' } }; return { session: state.session } as T }
      throw new Error(path)
    })
    renderScreen()
    const hold = await screen.findByRole('button', { name: /Нажмите и удерживайте/ })
    await waitFor(() => expect(hold).toBeEnabled())
    fireEvent.pointerDown(hold, { button: 0, pointerId: 1 })
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/start', { code: 'WIZARD' }))
    expect(await screen.findByText('Сейчас выполняется')).toBeInTheDocument()
    expect(screen.getAllByText('трогание вверх 2/3').length).toBeGreaterThan(0)
    expect(screen.getByText('40%')).toBeInTheDocument()
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/keepalive', {}), { timeout: 1000 })

    fireEvent.pointerUp(screen.getByRole('button', { name: /Калибровка идёт/ }), { pointerId: 1 })
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/abort', {}))
    expect(await screen.findByText('Калибровка прервана')).toBeInTheDocument()
    expect(screen.getByText('Причина: прервано оператором')).toBeInTheDocument()
  })

  it('shows the result with old and new values and saves them', async () => {
    state = {
      ...state,
      session: {
        ...baseSession, status: 'done', progress: 1, currentStage: null, hasChanges: true,
        stages: baseSession.stages.map((stage) => ({ ...stage, status: 'done' as const, progress: 1 })),
        changes: [{ scope: 'side', key: 'coulomb_up_n', side: 'left', label: 'Трение вверх', unit: 'Н', kind: 'float', old: value(49), new: { ...value(50.2, 'measured'), ci95: 0.4 }, changed: true }],
      },
    }
    vi.mocked(apiPost).mockResolvedValue({ version: 4, session: { ...state.session, savedVersion: 4 } })
    renderScreen()
    const result = await screen.findByRole('region', { name: 'Результат калибровки' })
    expect(within(result).getByText('Калибровка завершена')).toBeInTheDocument()
    expect(within(result).getByText('49 Н')).toBeInTheDocument()
    expect(within(result).getByText('50,2 Н')).toBeInTheDocument()
    fireEvent.click(within(result).getByRole('button', { name: 'Сохранить новые значения' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/accept', {}))
  })

  it('asks for the reference weight and shows the measurement report', async () => {
    vi.mocked(apiPost).mockImplementation(async <T,>(path: string): Promise<T> => {
      if (path.endsWith('/start')) return state as T
      return { running: true } as T
    })
    renderScreen()
    fireEvent.click(await screen.findByRole('button', { name: /Масштаб силы/ }))
    const hold = await screen.findByRole('button', { name: /Нажмите и удерживайте/ })
    const mass = screen.getByRole('spinbutton', { name: /Масса эталонного груза/ })
    expect(hold).toBeDisabled()
    fireEvent.change(mass, { target: { value: '100' } })
    expect(hold).toBeDisabled()
    fireEvent.change(mass, { target: { value: '20' } })
    await waitFor(() => expect(hold).toBeEnabled())
    fireEvent.pointerDown(hold, { button: 0, pointerId: 1 })
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/start', { code: 'S9', referenceKg: 20 }))
    fireEvent.pointerUp(hold, { pointerId: 1 })
  })

  it('renders the report of a check without profile changes', async () => {
    state = {
      ...state,
      session: {
        ...baseSession, id: 'G1-1', code: 'G1', title: 'Статическая точность', status: 'done', progress: 1, currentStage: null,
        stages: [{ code: 'G1', title: 'Статическая точность', status: 'done', progress: 1, note: '', reason: null, result: { report: [{ label: 'Допуск', value: '±0,50 кг', ok: true }] } }],
      },
    }
    renderScreen()
    await waitFor(() => expect(screen.getByText('Допуск').isConnected).toBe(true))
    const result = screen.getByRole('region', { name: 'Результат калибровки' })
    expect(within(result).getByText('Допуск')).toBeInTheDocument()
    expect(within(result).getByText(/±0,50 кг/)).toBeInTheDocument()
    expect(within(result).getByText('Проверка пройдена, параметры профиля не меняются.')).toBeInTheDocument()
    expect(within(result).queryByRole('button', { name: 'Сохранить новые значения' })).not.toBeInTheDocument()
    expect(within(result).getByRole('button', { name: 'Закрыть' })).toBeInTheDocument()
  })

  it('lists parameters with descriptions and saves edits in service mode', async () => {
    vi.mocked(apiPut).mockResolvedValue({ ...parameters, version: 4, runtimeVersion: 4 })
    renderScreen('/motor-calibration?tab=parameters')
    expect(await screen.findByText('Вес и трение')).toBeInTheDocument()
    expect(screen.getByText('Добавка к весу.')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Доля жёсткости удержания' }), { target: { value: '0.9' } })
    expect(await screen.findByText('не больше 0.6')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Трение вверх (Правая)' }), { target: { value: '55' } })
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Доля жёсткости удержания' }), { target: { value: '0.25' } })
    fireEvent.click(await screen.findByRole('button', { name: 'Сохранить' }))
    await waitFor(() => expect(apiPut).toHaveBeenCalledWith('/api/motor/parameters', {
      changes: [
        { scope: 'tunables', key: 'hold_k_fraction', value: 0.25 },
        { scope: 'side', key: 'coulomb_up_n', side: 'right', value: 55 },
      ],
      note: 'Ручная настройка: 2 параметр(ов)',
    }))
    expect(await screen.findByText('Сохранено: профиль v4')).toBeInTheDocument()
  })

  it('makes parameters read-only outside service mode', async () => {
    useHardwareStore.setState({ snapshot: snapshot(false) })
    renderScreen('/motor-calibration?tab=parameters')
    expect(await screen.findByText('Для изменения включите сервисный режим')).toBeInTheDocument()
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
  })
})
