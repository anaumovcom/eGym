import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FrictionTrackChart } from './friction-track-chart'
import { ChangesTable } from './calibration-run-controls'
import { mapChangeLabel, ParameterMap } from './parameter-map'
import { machineScenarios } from '@/mocks/data'
import type { CalibrationChange, CalibrationSessionPayload, CalibrationSpec, CalibrationState, ParametersPayload, ValueInfo } from '@/features/motor/api/motor-api'
import type { HardwareSnapshot } from '@/features/hardware/model/types'
import { MotorCalibrationScreen } from '@/screens/motor-calibration/motor-calibration-screen'
import { ApiError, apiGet, apiPost, apiPut } from '@/shared/api/client'
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
  { code: 'WIZARD', group: 'W', groupTitle: 'Мастер', title: 'Мастер первичной настройки', description: 'Последовательно выполняет B5, S3, C1.', priority: 'critical', priorityReason: 'Проверяет поддержку и торможение грифа.', steps: ['B5: направление', 'S3: окно', 'C1: устойчивость'], durationS: 240, requires: [], produces: ['left.coulomb_up_n'], implemented: true, runnable: true, status: 'missing', measuredAt: null },
  { code: 'B1', group: 'B', groupTitle: 'Привод и шина', title: 'Тайминг шины', description: 'Период цикла.', priority: 'important', priorityReason: 'Измеряет задержку связи с приводами.', steps: [], durationS: null, requires: ['B0'], produces: [], implemented: false, runnable: false, status: 'planned', measuredAt: null },
  { code: 'S9', group: 'S', groupTitle: 'Статика', title: 'Масштаб силы', description: 'Эталонный груз.', priority: 'critical', priorityReason: 'Определяет силу, соответствующую заданному весу.', steps: [], durationS: 150, requires: ['S3'], produces: ['left.n_per_raw'], inputs: ['referenceKg'], implemented: true, runnable: true, status: 'missing', measuredAt: null },
  { code: 'B5', group: 'B', groupTitle: 'Привод и шина', title: 'Направление', description: 'Знак момента.', priority: 'critical', priorityReason: 'Проверяет направление тяги обеих сторон.', steps: [], durationS: 20, requires: [], produces: ['left.direction_sign'], order: 1, implemented: true, runnable: true, status: 'missing', measuredAt: null },
  { code: 'D2', group: 'D', groupTitle: 'Динамика', title: 'Трение по скоростям', description: 'Измерение трения.', priority: 'important', priorityReason: 'Измеряет трение при разных скоростях.', steps: [], durationS: 60, requires: [], produces: [], middleZone: 'preferred', implemented: true, runnable: true, status: 'missing', measuredAt: null },
  { code: 'S3', group: 'S', groupTitle: 'Статика', title: 'Окно невесомости', description: 'Вес и трение.', priority: 'critical', priorityReason: 'Определяет усилие поддержки пустого грифа.', steps: [], durationS: 180, requires: ['B5'], produces: ['left.coulomb_up_n', 'right.coulomb_up_n'], order: 2, implemented: true, runnable: true, status: 'stale', staleReason: 'после неё выполнена S9: повторите', measuredAt: '2026-01-01T10:00:00Z' },
  { code: 'S6', group: 'S', groupTitle: 'Статика', title: 'Неравномерность винта', description: 'Замер по обороту винта.', priority: 'refinement', priorityReason: 'Выявляет периодические неровности хода.', steps: [], durationS: 45, requires: [], produces: [], implemented: true, runnable: true, status: 'actual', measuredAt: null },
]

