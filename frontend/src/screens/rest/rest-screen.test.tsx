import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RestScreen } from '@/screens/rest/rest-screen'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { useRuntimeStore } from '@/stores/runtime-store'

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
  beforeEach(() => {
    localStorage.clear()
    navigateMock.mockReset()
    runCommandMock.mockClear()
    useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
    useHardwareStore.setState({ snapshot: null, errorMessage: null, runCommand: runCommandMock })
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
    expect(runCommandMock).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ action: 'start_motion', exerciseSlug: 'barbell-floor-press', targetSet: 2 }))
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

  it('renders a unified loading state instead of a blank screen without a session', () => {
    useRuntimeStore.setState({ session: null, sessionSignature: null })
    act(() => {
      useRuntimeStore.setState({ session: null })
    })
    renderScreen()
    expect(screen.getByText('Загружаем отдых…').closest('[role="status"]')).not.toBeNull()
  })
})
