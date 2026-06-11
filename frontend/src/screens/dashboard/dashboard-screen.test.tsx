import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { dashboardStoryScenarios } from '@/mocks/data'
import { DashboardView } from '@/screens/dashboard/dashboard-screen'
import { useRuntimeStore } from '@/stores/runtime-store'

const navigateMock = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')

  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

describe('DashboardView', () => {
  beforeEach(() => {
    localStorage.clear()
    navigateMock.mockReset()
    useRuntimeStore.setState({ session: null, sessionSignature: null })
  })

  it('renders no-workout state', () => {
    render(
      <MemoryRouter>
        <DashboardView
          data={dashboardStoryScenarios['no-workout']}
          userName="Алексей"
          figureGender="male"
          emergencyStopActive={false}
          onStop={vi.fn()}
          onEmergencyStopChange={vi.fn()}
        />
      </MemoryRouter>,
    )

    expect(screen.getByText('Тренировки не найдены')).toBeInTheDocument()
  })

  it('renders blocking alert for drive-error state', () => {
    render(
      <MemoryRouter>
        <DashboardView
          data={dashboardStoryScenarios['drive-error']}
          userName="Алексей"
          figureGender="male"
          emergencyStopActive={false}
          onStop={vi.fn()}
          onEmergencyStopChange={vi.fn()}
        />
      </MemoryRouter>,
    )

    expect(screen.getByText('Ошибка правого привода')).toBeInTheDocument()
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

    render(
      <MemoryRouter>
        <DashboardView
          data={data}
          userName="Алексей"
          figureGender="male"
          emergencyStopActive={false}
          onStop={vi.fn()}
          onEmergencyStopChange={vi.fn()}
        />
      </MemoryRouter>,
    )

    await user.click(screen.getByRole('button', { name: /продолжить тренировку/i }))

    expect(useRuntimeStore.getState().session?.view).toBe('exercise-setup')
    expect(useRuntimeStore.getState().session?.currentExerciseId).toBe(session.exercises[1]?.id)
    expect(navigateMock).toHaveBeenCalledWith(`/exercise-setup?source=builder&programId=${encodeURIComponent(workoutId)}&photo=before`)
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

    render(
      <MemoryRouter>
        <DashboardView
          data={data}
          userName="Алексей"
          figureGender="male"
          emergencyStopActive={false}
          onStop={vi.fn()}
          onEmergencyStopChange={vi.fn()}
        />
      </MemoryRouter>,
    )

    await user.click(screen.getByRole('button', { name: /продолжить тренировку/i }))

    expect(navigateMock).toHaveBeenCalledWith(`/exercise-setup?source=builder&programId=${encodeURIComponent(workoutId)}&photo=before`)
  })
})