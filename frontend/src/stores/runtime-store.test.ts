import { beforeEach, describe, expect, it } from 'vitest'
import { useRuntimeStore } from '@/stores/runtime-store'

describe('runtime store photo progress', () => {
  beforeEach(() => {
    localStorage.clear()
    useRuntimeStore.setState({ session: null, sessionSignature: null })
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
})