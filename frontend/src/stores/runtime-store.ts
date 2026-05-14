import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ExerciseCalibrationStatus } from '@/entities/exercise/model/types'
import type {
  RuntimeCalibrationState,
  RuntimeExerciseOutcome,
  RuntimeFlowSource,
  RuntimePhotoMode,
  RuntimePhotoView,
  RuntimeWorkoutSession,
} from '@/entities/runtime/model/types'
import { buildExerciseSession, buildExerciseSummary, buildPhotoProgressState, buildRestState, buildWorkoutSummary, createRuntimeSession, rebuildSessionSnapshots, simulateSetResult } from '@/mocks/stage3-data'

type RuntimeStore = {
  session: RuntimeWorkoutSession | null
  sessionSignature: string | null
  initializeSession: (options: { source: RuntimeFlowSource; slug?: string; photoMode?: RuntimePhotoMode | null; calibrationState?: RuntimeCalibrationState }) => void
  ensureSession: (options: { source: RuntimeFlowSource; slug?: string; photoMode?: RuntimePhotoMode | null; calibrationState?: RuntimeCalibrationState }) => void
  setView: (view: RuntimeWorkoutSession['view']) => void
  completePhotoShot: (view: RuntimePhotoView) => void
  openPhotoProgress: (mode: RuntimePhotoMode) => void
  setPhotoTimer: (seconds: 3 | 5 | 10 | 0) => void
  skipPhotoProgress: () => void
  continueAfterPhoto: () => void
  updateCalibrationState: (state: RuntimeCalibrationState) => void
  updateLoadSettings: (patch: Partial<RuntimeWorkoutSession['exercises'][number]['loadSettings']>) => void
  startExercise: () => void
  finishCurrentSet: () => void
  beginNextStep: () => void
  adjustRestSeconds: (delta: number) => void
  pauseRestTimer: () => void
  completeExercise: (outcome?: RuntimeExerciseOutcome) => void
  continueAfterExerciseSummary: () => void
  completeWorkout: (outcome?: 'completed' | 'partial' | 'aborted') => void
}

function buildSignature(options: { source: RuntimeFlowSource; slug?: string; photoMode?: RuntimePhotoMode | null; calibrationState?: RuntimeCalibrationState }) {
  return [options.source, options.slug ?? '', options.photoMode ?? '', options.calibrationState ?? ''].join(':')
}

function getCurrentExercise(session: RuntimeWorkoutSession) {
  return session.exercises.find((exercise) => exercise.id === session.currentExerciseId) ?? session.exercises[0]
}

