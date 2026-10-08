import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ExerciseSessionScreen } from '@/screens/exercise-session/exercise-session-screen'
import { getExerciseDetails } from '@/mocks/stage2-data'
import { apiGet, apiPost } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import type { HardwareCalibration, HardwareSnapshot } from '@/features/hardware/model/types'
import { coachLifecycle } from '@/features/coach/lib/runtime-observation'

const navigateMock = vi.fn()
const runCommandMock = vi.fn().mockResolvedValue({})
let currentSearch = '?source=catalog&slug=barbell-floor-press'

vi.mock('react-router-dom', async () => ({
  ...await vi.importActual<typeof import('react-router-dom')>('react-router-dom'),
  useNavigate: () => navigateMock,
  useLocation: () => ({ search: currentSearch }),
  useSearchParams: () => [new URLSearchParams(currentSearch)],
}))

vi.mock('@/shared/api/client', async () => ({
  ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'),
  apiGet: vi.fn(),
  apiPost: vi.fn(),
}))

vi.mock('@/features/runtime/lib/runtime-persistence', async () => ({
  ...await vi.importActual<typeof import('@/features/runtime/lib/runtime-persistence')>('@/features/runtime/lib/runtime-persistence'),
  saveWorkoutToBackend: vi.fn().mockResolvedValue({ workoutSessionId: 42 }),
}))

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ExerciseSessionScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ExerciseSessionScreen', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_COACH_ENABLED', 'false')
    coachLifecycle.clear()
    localStorage.clear()
    currentSearch = '?source=catalog&slug=barbell-floor-press'
    navigateMock.mockReset()
    runCommandMock.mockClear()
    vi.mocked(apiGet).mockReset().mockResolvedValue([])
    vi.mocked(apiPost).mockReset()
    vi.mocked(apiPost).mockImplementation(async (path: string) => {
      if (path === '/api/runtime/exercises') return { exerciseSessionId: 7, outcome: 'completed', exerciseId: 'x', title: 'Итог', subtitle: '', setResults: [], totals: { setsCompleted: '1', repsOrTime: '8', volume: '0', tempo: 'хорошо' }, planVsFact: [], recommendation: '', nextStepLabel: '' } as never
      if (path === '/api/runtime/sets') return { setId: 1, exerciseSessionId: 7 } as never
      throw new Error(`Unexpected POST ${path}`)
    })
    useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
    useHardwareStore.setState({ snapshot: null, currentCalibration: null, errorMessage: null, runCommand: runCommandMock, loadCurrentCalibration: vi.fn().mockResolvedValue(null), setErrorMessage: vi.fn() })
    useRuntimeStore.setState({ session: null, sessionSignature: null })
    useRuntimeStore.getState().initializeSession({ source: 'catalog', slug: 'barbell-floor-press' })
    useRuntimeStore.getState().startExercise()
  })

  afterEach(() => { vi.unstubAllEnvs(); coachLifecycle.clear() })

  function enableCoachObservation(lastSet = false) {
    vi.stubEnv('VITE_COACH_ENABLED', 'true')
    const session = useRuntimeStore.getState().session!
    useRuntimeStore.setState({ session: { ...session, dataSource: 'backend',
      exercises: lastSet ? session.exercises.map(exercise => ({ ...exercise, plan: exercise.plan.slice(0, 1) })) : session.exercises,
    } })
  }

  it('E02 observes stop, save ack and exercise summary without adding hardware commands', async () => {
    enableCoachObservation(true)
    const user = userEvent.setup()
    renderScreen()
    const input = screen.getByRole('textbox', { name: 'Повторы' })
    await user.clear(input)
    await user.type(input, '2')
    await user.tab()
    await user.click(screen.getByRole('button', { name: 'Завершить подход' }))
    await waitFor(() => expect(navigateMock).toHaveBeenCalled())
    expect(coachLifecycle.snapshot().map(event => event.kind)).toEqual(['set_stopped', 'set_persisted', 'exercise_finalized'])
    expect(coachLifecycle.snapshot()[1].facts.find(fact => fact.id === 'result.outcome')?.value).toBe('partial')
    expect(runCommandMock.mock.calls.filter(([command]) => command.action === 'complete_set')).toHaveLength(1)
  })

  it('E02 keeps successful set ack when the later summary save fails', async () => {
    enableCoachObservation(true)
    vi.mocked(apiPost).mockImplementation(async (path, payload) => {
      if (path === '/api/runtime/sets') return { setId: 10, exerciseSessionId: 7 } as never
      if (path === '/api/runtime/exercises' && (payload as { status: string }).status === 'in_progress') return { exerciseSessionId: 7 } as never
      throw new Error('Summary save failed')
    })
    const user = userEvent.setup()
    renderScreen()
    await user.click(screen.getByRole('button', { name: 'Увеличить: Повторы' }))
    await user.click(screen.getByRole('button', { name: 'Завершить подход' }))
    await screen.findByRole('alert')
    expect(coachLifecycle.snapshot().map(event => event.kind)).toEqual(['set_stopped', 'set_persisted'])
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('E02 does not observe a late save ack after user identity changes', async () => {
    enableCoachObservation()
    let resolveAck: (value: unknown) => void = () => { throw new Error('No save pending') }
    vi.mocked(apiPost).mockImplementation(async path => {
      if (path === '/api/runtime/exercises') return { exerciseSessionId: 7 } as never
      if (path === '/api/runtime/sets') return await new Promise(resolve => { resolveAck = resolve }) as never
      throw new Error('Unexpected POST')
    })
    const user = userEvent.setup()
    renderScreen()
    await user.click(screen.getByRole('button', { name: 'Увеличить: Повторы' }))
    await user.click(screen.getByRole('button', { name: 'Завершить подход' }))
    await waitFor(() => expect(vi.mocked(apiPost).mock.calls.some(([path]) => path === '/api/runtime/sets')).toBe(true))
    act(() => useAppStore.setState({ selectedUserId: 'elena' }))
    await act(async () => resolveAck({ setId: 10, exerciseSessionId: 7 }))
    await waitFor(() => expect(navigateMock).toHaveBeenCalled())
    expect(coachLifecycle.snapshot()).toEqual([])
  })

  it('shows the exercise fullscreen with one large finish action and no scrollable navigation', () => {
    renderScreen()

    const session = useRuntimeStore.getState().session!
    const exercise = session.exercises[0]
    expect(screen.getByRole('heading', { level: 1, name: exercise.name })).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Основная навигация' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Аварийная остановка', exact: true })).toHaveLength(1)

    const actions = screen.getByRole('group', { name: 'Действия с подходом' })
    expect(within(actions).getByRole('button', { name: 'Завершить подход' })).toHaveAttribute('data-variant', 'primary')
    expect(within(actions).getByRole('button', { name: 'Пропустить упражнение' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^(Выполнено|Частично|Пропуск)$/ })).not.toBeInTheDocument()

    expect(screen.getByRole('group', { name: 'Повторы' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'Вес' })).toBeInTheDocument()
    expect(screen.getByRole('progressbar', { name: 'Прогресс подхода' })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('loads catalog video missing from mock media without restarting the running exercise', async () => {
    const slug = 'smith-machine-close-grip-bench-press'
    currentSearch = `?source=catalog&slug=${slug}`
    const videoUrl = `/media/exercises/${slug}/male-side.mp4`
    const details = getExerciseDetails(slug)
    expect(details.videos).toHaveLength(0)
    vi.mocked(apiGet).mockImplementation(async (path) => path.startsWith(`/api/exercises/${slug}?`)
      ? { ...details, previewVideoUrl: videoUrl, videos: [{ url: videoUrl, label: 'Мужчина · Сбоку', gender: 'male', view: 'side' }] }
      : [])
    useRuntimeStore.getState().initializeSession({ source: 'catalog', slug })
    useRuntimeStore.getState().updateLoadSettings({ reps: 15 })
    useRuntimeStore.getState().startExercise()
    const before = useRuntimeStore.getState().session!
    expect(before.exercises[0].details.videos).toHaveLength(0)

    const { container } = renderScreen()

    await waitFor(() => expect(container.querySelector('video source')?.getAttribute('src')).toBe(videoUrl))
    const after = useRuntimeStore.getState().session!
    expect(after.view).toBe('exercise-session')
    expect(after.startedAt).toBe(before.startedAt)
    expect(after.sessionState).toEqual(before.sessionState)
    expect(after.exercises[0].loadSettings.reps).toBe(15)
    expect(after.exercises[0].details.videos[0].url).toBe(videoUrl)
  })

  it('maps the bar position between the lower and upper markers across 80% of the rail', () => {
    const motion = {
      barPositionMm: 300.5, lowerBoundMm: 295, upperBoundMm: 306,
      leftPositionMm: 300.5, rightPositionMm: 300.5,
      amplitudePercent: 50, repetitionCount: 0, syncDeltaMm: 0,
    } as HardwareSnapshot['motion']
    useHardwareStore.setState({ snapshot: { motion, safety: { state: 'enabled' } } as HardwareSnapshot })
    renderScreen()

    const rail = screen.getByRole('region', { name: 'Положение грифа' })
    const barPosition = () => rail.querySelector('[data-rail-position="current"]')
    expect(within(rail).getByLabelText('Низ · 295 мм').parentElement).toHaveStyle({ bottom: '10%' })
    expect(within(rail).getByLabelText('Верх · 306 мм').parentElement).toHaveStyle({ bottom: '90%' })
    expect(barPosition()).toHaveStyle({ bottom: '50%' })
    expect(within(rail).getByLabelText('Гриф · 301 мм')).toBeInTheDocument()
    expect(within(rail).getByLabelText('Гриф · 301 мм')).toHaveClass('col-start-1')
    expect(within(rail).getByLabelText('Низ · 295 мм')).toHaveClass('col-start-3')
    expect(within(rail).getByLabelText('Верх · 306 мм')).toHaveClass('col-start-3')
    expect(rail.querySelector('[data-rail-limit="lower"] [aria-hidden="true"]')).toHaveClass('h-[2px]', 'w-10', 'justify-self-center')
    expect(rail.querySelector('[data-rail-limit="upper"] [aria-hidden="true"]')).toHaveClass('h-[2px]', 'w-10', 'justify-self-center')
    expect(within(rail).getByText('Положение · мм')).toBeInTheDocument()
    expect(within(rail).getByLabelText('Гриф · 301 мм')).toHaveTextContent('Гриф301')
    expect(within(rail).getByLabelText('Низ · 295 мм')).toHaveTextContent('Низ295')
    expect(within(rail).getByLabelText('Верх · 306 мм')).toHaveTextContent('Верх306')

    act(() => useHardwareStore.setState({ snapshot: { motion: { ...motion, barPositionMm: 306 }, safety: { state: 'enabled' } } as HardwareSnapshot }))
    expect(barPosition()).toHaveStyle({ bottom: '90%' })
    expect(within(rail).getByLabelText('Гриф · 306 мм')).toBeInTheDocument()
    act(() => useHardwareStore.setState({ snapshot: { motion: { ...motion, barPositionMm: 295 }, safety: { state: 'enabled' } } as HardwareSnapshot }))
    expect(barPosition()).toHaveStyle({ bottom: '10%' })
    expect(within(rail).getByLabelText('Гриф · 295 мм')).toBeInTheDocument()
  })

  it('shows weight and live bar telemetry for a zero-weight machine exercise', () => {
    const slug = 'smith-machine-close-grip-bench-press'
    currentSearch = `?source=catalog&slug=${slug}`
    useRuntimeStore.getState().initializeSession({ source: 'catalog', slug })
    useRuntimeStore.getState().updateLoadSettings({ weight: 0 })
    useRuntimeStore.getState().startExercise()
    expect(useRuntimeStore.getState().session!.exercises[0].loadSettings.weight).toBe(0)
    const motion = {
      barPositionMm: 450, lowerBoundMm: 356, upperBoundMm: 542,
      leftPositionMm: 450, rightPositionMm: 450,
      amplitudePercent: 40, repetitionCount: 0, syncDeltaMm: 0,
    } as HardwareSnapshot['motion']
    useHardwareStore.setState({ snapshot: { motion, safety: { state: 'enabled' } } as HardwareSnapshot })

    renderScreen()

    expect(screen.getByRole('group', { name: 'Вес' })).toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Положение грифа' })).getByLabelText('Гриф · 450 мм')).toBeInTheDocument()
    expect(screen.getByText('450 мм')).toBeInTheDocument()
  })

  it('shows a machine hold during the set and resumes it', async () => {
    const user = userEvent.setup()
    const motion = {
      barPositionMm: 450, lowerBoundMm: 356, upperBoundMm: 542,
      leftPositionMm: 450, rightPositionMm: 450,
      amplitudePercent: 40, repetitionCount: 1, syncDeltaMm: 0,
    } as HardwareSnapshot['motion']
    useHardwareStore.setState({ snapshot: { motion, control: { mode: 'training', label: 'Движение выполняется', message: '' }, safety: { state: 'enabled' } } as HardwareSnapshot })
    renderScreen()
    expect(screen.queryByRole('status', { name: 'Гриф удерживается' })).not.toBeInTheDocument()

    act(() => useHardwareStore.setState({ snapshot: { motion, control: { mode: 'paused', label: 'Спасение', message: 'Гриф удержан.' }, safety: { state: 'enabled' } } as HardwareSnapshot }))
    const hold = screen.getByRole('status', { name: 'Гриф удерживается' })
    expect(hold).toHaveTextContent('Спасение · повторы не засчитываются')
    await user.click(within(hold).getByRole('button', { name: 'Продолжить подход' }))

    expect(runCommandMock).toHaveBeenCalledWith({ action: 'resume', userId: 'alexey', exerciseSlug: 'barbell-floor-press' })
  })

  it('adjusts the repetition count and saves a partial set with the single finish button', async () => {
    const user = userEvent.setup()
    renderScreen()

    const counter = screen.getByRole('group', { name: 'Повторы' })
    const input = within(counter).getByRole('textbox', { name: 'Повторы' })
    const start = Number((input as HTMLInputElement).value)
    await user.click(within(counter).getByRole('button', { name: 'Увеличить: Повторы' }))
    await user.click(within(counter).getByRole('button', { name: 'Увеличить: Повторы' }))
    const session = useRuntimeStore.getState().session!
    const planned = session.sessionState!.targetMaxReps ?? session.sessionState!.targetValue
    expect(Number((input as HTMLInputElement).value)).toBe(Math.min(planned, start + 2))

    await user.click(within(counter).getByRole('button', { name: 'Уменьшить: Повторы' }))
    const fact = Number((input as HTMLInputElement).value)
    expect(fact).toBeLessThan(planned)

    await user.click(screen.getByRole('button', { name: 'Завершить подход' }))

    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(`/rest${currentSearch}`))
    // Hardware logic is unchanged: a machine exercise still confirms the set on the device.
    expect(runCommandMock).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ action: 'complete_set', exerciseSlug: 'barbell-floor-press', userId: 'alexey' }))
    const savedSet = vi.mocked(apiPost).mock.calls.find(([path]) => path === '/api/runtime/sets')
    if (fact > 0) {
      expect(savedSet?.[1]).toMatchObject({ exerciseSessionId: 7, actualValue: fact, machineMetrics: expect.objectContaining({ completionStatus: 'partial' }) })
    }
    const completed = useRuntimeStore.getState().session!.completedSets[session.currentExerciseId]
    expect(completed).toHaveLength(1)
    expect(completed[0]).toMatchObject({ actualValue: fact, completionStatus: 'partial' })
  })

  it('keeps finished sets when the rest of the exercise is skipped', async () => {
    const user = userEvent.setup()
    renderScreen()
    await user.click(screen.getByRole('button', { name: 'Завершить подход' }))
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(`/rest${currentSearch}`))
    act(() => useRuntimeStore.getState().beginNextStep())

    await user.click(screen.getByRole('button', { name: 'Пропустить упражнение' }))

    await waitFor(() => expect(navigateMock).toHaveBeenLastCalledWith(`/exercise-summary${currentSearch}`))
    const finalSave = vi.mocked(apiPost).mock.calls.filter(([path]) => path === '/api/runtime/exercises').at(-1)
    expect(finalSave?.[1]).toMatchObject({ status: 'partial', exerciseSessionId: 7 })
    const session = useRuntimeStore.getState().session!
    expect(session.completedSets[session.exercises[0].id]).toHaveLength(1)
  })

  it('shows save errors as an overlay over the centre and lets the user dismiss it', async () => {
    const user = userEvent.setup()
    vi.mocked(apiPost).mockRejectedValue(new Error('Сеть недоступна'))
    renderScreen()

    await user.click(screen.getByRole('button', { name: 'Завершить подход' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Не удалось сохранить подход')
    expect(alert).toHaveTextContent('Сеть недоступна')
    expect(navigateMock).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Завершить подход' })).toBeEnabled()

    await user.click(within(alert).getByRole('button', { name: 'Понятно' }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it.each([
    { setupType: 'bar_range', pointLabel: 'Нижняя точка', startPosition: 700, direction: 'up', endPosition: 710, expected: { lowerPointMm: 710, upperPointMm: 1100, fixedPositionMm: null } },
    { setupType: 'bar_range', pointLabel: 'Верхняя точка', startPosition: 1100, direction: 'down', endPosition: 1090, expected: { lowerPointMm: 700, upperPointMm: 1090, fixedPositionMm: null } },
    { setupType: 'fixed_position', pointLabel: 'Фиксированная высота', startPosition: 700, direction: 'up', endPosition: 710, expected: { lowerPointMm: null, upperPointMm: null, fixedPositionMm: 710 } },
  ] as const)('pauses and saves $pointLabel during the current set', async ({ setupType, pointLabel, startPosition, direction, endPosition, expected }) => {
    const user = userEvent.setup()
    const saved: HardwareCalibration = {
      id: 9, userId: 'alexey', exerciseSlug: 'barbell-floor-press', setupType,
      lowerPointMm: setupType === 'bar_range' ? 700 : null,
      upperPointMm: setupType === 'bar_range' ? 1100 : null,
      fixedPositionMm: setupType === 'fixed_position' ? 700 : null,
      zeroPositionMm: 700, movementRangeConfirmed: setupType === 'bar_range',
      calibrationRequired: true, isActive: true, capturedAt: new Date().toISOString(), expiresAt: null,
    }
    const initialSnapshot = {
      control: { mode: setupType === 'fixed_position' ? 'fixed_hold' : 'training' },
      motion: { barPositionMm: startPosition, leftPositionMm: startPosition, rightPositionMm: startPosition, repetitionCount: 0, moving: true, amplitudePercent: 0, syncDeltaMm: 0 },
      safety: { state: 'enabled' },
    } as HardwareSnapshot
    const save = vi.fn().mockImplementation(async (payload: Record<string, unknown>) => {
      const updated = { ...saved, ...payload }
      useHardwareStore.setState({ currentCalibration: updated })
      return updated
    })
    runCommandMock.mockImplementation(async ({ action }: { action: string }) => {
      if (action === 'pause') useHardwareStore.setState({ snapshot: { ...initialSnapshot, control: { mode: 'paused' }, motion: { ...initialSnapshot.motion, moving: false } } as HardwareSnapshot })
      if (action === 'jog_start') useHardwareStore.setState({ snapshot: { ...initialSnapshot, control: { mode: 'moving' }, motion: { ...initialSnapshot.motion, moving: true } } as HardwareSnapshot })
      if (action === 'jog_stop') useHardwareStore.setState({ snapshot: { ...initialSnapshot, control: { mode: 'paused' }, motion: { ...initialSnapshot.motion, moving: false, barPositionMm: endPosition } } as HardwareSnapshot })
      return {}
    })
    useHardwareStore.setState({ snapshot: initialSnapshot, currentCalibration: saved, saveCalibration: save })
    renderScreen()

    await user.click(screen.getByRole('button', { name: 'Настроить положение грифа' }))
    await waitFor(() => expect(runCommandMock).toHaveBeenCalledWith(expect.objectContaining({ action: 'pause' })))
    expect(screen.getByText(pointLabel)).toBeInTheDocument()
    const button = screen.getByRole('button', { name: direction === 'up' ? '↑ Вверх · удерживать' : '↓ Вниз · удерживать' })
    fireEvent.pointerDown(button, { pointerType: 'mouse', pointerId: 1, button: 0 })
    await waitFor(() => expect(runCommandMock).toHaveBeenCalledWith(expect.objectContaining({ action: 'jog_start', direction, mode: 'service' })))
    expect(screen.getByRole('button', { name: 'Сохранить положение' })).toBeDisabled()
    fireEvent.pointerUp(button, { pointerType: 'mouse', pointerId: 1 })
    await waitFor(() => expect(runCommandMock).toHaveBeenCalledWith(expect.objectContaining({ action: 'jog_stop' })))
    await user.click(screen.getByRole('button', { name: 'Сохранить положение' }))
    await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({ userId: 'alexey', exerciseSlug: 'barbell-floor-press', setupType, ...expected })))
    await user.click(screen.getByRole('button', { name: 'Продолжить подход' }))
    expect(runCommandMock).toHaveBeenCalledWith(expect.objectContaining({ action: 'resume', calibrationRequired: true, exerciseSlug: 'barbell-floor-press' }))
    expect(navigateMock).not.toHaveBeenCalled()
  })
})
