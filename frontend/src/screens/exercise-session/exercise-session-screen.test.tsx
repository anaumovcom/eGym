import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ExerciseSessionScreen } from '@/screens/exercise-session/exercise-session-screen'
import { apiPost } from '@/shared/api/client'
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

vi.mock('@/shared/api/client', async () => ({
  ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'),
  apiPost: vi.fn(),
}))

vi.mock('@/features/runtime/lib/runtime-persistence', async () => ({
  ...await vi.importActual<typeof import('@/features/runtime/lib/runtime-persistence')>('@/features/runtime/lib/runtime-persistence'),
  saveWorkoutToBackend: vi.fn().mockResolvedValue({ workoutSessionId: 42 }),
}))

function renderScreen() {
  return render(
    <MemoryRouter>
      <ExerciseSessionScreen />
    </MemoryRouter>,
  )
}

describe('ExerciseSessionScreen', () => {
  beforeEach(() => {
    localStorage.clear()
    navigateMock.mockReset()
    runCommandMock.mockClear()
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
})
