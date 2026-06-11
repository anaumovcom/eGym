import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useRuntimeStore } from '@/stores/runtime-store'

describe('runtime store photo progress', () => {
  beforeEach(() => {
    localStorage.clear()
    useRuntimeStore.setState({ session: null, sessionSignature: null })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('skips pre-workout photo progress to exercise setup', () => {
    useRuntimeStore.getState().initializeSession({ source: 'today', photoMode: 'pre-workout' })

    expect(useRuntimeStore.getState().session?.view).toBe('photo-progress')

    useRuntimeStore.getState().skipPhotoProgress()

    const session = useRuntimeStore.getState().session

    expect(session?.view).toBe('exercise-setup')
    expect(session?.photoProgress.completed).toBe(false)
    expect(session?.photoProgress.mode).toBe('pre-workout')
  })

  it('ticks and pauses rest timer', () => {
    useRuntimeStore.getState().initializeSession({ source: 'today' })
    useRuntimeStore.getState().startExercise()
    useRuntimeStore.getState().finishCurrentSet()

    useRuntimeStore.getState().tickRestTimer()
    let session = useRuntimeStore.getState().session

    expect(session?.restState?.remainingSeconds).toBe((session?.restState?.totalSeconds ?? 0) - 1)
    expect(session?.restState?.timerPaused).toBe(false)

    useRuntimeStore.getState().pauseRestTimer()
    useRuntimeStore.getState().tickRestTimer()
    session = useRuntimeStore.getState().session

    expect(session?.restState?.timerPaused).toBe(true)
    expect(session?.restState?.remainingSeconds).toBe((session?.restState?.totalSeconds ?? 0) - 1)
  })

  it('marks calibration as not needed when machine weight is removed', () => {
    useRuntimeStore.getState().initializeSession({ source: 'today' })

    useRuntimeStore.getState().updateLoadSettings({ weight: 0 })

    const session = useRuntimeStore.getState().session
    const exercise = session?.exercises.find((item) => item.id === session.currentExerciseId)

    expect(exercise?.calibrationState).toBe('not-needed')
    expect(exercise?.loadSettings.calibration).toBe('unavailable')
    expect(exercise?.movementRangeLabel).toBe('Не требуется')
  })

  it('restarts a stale persisted session after the 03:00 training-day reset', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-05-26T04:00:00'))

    useRuntimeStore.getState().initializeSession({ source: 'builder', programId: 'program-1' })

    const staleSession = useRuntimeStore.getState().session
    expect(staleSession).not.toBeNull()

    useRuntimeStore.setState({
      session: staleSession ? { ...staleSession, startedAt: '2026-05-25T02:30:00.000Z' } : null,
      sessionSignature: useRuntimeStore.getState().sessionSignature,
    })

    useRuntimeStore.getState().ensureSession({ source: 'builder', programId: 'program-1' })

    const renewedSession = useRuntimeStore.getState().session
    expect(renewedSession?.startedAt).not.toBe('2026-05-25T02:30:00.000Z')
    expect(renewedSession?.programId).toBe('program-1')
  })

  it('preserves local workout exercises when backend summary is incomplete', () => {
    useRuntimeStore.getState().initializeSession({ source: 'today' })

    const initialSession = useRuntimeStore.getState().session
    if (!initialSession) {
      throw new Error('Expected runtime session to be initialized')
    }

    const initialExercises = initialSession.workoutSummary.exercises
    expect(initialExercises.length).toBeGreaterThan(1)

    useRuntimeStore.getState().replaceWorkoutSummary(
      {
        ...initialSession.workoutSummary,
        exercises: [
          {
            ...initialExercises[0],
            exerciseId: null,
            result: 'пропущено',
            status: 'skipped',
          },
        ],
      },
      true,
    )

    const updatedExercises = useRuntimeStore.getState().session?.workoutSummary.exercises ?? []

    expect(updatedExercises).toHaveLength(initialExercises.length)
    expect(updatedExercises[0]?.status).toBe('skipped')
    expect(updatedExercises[1]?.name).toBe(initialExercises[1]?.name)
  })

  it('normalizes workout summary metrics from local session when backend counts are incomplete', () => {
    useRuntimeStore.getState().initializeSession({ source: 'today' })

    const initialSession = useRuntimeStore.getState().session
    if (!initialSession) {
      throw new Error('Expected runtime session to be initialized')
    }

    const exercises = initialSession.exercises.slice(0, 2)
    const nextSession = {
      ...initialSession,
      exercises,
      currentExerciseId: exercises[0].id,
      completedExerciseIds: exercises.map((exercise) => exercise.id),
      exerciseOutcomes: {
        [exercises[0].id]: 'skipped' as const,
        [exercises[1].id]: 'skipped' as const,
      },
      workoutTitle: 'Новая тренировка',
    }

    useRuntimeStore.setState({ session: nextSession })

    useRuntimeStore.getState().replaceWorkoutSummary(
      {
        ...nextSession.workoutSummary,
        subtitle: 'Новая тренировка · 1 минута · 0 из 1 упражнений выполнено',
        metrics: [
          { label: 'длительность', value: '1 минута', hint: 'итог тренировки' },
          { label: 'упражнений', value: '0 / 1', hint: 'по плану' },
          { label: 'подходов', value: '0 / 1', hint: 'засчитано' },
          { label: 'повторов', value: '0', hint: 'суммарно' },
          { label: 'объём', value: '0 кг', hint: 'общий объём' },
        ],
        exercises: [
          {
            ...nextSession.workoutSummary.exercises[0],
            exerciseId: exercises[0].id,
            name: exercises[0].name,
            status: 'skipped',
            result: 'пропущено',
          },
        ],
      },
      true,
    )

    const metrics = useRuntimeStore.getState().session?.workoutSummary.metrics ?? []
    const exerciseMetric = metrics.find((metric) => metric.label === 'упражнений')
    const subtitle = useRuntimeStore.getState().session?.workoutSummary.subtitle

    expect(exerciseMetric?.value).toBe('0 / 2')
    expect(subtitle).toContain('0 из 2 упражнений выполнено')
  })
})