import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ExerciseSessionScreen } from '@/screens/exercise-session/exercise-session-screen'
import { getExerciseDetails } from '@/mocks/stage2-data'
import { apiGet, apiPost, apiPut } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import type { HardwareCalibration, HardwareSnapshot } from '@/features/hardware/model/types'
import { coachLifecycle } from '@/features/coach/lib/runtime-observation'
import { expandPerSidePlan } from '@/features/runtime/lib/per-side'
import { saveWorkoutToBackend } from '@/features/runtime/lib/runtime-persistence'
import { buildExerciseSession } from '@/mocks/stage3-data'
import { playExerciseEventSound, useExerciseEventSounds } from '@/features/runtime/lib/exercise-event-sounds'

vi.mock('@/features/runtime/lib/exercise-event-sounds', () => ({ useExerciseEventSounds: vi.fn(), playExerciseEventSound: vi.fn() }))

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
  apiPut: vi.fn().mockResolvedValue({}),
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
  it('redirects a back navigation during side-change rest without restarting or saving the left side again', async () => {
    const original = useRuntimeStore.getState().session!
    const exercise = { ...original.exercises[0], perSide: true, plan: expandPerSidePlan(original.exercises[0].plan.slice(0, 1), true) }
    const session = { ...original, exercises: [exercise], currentSetIndex: 0 }
    useRuntimeStore.setState({ session: { ...session, sessionState: buildExerciseSession(session) } })
    const view = renderScreen()
    fireEvent.click(screen.getByRole('button', { name: 'Увеличить: Повторы' }))
    fireEvent.click(screen.getByRole('button', { name: 'Завершить подход' }))
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(`/rest${currentSearch}`))
    const resting = useRuntimeStore.getState().session!
    expect(resting.view).toBe('rest')
    expect(resting.currentSetIndex).toBe(0)
    expect(resting.completedSets[exercise.id]).toHaveLength(1)
    const postCount = vi.mocked(apiPost).mock.calls.length
    const commandCount = runCommandMock.mock.calls.length
    view.unmount()
    navigateMock.mockClear()

    renderScreen()

    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(`/rest${currentSearch}`, { replace: true }))
    expect(useRuntimeStore.getState().session).toBe(resting)
    expect(screen.queryByRole('button', { name: 'Завершить подход' })).not.toBeInTheDocument()
    expect(apiPost).toHaveBeenCalledTimes(postCount)
    expect(runCommandMock).toHaveBeenCalledTimes(commandCount)
  })

  it.each([false, true])('persists the full plan on creation and finalization (perSide=%s)', async (perSide) => {
    const persistence = await vi.importActual<typeof import('@/features/runtime/lib/runtime-persistence')>('@/features/runtime/lib/runtime-persistence')
    vi.mocked(saveWorkoutToBackend).mockImplementationOnce(persistence.saveWorkoutToBackend)
    const post = vi.mocked(apiPost).getMockImplementation()!
    vi.mocked(apiPost).mockImplementation(async (path, payload) => path === '/api/runtime/workouts'
      ? { workoutSessionId: 42 } as never : post(path, payload))
    const original = useRuntimeStore.getState().session!
    const exercise = { ...original.exercises[0], perSide: perSide ? true : undefined,
      plan: expandPerSidePlan(original.exercises[0].plan.slice(0, 2), perSide) }
    const session = { ...original, exercises: [exercise], currentSetIndex: exercise.plan.length - 1 }
    useRuntimeStore.setState({ session: { ...session, sessionState: buildExerciseSession(session) } })
    renderScreen()
    fireEvent.click(screen.getByRole('button', { name: 'Увеличить: Повторы' }))
    fireEvent.click(screen.getByRole('button', { name: 'Завершить подход' }))
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(`/exercise-summary${currentSearch}`))
    const saves = vi.mocked(apiPost).mock.calls.filter(([path]) => path === '/api/runtime/exercises')
    expect(saves).toHaveLength(2)
    for (const [, payload] of saves) expect(payload).toMatchObject({
      perSide, targetSets: exercise.plan.length,
      plannedTotal: exercise.plan.reduce((sum, plan) => sum + (plan.targetSeconds ?? plan.targetMaxReps ?? plan.targetReps ?? 0), 0),
    })
    const calls = vi.mocked(apiPost).mock.calls
    const creation = calls.findIndex(([path]) => path === '/api/runtime/workouts')
    const firstResult = calls.findIndex(([path]) => path === '/api/runtime/sets')
    expect(creation).toBeGreaterThanOrEqual(0)
    expect(creation).toBeLessThan(firstResult)
    expect(calls[creation][1]).toMatchObject({
      status: 'in_progress', exercises: [], exerciseSessionIds: [],
      coachPlan: { origin: 'declared-client-plan', exercises: [{
        exerciseId: exercise.id, slug: exercise.slug, perSide,
        sets: exercise.plan.map((set, index) => expect.objectContaining({ ordinal: index + 1, side: set.side ?? null })),
      }] },
    })
  })

  it('saves explicit open intent for a failure set rather than certifying its displayed numeric hint', async () => {
    const original = useRuntimeStore.getState().session!
    const exercise = { ...original.exercises[0], plan: [{ ...original.exercises[0].plan[0], setType: 'failure' as const }] }
    const session = { ...original, exercises: [exercise], currentSetIndex: 0 }
    useRuntimeStore.setState({ session: { ...session, sessionState: buildExerciseSession(session) } })
    renderScreen()
    fireEvent.click(screen.getByRole('button', { name: 'Увеличить: Повторы' }))
    fireEvent.click(screen.getByRole('button', { name: 'Завершить подход' }))
    await waitFor(() => expect(navigateMock).toHaveBeenCalled())
    expect(apiPost).toHaveBeenCalledWith('/api/runtime/sets', expect.objectContaining({
      plannedValue: 0, targetMinReps: null, targetMaxReps: null,
      machineMetrics: expect.objectContaining({ targetType: 'open' }),
    }))
  })

  it.each([0, 1, 2, 3])('shows logical round and persists side before advancing physical step %i', async (index) => {
    const original = useRuntimeStore.getState().session!
    const exercise = { ...original.exercises[0], perSide: true, plan: expandPerSidePlan(original.exercises[0].plan.slice(0, 2), true) }
    const session = { ...original, exercises: [exercise], currentSetIndex: index }
    useRuntimeStore.setState({ session: { ...session, sessionState: buildExerciseSession(session) } })
    const side = index % 2 === 0 ? 'left' : 'right'
    const roundNumber = Math.floor(index / 2) + 1
    // Simulate an older backend summary without side metadata.
    const post = vi.mocked(apiPost).getMockImplementation()!
    vi.mocked(apiPost).mockImplementation(async (path, payload) => {
      const response = await post(path, payload)
      return path === '/api/runtime/exercises'
        ? { ...response as object, setResults: [{ setNumber: index + 1, plannedValue: 10, actualValue: 1, tempoLabel: 'хорошо' }] } as never
        : response
    })
    renderScreen()
    expect(screen.getByText(`Подход ${roundNumber} из 2`)).toBeInTheDocument()
    expect(screen.getByText(side === 'left' ? 'Левая сторона' : 'Правая сторона')).toBeInTheDocument()
    expect(screen.getAllByText(/на сторону/).length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: 'Увеличить: Повторы' }))
    fireEvent.click(screen.getByRole('button', { name: 'Завершить подход' }))
    await waitFor(() => expect(navigateMock).toHaveBeenCalled())
    expect(apiPost).toHaveBeenCalledWith('/api/runtime/sets', expect.objectContaining({
      setNumber: index + 1, machineMetrics: expect.objectContaining({ side, roundNumber }),
    }))
    const saved = useRuntimeStore.getState().session!
    expect(saved.completedSets[exercise.id][0]).toMatchObject({ setNumber: index + 1, side, roundNumber })
    expect(navigateMock).toHaveBeenCalledWith(`${index === 3 ? '/exercise-summary' : '/rest'}${currentSearch}`)
    if (index === 3) expect(saved.exerciseSummary!.setResults[0]).toMatchObject({ setNumber: 4, side: 'right', roundNumber: 2 })
  })

  it.each(['training', 'start_hold', 'paused'])('saves LOAD for next set only in %s and keeps current snapshot direction', async mode => {
    const saved: HardwareCalibration = {
      id: 90, userId: 'alexey', exerciseSlug: 'barbell-floor-press', setupType: 'bar_range',
      lowerPointMm: 300, upperPointMm: 900, fixedPositionMm: null, startPoint: 'lower',
      zeroPositionMm: 600, movementRangeConfirmed: true, calibrationRequired: true,
      isActive: true, capturedAt: new Date().toISOString(), expiresAt: null,
    }
    const save = vi.fn().mockImplementation(async payload => {
      const updated = { ...saved, ...payload }
      useHardwareStore.setState({ currentCalibration: updated })
      return updated
    })
    const snapshot = { control: { mode }, safety: { state: 'enabled' }, motion: {
      loadDirection: 'down', barPositionMm: 600, leftPositionMm: 600, rightPositionMm: 600,
      repetitionCount: 0, moving: true, amplitudePercent: 0, syncDeltaMm: 0,
    } } as HardwareSnapshot
    useHardwareStore.setState({ snapshot, currentCalibration: saved, saveCalibration: save })
    renderScreen()
    await userEvent.click(screen.getByRole('button', { name: 'Тяга вверх', exact: true }))
    await waitFor(() => expect(save).toHaveBeenCalledWith(expect.objectContaining({ loadDirection: 'up', startPoint: 'lower' })))
    expect(runCommandMock.mock.calls.filter(([command]) => command.action !== 'set_load')).toHaveLength(0)
    expect(screen.getByRole('status', { name: 'Текущее направление нагрузки' })).toHaveTextContent('Нагрузка вниз')
    expect(screen.getByText(/только со следующего подхода/)).toBeInTheDocument()
    expect(useHardwareStore.getState().snapshot).toBe(snapshot)
  })

  beforeEach(() => {
    vi.mocked(playExerciseEventSound).mockClear()
    vi.mocked(useExerciseEventSounds).mockClear()
    vi.stubEnv('VITE_COACH_ENABLED', 'false')
    coachLifecycle.clear()
    localStorage.clear()
    currentSearch = '?source=catalog&slug=barbell-floor-press'
    navigateMock.mockReset()
    runCommandMock.mockReset().mockResolvedValue({})
    vi.mocked(apiGet).mockReset().mockResolvedValue([])
    vi.mocked(apiPut).mockReset().mockResolvedValue({})
    vi.mocked(apiPost).mockReset()
    vi.mocked(apiPost).mockImplementation(async (path: string) => {
      if (path === '/api/runtime/exercises/reset') return { missingExerciseSessionIds: [] } as never
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

  it.each([false, true])('plays success once after a fully completed manual set (last=%s)', async lastSet => {
    if (lastSet) {
      const session = useRuntimeStore.getState().session!
      useRuntimeStore.setState({ session: { ...session, exercises: session.exercises.map(exercise => ({ ...exercise, plan: exercise.plan.slice(0, 1) })) } })
    }
    renderScreen()
    const target = useRuntimeStore.getState().session!.sessionState!.targetValue
    const input = screen.getByRole('textbox', { name: 'Повторы' })
    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: String(target) } })
    fireEvent.blur(input)
    fireEvent.click(screen.getByRole('button', { name: 'Завершить подход' }))
    await waitFor(() => expect(navigateMock).toHaveBeenCalled())
    expect(playExerciseEventSound).toHaveBeenCalledExactlyOnceWith('success')
    const payload = vi.mocked(apiPost).mock.calls.find(([path]) => path === '/api/runtime/sets')?.[1]
    expect(payload).toMatchObject({ subjectiveEffort: null, discomfortLevel: null })
    if (!lastSet) expect(useRuntimeStore.getState().session?.restState?.completedSet.backendSetId).toBe(1)
  })

  it('does not play success when saving a completed set fails', async () => {
    vi.mocked(apiPost).mockRejectedValue(new Error('Save failed'))
    renderScreen()
    const input = screen.getByRole('textbox', { name: 'Повторы' })
    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: String(useRuntimeStore.getState().session!.sessionState!.targetValue) } })
    fireEvent.blur(input)
    fireEvent.click(screen.getByRole('button', { name: 'Завершить подход' }))
    await screen.findByRole('alert')
    expect(playExerciseEventSound).not.toHaveBeenCalled()
  })

  it('plays success after automatic completion from hardware reps', async () => {
    const target = useRuntimeStore.getState().session!.sessionState!.targetValue
    const motion = { repetitionCount: 0, barPositionMm: 600, leftPositionMm: 600, rightPositionMm: 600, amplitudePercent: 0, syncDeltaMm: 0 } as HardwareSnapshot['motion']
    const snapshot = { motion, safety: { state: 'enabled' } } as HardwareSnapshot
    useHardwareStore.setState({ snapshot })
    renderScreen()
    act(() => useHardwareStore.setState({ snapshot: { ...snapshot, motion: { ...motion, repetitionCount: target } } }))
    await waitFor(() => expect(navigateMock).toHaveBeenCalled())
    expect(playExerciseEventSound).toHaveBeenCalledExactlyOnceWith('success')
  })

  it.each([false, true])('keeps fixed-hold reps manual despite telemetry and saves the entered value (full=%s)', async full => {
    const target = useRuntimeStore.getState().session!.sessionState!.targetValue
    const entered = full ? target : 3
    const motion = { repetitionCount: target, barPositionMm: 500, leftPositionMm: 500, rightPositionMm: 500, amplitudePercent: 0, syncDeltaMm: 0 } as HardwareSnapshot['motion']
    const snapshot = { motion, control: { mode: 'fixed_hold' }, safety: { state: 'enabled' } } as HardwareSnapshot
    useHardwareStore.setState({ snapshot })
    renderScreen()
    const input = screen.getByRole('textbox', { name: 'Повторы' })
    expect(input).toHaveValue('0')
    expect(navigateMock).not.toHaveBeenCalled()
    expect(screen.getByText(/Введите количество повторов вручную/)).toBeInTheDocument()
    fireEvent.focus(input)
    fireEvent.change(input, { target: { value: String(entered) } })
    fireEvent.blur(input)
    act(() => useHardwareStore.setState({ snapshot: { ...snapshot, motion: { ...motion, repetitionCount: target + 10, barPositionMm: 520 } } }))
    expect(input).toHaveValue(String(entered))
    expect(screen.getByRole('progressbar', { name: 'Прогресс подхода' })).toHaveAttribute('aria-valuenow', String(Math.round(entered / target * 100)))
    expect(navigateMock).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Завершить подход' }))
    await waitFor(() => expect(navigateMock).toHaveBeenCalled())
    expect(apiPost).toHaveBeenCalledWith('/api/runtime/sets', expect.objectContaining({ reps: entered, actualValue: entered }))
  })

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

  it('connects endpoint positions and runtime problems to event sounds independently of rep counting', () => {
    const motion = {
      barPositionMm: 600, lowerBoundMm: 300, upperBoundMm: 900,
      leftPositionMm: 600, rightPositionMm: 600, repetitionCount: 0,
      partialReps: 0, amplitudePercent: 0, syncDeltaMm: 0,
    } as HardwareSnapshot['motion']
    const snapshot = { motion, safety: { state: 'enabled' } } as HardwareSnapshot
    useHardwareStore.setState({ snapshot })
    renderScreen()
    expect(vi.mocked(useExerciseEventSounds).mock.lastCall?.[1]).toBe('neutral')
    act(() => useHardwareStore.setState({ snapshot: { ...snapshot, motion: { ...motion, barPositionMm: 900 } } }))
    expect(vi.mocked(useExerciseEventSounds).mock.lastCall?.[1]).toBe('upper')
    act(() => useHardwareStore.setState({ snapshot: { ...snapshot, motion: { ...motion, barPositionMm: 300 } } }))
    expect(vi.mocked(useExerciseEventSounds).mock.lastCall?.[1]).toBe('lower')
    act(() => useHardwareStore.setState({ errorMessage: 'Связь потеряна', snapshot: {
      ...snapshot, alerts: ['Перекос грифа'], control: { mode: 'fault', faultCode: 'sync_error' },
      motion: { ...motion, partialReps: 1 },
    } as HardwareSnapshot }))
    expect(vi.mocked(useExerciseEventSounds).mock.lastCall?.[2]).toEqual(expect.arrayContaining(['Связь потеряна', 'Перекос грифа', 'sync_error', 'fault']))
    expect(vi.mocked(useExerciseEventSounds).mock.lastCall?.[3]).toBe(1)
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

  it('tells the user when reps are counted as partial', () => {
    const motion = {
      barPositionMm: 450, lowerBoundMm: 356, upperBoundMm: 542,
      leftPositionMm: 450, rightPositionMm: 450,
      amplitudePercent: 60, repetitionCount: 1, partialReps: 0, syncDeltaMm: 0,
    } as HardwareSnapshot['motion']
    useHardwareStore.setState({ snapshot: { motion, control: { mode: 'training', label: '', message: '' }, safety: { state: 'enabled' } } as HardwareSnapshot })
    renderScreen()
    expect(screen.queryByRole('status', { name: 'Неполные повторы' })).not.toBeInTheDocument()

    act(() => useHardwareStore.setState({ snapshot: { motion: { ...motion, partialReps: 2 }, control: { mode: 'training', label: '', message: '' }, safety: { state: 'enabled' } } as HardwareSnapshot }))
    expect(screen.getByRole('status', { name: 'Неполные повторы' })).toHaveTextContent('Неполных повторов: 2 · не засчитаны')
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
    expect(playExerciseEventSound).not.toHaveBeenCalled()
  })

  it.each(['fixed_hold', 'training'])('ends the hardware set before saving a skipped exercise in %s', async mode => {
    const user = userEvent.setup()
    useHardwareStore.setState({ snapshot: {
      control: { mode }, safety: { state: 'enabled' },
      motion: { barPositionMm: 600, leftPositionMm: 600, rightPositionMm: 600, repetitionCount: 0, amplitudePercent: 0 },
    } as HardwareSnapshot })
    let finish!: () => void
    runCommandMock.mockImplementation(command => command.action === 'complete_set'
      ? new Promise<void>(resolve => { finish = resolve }) : Promise.resolve({}))
    renderScreen()
    await user.click(screen.getByRole('button', { name: 'Пропустить упражнение' }))
    await user.click(within(screen.getByRole('dialog', { name: 'Пропустить упражнение?' })).getByRole('button', { name: 'Пропустить', exact: true }))
    expect(runCommandMock).toHaveBeenCalledWith(expect.objectContaining({ action: 'complete_set', exerciseSlug: 'barbell-floor-press' }))
    expect(navigateMock).not.toHaveBeenCalled()
    expect(apiPost).not.toHaveBeenCalled()
    await act(async () => finish())
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(`/exercise-summary${currentSearch}`))
    expect(vi.mocked(apiPost).mock.calls.some(([path]) => path === '/api/runtime/sets')).toBe(false)
    expect(useRuntimeStore.getState().session!.exerciseOutcomes).toEqual(expect.objectContaining({
      [useRuntimeStore.getState().session!.currentExerciseId]: 'skipped',
    }))
  })

  it('does not leave a skipped exercise when hardware teardown fails', async () => {
    runCommandMock.mockRejectedValue(new Error('Не удалось завершить аппаратный подход'))
    renderScreen()
    await userEvent.click(screen.getByRole('button', { name: 'Пропустить упражнение' }))
    await userEvent.click(within(screen.getByRole('dialog', { name: 'Пропустить упражнение?' })).getByRole('button', { name: 'Пропустить', exact: true }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Не удалось завершить аппаратный подход'))
    expect(navigateMock).not.toHaveBeenCalled()
    expect(apiPost).not.toHaveBeenCalled()
  })

  it('keeps finished sets when the rest of the exercise is skipped', async () => {
    const user = userEvent.setup()
    renderScreen()
    await user.click(screen.getByRole('button', { name: 'Завершить подход' }))
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(`/rest${currentSearch}`))
    act(() => useRuntimeStore.getState().beginNextStep())

    await user.click(screen.getByRole('button', { name: 'Пропустить упражнение' }))
    const confirm = screen.getByRole('dialog', { name: 'Пропустить упражнение?' })
    expect(navigateMock).not.toHaveBeenCalledWith(`/exercise-summary${currentSearch}`)
    await user.click(within(confirm).getByRole('button', { name: 'Пропустить', exact: true }))
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

  it('shows the saved points when the trainer was not started and starts the set on request', async () => {
    const user = userEvent.setup()
    const saved: HardwareCalibration = {
      id: 9, userId: 'alexey', exerciseSlug: 'barbell-floor-press', setupType: 'bar_range',
      lowerPointMm: 550, upperPointMm: 945, fixedPositionMm: null,
      zeroPositionMm: 747, movementRangeConfirmed: true,
      calibrationRequired: true, isActive: true, capturedAt: new Date().toISOString(), expiresAt: null,
    }
    useHardwareStore.setState({
      currentCalibration: saved,
      snapshot: {
        control: { mode: 'idle' },
        motion: { barPositionMm: 19, lowerBoundMm: 0, upperBoundMm: 0, leftPositionMm: 19, rightPositionMm: 19, repetitionCount: 0, moving: false, amplitudePercent: 0, syncDeltaMm: 0 },
        safety: { state: 'enabled' },
      } as HardwareSnapshot,
    })
    renderScreen()

    const rail = screen.getByRole('region', { name: 'Положение грифа' })
    expect(within(rail).getByLabelText('Низ · 550 мм')).toBeInTheDocument()
    expect(within(rail).getByLabelText('Верх · 945 мм')).toBeInTheDocument()
    const idle = await screen.findByRole('status', { name: 'Тренажёр не запущен' }, { timeout: 3000 })
    expect(idle).toHaveTextContent('низ 55.0 см, верх 94.5 см')

    await user.click(within(idle).getByRole('button', { name: 'Запустить подход' }))

    expect(runCommandMock).toHaveBeenCalledWith(expect.objectContaining({
      action: 'start_motion', userId: 'alexey', exerciseSlug: 'barbell-floor-press',
      calibrationRequired: true, rangeConfirmed: true, mode: 'machine', targetSet: 1,
    }))
  })

  it('goes back to the previous exercise and does it again from the first set', async () => {
    const user = userEvent.setup()
    const session = useRuntimeStore.getState().session!
    const first = session.exercises[0]
    const second = { ...first, id: `${first.id}-again`, order: 2 }
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
    useRuntimeStore.getState().startExercise()
    renderScreen()

    await user.click(screen.getByRole('button', { name: 'Предыдущее упражнение' }))
    const confirm = screen.getByRole('dialog', { name: 'Вернуться к предыдущему упражнению?' })
    await user.click(within(confirm).getByRole('button', { name: 'Выполнить заново' }))

    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(`/exercise-setup${currentSearch}`))
    expect(apiPost).toHaveBeenCalledWith('/api/runtime/exercises/reset', { exercises: [expect.objectContaining({ exerciseSessionId: 5, status: 'in_progress', sets: [], resetSets: true })] })
    const restarted = useRuntimeStore.getState().session!
    expect(restarted.currentExerciseId).toBe(first.id)
    expect(restarted.currentSetIndex).toBe(0)
    expect(restarted.completedSets[first.id]).toBeUndefined()
    expect(restarted.completedExerciseIds).not.toContain(first.id)
  })

  it('does not auto-save repetitions while a previous-exercise reset is in flight', async () => {
    const original = useRuntimeStore.getState().session!
    const first = original.exercises[0]
    const second = { ...first, id: 'second', order: 2 }
    useRuntimeStore.setState({ session: { ...original, exercises: [first, second], currentExerciseId: second.id,
      completedExerciseIds: [first.id], backendExerciseSessionIds: { [first.id]: 5 } } })
    useRuntimeStore.getState().startExercise()
    const snapshot = { control: { mode: 'training' }, safety: { state: 'enabled' }, motion: {
      barPositionMm: 600, leftPositionMm: 600, rightPositionMm: 600, repetitionCount: 0, amplitudePercent: 0,
    } } as HardwareSnapshot
    useHardwareStore.setState({ snapshot })
    let reset!: (value: unknown) => void
    vi.mocked(apiPost).mockImplementation(() => new Promise(resolve => { reset = resolve }))
    renderScreen()
    await userEvent.click(screen.getByRole('button', { name: 'Предыдущее упражнение' }))
    // Hitting the rep target while confirming must not save the exercise the user is about to reset.
    act(() => useHardwareStore.setState({ snapshot: { ...snapshot, motion: { ...snapshot.motion, repetitionCount: 100 } } }))
    expect(apiPost).not.toHaveBeenCalled()
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Выполнить заново' }))
    await waitFor(() => expect(apiPost).toHaveBeenCalledTimes(1))
    act(() => useHardwareStore.setState({ snapshot: { ...snapshot, motion: { ...snapshot.motion, repetitionCount: 101 } } }))
    expect(apiPost).toHaveBeenCalledTimes(1)
    expect(runCommandMock.mock.calls.filter(([command]) => command.action === 'complete_set')).toHaveLength(1)
    await act(async () => reset({ missingExerciseSessionIds: [] }))
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(`/exercise-setup${currentSearch}`))
    expect(apiPost).toHaveBeenCalledTimes(1)
  })

  it('keeps both local results and the current exercise when atomic reset fails', async () => {
    const original = useRuntimeStore.getState().session!
    const first = original.exercises[0]
    const second = { ...first, id: 'second', order: 2 }
    const completedSets = { [first.id]: [{ setNumber: 1 } as never], [second.id]: [{ setNumber: 1 } as never] }
    useRuntimeStore.setState({ session: { ...original, exercises: [first, second], currentExerciseId: second.id,
      completedSets, backendExerciseSessionIds: { [first.id]: 5, [second.id]: 6 } } })
    useRuntimeStore.getState().startExercise()
    vi.mocked(apiPost).mockRejectedValue(new Error('Сброс не выполнен'))
    renderScreen()
    await userEvent.click(screen.getByRole('button', { name: 'Предыдущее упражнение' }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Выполнить заново' }))
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Сброс не выполнен'))
    expect(useRuntimeStore.getState().session!.completedSets).toEqual(completedSets)
    expect(useRuntimeStore.getState().session!.currentExerciseId).toBe(second.id)
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('goes back to the previous exercise when its backend record is already gone', async () => {
    const user = userEvent.setup()
    vi.mocked(apiPost).mockResolvedValue({ missingExerciseSessionIds: [5] })
    const session = useRuntimeStore.getState().session!
    const first = session.exercises[0]
    const second = { ...first, id: `${first.id}-again`, order: 2 }
    useRuntimeStore.setState({ session: {
      ...session,
      exercises: [first, second],
      currentExerciseId: second.id,
      backendWorkoutSessionId: 42,
      backendExerciseSessionIds: { [first.id]: 5 },
    } })
    useRuntimeStore.getState().startExercise()
    renderScreen()

    await user.click(screen.getByRole('button', { name: 'Предыдущее упражнение' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Выполнить заново' }))

    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith(`/exercise-setup${currentSearch}`))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    const restarted = useRuntimeStore.getState().session!
    expect(restarted.currentExerciseId).toBe(first.id)
    expect(restarted.backendExerciseSessionIds?.[first.id]).toBeUndefined()
  })

  it('has no previous exercise button on the first exercise', () => {
    renderScreen()
    expect(screen.queryByRole('button', { name: 'Предыдущее упражнение' })).not.toBeInTheDocument()
  })
})
