import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RestScreen } from '@/screens/rest/rest-screen'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import { expandPerSidePlan } from '@/features/runtime/lib/per-side'

const navigateMock = vi.fn()
const runCommandMock = vi.fn().mockResolvedValue({})
const currentSearch = '?source=catalog&slug=barbell-floor-press'

vi.mock('react-router-dom', async () => ({
  ...await vi.importActual<typeof import('react-router-dom')>('react-router-dom'),
  useNavigate: () => navigateMock,
  useLocation: () => ({ search: currentSearch }),
  useSearchParams: () => [new URLSearchParams(currentSearch)],
}))

function renderScreen() {
  return render(
    <MemoryRouter>
      <RestScreen />
    </MemoryRouter>,
  )
}

describe('RestScreen', () => {
  it('never auto-starts a side change, even unpaused, and confirms the right side exactly once', async () => {
    const original = useRuntimeStore.getState().session!
    const exercise = { ...original.exercises[0], perSide: true, plan: expandPerSidePlan(original.exercises[0].plan.slice(0, 2), true) }
    useRuntimeStore.setState({ session: { ...original, exercises: [exercise], completedSets: {}, restState: undefined, view: 'exercise-session' } })
    useRuntimeStore.getState().finishCurrentSet()
    expect(useRuntimeStore.getState().session!.restState).toMatchObject({ title: 'Смените сторону', totalSeconds: 0, timerPaused: true })
    vi.useFakeTimers()
    try {
      renderScreen()
      expect(screen.getByRole('heading', { name: 'Смените сторону' })).toBeInTheDocument()
      expect(screen.getByText('Подход 1 из 2 · Правая сторона')).toBeInTheDocument()
      expect(screen.getByRole('note')).toHaveTextContent('Перейдите на правую сторону')
      expect(screen.queryByRole('button', { name: 'Пропустить' })).not.toBeInTheDocument()
      await act(async () => { vi.advanceTimersByTime(120_000) })
      act(() => useRuntimeStore.getState().pauseRestTimer())
      await act(async () => { vi.advanceTimersByTime(120_000) })
      expect(runCommandMock).not.toHaveBeenCalled()
      expect(navigateMock).not.toHaveBeenCalled()
      expect(useRuntimeStore.getState().session!.currentSetIndex).toBe(0)
      const button = screen.getByRole('button', { name: 'Начать правую сторону' })
      await act(async () => { fireEvent.click(button); fireEvent.click(button) })
      expect(runCommandMock).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ action: 'start_motion', targetSet: 2 }))
      expect(navigateMock).toHaveBeenCalledTimes(1)
      expect(useRuntimeStore.getState().session!.sessionState).toMatchObject({ side: 'right', roundNumber: 1, setNumber: 2, totalSets: 4 })
    } finally {
      vi.useRealTimers()
    }
  })

  beforeEach(() => {
    localStorage.clear()
    navigateMock.mockReset()
    runCommandMock.mockReset().mockResolvedValue({})
    useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
    useHardwareStore.setState({
      snapshot: null, errorMessage: null, runCommand: runCommandMock,
      loadCurrentCalibration: vi.fn().mockResolvedValue({ setupType: 'bar_range', lowerPointMm: 560, upperPointMm: 760, fixedPositionMm: null }),
    })
    useRuntimeStore.setState({ session: null, sessionSignature: null })
    useRuntimeStore.getState().initializeSession({ source: 'catalog', slug: 'barbell-floor-press' })
    useRuntimeStore.getState().startExercise()
    useRuntimeStore.getState().finishCurrentSet()
    useRuntimeStore.getState().pauseRestTimer()
  })

  it('shows a large timer, the next task and exactly three actions', () => {
    renderScreen()

    const rest = useRuntimeStore.getState().session!.restState!
    expect(screen.getByRole('timer')).toHaveAccessibleName(`Осталось ${rest.remainingSeconds} секунд`)
    expect(screen.getByRole('region', { name: 'Таймер отдыха' })).toBeInTheDocument()
    expect(screen.getByText('Дальше')).toBeInTheDocument()
    const actions = screen.getByRole('group', { name: 'Действия во время отдыха' })
    expect(actions.querySelectorAll('button')).toHaveLength(3)
    expect(screen.getByRole('button', { name: '+30 сек' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Пропустить' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Завершить тренировку' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Пауза|Уменьшить отдых/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Основная навигация' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Аварийная остановка', exact: true })).toHaveLength(1)
  })

  it('adds 30 seconds and skips rest, starting the next set on the machine as before', async () => {
    const user = userEvent.setup()
    renderScreen()
    const before = useRuntimeStore.getState().session!.restState!.remainingSeconds

    await user.click(screen.getByRole('button', { name: '+30 сек' }))
    expect(useRuntimeStore.getState().session!.restState!.remainingSeconds).toBe(before + 30)

    await user.click(screen.getByRole('button', { name: 'Пропустить' }))
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(`/exercise-session${currentSearch}`))
    expect(useRuntimeStore.getState().session!.view).toBe('exercise-session')
    expect(runCommandMock).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ action: 'start_motion', exerciseSlug: 'barbell-floor-press', targetSet: 2, loadDirection: 'down' }))
  })

  it('asks for confirmation before finishing the workout', async () => {
    const user = userEvent.setup()
    renderScreen()

    await user.click(screen.getByRole('button', { name: 'Завершить тренировку' }))
    const dialog = screen.getByRole('dialog', { name: 'Завершить тренировку сейчас?' })
    expect(useRuntimeStore.getState().session!.view).toBe('rest')

    await user.click(screen.getByRole('button', { name: 'Продолжить отдых' }))
    await waitFor(() => expect(dialog).not.toBeInTheDocument())
    expect(navigateMock).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Завершить тренировку' }))
    await user.click(screen.getByRole('dialog').querySelector('button[data-variant="primary"]') as HTMLElement)
    expect(useRuntimeStore.getState().session!.view).toBe('workout-summary')
    expect(useRuntimeStore.getState().session!.workoutSummary.outcome).toBe('partial')
    expect(navigateMock).toHaveBeenCalledWith(`/workout-summary${currentSearch}`)
  })

  it('starts the opposite-direction exercise after rest expires', async () => {
    useHardwareStore.setState({ loadCurrentCalibration: vi.fn().mockResolvedValue({ setupType: 'bar_range', loadDirection: 'up' }) })
    const session = useRuntimeStore.getState().session!
    useRuntimeStore.setState({ session: { ...session, restState: { ...session.restState!, remainingSeconds: 0, timerPaused: false } } })
    renderScreen()
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(`/exercise-session${currentSearch}`))
    expect(runCommandMock).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ action: 'start_motion', loadDirection: 'up' }))
  })

  it('pauses a failed automatic start without looping and rearms after more rest', async () => {
    runCommandMock.mockRejectedValueOnce(new Error('Гриф ещё разгружается'))
    const session = useRuntimeStore.getState().session!
    useRuntimeStore.setState({ session: { ...session, restState: { ...session.restState!, remainingSeconds: 0, timerPaused: false } } })
    renderScreen()
    await waitFor(() => expect(useRuntimeStore.getState().session!.restState!.timerPaused).toBe(true))
    expect(useHardwareStore.getState().errorMessage).toBe('Гриф ещё разгружается')
    expect(useRuntimeStore.getState().session!.view).toBe('rest')
    expect(navigateMock).not.toHaveBeenCalled()
    expect(runCommandMock).toHaveBeenCalledTimes(1)

    act(() => {
      useRuntimeStore.getState().adjustRestSeconds(30)
      useRuntimeStore.getState().pauseRestTimer()
    })
    act(() => {
      useRuntimeStore.getState().adjustRestSeconds(-30)
    })
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(`/exercise-session${currentSearch}`))
    expect(runCommandMock).toHaveBeenCalledTimes(2)
  })

  it('allows a manual retry after an automatic direction-start rejection', async () => {
    runCommandMock.mockRejectedValueOnce(new Error('Направление нагрузки меняется только после завершения подхода'))
    const session = useRuntimeStore.getState().session!
    useRuntimeStore.setState({ session: { ...session, restState: { ...session.restState!, remainingSeconds: 0, timerPaused: false } } })
    renderScreen()
    await waitFor(() => expect(useRuntimeStore.getState().session!.restState!.timerPaused).toBe(true))
    await userEvent.setup().click(screen.getByRole('button', { name: 'Пропустить' }))
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(`/exercise-session${currentSearch}`))
    expect(runCommandMock).toHaveBeenCalledTimes(2)
  })

  it('reuses a fixed position for the next set', async () => {
    useHardwareStore.setState({ loadCurrentCalibration: vi.fn().mockResolvedValue({ setupType: 'fixed_position', fixedPositionMm: 1480 }) })
    renderScreen()
    await userEvent.setup().click(screen.getByRole('button', { name: 'Пропустить' }))
    await waitFor(() => expect(runCommandMock).toHaveBeenCalledWith(expect.objectContaining({ action: 'start_fixed_position', positionMm: 1480, targetSet: 2 })))
  })

  it('renders a unified loading state instead of a blank screen without a session', () => {
    useRuntimeStore.setState({ session: null, sessionSignature: null })
    act(() => {
      useRuntimeStore.setState({ session: null })
    })
    renderScreen()
    expect(screen.getByText('Загружаем отдых…').closest('[role="status"]')).not.toBeNull()
  })
})