const parameters: ParametersPayload = {
  version: 3,
  runtimeVersion: 3,
  groups: [
    { id: 'statics', title: 'Вес и трение', description: 'Окно невесомости.', items: [
      { scope: 'side', key: 'coulomb_up_n', label: 'Трение вверх', description: 'Добавка к весу.', unit: 'Н', kind: 'float', editable: true, min: 0, max: 500, step: 1, producedBy: ['S3'], restart: false, values: { left: value(49), right: value(50) } },
    ] },
    { id: 'behaviour', title: 'Поведение тренажёра', description: 'Коэффициенты.', items: [
      { scope: 'tunables', key: 'hold_k_fraction', label: 'Доля жёсткости удержания', description: 'Доля K_u.', unit: '×', kind: 'float', editable: true, min: 0.05, max: 0.6, step: 0.05, producedBy: [], restart: false, value: value(0.3) },
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
  it('shows independent peaks and leaves missing sections open in an archived friction map', () => {
    const { container } = render(<FrictionTrackChart stage={{ ...baseSession.stages[0], code: 'S10', result: { track: {
      heightsMm: [590, 610, 630, 650, 670], sides: { left: [17, 2, null, 0, 0], right: [0, 1, 0, 2, 22] },
      summary: {
        left: { peakMm: 590, peakN: 17, weightResidualN: 6, weightWithinTolerance: false },
        right: { peakMm: 670, peakN: 22, weightResidualN: 2, weightWithinTolerance: true },
      },
    } } }} />)
    expect(screen.getByText('Пик на 590 мм · +17 Н')).toBeVisible()
    expect(screen.getByText('Пик на 670 мм · +22 Н')).toBeVisible()
    expect(screen.getByText('Измерено участков 4 из 5')).toBeVisible()
    expect(screen.getByText(/левая до 6 Н/)).toBeVisible()
    expect(container.querySelector('path')?.getAttribute('d')?.match(/M/g)).toHaveLength(2)
  })
  it('describes the selected calibration and blocks the start button until preconditions pass', async () => {
    state = { ...state, preconditions: preconditions(false) }
    renderScreen()
    expect(await screen.findByText('Последовательно выполняет B5, S3, C1.')).toBeInTheDocument()
    const route = screen.getByRole('region', { name: 'Маршрут первого запуска' })
    expect(within(route).getByText('Критично')).toBeVisible()
    expect(within(screen.getByRole('region', { name: 'Калибровка' })).getByText('Проверяет поддержку и торможение грифа.')).toBeVisible()
    expect(screen.getByText('S3: окно')).toBeInTheDocument()
    expect(await screen.findByText('Настройки → Сервис')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Запустить калибровку/ })).toBeDisabled()

    fireEvent.change(screen.getByRole('searchbox', { name: 'Поиск по всем калибровкам' }), { target: { value: 'B1' } })
    fireEvent.click(screen.getByRole('button', { name: /Тайминг шины/ }))
    expect(await screen.findByText('Запуск этой калибровки из интерфейса пока не реализован.')).toBeInTheDocument()
  })

  it('shows importance alongside the measurement status and searches all three levels', async () => {
    renderScreen('/motor-calibration?scenario=all&code=S3')
    const list = await screen.findByRole('list', { name: 'Процедуры' })
    const s3 = within(list).getByRole('button', { name: /S3 Окно невесомости/ })
    expect(within(s3).getByText('Критично')).toHaveAttribute('data-priority', 'critical')
    expect(within(s3).getByText(/устарела/)).toBeVisible()
    const detail = screen.getByRole('region', { name: 'Калибровка' })
    expect(within(detail).getByText('Определяет усилие поддержки пустого грифа.')).toBeVisible()
    const search = screen.getByRole('searchbox', { name: 'Поиск по всем калибровкам' })
    for (const [query, codes] of [
      ['КРИТИЧНО', ['Мастер', 'S9', 'B5', 'S3']], ['Важно', ['B1', 'D2']], ['Тонкая настройка', ['S6']],
    ] as const) {
      fireEvent.change(search, { target: { value: query } })
      expect(within(list).getAllByRole('button')).toHaveLength(codes.length)
      for (const code of codes) expect(within(list).getByText(code)).toBeInTheDocument()
    }
    fireEvent.click(within(list).getByRole('button', { name: /S6 Неравномерность винта/ }))
    expect(await within(detail).findByText('Выявляет периодические неровности хода.')).toBeVisible()
    expect(within(detail).getByText('Тонкая настройка')).toHaveAttribute('data-priority', 'refinement')
    expect(within(detail).getByText('актуальна')).toBeVisible()
  })

  it('shows the running stage’s own importance inside a critical series', async () => {
    state = { ...state, session: { ...baseSession, currentStage: 'D2', stages: [
      baseSession.stages[0], { ...baseSession.stages[1], code: 'D2', title: 'Трение по скоростям' },
    ] } }
    renderScreen()
    const current = await screen.findByText('D2 · Трение по скоростям')
    expect(within(current.parentElement!).getByText('Важно')).toBeVisible()
    expect(within(current.parentElement!).getByText('Измеряет трение при разных скоростях.')).toBeVisible()
    fireEvent.click(screen.getByText('Все этапы серии'))
    const stages = screen.getByRole('list', { name: 'Этапы' })
    expect(within(stages).getByText('Критично')).toBeVisible()
    expect(within(stages).getByText('Важно')).toBeVisible()
  })

  it('labels an archived series and the selected stage using the catalog', async () => {
    const defaultGet = vi.mocked(apiGet).getMockImplementation()!
    const stage = { ...baseSession.stages[1], code: 'D2', title: 'Трение по скоростям' }
    vi.mocked(apiGet).mockImplementation(async <T,>(path: string): Promise<T> => {
      if (path === '/api/motor/calibration/runs/WIZARD-1') {
        return { id: baseSession.id, stages: [baseSession.stages[0], stage], log: baseSession.log, stageLogs: { D2: baseSession.log } } as T
      }
      if (path.startsWith('/api/motor/calibration/runs?')) {
        return [{ ...baseSession, status: 'saved', savedVersion: 4 }] as T
      }
      return defaultGet<T>(path)
    })
    renderScreen('/motor-calibration?scenario=all&code=D2')
    const history = await screen.findByRole('region', { name: 'История калибровок' })
    const record = await within(history).findByRole('button', { name: /WIZARD · Мастер/ })
    expect(within(record).getByText('Критично')).toBeVisible()
    expect(within(record).getByText('сохранена')).toBeVisible()
    fireEvent.click(record)
    expect(await within(history).findByText('Проверяет поддержку и торможение грифа.')).toBeVisible()
    fireEvent.change(within(history).getByRole('combobox', { name: 'Посмотреть запись' }), { target: { value: 'D2' } })
    expect(await within(history).findByText('Измеряет трение при разных скоростях.')).toBeVisible()
    expect(within(history).getByText('Важно')).toHaveAttribute('data-priority', 'important')
  })

  it('starts on a click, keeps the screen heartbeat and aborts on STOP', async () => {
    vi.mocked(apiPost).mockImplementation(async <T,>(path: string): Promise<T> => {
      if (path.endsWith('/start')) { state = { ...state, session: baseSession }; return state as T }
      if (path.endsWith('/keepalive')) return { running: true } as T
      if (path.endsWith('/abort')) { state = { ...state, session: { ...baseSession, status: 'aborted', reason: 'прервано оператором' } }; return { session: state.session } as T }
      throw new Error(path)
    })
    renderScreen()
    const start = await screen.findByRole('button', { name: /Запустить калибровку/ })
    await waitFor(() => expect(start).toBeEnabled())
    fireEvent.click(start)
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/start', { code: 'WIZARD' }))
    expect(await screen.findByText(/Этап \d+ из \d+/)).toBeInTheDocument()
    expect(screen.getAllByText('трогание вверх 2/3').length).toBeGreaterThan(0)
    expect(screen.getByText('40%')).toBeInTheDocument()
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/keepalive', expect.anything()), { timeout: 1000 })
    expect(apiPost).not.toHaveBeenCalledWith('/api/motor/calibration/abort', expect.anything())

    fireEvent.click(screen.getByRole('button', { name: /СТОП/ }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/abort', { sessionId: 'WIZARD-1' }))
    expect(await screen.findByText('Калибровка прервана')).toBeInTheDocument()
    expect(screen.getByText('прервано оператором')).toBeInTheDocument()
  })

  it('shows the operator prompt and sends the answer', async () => {
    const prompt = { text: 'Измерьте рулеткой высоту грифа', kind: 'input' as const, label: 'Высота', unit: 'мм', min: 50, max: 600 }
    vi.mocked(apiPost).mockImplementation(async <T,>(path: string): Promise<T> => {
      if (path.endsWith('/start')) { state = { ...state, session: { ...baseSession, prompt } }; return state as T }
      if (path.endsWith('/keepalive')) return { running: true } as T
      if (path.endsWith('/reply')) { state = { ...state, session: { ...baseSession, prompt: null } }; return { session: state.session } as T }
      return { session: null } as T
    })
    renderScreen()
    const start = await screen.findByRole('button', { name: /Запустить калибровку/ })
    await waitFor(() => expect(start).toBeEnabled())
    fireEvent.click(start)
    const dialog = await screen.findByRole('alertdialog', { name: 'Действие оператора' })
    expect(within(dialog).getByText('Измерьте рулеткой высоту грифа')).toBeInTheDocument()
    const done = within(dialog).getByRole('button', { name: 'Готово' })
    const field = within(dialog).getByRole('spinbutton', { name: /Высота, мм/ })
    fireEvent.change(field, { target: { value: '700' } })
    expect(done).toBeDisabled()
    fireEvent.change(field, { target: { value: '251.5' } })
    expect(done).toBeEnabled()
    fireEvent.click(done)
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/reply', { sessionId: 'WIZARD-1', value: 251.5, promptText: 'Измерьте рулеткой высоту грифа' }))
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
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
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/accept', { sessionId: 'WIZARD-1' }))
  })

  it('resumes at the first unfinished checkpoint and asks before applying the shorter travel limit', async () => {
    const get = vi.mocked(apiGet).getMockImplementation()!
    const specs = [
      { ...catalog[0], status: 'actual' },
      { ...catalog[0], code: 'B8', title: 'Ход', stages: ['B8'] },
      { ...catalog[0], code: 'B6', title: 'Масштаб', participation: 'tape' },
    ]
    vi.mocked(apiGet).mockImplementation(async <T,>(path: string): Promise<T> => path === '/api/motor/calibrations' ? specs as T : get<T>(path))
    const stage = { ...baseSession.stages[0], code: 'B8', status: 'done' as const, result: { suggestedSoftMaxMm: 1250 } }
    const completed = { ...baseSession, id: 'B8-test', code: 'B8', status: 'done' as const, stages: [stage], currentStage: null, progress: 1, hasChanges: true }
    vi.mocked(apiPost).mockImplementation(async <T,>(path: string): Promise<T> => {
      if (path.endsWith('/start')) state = { ...state, session: completed }
      if (path.endsWith('/accept')) state = { ...state, session: { ...completed, savedVersion: 4 } }
      if (path.endsWith('/discard')) state = { ...state, session: null }
      return state as T
    })
    renderScreen()
    expect(await screen.findByRole('heading', { name: 'Измерить полный ход' })).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: /Запустить калибровку/ }))
    const save = await screen.findByRole('button', { name: 'Сохранить ход и предел 1250 мм' })
    expect(screen.queryByRole('button', { name: 'К следующему этапу' })).toBeNull()
    vi.mocked(window.confirm).mockReturnValueOnce(false)
    fireEvent.click(save)
    expect(apiPost).not.toHaveBeenCalledWith('/api/motor/calibration/accept', expect.anything())
    fireEvent.click(save)
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/accept', { sessionId: 'B8-test', fitTravelLimit: true }))
    fireEvent.click(await screen.findByRole('button', { name: 'К следующему этапу' }))
    expect(await screen.findByRole('heading', { name: 'Сверить высоту рулеткой' })).toBeVisible()
    expect(vi.mocked(apiPost).mock.calls.filter(([path]) => path.endsWith('/start'))).toHaveLength(1)
  })

  it('asks for the reference weight and shows the measurement report', async () => {
    vi.mocked(apiPost).mockImplementation(async <T,>(path: string): Promise<T> => {
      if (path.endsWith('/start')) return state as T
      return { running: true } as T
    })
    renderScreen()
    fireEvent.click(await screen.findByRole('button', { name: /Рабочий вес/ }))
    const hold = await screen.findByRole('button', { name: /Запустить калибровку/ })
    const mass = screen.getByRole('spinbutton', { name: /Масса эталонного груза/ })
    expect(hold).toBeDisabled()
    fireEvent.change(mass, { target: { value: '100' } })
    expect(hold).toBeDisabled()
    fireEvent.change(mass, { target: { value: '20' } })
    await waitFor(() => expect(hold).toBeEnabled())
    fireEvent.click(hold)
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/start', { code: 'S9', referenceKg: 20 }))
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

  it('opens scenarios and finds prerequisites outside the selected route', async () => {
    renderScreen()
    const nav = await screen.findByRole('navigation', { name: 'Сценарии калибровки' })
    fireEvent.click(within(nav).getByRole('button', { name: /Рабочий вес/ }))
    expect(await screen.findByRole('heading', { name: 'Масштаб силы' })).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Поиск по всем калибровкам' }), { target: { value: 's3' } })
    fireEvent.click(screen.getByRole('button', { name: /S3 Окно невесомости/ }))
    expect(await screen.findByText('Результат устарел')).toBeInTheDocument()
    expect(screen.getByText('Сначала выполните')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'B5 · Направление' })).toBeInTheDocument()
    expect(await screen.findByText('Определяет · текущие значения')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'B5 · Направление' }))
    expect(await screen.findByRole('heading', { name: 'Направление' })).toBeInTheDocument()
  })

  it('starts an eligible measurement in the server-confirmed middle window by default', async () => {
    state = { ...state, preconditions: [...preconditions(true), { id: 'middleZone', label: 'Ноль подтверждён', ok: true, detail: null }], workingZone: { lowMm: 420, highMm: 820 } }
    vi.mocked(apiPost).mockResolvedValue({ ...state, session: { ...baseSession, code: 'D2' } })
    renderScreen('/motor-calibration?code=D2')
    expect(await screen.findByText('420–820 мм')).toBeInTheDocument()
    const start = screen.getByRole('button', { name: /Запустить калибровку/ })
    fireEvent.click(start)
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/api/motor/calibration/start', { code: 'D2', workingZone: 'middle' }))
  })

  it('plots feedback for a finished run in selectable physical units', async () => {
    state = { ...state, session: { ...baseSession, code: 'D2', status: 'done', log: { ...baseSession.log, vL: [0, 650, 1500], vR: [0, 600, 1480] } } }
    renderScreen('/motor-calibration?code=D2')
    fireEvent.click(await screen.findByText('График записи'))
    const plot = screen.getByRole('region', { name: 'График калибровки' })
    expect(within(plot).getByText('Скорость, м/с')).toBeInTheDocument()
    expect(within(plot).getByText('1,5')).toBeInTheDocument()
    fireEvent.change(within(plot).getByRole('slider', { name: 'Момент записи' }), { target: { value: '1' } })
    expect(within(plot).getByText('0,65')).toBeInTheDocument()
    fireEvent.click(within(plot).getByRole('button', { name: 'К последнему кадру' }))
    fireEvent.click(within(plot).getByRole('button', { name: 'Перекос' }))
    expect(within(plot).getByText('Перекос, мм')).toBeInTheDocument()
  })

  it('filters parameters and links them to their calibration', async () => {
    renderScreen('/motor-calibration?tab=parameters')
    expect(await screen.findByText('Трение вверх')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Поиск параметра' }), { target: { value: 'жёсткост' } })
    expect(screen.queryByText('Трение вверх')).not.toBeInTheDocument()
    fireEvent.change(screen.getByRole('searchbox', { name: 'Поиск параметра' }), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Измерено' }))
    expect(screen.getByText('Ничего не найдено.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Все' }))
    fireEvent.click(screen.getByRole('button', { name: /измеряет S3/ }))
    expect(await screen.findByRole('heading', { name: 'Окно невесомости' })).toBeInTheDocument()
  })

  it('lists parameters with descriptions and saves edits in service mode', async () => {
    vi.mocked(apiPut).mockResolvedValue({ ...parameters, version: 4, runtimeVersion: 4 })
    vi.mocked(apiPost).mockResolvedValue({ baseVersion: 3, changes: [
      { key: 'hold_k_fraction', scope: 'tunables', label: 'Доля жёсткости удержания', side: null, unit: '×', kind: 'float', before: value(0.3), after: value(0.25) },
      { key: 'coulomb_up_n', scope: 'side', label: 'Трение вверх', side: 'right', unit: 'Н', kind: 'float', before: value(50), after: value(55) },
    ], statusChanges: [{ code: 'S3', title: 'Окно невесомости', before: 'actual', after: 'missing' }] })
    renderScreen('/motor-calibration?tab=parameters')
    expect(await screen.findByText('Вес и трение')).toBeInTheDocument()
    expect(screen.getByText('Добавка к весу.')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Доля жёсткости удержания' }), { target: { value: '0.9' } })
    expect(await screen.findByText('не больше 0.6')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Трение вверх (Правая)' }), { target: { value: '55' } })
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Доля жёсткости удержания' }), { target: { value: '0.25' } })
    fireEvent.click(await screen.findByRole('button', { name: 'Проверить изменения' }))
    const review = await screen.findByRole('region', { name: 'Предварительная проверка правок' })
    expect(within(review).getByText('Правая')).toBeVisible()
    expect(within(review).getByText('55 Н')).toBeVisible()
    expect(within(review).getByText(/актуальна → не выполнена/)).toBeVisible()
    expect(apiPut).not.toHaveBeenCalled()
    fireEvent.click(await screen.findByRole('button', { name: 'Сохранить и применить' }))
    await waitFor(() => expect(apiPut).toHaveBeenCalledWith('/api/motor/parameters', {
      changes: [
        { scope: 'tunables', key: 'hold_k_fraction', value: 0.25 },
        { scope: 'side', key: 'coulomb_up_n', side: 'right', value: 55 },
      ],
      note: 'Ручная настройка: 2 параметр(ов)',
      baseVersion: 3,
    }))
    expect(await screen.findByText('Сохранено: профиль v4')).toBeInTheDocument()
  })

  it('compares map values at measured coordinates even when scalar summaries and counts are identical', async () => {
    const info = (rows: [number, number][]): ValueInfo => ({ ...value(0), value: null, points: rows.length, rows })
    const old = info([[250, 10], [500, 25]]), next = info([[500, 30], [650, 7]])
    const change: CalibrationChange = { scope: 'side', key: 'friction_map', kind: 'table', label: 'Карта трения', side: 'left', unit: 'Н', old, new: next, changed: true }
    expect(mapChangeLabel({ ...change, new: { ...old, rows: [...old.rows!].reverse() } })).toBe('Карта подтверждена')
    expect(mapChangeLabel({ ...change, old: { ...old, rows: undefined } })).toMatch(/нужны прежние координаты/)
    render(<ChangesTable changes={[change]} />)
    expect(screen.getByText('Изменились точки карты')).toBeVisible()
    fireEvent.click(screen.getByText('Сравнить точки · Карта трения · левая'))
    expect(await screen.findByText(/общих точек · 1.*5 Н при 500 мм/)).toBeVisible()
    fireEvent.change(screen.getByRole('slider', { name: 'Координата карты' }), { target: { value: '2' } })
    expect(screen.getByText('Было · нет точки')).toBeVisible()
    expect(screen.getByText('Стало · 7 Н')).toBeVisible()
  })

  it('compares inertia in percentage points and explains non-overlapping coordinates', async () => {
    const series = (name: string, x: number, y: number) => ({ name, info: { ...value(0), rows: [[x, y] as [number, number]], points: 1 } })
    const { rerender } = render(<ParameterMap paramKey="inertia_table" label="Точки" unit="" series={[series('Было', 20, .1), series('Стало', 20, .3)]} />)
    fireEvent.click(screen.getByText('Точки'))
    expect(await screen.findByText(/20 п. п. при 20 Н/)).toBeVisible()
    rerender(<ParameterMap paramKey="inertia_table" label="Точки" unit="" series={[series('Было', 20, .1), series('Стало', 30, .3)]} />)
    expect(screen.getByText('Общих точек для прямого сравнения нет.')).toBeVisible()
  })

  it('makes parameters read-only outside service mode', async () => {
    useHardwareStore.setState({ snapshot: snapshot(false) })
    renderScreen('/motor-calibration?tab=parameters')
    expect(await screen.findByText('Для изменения включите сервисный режим')).toBeInTheDocument()
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument()
  })

  it('opens the source of each carriage even outside the recent history and shows missing stage telemetry honestly', async () => {
    const original = vi.mocked(apiGet).getMockImplementation()!
    const item = parameters.groups[0].items[0]
    const template = { ...value(20, 'measured'), ci95: 0, measuredAt: '2026-01-01T12:00:00Z' }
    const diags = [{ ...baseSession.stages[0], code: 'S8', title: 'Тугие места', result: { report: [{ label: 'Тугой участок', value: '670 мм', ok: false }] } },
      { ...baseSession.stages[0], code: 'S10', title: 'Карта трения', result: null },
      { ...baseSession.stages[0], code: 'X3', title: 'Подбор синхронизации', result: { report: [{ label: 'Пробный коэффициент', value: '4 Н/мм', ok: false }] } }]
    vi.mocked(apiGet).mockImplementation(async <T,>(path: string): Promise<T> => {
      if (path.endsWith('/parameters')) return { ...parameters, groups: [{ ...parameters.groups[0], items: [{ ...item,
        values: { left: { ...template, runId: 'older-A' }, right: { ...template, value: 24, runId: 'older-B' } },
      }] }] } as T
      if (path.endsWith('/runs/older-B')) return { code: 'AUTO_GUIDES', title: 'Направляющие', stages: diags, log: baseSession.log, stageLogs: {}, adapter: 'twin' } as T
      if (path.endsWith('/runs/older-A')) throw new ApiError(404, { detail: 'нет записи' })
      return original<T>(path)
    })
    renderScreen('/motor-calibration?tab=parameters')
    expect(await screen.findByText('Правая минус левая · +4 Н · замеры из разных запусков')).toBeVisible()
    expect(screen.getAllByText('95 % ДИ ± 0 Н')).toHaveLength(2)
    expect(apiGet).not.toHaveBeenCalledWith(expect.stringContaining('/calibration/runs'))
    fireEvent.click(screen.getByRole('button', { name: 'Запись замера · Трение вверх · Левая' }))
    expect(await screen.findByText('Запись этого замера отсутствует в архиве.')).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'Запись замера · Трение вверх · Правая' }))
    const findings = await screen.findByRole('region', { name: 'Замечания протокола' })
    expect(within(findings).getByText('Тугой участок · 670 мм')).toBeVisible()
    expect(within(findings).queryByText(/Пробный коэффициент/)).not.toBeInTheDocument()
    fireEvent.click(within(findings).getByRole('button', { name: /S8/ }))
    expect(await screen.findByText(/Отдельная телеметрия этапа отсутствует/)).toBeVisible()
    expect(screen.queryByRole('region', { name: 'График калибровки' })).not.toBeInTheDocument()
  })

  it('requires a fresh preview after another operator saves while preserving the requested value', async () => {
    const original = vi.mocked(apiGet).getMockImplementation()!
    let version = 3
    vi.mocked(apiGet).mockImplementation(async <T,>(path: string): Promise<T> => path.endsWith('/parameters') ? { ...parameters, version } as T : original<T>(path))
    vi.mocked(apiPost).mockImplementation(async <T,>(): Promise<T> => ({ baseVersion: version, changes: [], statusChanges: [] }) as T)
    vi.mocked(apiPut).mockImplementation(async () => { version = 4; throw new ApiError(409, { detail: 'Профиль изменился' }) })
    renderScreen('/motor-calibration?tab=parameters')
    const input = await screen.findByRole('spinbutton', { name: 'Трение вверх (Правая)' })
    fireEvent.change(input, { target: { value: '57' } })
    fireEvent.click(screen.getByRole('button', { name: 'Проверить изменения' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Сохранить и применить' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Профиль изменился')
    expect(input).toHaveValue(57)
    expect(screen.queryByRole('button', { name: 'Сохранить и применить' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Проверить изменения' }))
    expect(await screen.findByText('Что изменится в профиле v4')).toBeVisible()
    expect(apiPost).toHaveBeenLastCalledWith('/api/motor/parameters/preview', { baseVersion: 4, changes: [{ scope: 'side', key: 'coulomb_up_n', side: 'right', value: 57 }] })
    expect(apiPut).toHaveBeenCalledTimes(1)
  })
})
