import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ExerciseSessionScreen } from '@/screens/exercise-session/exercise-session-screen'
import { apiPost } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import type { HardwareCalibration, HardwareSnapshot } from '@/features/hardware/model/types'

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
