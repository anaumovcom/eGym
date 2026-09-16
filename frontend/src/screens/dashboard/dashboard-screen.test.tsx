import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { dashboardStoryScenarios } from '@/mocks/data'
import type { DashboardBuilderWorkout, DashboardData } from '@/entities/dashboard/model/types'
import { DashboardScreen, DashboardView } from '@/screens/dashboard/dashboard-screen'
import { apiGet } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import { useRuntimeStore } from '@/stores/runtime-store'

const navigateMock = vi.fn()
const fetchMock = vi.fn().mockRejectedValue(new Error('Real network is forbidden in dashboard tests'))
const originalAppState = useAppStore.getState()
const originalRuntimeState = useRuntimeStore.getState()
const originalHardwareState = useHardwareStore.getState()
let queryClient: QueryClient

vi.mock('@/shared/api/client', async () => ({
  ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'),
  apiGet: vi.fn(),
}))

vi.mock('@/shared/ui/stage2/screen-components', async () => ({
  ...await vi.importActual<typeof import('@/shared/ui/stage2/screen-components')>('@/shared/ui/stage2/screen-components'),
  CompactBodyMapGrid: () => <div data-testid="recovery-map" />,
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')

  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

function renderDashboard(data?: DashboardData) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        {data ? <DashboardView
          data={data}
          userName="Алексей"
          emergencyStopActive={false}
          onStop={vi.fn()}
          onEmergencyStopChange={vi.fn()}
        /> : <DashboardScreen />}
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function makeWorkout(index: number): DashboardBuilderWorkout {
  return {
    id: `workout ${index}`,
    title: `Тренировка ${index}`,
    duration: '30 минут',
    exercises: [{ slug: 'machine-pulldown', name: 'Тяга сверху' }],
  }
}

function captureStores() {
  const app = useAppStore.getState()
  const runtime = useRuntimeStore.getState()
  const session = structuredClone(runtime.session)
  const persisted = { ...localStorage }
  return () => {
    expect(useAppStore.getState()).toBe(app)
    expect(useRuntimeStore.getState()).toBe(runtime)
    expect(useRuntimeStore.getState().session).toEqual(session)
    expect({ ...localStorage }).toEqual(persisted)
  }
}

async function selectWorkout(user: ReturnType<typeof userEvent.setup>, title: string) {
  const expectStoresUnchanged = captureStores()
  await user.click(screen.getByRole('button', { name: `Выбрать тренировку «${title}»`, exact: true }))
  const dialog = screen.getByRole('dialog', { name: title, exact: true })
  expect(dialog).toBeVisible()
  expect(navigateMock).not.toHaveBeenCalled()
  expectStoresUnchanged()
  return within(dialog)
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.stubGlobal('fetch', fetchMock)
  localStorage.clear()
  useAppStore.setState({ ...originalAppState, selectedUserId: 'alexey', selectedProgramId: 'previous-program', emergencyStopActive: false }, true)
  useRuntimeStore.setState({ ...originalRuntimeState, session: null, sessionSignature: null }, true)
  useHardwareStore.setState({ ...originalHardwareState, snapshot: null }, true)
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })
  vi.mocked(apiGet).mockReset().mockRejectedValue(new Error('Unexpected API request in dashboard test'))
})

afterEach(() => {
  cleanup()
  queryClient.clear()
  useAppStore.setState(originalAppState, true)
  useRuntimeStore.setState(originalRuntimeState, true)
  useHardwareStore.setState(originalHardwareState, true)
  localStorage.clear()
  vi.unstubAllGlobals()
  expect(fetchMock).not.toHaveBeenCalled()
})

