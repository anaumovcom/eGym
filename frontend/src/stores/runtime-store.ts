import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ExerciseCalibrationStatus } from '@/entities/exercise/model/types'
import type {
  RuntimeCalibrationState,
  RuntimeExerciseSummaryState,
  RuntimeExerciseOutcome,
  RuntimeFlowSource,
  RuntimePhotoMode,
  RuntimePhotoView,
  RuntimeSetResult,
  RuntimeWorkoutSession,
} from '@/entities/runtime/model/types'
import { requiresMachineCalibration } from '@/features/runtime/lib/runtime-exercise'
import { buildStrengthPlan, getStrengthModeTitle, normalizeStrengthDayType, normalizeStrengthModeId, toRuntimeSetPlan } from '@/features/strength/lib/strength-plan'
import { buildExerciseSession, buildExerciseSummary, buildPhotoProgressState, buildRestState, buildWorkoutSummary, createRuntimeSession, rebuildSessionSnapshots, simulateSetResult } from '@/mocks/stage3-data'

type RuntimeSessionInitOptions = { source: RuntimeFlowSource; slug?: string; programId?: string; runId?: string; photoMode?: RuntimePhotoMode | null; calibrationState?: RuntimeCalibrationState }

type RuntimeStore = {
  session: RuntimeWorkoutSession | null
  sessionSignature: string | null
  initializeSession: (options: RuntimeSessionInitOptions) => void
  initializeBackendSession: (session: RuntimeWorkoutSession, options: RuntimeSessionInitOptions) => void
  ensureSession: (options: RuntimeSessionInitOptions) => void
  setView: (view: RuntimeWorkoutSession['view']) => void
  completePhotoShot: (view: RuntimePhotoView, imageUrl?: string, takenAt?: string) => void
  openPhotoProgress: (mode: RuntimePhotoMode) => void
  setPhotoTimer: (seconds: 2 | 3 | 5) => void
  skipPhotoProgress: () => void
  continueAfterPhoto: () => void
  updateCalibrationState: (state: RuntimeCalibrationState) => void
  updateLoadSettings: (patch: Partial<RuntimeWorkoutSession['exercises'][number]['loadSettings']>) => void
  selectStrengthMode: (modeId: string, dayType?: string | null) => void
  startExercise: () => void
  finishCurrentSet: (result?: RuntimeSetResult) => void
  beginNextStep: () => void
  adjustRestSeconds: (delta: number) => void
  tickRestTimer: () => void
  pauseRestTimer: () => void
  completeExercise: (outcome?: RuntimeExerciseOutcome) => void
  replaceExerciseSummary: (summary: RuntimeExerciseSummaryState) => void
  continueAfterExerciseSummary: () => void
  completeWorkout: (outcome?: 'completed' | 'partial' | 'aborted') => void
}

function buildSignature(options: RuntimeSessionInitOptions) {
  return [options.source, options.slug ?? '', options.programId ?? '', options.runId ?? '', options.photoMode ?? '', options.calibrationState ?? ''].join(':')
}

function getCurrentExercise(session: RuntimeWorkoutSession) {
  return session.exercises.find((exercise) => exercise.id === session.currentExerciseId) ?? session.exercises[0]
}

function rebuildExercisePlan(exercise: RuntimeWorkoutSession['exercises'][number]) {
  if (exercise.kind === 'timed' || exercise.kind === 'group') {
    return exercise.plan
  }

  const strengthMode = exercise.strengthMode ?? { id: 'basic', dayType: null }
  return buildStrengthPlan(strengthMode.id, strengthMode.dayType, exercise.loadSettings, exercise.kind).map(toRuntimeSetPlan)
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
  initializeBackendSession: (session, options) => {
    set({ session, sessionSignature: buildSignature(options) })
  },
  ensureSession: (options) => {
    if (!get().session || get().sessionSignature !== buildSignature(options)) {
      get().initializeSession(options)
    }
  },
  setView: (view) =>
    set((state) => (state.session ? { session: { ...state.session, view } } : state)),
  completePhotoShot: (view, imageUrl, takenAt) =>
    set((state) => {
      if (!state.session) {
        return state
      }

      const shots = state.session.photoProgress.shots.map((shot) =>
        shot.view === view
          ? {
              ...shot,
              status: 'ready' as const,
              imageUrl: imageUrl ?? shot.imageUrl,
              takenAt: takenAt ?? shot.takenAt ?? new Date().toLocaleString('ru-RU'),
            }
          : shot,
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
      if (currentExercise.calibrationState === calibrationState && currentExercise.loadSettings.calibration === nextCalibration) {
        return state
      }

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
          ? (() => {
              const loadSettings = { ...exercise.loadSettings, ...patch }
              const calibrationState: RuntimeCalibrationState = requiresMachineCalibration({ ...exercise, loadSettings })
                ? (exercise.calibrationState === 'not-needed' ? 'missing' : exercise.calibrationState)
                : 'not-needed'
              const calibration: ExerciseCalibrationStatus = calibrationState === 'saved' ? 'ready' : calibrationState === 'missing' ? 'required' : 'unavailable'
              const nextExercise: RuntimeWorkoutSession['exercises'][number] = {
                ...exercise,
                calibrationState,
                movementRangeSaved: calibrationState === 'saved',
                movementRangeLabel: calibrationState === 'saved' ? '64–132 см' : calibrationState === 'missing' ? 'Калибровка не найдена' : 'Не требуется',
                loadSettings: {
                  ...loadSettings,
                  calibration,
                },
              }
              return {
                ...nextExercise,
                plan: rebuildExercisePlan(nextExercise),
              }
            })()
          : exercise,
      )

      const session = { ...state.session, exercises }
      return { session: { ...session, ...rebuildSessionSnapshots(session, state.session.workoutSummary.outcome) } }
    }),
  selectStrengthMode: (modeId, dayType) =>
    set((state) => {
      if (!state.session) {
        return state
      }

      const normalizedModeId = normalizeStrengthModeId(modeId)
      const normalizedDayType = normalizeStrengthDayType(normalizedModeId, dayType)
      const currentExercise = getCurrentExercise(state.session)
      const exercises = state.session.exercises.map((exercise) => {
        if (exercise.id !== currentExercise.id) {
          return exercise
        }

        const strengthMode = {
          id: normalizedModeId,
          title: getStrengthModeTitle(normalizedModeId),
          dayType: normalizedDayType,
        }
        const nextExercise = { ...exercise, strengthMode }
        return {
          ...nextExercise,
          plan: rebuildExercisePlan(nextExercise),
        }
      })

      const session = { ...state.session, exercises, currentSetIndex: 0 }
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
  finishCurrentSet: (providedResult) =>
    set((state) => {
      if (!state.session) {
        return state
      }

      const currentExercise = getCurrentExercise(state.session)
      const result = providedResult ?? simulateSetResult(state.session)
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
  tickRestTimer: () =>
    set((state) => {
      if (!state.session?.restState || state.session.restState.timerPaused || state.session.restState.remainingSeconds <= 0) {
        return state
      }

      return {
        session: {
          ...state.session,
          restState: {
            ...state.session.restState,
            remainingSeconds: Math.max(0, state.session.restState.remainingSeconds - 1),
          },
        },
      }
    }),
  pauseRestTimer: () =>
    set((state) =>
      state.session?.restState
        ? {
            session: {
              ...state.session,
              restState: {
                ...state.session.restState,
                timerPaused: !state.session.restState.timerPaused,
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
  replaceExerciseSummary: (summary) =>
    set((state) => (state.session ? { session: { ...state.session, exerciseSummary: summary } } : state)),
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