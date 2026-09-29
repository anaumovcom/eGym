import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { ExerciseSetupScreen } from '@/screens/exercise-setup/exercise-setup-screen'
import { getExerciseDetails } from '@/mocks/stage2-data'
import { apiGet } from '@/shared/api/client'
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

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/exercise-setup${currentSearch}`]}>
        <ExerciseSetupScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ExerciseSetupScreen', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(apiGet).mockReset().mockResolvedValue([])
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

  it('shows the video separately and places the bar setup below the exercise parameters', () => {
    const { container } = renderScreen()
    const body = container.querySelector('.rt-setup-body')
    const media = body?.querySelector('.rt-setup-media')
    const right = body?.querySelector('.rt-setup-right')
    const parameters = screen.getByRole('region', { name: 'Параметры упражнения' })
    const calibration = screen.getByRole('region', { name: 'Настройка грифа' })

    expect(media?.querySelector('.rt-media-frame')).toBeInTheDocument()
    expect(media).not.toContainElement(calibration)
    expect(right).toContainElement(parameters)
    expect(right).toContainElement(calibration)
    expect(parameters.compareDocumentPosition(calibration) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
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
    const after = useRuntimeStore.getState().session!
    expect(after.exercises[0].details.videos[0].url).toBe(videoUrl)
    expect(after.exercises[0].summary.previewVideoUrl).toBe(videoUrl)
    expect(after.exercises[0].loadSettings.reps).toBe(15)
    expect(after.exercises[0].calibrationState).toBe('missing')
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
    await user.click(screen.getByRole('button', { name: 'Запустить упражнение' }))
    await waitFor(() => expect(command).toHaveBeenCalledWith(expect.objectContaining({ action: 'start_fixed_position', positionMm: 560, repCountSource: 'load' })))
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
    await user.click(screen.getByRole('button', { name: 'Калибровка: 56 см - 76 см' }))
    await user.click(screen.getByRole('button', { name: 'Фиксированное положение' }))
    expect(screen.getByRole('button', { name: 'Старт недоступен' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Сбросить изменения' }))
    expect(screen.getByRole('button', { name: 'Запустить упражнение' })).toBeEnabled()
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
    expect(await screen.findByRole('button', { name: 'Фиксация: 148 см' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Запустить упражнение' })).toBeEnabled()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Фиксация: 148 см' }))
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
})