export const useRuntimeStore = create<RuntimeStore>()(
  persist(
    (set, get) => ({
  session: null,
  sessionSignature: null,
  initializeSession: (options) => {
    const session = createRuntimeSession(options)
    const snapshots = rebuildSessionSnapshots(session, 'completed')
    set({ session: { ...session, ...snapshots }, sessionSignature: buildSignature(options) })
  },
  ensureSession: (options) => {
    if (!get().session || get().sessionSignature !== buildSignature(options)) {
      get().initializeSession(options)
    }
  },
  setView: (view) =>
    set((state) => (state.session ? { session: { ...state.session, view } } : state)),
  completePhotoShot: (view) =>
    set((state) => {
      if (!state.session) {
        return state
      }

      const shots = state.session.photoProgress.shots.map((shot) =>
        shot.view === view ? { ...shot, status: 'ready' as const, imageUrl: `/mock-assets/photo-progress/${view}.jpg`, takenAt: '14 мая 2026' } : shot,
      )
      const nextView = shots.find((shot) => shot.status === 'pending')?.view ?? 'back'
      const completed = shots.every((shot) => shot.status === 'ready')

      return {
        session: {
          ...state.session,
          photoProgress: {
            ...state.session.photoProgress,
            shots,
            currentView: nextView,
            completed,
          },
        },
      }
    }),
  openPhotoProgress: (mode) =>
    set((state) =>
      state.session
        ? {
            session: {
              ...state.session,
              photoProgress: buildPhotoProgressState(mode, false),
              view: 'photo-progress',
            },
          }
        : state,
    ),
  setPhotoTimer: (seconds) =>
    set((state) =>
      state.session
        ? {
            session: {
              ...state.session,
              photoProgress: { ...state.session.photoProgress, timerSeconds: seconds },
            },
          }
        : state,
    ),
  skipPhotoProgress: () =>
    set((state) =>
      state.session
        ? {
            session: {
              ...state.session,
              photoProgress: buildPhotoProgressState(state.session.photoProgress.mode, false),
              view: 'exercise-setup',
            },
          }
        : state,
    ),
  continueAfterPhoto: () =>
    set((state) =>
      state.session
        ? {
            session: {
              ...state.session,
              photoProgress: { ...state.session.photoProgress, completed: true },
              view: 'exercise-setup',
            },
          }
        : state,
    ),
  updateCalibrationState: (calibrationState) =>
    set((state) => {
      if (!state.session) {
        return state
      }

      const currentExercise = getCurrentExercise(state.session)
      const nextCalibration: ExerciseCalibrationStatus = calibrationState === 'saved' ? 'ready' : calibrationState === 'missing' ? 'required' : 'unavailable'
      const exercises = state.session.exercises.map((exercise) =>
        exercise.id === currentExercise.id
          ? {
              ...exercise,
              calibrationState,
              movementRangeSaved: calibrationState === 'saved',
              movementRangeLabel: calibrationState === 'saved' ? '64–132 см' : calibrationState === 'missing' ? 'Калибровка не найдена' : 'Не требуется',
              loadSettings: {
                ...exercise.loadSettings,
                calibration: nextCalibration,
              },
            }
          : exercise,
      )

      const session = { ...state.session, exercises }
      return { session: { ...session, ...rebuildSessionSnapshots(session, state.session.workoutSummary.outcome) } }
    }),
  updateLoadSettings: (patch) =>
    set((state) => {
      if (!state.session) {
        return state
      }

      const currentExercise = getCurrentExercise(state.session)
      const exercises = state.session.exercises.map((exercise) =>
        exercise.id === currentExercise.id
          ? {
              ...exercise,
              loadSettings: { ...exercise.loadSettings, ...patch },
            }
          : exercise,
      )

      const session = { ...state.session, exercises }
      return { session: { ...session, ...rebuildSessionSnapshots(session, state.session.workoutSummary.outcome) } }
    }),
  startExercise: () =>
    set((state) => {
      if (!state.session) {
        return state
      }

      const session = { ...state.session, view: 'exercise-session' as const }
      return { session: { ...session, sessionState: buildExerciseSession(session) } }
    }),
  finishCurrentSet: () =>
    set((state) => {
      if (!state.session) {
        return state
      }

      const currentExercise = getCurrentExercise(state.session)
      const result = simulateSetResult(state.session)
      const completedSets = {
        ...state.session.completedSets,
        [currentExercise.id]: [...(state.session.completedSets[currentExercise.id] ?? []), result],
      }
      const isLastSet = state.session.currentSetIndex >= currentExercise.plan.length - 1

      if (!isLastSet) {
        return {
          session: {
            ...state.session,
            completedSets,
            restState: buildRestState({ ...state.session, completedSets }, result),
            view: 'rest',
          },
        }
      }

      const completedExerciseIds = state.session.completedExerciseIds.includes(currentExercise.id)
        ? state.session.completedExerciseIds
        : [...state.session.completedExerciseIds, currentExercise.id]

      return {
        session: {
          ...state.session,
          completedSets,
          completedExerciseIds,
          exerciseSummary: buildExerciseSummary({ ...state.session, completedSets, completedExerciseIds }, 'completed'),
          view: 'exercise-summary',
        },
      }
    }),
  beginNextStep: () =>
    set((state) => {
      if (!state.session || !state.session.restState) {
        return state
      }

      const currentExercise = getCurrentExercise(state.session)
      const hasNextSet = state.session.currentSetIndex < currentExercise.plan.length - 1
      const nextExercise = state.session.exercises[currentExercise.order]
      const currentSetIndex = hasNextSet ? state.session.currentSetIndex + 1 : 0
      const currentExerciseId = hasNextSet ? currentExercise.id : nextExercise?.id ?? currentExercise.id
      const completedExerciseIds = hasNextSet ? state.session.completedExerciseIds : [...state.session.completedExerciseIds, currentExercise.id]
      const session = {
        ...state.session,
        currentExerciseId,
        currentSetIndex,
        completedExerciseIds,
        restState: undefined,
        view: 'exercise-session' as const,
      }
      return { session: { ...session, sessionState: buildExerciseSession(session) } }
    }),
  adjustRestSeconds: (delta) =>
    set((state) =>
      state.session?.restState
        ? {
            session: {
              ...state.session,
              restState: {
                ...state.session.restState,
                totalSeconds: Math.max(15, state.session.restState.totalSeconds + delta),
                remainingSeconds: Math.max(0, state.session.restState.remainingSeconds + delta),
              },
            },
          }
        : state,
    ),
  pauseRestTimer: () =>
    set((state) =>
      state.session?.restState
        ? {
            session: {
              ...state.session,
              restState: {
                ...state.session.restState,
                recommendation: state.session.restState.recommendation.includes('Таймер')
                  ? 'Оставить текущий отдых и переходить дальше по готовности.'
                  : `${state.session.restState.recommendation} Таймер поставлен на паузу.`,
              },
            },
          }
        : state,
    ),
  completeExercise: (outcome = 'completed') =>
    set((state) => {
      if (!state.session) {
        return state
      }

      const currentExercise = getCurrentExercise(state.session)
      const completedExerciseIds = state.session.completedExerciseIds.includes(currentExercise.id)
        ? state.session.completedExerciseIds
        : [...state.session.completedExerciseIds, currentExercise.id]
      const session = {
        ...state.session,
        completedExerciseIds,
        exerciseSummary: buildExerciseSummary({ ...state.session, completedExerciseIds }, outcome),
        view: 'exercise-summary' as const,
      }
      return { session }
    }),
  continueAfterExerciseSummary: () =>
    set((state) => {
      if (!state.session || !state.session.exerciseSummary) {
        return state
      }

      const currentExercise = getCurrentExercise(state.session)
      const nextExercise = state.session.exercises[currentExercise.order]

      if (!nextExercise || state.session.source === 'quick-start' || state.session.source === 'catalog') {
        const workoutSummary = buildWorkoutSummary(
          state.session.workoutSummary.muscleLoad,
          state.session.exerciseSummary.outcome === 'aborted' ? 'aborted' : 'completed',
        )

        return {
          session: {
            ...state.session,
            exerciseSummary: undefined,
            workoutSummary,
            view: 'workout-summary',
          },
        }
      }

      const session = {
        ...state.session,
        currentExerciseId: nextExercise.id,
        currentSetIndex: 0,
        exerciseSummary: undefined,
        view: 'exercise-setup' as const,
      }
      return { session: { ...session, ...rebuildSessionSnapshots(session, 'partial') } }
    }),
  completeWorkout: (outcome = 'completed') =>
    set((state) =>
      state.session
        ? {
            session: {
              ...state.session,
              view: 'workout-summary',
              workoutSummary: buildWorkoutSummary(state.session.workoutSummary.muscleLoad, outcome),
            },
          }
        : state,
    ),
    }),
    {
      name: 'egym-runtime-store',
      partialize: (state) => ({
        session: state.session,
        sessionSignature: state.sessionSignature,
      }),
    },
  ),
)