describe('DashboardView', () => {
  afterEach(() => {
    expect(apiGet).not.toHaveBeenCalled()
  })

  it('renders no-workout state', () => {
    renderDashboard(dashboardStoryScenarios['no-workout'])

    expect(screen.getByText('Тренировки не найдены. Создайте первую и добавьте упражнения.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Новая тренировка/ })).toBeEnabled()
  })

  it('renders blocking alert for drive-error state', () => {
    renderDashboard(dashboardStoryScenarios['drive-error'])

    expect(screen.getByText('Ошибка правого привода')).toBeInTheDocument()
  })

  it.each([0, 3, 4, 5])('renders all %i workout cards and offers creation only below four', async (count) => {
    const user = userEvent.setup()
    const workouts = Array.from({ length: count }, (_, index) => makeWorkout(index + 1))
    const expectStoresUnchanged = captureStores()
    renderDashboard({ ...dashboardStoryScenarios.default, workouts })

    expect(screen.getByRole('heading', { name: 'Какую тренировку выберете?' })).toBeVisible()
    expect(screen.queryAllByRole('button', { name: /^Выбрать тренировку «/ })).toHaveLength(count)
    for (const workout of workouts) {
      expect(screen.getByRole('button', { name: `Выбрать тренировку «${workout.title}»` })).toBeVisible()
    }
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(navigateMock).not.toHaveBeenCalled()
    expectStoresUnchanged()

    const create = screen.queryByRole('button', { name: /Новая тренировка/ })
    if (count < 4) {
      expect(create).toBeVisible()
      await user.click(create!)
      expect(navigateMock).toHaveBeenCalledTimes(1)
      expect(navigateMock).toHaveBeenCalledWith('/builder?create=new')
      expectStoresUnchanged()
    } else {
      expect(create).not.toBeInTheDocument()
    }
  })

  it('always shows the recovery map without a summary, dialog, statistics or daily reset controls', () => {
    const data = { ...dashboardStoryScenarios.default, workouts: [makeWorkout(1)] }
    const expectStoresUnchanged = captureStores()
    renderDashboard(data)

    const main = within(screen.getByRole('main'))
    const recovery = main.getByRole('region', { name: 'Восстановление мышц' })
    expect(recovery).toBeVisible()
    expect(within(recovery).getByTestId('recovery-map')).toBeVisible()
    expect(within(recovery).getByRole('heading', { name: 'Усталость мышц' })).toBeVisible()
    expect(main.queryByRole('button', { name: 'Карта мышц', exact: true })).not.toBeInTheDocument()
    expect(main.queryByRole('list', { name: 'Краткая сводка усталости' })).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(navigateMock).not.toHaveBeenCalled()
    expectStoresUnchanged()
    expect(main.queryByText(/статистика|сброс|03:00/i)).not.toBeInTheDocument()
    expect(main.queryByRole('button', { name: /сброс|обнулить|начать заново/i })).not.toBeInTheDocument()
    expect(main.queryByText(data.greeting)).not.toBeInTheDocument()
    expect(main.queryByText(data.recommendationTitle)).not.toBeInTheDocument()
    expect(main.queryByText(data.recommendationText)).not.toBeInTheDocument()
    for (const metric of data.progress) expect(main.queryByText(metric.label)).not.toBeInTheDocument()
  })

  it('does not preselect a workout or open a dialog for the stored selected program', () => {
    useRuntimeStore.getState().initializeSession({ source: 'builder', programId: 'back-biceps' })
    useAppStore.getState().setSelectedProgramId('back-biceps')
    const session = useRuntimeStore.getState().session!
    const expectStoresUnchanged = captureStores()
    renderDashboard({
      ...dashboardStoryScenarios.default,
      workouts: [{
        ...makeWorkout(1), id: 'back-biceps', todayStatus: 'in_progress',
        exercises: session.exercises.map(({ slug, name }) => ({ slug, name })),
      }],
    })

    expect(screen.getByRole('button', { name: 'Выбрать тренировку «Тренировка 1»' })).toBeVisible()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^(Начать|Продолжить)$/ })).not.toBeInTheDocument()
    expect(navigateMock).not.toHaveBeenCalled()
    expectStoresUnchanged()
  })

  it.each(['idle', 'in_progress'] as const)('disables confirmation for an empty %s workout but keeps back and edit working', async (todayStatus) => {
    const user = userEvent.setup()
    const workout = { ...makeWorkout(1), exercises: [], todayStatus }
    const expectStoresUnchanged = captureStores()
    renderDashboard({ ...dashboardStoryScenarios.default, workouts: [workout] })

    const trigger = screen.getByRole('button', { name: `Выбрать тренировку «${workout.title}»` })
    expect(trigger).toBeEnabled()
    expect(within(trigger).getByText('Пока нет упражнений')).toBeVisible()
    let dialog = await selectWorkout(user, workout.title)
    const confirm = dialog.getByRole('button', { name: 'Начать', exact: true })
    expect(confirm).toBeDisabled()
    expect(dialog.getByText('Добавьте упражнения через «Изменить», прежде чем начинать.')).toBeVisible()
    expect(dialog.queryAllByRole('listitem')).toHaveLength(0)
    await user.click(confirm)
    expect(navigateMock).not.toHaveBeenCalled()
    expectStoresUnchanged()

    await user.click(dialog.getByRole('button', { name: 'Назад', exact: true }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await waitFor(() => expect(trigger).toHaveFocus())
    expect(navigateMock).not.toHaveBeenCalled()
    expectStoresUnchanged()

    dialog = await selectWorkout(user, workout.title)
    expect(dialog.getByRole('button', { name: 'Изменить', exact: true })).toBeEnabled()
    await user.click(dialog.getByRole('button', { name: 'Изменить', exact: true }))
    expect(navigateMock).toHaveBeenCalledTimes(1)
    expect(navigateMock).toHaveBeenCalledWith('/builder?programId=workout%201')
    expectStoresUnchanged()
  })

  it.each(['Назад', 'Escape'])('cancels with %s, restores the exact card focus and preserves the summary session and stores', async (cancel) => {
    const user = userEvent.setup()
    useRuntimeStore.getState().initializeSession({ source: 'builder', programId: 'back-biceps' })
    useRuntimeStore.getState().finishExerciseWithResults([], 'completed')
    const session = useRuntimeStore.getState().session!
    expect(session.view).toBe('exercise-summary')
    const workout = {
      ...makeWorkout(2), id: 'back-biceps',
      exercises: session.exercises.map(({ slug, name }) => ({ slug, name })),
    }
    const expectStoresUnchanged = captureStores()
    renderDashboard({ ...dashboardStoryScenarios.default, workouts: [makeWorkout(1), workout] })
    const trigger = screen.getByRole('button', { name: `Выбрать тренировку «${workout.title}»` })
    const dialog = await selectWorkout(user, workout.title)
    expect(dialog.getByRole('button', { name: 'Продолжить', exact: true })).toBeEnabled()

    if (cancel === 'Escape') await user.keyboard('{Escape}')
    else await user.click(dialog.getByRole('button', { name: 'Назад', exact: true }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await waitFor(() => expect(trigger).toHaveFocus())
    expect(navigateMock).not.toHaveBeenCalled()
    expectStoresUnchanged()
    const reopened = await selectWorkout(user, workout.title)
    expect(reopened.getByRole('button', { name: 'Продолжить', exact: true })).toBeEnabled()
    expectStoresUnchanged()
  })

  it('resumes builder workout from the next exercise after an exercise summary', async () => {
    const user = userEvent.setup()
    const workoutId = 'back-biceps'
    const data = {
      ...dashboardStoryScenarios.default,
      workouts: [
        {
          id: workoutId,
          title: 'Спина + бицепс',
          duration: '45 минут',
          todayStatus: 'in_progress' as const,
          todayProgressPercent: 20,
          todayCompletedExercises: 1,
          todayTotalExercises: 5,
          exercises: [
            { slug: 'machine-pulldown', name: 'Тяга сверху', status: 'completed' as const, completedSets: 4, targetSets: 4, progressPercent: 100 },
            { slug: 'machine-seated-cable-row', name: 'Тяга к поясу', status: 'in_progress' as const, completedSets: 0, targetSets: 4, progressPercent: 0 },
          ],
        },
      ],
    }

    useRuntimeStore.getState().initializeSession({ source: 'today' })

    const initialSession = useRuntimeStore.getState().session
    if (!initialSession) {
      throw new Error('Expected runtime session to be initialized')
    }

    useRuntimeStore.setState({
      session: {
        ...initialSession,
        source: 'builder',
        programId: workoutId,
        startedAt: new Date().toISOString(),
        exercises: initialSession.exercises.slice(0, 2).map((exercise, index) => {
          if (index === 0) {
            return {
              ...exercise,
              slug: 'machine-pulldown',
              name: 'Тяга сверху',
            }
          }

          if (index === 1) {
            return {
              ...exercise,
              slug: 'machine-seated-cable-row',
              name: 'Тяга к поясу',
            }
          }

          return exercise
        }),
      },
    })

    const session = useRuntimeStore.getState().session
    if (!session) {
      throw new Error('Expected runtime session to be initialized')
    }

    const firstExercise = session.exercises[0]
    const firstExerciseResults = firstExercise.plan.map((plan, index) => ({
      setNumber: index + 1,
      plannedValue: plan.targetMaxReps ?? plan.targetReps ?? plan.targetSeconds ?? 0,
      actualValue: plan.targetMaxReps ?? plan.targetReps ?? plan.targetSeconds ?? 0,
      completionStatus: 'completed' as const,
      setType: plan.setType,
      targetMinReps: plan.targetMinReps,
      targetMaxReps: plan.targetMaxReps ?? plan.targetReps,
      reps: plan.targetSeconds ? null : (plan.targetMaxReps ?? plan.targetReps ?? 0),
      weightKg: plan.recommendedWeightKg ?? 0,
      rir: null,
      subjectiveEffort: 7,
      discomfortLevel: 0,
      pain: false,
      techniqueBreakdown: false,
      comment: null,
      volumeKg: 0,
      amplitudePercent: undefined,
      tempoLabel: 'хорошо',
      syncLabel: undefined,
    }))

    useRuntimeStore.getState().finishExerciseWithResults(firstExerciseResults, 'completed')

    renderDashboard(data)

    const summarySession = useRuntimeStore.getState().session!
    expect(summarySession.view).toBe('exercise-summary')
    const dialog = await selectWorkout(user, 'Спина + бицепс')
    expect(useRuntimeStore.getState().session).toBe(summarySession)
    await user.click(dialog.getByRole('button', { name: 'Продолжить', exact: true }))

    expect(useRuntimeStore.getState().session?.view).toBe('exercise-setup')
    expect(useRuntimeStore.getState().session?.currentExerciseId).toBe(session.exercises[1]?.id)
    expect(useRuntimeStore.getState().session?.runId).toBe(summarySession.runId)
    expect(useRuntimeStore.getState().session?.exercises[0]).toEqual(summarySession.exercises[0])
    expect(useAppStore.getState().selectedProgramId).toBe(workoutId)
    expect(navigateMock).toHaveBeenCalledTimes(1)
    expect(navigateMock).toHaveBeenCalledWith(`/exercise-setup?source=builder&programId=${encodeURIComponent(workoutId)}`)
  })

  it('does not resume a stale builder runtime session when dashboard workout has changed', async () => {
    const user = userEvent.setup()
    const workoutId = 'back-biceps'
    const data = {
      ...dashboardStoryScenarios.default,
      workouts: [
        {
          id: workoutId,
          title: 'Спина + бицепс',
          duration: '45 минут',
          todayStatus: 'in_progress' as const,
          todayProgressPercent: 20,
          todayCompletedExercises: 1,
          todayTotalExercises: 2,
          exercises: [
            { slug: 'new-exercise', name: 'Новое упражнение', status: 'idle' as const, completedSets: 0, targetSets: 4, progressPercent: 0 },
            { slug: 'machine-seated-cable-row', name: 'Тяга к поясу', status: 'idle' as const, completedSets: 0, targetSets: 4, progressPercent: 0 },
          ],
        },
      ],
    }

    useRuntimeStore.getState().initializeSession({ source: 'today' })

    const initialSession = useRuntimeStore.getState().session
    if (!initialSession) {
      throw new Error('Expected runtime session to be initialized')
    }

    useRuntimeStore.setState({
      session: {
        ...initialSession,
        source: 'builder',
        programId: workoutId,
        startedAt: new Date().toISOString(),
        view: 'exercise-session',
        exercises: initialSession.exercises.map((exercise, index) =>
          index === 0
            ? {
                ...exercise,
                slug: 'old-exercise',
                name: 'Старое упражнение',
              }
            : exercise
        ),
      },
    })

    renderDashboard(data)

    const staleSession = useRuntimeStore.getState().session
    const dialog = await selectWorkout(user, 'Спина + бицепс')
    expect(dialog.getByText(/Будет начата новая сессия/)).toBeVisible()
    await user.click(dialog.getByRole('button', { name: 'Начать', exact: true }))

    expect(useRuntimeStore.getState().session).toBe(staleSession)
    expect(useAppStore.getState().selectedProgramId).toBe(workoutId)
    expect(navigateMock).toHaveBeenCalledTimes(1)
    expect(navigateMock).toHaveBeenCalledWith(`/exercise-setup?source=builder&programId=${encodeURIComponent(workoutId)}`)
  })

  it('launches a nonempty workout only after explicit confirmation, without a photo URL or CTA', async () => {
    const user = userEvent.setup()
    renderDashboard({
      ...dashboardStoryScenarios.default,
      workouts: [{ ...makeWorkout(1), id: 'new workout', title: 'Новая тренировка' }],
    })

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /фото/i })).not.toBeInTheDocument()
    const dialog = await selectWorkout(user, 'Новая тренировка')
    expect(dialog.getAllByRole('listitem')).toHaveLength(1)
    expect(dialog.getByText('Тяга сверху')).toBeVisible()
    expect(dialog.getByRole('button', { name: 'Начать', exact: true })).toBeEnabled()
    await user.dblClick(dialog.getByRole('button', { name: 'Начать', exact: true }))

    expect(navigateMock).toHaveBeenCalledTimes(1)
    expect(navigateMock).toHaveBeenCalledWith('/exercise-setup?source=builder&programId=new%20workout')
    expect(useAppStore.getState().selectedProgramId).toBe('new workout')
    expect(useRuntimeStore.getState().session).toBeNull()
    expect(screen.queryByRole('button', { name: /фото/i })).not.toBeInTheDocument()
  })

  it.each([
    ['exercise-session', 'manual', '/exercise-session'],
    ['rest', 'manual', '/rest'],
    ['exercise-setup', 'manual', '/exercise-setup'],
    ['workout-summary', 'manual', '/workout-summary'],
    ['photo-progress', 'pre-workout', '/exercise-setup'],
    ['photo-progress', 'post-workout', '/workout-summary'],
  ] as const)('resumes %s (%s) without routing to photos', async (view, mode, path) => {
    const user = userEvent.setup()
    useRuntimeStore.getState().initializeSession({ source: 'builder', programId: 'back-biceps' })
    const initialSession = useRuntimeStore.getState().session!
    const session = {
      ...initialSession,
      view,
      backendWorkoutSessionId: 42,
      photoProgress: { ...initialSession.photoProgress, mode, autoPrompt: mode !== 'manual' },
    }
    useRuntimeStore.setState({ session })
    renderDashboard({
      ...dashboardStoryScenarios.default,
      workouts: [{
        id: 'back-biceps', title: 'Спина + бицепс', duration: '45 минут', todayStatus: 'in_progress',
        exercises: session.exercises.map((exercise) => ({ slug: exercise.slug, name: exercise.name })),
      }],
    })

    const dialog = await selectWorkout(user, 'Спина + бицепс')
    await user.click(dialog.getByRole('button', { name: 'Продолжить', exact: true }))

    expect(navigateMock).toHaveBeenCalledTimes(1)
    expect(navigateMock).toHaveBeenCalledWith(`${path}?source=builder&programId=back-biceps`)
    expect(useAppStore.getState().selectedProgramId).toBe('back-biceps')
    expect(useRuntimeStore.getState().session).toBe(session)
  })
})

