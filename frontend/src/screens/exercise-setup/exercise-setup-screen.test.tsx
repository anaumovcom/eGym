import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { ExerciseSetupScreen } from '@/screens/exercise-setup/exercise-setup-screen'
import { getExerciseDetails } from '@/mocks/stage2-data'
import { apiGet, apiPost, apiPut } from '@/shared/api/client'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import type { HardwareSnapshot } from '@/features/hardware/model/types'
import type { HardwareCalibration } from '@/features/hardware/model/types'

const navigateMock = vi.fn()
const loadCurrentCalibrationMock = vi.fn<(...args: unknown[]) => Promise<HardwareCalibration | null>>()
const buildBackendBuilderRuntimeSessionMock = vi.fn<(...args: unknown[]) => Promise<RuntimeWorkoutSession>>()
let currentSearch = '?source=catalog&slug=barbell-floor-press&calibration=missing'

vi.mock('@/shared/api/client', async () => ({
  ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'),
  apiGet: vi.fn().mockResolvedValue([]),
  apiPost: vi.fn(),
  apiPut: vi.fn().mockResolvedValue({}),
}))

vi.mock('@/features/runtime/lib/backend-builder-session', () => ({
  buildBackendBuilderRuntimeSession: (...args: unknown[]) => buildBackendBuilderRuntimeSessionMock(...args),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')

  return {
    ...actual,
    useNavigate: () => navigateMock,
    useLocation: () => ({ search: currentSearch }),
    useSearchParams: () => [new URLSearchParams(currentSearch)],
  }
})

function createSnapshot(barPositionMm: number): HardwareSnapshot {
  return {
    motion: {
      barPositionMm,
    },
    safety: {
      state: 'enabled',
    },
  } as HardwareSnapshot
}

function renderScreen() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/exercise-setup${currentSearch}`]}>
        <ExerciseSetupScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...result, queryClient }
}

describe('ExerciseSetupScreen', () => {
  it('keeps locally edited weight, sets, reps and rest across hardware updates and unchanged backend refetches', async () => {
    currentSearch = '?source=builder&programId=back-biceps'
    const original = useRuntimeStore.getState().session!
    const exercise = original.exercises[0]
    const session: RuntimeWorkoutSession = { ...original, source: 'builder', programId: 'back-biceps', dataSource: 'backend', exercises: [exercise] }
    useRuntimeStore.setState({ session })
    buildBackendBuilderRuntimeSessionMock.mockResolvedValue(session)
    const { queryClient } = renderScreen()
    const user = userEvent.setup()
    await waitFor(() => expect(buildBackendBuilderRuntimeSessionMock).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Вес, кг' })).toBeInTheDocument())

    for (const [label, value] of [['Вес, кг', '37'], ['Подходы', '5'], ['Повторы', '13'], ['Отдых, сек', '75']]) {
      const input = screen.getByRole('textbox', { name: label })
      await user.clear(input)
      await user.type(input, value)
      await user.tab()
      await waitFor(() => expect(screen.getByRole('textbox', { name: label })).toHaveValue(value))
    }
    act(() => { useHardwareStore.setState({ snapshot: createSnapshot(760) }) })
    // A structurally identical server snapshot must not overwrite the user's local plan.
    await act(async () => { await queryClient.refetchQueries({ queryKey: ['runtime-builder-session'] }) })
    expect(useRuntimeStore.getState().session!.exercises[0].loadSettings).toMatchObject({ weight: 37, sets: 5, reps: 13, restSeconds: 75 })
    expect(screen.getByRole('textbox', { name: 'Вес, кг' })).toHaveValue('37')
    expect(screen.getByRole('textbox', { name: 'Подходы' })).toHaveValue('5')
    expect(useHardwareStore.getState().runCommand).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Увеличить: Вес' }))
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Вес, кг' })).toHaveValue('39.5'))
    await user.click(screen.getByRole('button', { name: 'Уменьшить: Подходы' }))
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Подходы' })).toHaveValue('4'))

    // Real server plan edits must still be applied; ignoring every refetch would hide those changes.
    const changedExercise = { ...exercise, loadSettings: { ...exercise.loadSettings, weight: 50 },
      plan: exercise.plan.map((set) => ({ ...set, recommendedWeightKg: 50 })) }
    buildBackendBuilderRuntimeSessionMock.mockResolvedValue({ ...session, exercises: [changedExercise] })
    await act(async () => { await queryClient.refetchQueries({ queryKey: ['runtime-builder-session'] }) })
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Вес, кг' })).toHaveValue('50'))
    expect(useRuntimeStore.getState().session!.exercises[0]).toEqual(changedExercise)
  })

  it.each(['perSide', 'side', 'roundNumber'] as const)('refreshes backend setup when only %s changes', async (field) => {
    currentSearch = '?source=builder&programId=back-biceps'
    const original = useRuntimeStore.getState().session!
    const exercise = { ...original.exercises[0], perSide: true, plan: original.exercises[0].plan.map((plan) => ({ ...plan, side: 'left' as const, roundNumber: 1 })) }
    const session: RuntimeWorkoutSession = { ...original, source: 'builder', programId: 'back-biceps', dataSource: 'backend', exercises: [exercise] }
    const updatedExercise = field === 'perSide'
      ? { ...exercise, perSide: false }
      : { ...exercise, plan: exercise.plan.map((plan, index) => index ? plan : { ...plan, ...(field === 'side' ? { side: 'right' as const } : { roundNumber: 2 }) }) }
    useRuntimeStore.setState({ session })
    buildBackendBuilderRuntimeSessionMock.mockResolvedValue({ ...session, exercises: [updatedExercise] })
    renderScreen()
    await waitFor(() => expect(useRuntimeStore.getState().session!.exercises[0]).toEqual(updatedExercise))
    expect(screen.getByText(field === 'perSide' ? 'Обычное выполнение' : 'Поочерёдно · на каждую сторону')).toBeInTheDocument()
    if (field !== 'perSide') expect(screen.getByText(/на сторону/)).toBeInTheDocument()
    expect(useHardwareStore.getState().runCommand).not.toHaveBeenCalled()
  })

  it('defaults LOAD down and saves up independently of the start point, then starts with up', async () => {
    const saved: HardwareCalibration = {
      id: 90, userId: 'alexey', exerciseSlug: 'barbell-floor-press', setupType: 'bar_range',
      lowerPointMm: 300, upperPointMm: 900, fixedPositionMm: null, startPoint: 'lower',
      zeroPositionMm: 600, movementRangeConfirmed: true, calibrationRequired: true,
      isActive: true, capturedAt: new Date().toISOString(), expiresAt: null,
    }
    loadCurrentCalibrationMock.mockImplementation(async () => {
      useHardwareStore.setState({ currentCalibration: saved })
      return saved
    })
    const save = vi.fn().mockImplementation(async payload => {
      const updated = { ...saved, ...payload }
      useHardwareStore.setState({ currentCalibration: updated })
      return updated
    })
    const command = vi.fn().mockResolvedValue({})
    useHardwareStore.setState({ saveCalibration: save, runCommand: command, checkSafetyGate: vi.fn().mockResolvedValue({ allowed: true }) })
    renderScreen()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Тяга вверх', exact: true })).toBeEnabled())
    expect(screen.getByRole('button', { name: 'Нагрузка вниз', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(screen.getByRole('button', { name: 'Тяга вверх', exact: true }))
    await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({ loadDirection: 'up', startPoint: 'lower', lowerPointMm: 300, upperPointMm: 900 })))
    expect(screen.getByText(/удобнее начинать у верхней точки/)).toBeInTheDocument()
    expect(command).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: 'Запустить упражнение' }))
    expect(command).toHaveBeenCalledWith(expect.objectContaining({ action: 'start_motion', loadDirection: 'up', startPoint: 'lower' }))
  })

  beforeEach(() => {
    localStorage.clear()
    vi.mocked(apiGet).mockReset().mockImplementation(async path => path.startsWith('/api/runtime/exercises/settings?') ? null as never : [] as never)
    vi.mocked(apiPut).mockReset().mockResolvedValue({})
    vi.mocked(apiPost).mockReset().mockResolvedValue({ missingExerciseSessionIds: [] })
    currentSearch = '?source=catalog&slug=barbell-floor-press&calibration=missing'
    navigateMock.mockReset()
    loadCurrentCalibrationMock.mockReset()
    loadCurrentCalibrationMock.mockResolvedValue(null)
    buildBackendBuilderRuntimeSessionMock.mockReset()

    useAppStore.setState({
      selectedUserId: 'alexey',
      selectedExerciseSlug: 'barbell-floor-press',
      selectedProgramId: 'back-biceps',
      selectedCalendarDayId: '2026-05-14',
      emergencyStopActive: false,
      favoriteExerciseSlugs: ['barbell-floor-press', 'barbell-bench-press', 'machine-pulldown', 'forearm-plank'],
      blacklistedExerciseSlugs: ['smith-machine-bench-press'],
    })
    useRuntimeStore.setState({ session: null, sessionSignature: null })
    useRuntimeStore.getState().initializeSession({
      source: 'catalog',
      slug: 'barbell-floor-press',
      calibrationState: 'missing',
    })
    useHardwareStore.setState({
      snapshot: createSnapshot(560),
      currentCalibration: null,
      errorMessage: null,
      loadCurrentCalibration: loadCurrentCalibrationMock,
      saveCalibration: vi.fn(),
      deleteCalibration: vi.fn(),
      checkSafetyGate: vi.fn(),
      runCommand: vi.fn(),
      setErrorMessage: vi.fn(),
    })
  })

  it.each(['', '&photo=before', '&photo=after', '&photo=manual'])('opens setup without photo prompts and keeps calibration gating (%s)', async (photo) => {
    currentSearch += photo
    useRuntimeStore.setState({ session: null, sessionSignature: null })

    renderScreen()

    await waitFor(() => expect(loadCurrentCalibrationMock).toHaveBeenCalledWith('alexey', 'barbell-floor-press'))
    expect(useRuntimeStore.getState().session?.view).toBe('exercise-setup')
    expect(screen.queryByRole('button', { name: /фото/i })).not.toBeInTheDocument()
    expect(screen.queryByText(/фото/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Старт недоступен' })).toBeDisabled()
    expect(navigateMock).not.toHaveBeenCalled()
    expect(useHardwareStore.getState().runCommand).not.toHaveBeenCalled()
  })

  it.each(['', '&photo=before', '&photo=after'])('keeps the bodyweight exercise flow without a photo detour (%s)', async (photo) => {
    currentSearch = `?source=catalog&slug=push-up${photo}`
    useRuntimeStore.setState({ session: null, sessionSignature: null })

    renderScreen()

    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(`/exercise-session${currentSearch}`, { replace: true }))
    expect(useRuntimeStore.getState().session?.view).toBe('exercise-session')
    expect(navigateMock.mock.calls.some(([path]) => String(path).includes('/photo-progress'))).toBe(false)
    expect(useHardwareStore.getState().runCommand).not.toHaveBeenCalled()
  })

  it('does not show a runtime photo confirmation for saved legacy photos', () => {
    const session = useRuntimeStore.getState().session!
    useRuntimeStore.setState({ session: { ...session, photoProgress: { ...session.photoProgress, completed: true, mode: 'pre-workout' } } })

    renderScreen()

    expect(screen.queryByText(/фото/i)).not.toBeInTheDocument()
  })

  it('keeps captured calibration points after rerendering the same exercise without a saved calibration', async () => {
    const user = userEvent.setup()

    renderScreen()

    await waitFor(() => expect(loadCurrentCalibrationMock).toHaveBeenCalledWith('alexey', 'barbell-floor-press'))

    await user.click(screen.getByRole('button', { name: 'Зафиксировать нижнюю точку' }))
    expect(screen.getAllByText('56 см').length).toBeGreaterThan(0)

    act(() => {
      useHardwareStore.setState({ snapshot: createSnapshot(760) })
    })

    await user.click(screen.getByRole('button', { name: 'Зафиксировать верхнюю точку' }))
    expect(screen.getAllByText('76 см').length).toBeGreaterThan(0)

    act(() => {
      useRuntimeStore.getState().updateCalibrationState('missing')
    })

    expect(screen.getAllByText('56 см').length).toBeGreaterThan(0)
    expect(screen.getAllByText('76 см').length).toBeGreaterThan(0)
  })

  it('places video, parameters and persistent calibration in independent grid areas', () => {
    const { container } = renderScreen()
    const body = container.querySelector('.rt-setup-body')
    const media = body?.querySelector('.rt-setup-media')
    const parameters = screen.getByRole('region', { name: 'Параметры упражнения' })
    const calibration = screen.getByRole('region', { name: 'Настройка грифа' })

    expect(media?.querySelector('.rt-media-frame')).toBeInTheDocument()
    expect(media).not.toContainElement(calibration)
    expect(parameters.parentElement).toBe(body)
    expect(calibration.parentElement).toBe(body)
    expect(media?.parentElement).toBe(body)
    expect(parameters.compareDocumentPosition(calibration) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('groups movement and capture separately and keeps save as the final calibration action', () => {
    renderScreen()
    const calibration = screen.getByRole('region', { name: 'Настройка грифа', exact: true })
    const movement = within(calibration).getByRole('group', { name: 'Перемещение грифа при настройке' })
    const capture = within(calibration).getByRole('group', { name: 'Фиксация положения грифа' })
    const save = within(calibration).getByRole('button', { name: 'Сохранить амплитуду' })
    expect(within(movement).getAllByRole('button')).toHaveLength(2)
    expect(within(capture).getAllByRole('button')).toHaveLength(2)
    expect(capture).not.toContainElement(save)
    expect(capture.compareDocumentPosition(save) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect([...calibration.querySelectorAll('button')].at(-1)).toBe(save)
    for (const button of calibration.querySelectorAll('button')) {
      expect(button.querySelector('svg[aria-hidden="true"]')).toBeInTheDocument()
    }
  })

  it('shows two distinct video angles in the same vertical media column', async () => {
    const slug = 'barbell-floor-press'
    const details = getExerciseDetails(slug)
    const sideUrl = `/media/exercises/${slug}/male-side.mp4`
    const frontUrl = `/media/exercises/${slug}/male-front.mp4`
    vi.mocked(apiGet).mockImplementation(async (path) => path.startsWith(`/api/exercises/${slug}?`)
      ? { ...details, videos: [
        { url: `/media/exercises/${slug}/female-front.mp4`, label: 'Женщина · Спереди', gender: 'female', view: 'front' },
        { url: frontUrl, label: 'Мужчина · Спереди', gender: 'male', view: 'front' },
        { url: sideUrl, label: 'Мужчина · Сбоку', gender: 'male', view: 'side' },
        { url: sideUrl, label: 'Дубликат', gender: 'male', view: 'side' },
      ] }
      : [])

    const { container } = renderScreen()
    await waitFor(() => expect([...container.querySelectorAll('.rt-setup-media video source')].map((node) => node.getAttribute('src'))).toEqual([sideUrl, frontUrl]))
    const media = container.querySelector('.rt-setup-media')
    expect(media).toHaveAttribute('data-video-count', '2')
    expect(media?.querySelectorAll(':scope > .rt-media')).toHaveLength(2)
    expect(screen.getByRole('region', { name: 'Настройка грифа', exact: true })).toBeVisible()
  })

  it('shows API video for a catalog exercise missing from mock media and retains session settings', async () => {
    const slug = 'smith-machine-close-grip-bench-press'
    const videoUrl = `/media/exercises/${slug}/male-side.mp4`
    const details = getExerciseDetails(slug)
    expect(details.videos).toHaveLength(0)
    vi.mocked(apiGet).mockImplementation(async (path) => path.startsWith(`/api/exercises/${slug}?`)
      ? { ...details, previewVideoUrl: videoUrl, videos: [{ url: videoUrl, label: 'Мужчина · Сбоку', gender: 'male', view: 'side' }] }
      : [])
    currentSearch = `?source=catalog&slug=${slug}&calibration=missing`
    useRuntimeStore.getState().initializeSession({ source: 'catalog', slug, calibrationState: 'missing' })
    useRuntimeStore.getState().updateLoadSettings({ reps: 15 })
    const before = useRuntimeStore.getState().session!

    const { container } = renderScreen()

    await waitFor(() => expect(container.querySelector('video source')?.getAttribute('src')).toBe(videoUrl))
    expect(container.querySelectorAll('.rt-setup-media video')).toHaveLength(1)
    expect(container.querySelector('.rt-setup-media')).toHaveAttribute('data-video-count', '1')
    const after = useRuntimeStore.getState().session!
    expect(after.exercises[0].details.videos[0].url).toBe(videoUrl)
    expect(after.exercises[0].summary.previewVideoUrl).toBe(videoUrl)
    expect(after.exercises[0].loadSettings.reps).toBe(15)
    expect(after.exercises[0].calibrationState).toBe(before.exercises[0].calibrationState)
    expect(after.currentSetIndex).toBe(before.currentSetIndex)
    expect(after.startedAt).toBe(before.startedAt)
  })

  it('moves the bar with buttons before capturing a range point', async () => {
    const user = userEvent.setup()
    const command = vi.fn().mockImplementation(async ({ action }: { action: string }) => {
      if (action === 'jog_stop') useHardwareStore.setState({ snapshot: createSnapshot(570) })
      return {}
    })
    useHardwareStore.setState({ runCommand: command })
    renderScreen()

    const up = screen.getByRole('button', { name: '↑ Вверх · удерживать' })
    fireEvent.pointerDown(up, { pointerType: 'mouse', pointerId: 1, button: 0 })
    await waitFor(() => expect(command).toHaveBeenCalledWith(expect.objectContaining({ action: 'jog_start', direction: 'up', mode: 'service', userId: 'alexey', exerciseSlug: 'barbell-floor-press' })))
    fireEvent.pointerUp(up, { pointerType: 'mouse', pointerId: 1 })
    await waitFor(() => expect(command).toHaveBeenCalledWith(expect.objectContaining({ action: 'jog_stop' })))
    await user.click(screen.getByRole('button', { name: 'Зафиксировать нижнюю точку' }))
    expect(screen.getAllByText('57 см').length).toBeGreaterThan(0)
  })

  it('moves the bar down before capturing a fixed position', async () => {
    const user = userEvent.setup()
    const command = vi.fn().mockImplementation(async ({ action }: { action: string }) => {
      if (action === 'jog_stop') useHardwareStore.setState({ snapshot: createSnapshot(550) })
      return {}
    })
    useHardwareStore.setState({ runCommand: command })
    renderScreen()
    await user.click(screen.getByRole('button', { name: 'Фиксированное положение' }))
    const down = screen.getByRole('button', { name: '↓ Вниз · удерживать' })
    fireEvent.pointerDown(down, { pointerType: 'mouse', pointerId: 1, button: 0 })
    await waitFor(() => expect(command).toHaveBeenCalledWith(expect.objectContaining({ action: 'jog_start', direction: 'down' })))
    fireEvent.pointerUp(down, { pointerType: 'mouse', pointerId: 1 })
    await waitFor(() => expect(command).toHaveBeenCalledWith(expect.objectContaining({ action: 'jog_stop' })))
    await user.click(screen.getByRole('button', { name: 'Зафиксировать высоту грифа' }))
    expect(screen.getAllByText('55 см').length).toBeGreaterThan(0)
    expect(command).toHaveBeenCalledWith(expect.objectContaining({ action: 'jog_start', direction: 'down' }))
  })

  it('enters weightless once when opened on an idle machine', async () => {
    const command = vi.fn().mockResolvedValue({})
    useHardwareStore.setState({ runCommand: command, snapshot: { ...createSnapshot(560), motion: { barPositionMm: 560, controlMode: 'idle' } } as HardwareSnapshot })

    renderScreen()

    await waitFor(() => expect(command).toHaveBeenCalledWith(expect.objectContaining({ action: 'enter_weightless', exerciseSlug: 'barbell-floor-press' })))
    act(() => {
      useHardwareStore.setState({ snapshot: { ...createSnapshot(560), motion: { barPositionMm: 560, controlMode: 'paused' } } as HardwareSnapshot })
    })
    expect(command.mock.calls.filter(([payload]) => payload.action === 'enter_weightless')).toHaveLength(1)
  })

  it('does not switch a set started elsewhere to weightless when it pauses later', async () => {
    const command = vi.fn().mockResolvedValue({})
    useHardwareStore.setState({ runCommand: command, snapshot: { ...createSnapshot(560), motion: { barPositionMm: 560, controlMode: 'training' } } as HardwareSnapshot })

    renderScreen()
    await waitFor(() => expect(loadCurrentCalibrationMock).toHaveBeenCalledWith('alexey', 'barbell-floor-press'))
    act(() => {
      useHardwareStore.setState({ snapshot: { ...createSnapshot(560), motion: { barPositionMm: 560, controlMode: 'paused' } } as HardwareSnapshot })
    })

    expect(command).not.toHaveBeenCalledWith(expect.objectContaining({ action: 'enter_weightless' }))
  })

  it('saves a fixed height for pull-ups and starts with the saved position', async () => {
    currentSearch = '?source=catalog&slug=bodyweight-pull-up'
    useRuntimeStore.setState({ session: null, sessionSignature: null })
    useRuntimeStore.getState().initializeSession({ source: 'catalog', slug: 'bodyweight-pull-up' })
    const user = userEvent.setup()
    const saved: HardwareCalibration = {
      id: 12, userId: 'alexey', exerciseSlug: 'bodyweight-pull-up', setupType: 'fixed_position',
      lowerPointMm: null, upperPointMm: null, fixedPositionMm: 560, zeroPositionMm: 560,
      movementRangeConfirmed: false, calibrationRequired: true, isActive: true,
      capturedAt: new Date().toISOString(), expiresAt: null,
    }
    const save = vi.fn().mockImplementation(async () => {
      useHardwareStore.setState({ currentCalibration: saved })
      return saved
    })
    const gate = vi.fn().mockResolvedValue({ allowed: true })
    const command = vi.fn().mockResolvedValue({})
    useHardwareStore.setState({ saveCalibration: save, checkSafetyGate: gate, runCommand: command })

    renderScreen()
    await waitFor(() => expect(loadCurrentCalibrationMock).toHaveBeenCalledWith('alexey', 'bodyweight-pull-up'))
    expect(screen.getByRole('button', { name: 'Старт недоступен' })).toBeDisabled()
    expect(navigateMock).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Фиксированное положение' }))
    expect(screen.queryByText('Нижняя точка')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Зафиксировать высоту грифа' }))
    await user.click(screen.getByRole('button', { name: 'Сохранить положение' }))
    await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({ userId: 'alexey', exerciseSlug: 'bodyweight-pull-up', setupType: 'fixed_position', fixedPositionMm: 560, lowerPointMm: null, upperPointMm: null })))
    expect(screen.getByRole('region', { name: 'Настройка грифа', exact: true })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Зафиксировать высоту грифа' })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Свернуть' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Запустить упражнение' }))
    await waitFor(() => expect(command).toHaveBeenCalledWith(expect.objectContaining({ action: 'start_fixed_position', positionMm: 560, repCountSource: 'manual' })))
    expect(navigateMock).toHaveBeenCalledWith(`/exercise-session${currentSearch}`)
  })

  it('loads a saved range and blocks start until edits are saved', async () => {
    const saved: HardwareCalibration = {
      id: 3, userId: 'alexey', exerciseSlug: 'barbell-floor-press', setupType: 'bar_range',
      lowerPointMm: 560, upperPointMm: 760, fixedPositionMm: null, zeroPositionMm: 660,
      movementRangeConfirmed: true, calibrationRequired: true, isActive: true,
      capturedAt: new Date().toISOString(), expiresAt: null,
    }
    loadCurrentCalibrationMock.mockImplementation(async () => {
      useHardwareStore.setState({ currentCalibration: saved })
      return saved
    })
    const user = userEvent.setup()
    renderScreen()
    expect(await screen.findByRole('button', { name: 'Запустить упражнение' })).toBeEnabled()
    expect(screen.getByText('Калибровка: 56 см - 76 см')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Настройка грифа', exact: true })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Свернуть' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Фиксированное положение' }))
    expect(screen.getByRole('button', { name: 'Старт недоступен' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Сбросить изменения' }))
    expect(screen.getByRole('button', { name: 'Запустить упражнение' })).toBeEnabled()
    expect(screen.getByRole('region', { name: 'Настройка грифа', exact: true })).toBeVisible()
  })

  it('loads a previously saved fixed height without capturing points again', async () => {
    const saved: HardwareCalibration = {
      id: 7, userId: 'alexey', exerciseSlug: 'barbell-floor-press', setupType: 'fixed_position',
      lowerPointMm: null, upperPointMm: null, fixedPositionMm: 1480, zeroPositionMm: 1480,
      movementRangeConfirmed: false, calibrationRequired: true, isActive: true,
      capturedAt: new Date().toISOString(), expiresAt: null,
    }
    loadCurrentCalibrationMock.mockImplementation(async () => {
      useHardwareStore.setState({ currentCalibration: saved })
      return saved
    })
    renderScreen()
    expect(await screen.findByText('Фиксация: 148 см')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Запустить упражнение' })).toBeEnabled()
    expect(screen.getByRole('region', { name: 'Настройка грифа', exact: true })).toBeVisible()
    expect(screen.getByText('Фиксированная высота')).toBeInTheDocument()
    expect(screen.queryByText('Нижняя точка')).not.toBeInTheDocument()
    const save = vi.fn().mockImplementation(async () => {
      const updated = { ...saved, fixedPositionMm: 560 }
      useHardwareStore.setState({ currentCalibration: updated })
      return updated
    })
    useHardwareStore.setState({ saveCalibration: save })
    await userEvent.setup().click(screen.getByRole('button', { name: 'Зафиксировать высоту грифа' }))
    expect(screen.getByRole('button', { name: 'Старт недоступен' })).toBeDisabled()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Сохранить положение' }))
    await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({ setupType: 'fixed_position', fixedPositionMm: 560 })))
    expect(screen.getByRole('button', { name: 'Запустить упражнение' })).toBeEnabled()
    expect(screen.getByRole('region', { name: 'Настройка грифа', exact: true })).toBeVisible()
  })

  it('replaces a stale backend builder session with the updated exercise plan', async () => {
    currentSearch = '?source=builder&programId=back-biceps&photo=before'

    useRuntimeStore.getState().initializeSession({
      source: 'builder',
      programId: 'back-biceps',
      photoMode: 'pre-workout',
    })

    const initialSession = useRuntimeStore.getState().session
    if (!initialSession) {
      throw new Error('Expected runtime session to be initialized')
    }

    const staleSession: RuntimeWorkoutSession = {
      ...initialSession,
      source: 'builder',
      programId: 'back-biceps',
      dataSource: 'backend',
      view: 'exercise-setup',
      exercises: initialSession.exercises.map((exercise, index) =>
        index === 0
          ? {
              ...exercise,
              slug: 'old-exercise',
              name: 'Старое упражнение',
            }
          : exercise,
      ),
    }
    const updatedSession: RuntimeWorkoutSession = {
      ...staleSession,
      exercises: staleSession.exercises.map((exercise, index) =>
        index === 0
          ? {
              ...exercise,
              slug: 'new-exercise',
              name: 'Новое упражнение',
            }
          : exercise,
      ),
    }

    useRuntimeStore.setState({ session: staleSession, sessionSignature: 'builder::back-biceps::pre-workout' })
    buildBackendBuilderRuntimeSessionMock.mockResolvedValue(updatedSession)

    renderScreen()

    await waitFor(() => expect(buildBackendBuilderRuntimeSessionMock).toHaveBeenCalled())
    await waitFor(() => expect(useRuntimeStore.getState().session?.exercises[0]?.slug).toBe('new-exercise'))
    expect(buildBackendBuilderRuntimeSessionMock).toHaveBeenCalledWith({ userId: 'alexey', programId: 'back-biceps', runId: undefined, calibrationState: undefined })
    expect(navigateMock.mock.calls.some(([path]) => String(path).includes('/photo-progress'))).toBe(false)
  })

  it('preserves a matching backend session and saved results when reopening without the old photo parameter', async () => {
    currentSearch = '?source=builder&programId=back-biceps'
    const initialSession = useRuntimeStore.getState().session!
    const session: RuntimeWorkoutSession = {
      ...initialSession,
      source: 'builder', programId: 'back-biceps', dataSource: 'backend', backendWorkoutSessionId: 42,
      currentSetIndex: 1,
      completedSets: { [initialSession.currentExerciseId]: [{ setNumber: 1, plannedValue: 10, actualValue: 10, tempoLabel: 'хорошо' }] },
    }
    useRuntimeStore.setState({ session, sessionSignature: 'builder::back-biceps::pre-workout:' })
    buildBackendBuilderRuntimeSessionMock.mockResolvedValue({ ...session, currentSetIndex: 0, completedSets: {}, backendWorkoutSessionId: undefined })

    renderScreen()

    await waitFor(() => expect(buildBackendBuilderRuntimeSessionMock).toHaveBeenCalled())
    expect(useRuntimeStore.getState().session).toMatchObject({ id: session.id, backendWorkoutSessionId: 42, currentSetIndex: 1, completedSets: session.completedSets })
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('starts the same workout from the first exercise on a new training day', async () => {
    currentSearch = '?source=builder&programId=back-biceps'
    const initialSession = useRuntimeStore.getState().session!
    const first = initialSession.exercises[0]
    const second = { ...first, id: `${first.id}-2`, order: 2 }
    const yesterday: RuntimeWorkoutSession = {
      ...initialSession,
      exercises: [first, second],
      source: 'builder', programId: 'back-biceps', dataSource: 'backend', backendWorkoutSessionId: 42,
      startedAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
      currentExerciseId: second.id, completedExerciseIds: [first.id],
      completedSets: { [first.id]: [{ setNumber: 1, plannedValue: 10, actualValue: 10, tempoLabel: 'хорошо' }] },
    }
    useRuntimeStore.setState({ session: yesterday, sessionSignature: 'builder::back-biceps::' })
    buildBackendBuilderRuntimeSessionMock.mockResolvedValue({
      ...yesterday, startedAt: new Date().toISOString(), currentExerciseId: first.id, completedExerciseIds: [],
      completedSets: {}, backendWorkoutSessionId: undefined,
    })

    renderScreen()

    await waitFor(() => expect(useRuntimeStore.getState().session?.currentExerciseId).toBe(first.id))
    expect(useRuntimeStore.getState().session).toMatchObject({ completedSets: {}, backendWorkoutSessionId: undefined })
  })

  it('goes back to the previous exercise and does it again instead of returning to its consumed summary', async () => {
    const user = userEvent.setup()
    vi.mocked(apiPost).mockResolvedValue({ missingExerciseSessionIds: [] })
    const session = useRuntimeStore.getState().session!
    const first = session.exercises[0]
    const second = { ...first, id: `${first.id}-2`, order: 2 }
    useRuntimeStore.setState({ session: {
      ...session,
      exercises: [first, second],
      currentExerciseId: second.id,
      completedSets: { [first.id]: [{ setNumber: 1 } as never] },
      completedExerciseIds: [first.id],
      exerciseOutcomes: { [first.id]: 'completed' },
      backendWorkoutSessionId: 42,
      backendExerciseSessionIds: { [first.id]: 5 },
    } })
    renderScreen()

    await user.click(screen.getByRole('button', { name: 'Предыдущее упражнение' }))
    const confirm = screen.getByRole('dialog', { name: 'Вернуться к предыдущему упражнению?' })
    await user.click(within(confirm).getByRole('button', { name: 'Выполнить заново' }))

    await waitFor(() => expect(useRuntimeStore.getState().session?.currentExerciseId).toBe(first.id))
    expect(apiPost).toHaveBeenCalledWith('/api/runtime/exercises/reset', { exercises: [expect.objectContaining({ exerciseSessionId: 5, sets: [], resetSets: true })] })
    expect(useRuntimeStore.getState().session?.completedSets[first.id]).toBeUndefined()
    expect(navigateMock).not.toHaveBeenCalledWith(-1)
  })

  it.each(['moving', 'fixed_hold'])('stops %s before resetting previous exercise from setup', async mode => {
    const original = useRuntimeStore.getState().session!
    const first = original.exercises[0]
    const second = { ...first, id: 'second', order: 2 }
    useRuntimeStore.setState({ session: { ...original, exercises: [first, second], currentExerciseId: second.id,
      backendExerciseSessionIds: { [first.id]: 5 } } })
    useHardwareStore.setState({ snapshot: { ...createSnapshot(560), control: { mode } } as HardwareSnapshot })
    let finish!: () => void
    const run = vi.fn().mockImplementation(() => new Promise<void>(resolve => { finish = resolve }))
    useHardwareStore.setState({ runCommand: run })
    vi.mocked(apiPost).mockResolvedValue({ missingExerciseSessionIds: [] })
    renderScreen()
    await userEvent.click(screen.getByRole('button', { name: 'Предыдущее упражнение' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Выполнить заново' }))
    expect(run).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ action: 'complete_set' }))
    expect(apiPost).not.toHaveBeenCalled()
    expect(useRuntimeStore.getState().session!.currentExerciseId).toBe(second.id)
    await act(async () => finish())
    await waitFor(() => expect(useRuntimeStore.getState().session!.currentExerciseId).toBe(first.id))
  })

  it('blocks duplicate start and previous-exercise actions while the start safety check is pending', async () => {
    const original = useRuntimeStore.getState().session!
    const first = original.exercises[0]
    const second = { ...first, id: 'second', order: 2 }
    useRuntimeStore.setState({ session: { ...original, exercises: [first, second], currentExerciseId: second.id } })
    const saved: HardwareCalibration = {
      id: 90, userId: 'alexey', exerciseSlug: first.slug, setupType: 'bar_range',
      lowerPointMm: 300, upperPointMm: 900, fixedPositionMm: null, startPoint: 'lower',
      zeroPositionMm: 560, movementRangeConfirmed: true, calibrationRequired: true,
      isActive: true, capturedAt: new Date().toISOString(), expiresAt: null,
    }
    loadCurrentCalibrationMock.mockImplementation(async () => {
      useHardwareStore.setState({ currentCalibration: saved })
      return saved
    })
    let checked!: (value: { allowed: boolean }) => void
    const check = vi.fn().mockImplementation(() => new Promise(resolve => { checked = resolve }))
    const run = vi.fn().mockResolvedValue({})
    useHardwareStore.setState({ checkSafetyGate: check, runCommand: run })
    renderScreen()
    const start = await screen.findByRole('button', { name: 'Запустить упражнение' })
    await waitFor(() => expect(start).toBeEnabled())
    await userEvent.dblClick(start)
    expect(check).toHaveBeenCalledTimes(1)
    expect(start).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Предыдущее упражнение' })).toBeDisabled()
    await act(async () => checked({ allowed: true }))
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(`/exercise-session${currentSearch}`))
    expect(run).toHaveBeenCalledTimes(1)
  })

  it('does not erase saved results if stopping the setup motor fails', async () => {
    const original = useRuntimeStore.getState().session!
    const first = original.exercises[0]
    const second = { ...first, id: 'second', order: 2 }
    useRuntimeStore.setState({ session: { ...original, exercises: [first, second], currentExerciseId: second.id,
      backendExerciseSessionIds: { [first.id]: 5 } } })
    useHardwareStore.setState({ snapshot: { ...createSnapshot(560), control: { mode: 'fixed_hold' } } as HardwareSnapshot,
      runCommand: vi.fn().mockRejectedValue(new Error('Привод не ответил')) })
    renderScreen()
    await userEvent.click(screen.getByRole('button', { name: 'Предыдущее упражнение' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Выполнить заново' }))
    await waitFor(() => expect(screen.getByText('Привод не ответил')).toBeVisible())
    expect(apiPost).not.toHaveBeenCalled()
    expect(useRuntimeStore.getState().session!.currentExerciseId).toBe(second.id)
  })

  it('keeps a plain back button on the first exercise', () => {
    renderScreen()
    expect(screen.getByRole('button', { name: 'Назад' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Предыдущее упражнение' })).not.toBeInTheDocument()
  })
})