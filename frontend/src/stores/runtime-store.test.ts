import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getReturnableExercises, useRuntimeStore } from '@/stores/runtime-store'
import { useAppStore } from '@/stores/app-store'

describe('runtime store', () => {
  beforeEach(() => {
    localStorage.clear()
    useRuntimeStore.setState({ session: null, sessionSignature: null })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns to a skipped exercise and then continues with the next exercise not done yet', () => {
    useRuntimeStore.getState().initializeSession({ source: 'today' })
    const [first, second, third] = useRuntimeStore.getState().session!.exercises
    expect(third).toBeDefined()

    useRuntimeStore.getState().completeExercise('skipped')
    useRuntimeStore.getState().continueAfterExerciseSummary()
    expect(useRuntimeStore.getState().session?.currentExerciseId).toBe(second.id)
    useRuntimeStore.getState().finishExerciseWithResults([], 'completed')
    expect(getReturnableExercises(useRuntimeStore.getState().session!).map((exercise) => exercise.id)).toEqual([first.id])

    expect(useRuntimeStore.getState().resumeWorkoutExercise(first.id)).toBe('exercise-setup')
    const resumed = useRuntimeStore.getState().session!
    expect(resumed).toMatchObject({ currentExerciseId: first.id, currentSetIndex: 0, view: 'exercise-setup' })
    expect(resumed.completedExerciseIds).not.toContain(first.id)
    expect(resumed.exerciseOutcomes?.[first.id]).toBeUndefined()

    useRuntimeStore.getState().finishExerciseWithResults([], 'completed')
    useRuntimeStore.getState().continueAfterExerciseSummary()
    // The second exercise is already done: the workout goes on with the third one.
    expect(useRuntimeStore.getState().session).toMatchObject({ currentExerciseId: third.id, view: 'exercise-setup' })
  })

  it('opens the workout summary as partial when the last pending exercise is done but earlier ones are not started', () => {
    useRuntimeStore.getState().initializeSession({ source: 'today' })
    const exercises = useRuntimeStore.getState().session!.exercises
    const last = exercises[exercises.length - 1]
    useRuntimeStore.setState({ session: { ...useRuntimeStore.getState().session!, currentExerciseId: last.id } })

    useRuntimeStore.getState().finishExerciseWithResults([], 'completed')
    useRuntimeStore.getState().continueAfterExerciseSummary()

    expect(useRuntimeStore.getState().session?.view).toBe('workout-summary')
    expect(useRuntimeStore.getState().session?.workoutSummary.outcome).toBe('partial')
  })

  it.each(['pre-workout', 'post-workout', 'manual'] as const)('does not initialize a workout photo step for %s', (photoMode) => {
    useRuntimeStore.getState().initializeSession({ source: 'today', photoMode })

    expect(useRuntimeStore.getState().session?.view).toBe('exercise-setup')
    expect(useRuntimeStore.getState().session?.photoProgress.autoPrompt).toBe(false)
  })

  it.each(['pre-workout', 'post-workout', 'manual'] as const)('preserves a running session when legacy %s is removed from its URL', (photoMode) => {
    useRuntimeStore.getState().initializeSession({ source: 'today', photoMode })
    useRuntimeStore.getState().startExercise()
    useRuntimeStore.getState().finishCurrentSet()
    useRuntimeStore.getState().setBackendWorkoutSessionId(42)
    const session = useRuntimeStore.getState().session
    useRuntimeStore.setState({ sessionSignature: `today::::${photoMode}:` })

    useRuntimeStore.getState().ensureSession({ source: 'today' })

    expect(useRuntimeStore.getState().session).toBe(session)
    expect(useRuntimeStore.getState().session?.view).toBe('rest')
    expect(useRuntimeStore.getState().sessionSignature).toBe('today:::::')
    useRuntimeStore.getState().ensureSession({ source: 'today', photoMode })
    expect(useRuntimeStore.getState().session).toBe(session)
  })

  it.each([
    ['pre-workout', 'exercise-setup'],
    ['post-workout', 'workout-summary'],
  ] as const)('rehydrates a legacy %s step without losing saved results', async (mode, view) => {
    useRuntimeStore.getState().initializeSession({ source: 'today' })
    useRuntimeStore.getState().startExercise()
    useRuntimeStore.getState().finishCurrentSet()
    useRuntimeStore.getState().setBackendWorkoutSessionId(42)
    const session = useRuntimeStore.getState().session!
    const legacySession = {
      ...session,
      view: 'photo-progress' as const,
      photoProgress: { ...session.photoProgress, mode, autoPrompt: true },
    }
    useRuntimeStore.setState({ session: null, sessionSignature: null })
    localStorage.setItem('egym-runtime-store', JSON.stringify({
      state: { session: legacySession, sessionSignature: `today::::${mode}:` },
      version: 0,
    }))

    await useRuntimeStore.persist.rehydrate()

    expect(useRuntimeStore.getState().session).toEqual({
      ...legacySession,
      view,
      photoProgress: { ...legacySession.photoProgress, autoPrompt: false },
    })
    expect(useRuntimeStore.getState().sessionSignature).toBe('today:::::')
  })

  it('keeps standalone manual photos separate from the active workout view and identity', () => {
    useRuntimeStore.getState().initializeSession({ source: 'today' })
    useRuntimeStore.getState().startExercise()
    useRuntimeStore.getState().finishCurrentSet()
    const session = useRuntimeStore.getState().session!
    const signature = useRuntimeStore.getState().sessionSignature

    useRuntimeStore.getState().openPhotoProgress('manual')
    useRuntimeStore.getState().completePhotoShot('front', 'data:image/jpeg;base64,photo')
    useRuntimeStore.getState().continueAfterPhoto()
    useRuntimeStore.getState().skipPhotoProgress()

    expect(useRuntimeStore.getState().session).toEqual({
      ...session,
      photoProgress: expect.objectContaining({ mode: 'manual', autoPrompt: false, completed: false }),
    })
    expect(useRuntimeStore.getState().sessionSignature).toBe(signature)
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

  it.each(['basic', 'hypertrophy', 'strength'])('restores exact targets instead of %s template defaults', (trainingMode) => {
    useRuntimeStore.getState().initializeSession({ source: 'today' })
    useRuntimeStore.getState().restoreExerciseSettings({ weight: 27.5, sets: 2, reps: 7, restSeconds: 0,
      mode: 'Обычный вес', tempo: 'Медленно', trainingMode, trainingDayType: null })
    const exercise = useRuntimeStore.getState().session!.exercises[0]
    expect(exercise.loadSettings).toMatchObject({ weight: 27.5, sets: 2, reps: 7, restSeconds: 0, tempo: 'Медленно' })
    expect(exercise.plan).toHaveLength(2)
    expect(exercise.plan.every(plan => plan.targetReps === 7 && plan.recommendedWeightKg === 27.5 && plan.restSeconds === 0)).toBe(true)
  })

  it('carries a live weight change forward without resetting counters or completed plans', () => {
    useRuntimeStore.getState().initializeSession({ source: 'today' })
    useRuntimeStore.getState().startExercise()
    useRuntimeStore.getState().finishCurrentSet()
    useRuntimeStore.getState().beginNextStep()
    const before = useRuntimeStore.getState().session!
    useRuntimeStore.getState().updateExerciseWeight(0)
    const after = useRuntimeStore.getState().session!
    expect(after.sessionState).toBe(before.sessionState)
    expect(after.completedSets).toBe(before.completedSets)
    expect(after.currentSetIndex).toBe(before.currentSetIndex)
    expect(after.exercises[0].plan[0]).toBe(before.exercises[0].plan[0])
    expect(after.exercises[0].plan.slice(after.currentSetIndex).every(plan => plan.recommendedWeightKg === 0)).toBe(true)
  })

  it('does not reuse a persisted runtime workout after switching user', () => {
    useAppStore.setState({ selectedUserId: 'alexey' })
    useRuntimeStore.getState().initializeSession({ source: 'today' })
    const before = useRuntimeStore.getState().session
    useAppStore.setState({ selectedUserId: 'elena' })
    useRuntimeStore.getState().ensureSession({ source: 'today' })
    expect(useRuntimeStore.getState().session).not.toBe(before)
    expect(useRuntimeStore.getState().session?.userId).toBe('elena')
    useAppStore.setState({ selectedUserId: null })
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