describe('DashboardScreen', () => {
  it('shows loading without workout selection or store mutations while the request is pending', () => {
    vi.mocked(apiGet).mockReturnValue(new Promise<DashboardData>(() => {}))
    const expectStoresUnchanged = captureStores()
    renderDashboard()

    expect(screen.getByRole('heading', { name: 'Загрузка тренировок…' })).toBeVisible()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Выбрать тренировку/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Новая тренировка/ })).not.toBeInTheDocument()
    expect(apiGet).toHaveBeenCalledExactlyOnceWith('/api/dashboard?userId=alexey&scenario=default')
    expect(navigateMock).not.toHaveBeenCalled()
    expectStoresUnchanged()
  })

  it('shows a recoverable load error and retries only when requested', async () => {
    const user = userEvent.setup()
    vi.mocked(apiGet).mockRejectedValueOnce(new Error('Dashboard unavailable'))
    const expectStoresUnchanged = captureStores()
    renderDashboard()

    expect(await screen.findByRole('heading', { name: 'Не удалось загрузить тренировки' })).toBeVisible()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(apiGet).toHaveBeenCalledTimes(1)
    vi.mocked(apiGet).mockResolvedValueOnce({ ...dashboardStoryScenarios.default, workouts: [makeWorkout(1)] })
    await user.click(screen.getByRole('button', { name: 'Повторить', exact: true }))

    expect(await screen.findByRole('button', { name: 'Выбрать тренировку «Тренировка 1»' })).toBeVisible()
    expect(screen.queryByRole('heading', { name: 'Не удалось загрузить тренировки' })).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(apiGet).toHaveBeenCalledTimes(2)
    expect(apiGet).toHaveBeenLastCalledWith('/api/dashboard?userId=alexey&scenario=default')
    expect(navigateMock).not.toHaveBeenCalled()
    expectStoresUnchanged()
  })
})