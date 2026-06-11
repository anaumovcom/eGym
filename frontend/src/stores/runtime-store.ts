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
import type { LoadAdjustmentResponse } from '@/features/runtime/lib/runtime-persistence'
import { isSessionInCurrentTrainingDay } from '@/features/runtime/lib/runtime-day'
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
  finishExerciseWithResults: (results: RuntimeSetResult[], outcome: RuntimeExerciseOutcome) => void
  completeExercise: (outcome?: RuntimeExerciseOutcome) => void
  replaceExerciseSummary: (summary: RuntimeExerciseSummaryState) => void
  replaceWorkoutSummary: (summary: RuntimeWorkoutSession['workoutSummary'], saved?: boolean) => void
  applyLoadAdjustment: (exerciseSlug: string, adjustment: LoadAdjustmentResponse) => void
  resumeWorkoutExercise: (exerciseId: string) => RuntimeWorkoutSession['view'] | null
  setBackendWorkoutSessionId: (workoutSessionId: number) => void
  setBackendExerciseSessionId: (exerciseId: string, exerciseSessionId: number) => void
  markExerciseSaved: (exerciseId: string, exerciseSessionId: number | undefined, outcome: RuntimeExerciseOutcome) => void
  continueAfterExerciseSummary: () => void
  completeWorkout: (outcome?: 'completed' | 'partial' | 'aborted') => void
  resetSession: () => void
}

function buildSignature(options: RuntimeSessionInitOptions) {
  return [options.source, options.slug ?? '', options.programId ?? '', options.runId ?? '', options.photoMode ?? '', options.calibrationState ?? ''].join(':')
}

function getCurrentExercise(session: RuntimeWorkoutSession) {
  return session.exercises.find((exercise) => exercise.id === session.currentExerciseId) ?? session.exercises[0]
}

function getWorkoutSummaryExerciseMergeBase(exercise: RuntimeWorkoutSession['workoutSummary']['exercises'][number]) {
  return exercise.exerciseSlug
    ?? exercise.exerciseId
    ?? exercise.name
}

function buildWorkoutSummaryExerciseMergeKeys(exercises: RuntimeWorkoutSession['workoutSummary']['exercises']) {
  const occurrenceByBase = new Map<string, number>()

  return exercises.map((exercise) => {
    const base = getWorkoutSummaryExerciseMergeBase(exercise)
    const occurrence = occurrenceByBase.get(base) ?? 0
    occurrenceByBase.set(base, occurrence + 1)
    return `${base}#${occurrence}`
  })
}

function buildNormalizedWorkoutSummary(
  session: RuntimeWorkoutSession,
  summary: RuntimeWorkoutSession['workoutSummary'],
  exercises: RuntimeWorkoutSession['workoutSummary']['exercises'],
): RuntimeWorkoutSession['workoutSummary'] {
  const durationValue = summary.metrics.find((metric) => metric.label === 'длительность')?.value
    ?? session.workoutSummary.metrics.find((metric) => metric.label === 'длительность')?.value
    ?? '—'
  const completedExercises = session.exercises.filter((exercise) => (session.exerciseOutcomes?.[exercise.id] ?? null) === 'completed').length
  const targetExercises = session.exercises.length
  const targetSets = session.exercises.reduce((total, exercise) => total + exercise.plan.length, 0)
  const completedSets = Object.values(session.completedSets).reduce((total, results) => total + results.length, 0)
  const totalReps = Object.values(session.completedSets).reduce(
    (total, results) => total + results.reduce((resultTotal, result) => resultTotal + (result.reps ?? result.actualValue ?? 0), 0),
    0,
  )
  const totalVolume = Object.values(session.completedSets).reduce(
    (total, results) => total + results.reduce((resultTotal, result) => resultTotal + (result.volumeKg ?? ((result.weightKg ?? 0) * (result.reps ?? result.actualValue ?? 0))), 0),
    0,
  )

  return {
    ...summary,
    subtitle: `${session.workoutTitle} · ${durationValue} · ${completedExercises} из ${targetExercises} упражнений выполнено`,
    metrics: [
      { label: 'длительность', value: durationValue, hint: summary.outcome === 'aborted' ? 'частично выполнено' : 'итог тренировки' },
      { label: 'упражнений', value: `${completedExercises} / ${targetExercises}`, hint: 'по плану' },
      { label: 'подходов', value: `${completedSets} / ${targetSets}`, hint: 'засчитано' },
      { label: 'повторов', value: String(totalReps), hint: 'суммарно' },
      { label: 'объём', value: `${Math.round(totalVolume)} кг`, hint: 'общий объём' },
    ],
    exercises,
  }
}

function rebuildExercisePlan(exercise: RuntimeWorkoutSession['exercises'][number]) {
  if (exercise.kind === 'timed' || exercise.kind === 'group') {
    return exercise.plan
  }

  const strengthMode = exercise.strengthMode ?? { id: 'basic', dayType: null }
  return buildStrengthPlan(strengthMode.id, strengthMode.dayType, exercise.loadSettings, exercise.kind).map((plan) =>
    toRuntimeSetPlan(plan, exercise.loadSettings.reps),
  )
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
    if (get().session && !isSessionInCurrentTrainingDay(get().session)) {
      set({ session: null, sessionSignature: null })
    }

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
      const exerciseOutcomes = { ...(state.session.exerciseOutcomes ?? {}), [currentExercise.id]: 'completed' as RuntimeExerciseOutcome }

      return {
        session: {
          ...state.session,
          completedSets,
          completedExerciseIds,
          exerciseOutcomes,
          backendWorkoutSaved: false,
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
  finishExerciseWithResults: (results, outcome) =>
    set((state) => {
      if (!state.session) {
        return state
      }

      const currentExercise = getCurrentExercise(state.session)
      const completedSets = {
        ...state.session.completedSets,
        [currentExercise.id]: results,
      }
      const completedExerciseIds = state.session.completedExerciseIds.includes(currentExercise.id)
        ? state.session.completedExerciseIds
        : [...state.session.completedExerciseIds, currentExercise.id]
      const exerciseOutcomes = { ...(state.session.exerciseOutcomes ?? {}), [currentExercise.id]: outcome }
      const session = {
        ...state.session,
        completedSets,
        completedExerciseIds,
        exerciseOutcomes,
        backendWorkoutSaved: false,
        exerciseSummary: buildExerciseSummary({ ...state.session, completedSets, completedExerciseIds }, outcome),
        view: 'exercise-summary' as const,
      }
      return { session }
    }),
  completeExercise: (outcome = 'completed') =>
    set((state) => {
      if (!state.session) {
        return state
      }

      const currentExercise = getCurrentExercise(state.session)
      const completedExerciseIds = state.session.completedExerciseIds.includes(currentExercise.id)
        ? state.session.completedExerciseIds
        : [...state.session.completedExerciseIds, currentExercise.id]
      const exerciseOutcomes = { ...(state.session.exerciseOutcomes ?? {}), [currentExercise.id]: outcome }
      const session = {
        ...state.session,
        completedExerciseIds,
        exerciseOutcomes,
        backendWorkoutSaved: false,
        exerciseSummary: buildExerciseSummary({ ...state.session, completedExerciseIds }, outcome),
        view: 'exercise-summary' as const,
      }
      return { session }
    }),
  replaceExerciseSummary: (summary) =>
    set((state) => (state.session ? { session: { ...state.session, exerciseSummary: summary } } : state)),
  replaceWorkoutSummary: (summary, saved = false) =>
    set((state) => {
      if (!state.session) {
        return state
      }

      const currentExercises = state.session.workoutSummary.exercises
      const currentKeys = buildWorkoutSummaryExerciseMergeKeys(currentExercises)
      const incomingKeys = buildWorkoutSummaryExerciseMergeKeys(summary.exercises)
      const currentExercisesByKey = new Map(currentExercises.map((exercise, index) => [currentKeys[index], exercise]))
      const incomingExercisesByKey = new Map(summary.exercises.map((exercise, index) => [incomingKeys[index], exercise]))
      const mergedExercises = currentExercises.map((exercise, index) => {
        const incoming = incomingExercisesByKey.get(currentKeys[index])
        if (!incoming) {
          return exercise
        }

        return {
          ...exercise,
          ...incoming,
          nextLoad: exercise.nextLoad ?? incoming.nextLoad ?? incoming.currentLoad ?? exercise.currentLoad,
          nextWeightKg: exercise.nextWeightKg ?? incoming.nextWeightKg ?? incoming.currentWeightKg ?? exercise.currentWeightKg,
          nextReps: exercise.nextReps ?? incoming.nextReps ?? incoming.currentReps ?? exercise.currentReps,
          nextSets: exercise.nextSets ?? incoming.nextSets ?? incoming.currentSets ?? exercise.currentSets,
          nextRestSeconds: exercise.nextRestSeconds ?? incoming.nextRestSeconds ?? incoming.restSeconds ?? exercise.restSeconds,
        }
      })
      const appendedExercises = summary.exercises
        .filter((exercise, index) => !currentExercisesByKey.has(incomingKeys[index]))
        .map((exercise, index) => {
          const current = currentExercisesByKey.get(incomingKeys[index])
          return {
            ...exercise,
            nextLoad: current?.nextLoad ?? exercise.nextLoad ?? exercise.currentLoad ?? current?.currentLoad,
            nextWeightKg: current?.nextWeightKg ?? exercise.nextWeightKg ?? exercise.currentWeightKg ?? current?.currentWeightKg,
            nextReps: current?.nextReps ?? exercise.nextReps ?? exercise.currentReps ?? current?.currentReps,
            nextSets: current?.nextSets ?? exercise.nextSets ?? exercise.currentSets ?? current?.currentSets,
            nextRestSeconds: current?.nextRestSeconds ?? exercise.nextRestSeconds ?? exercise.restSeconds ?? current?.restSeconds,
          }
        })

      return {
        session: {
          ...state.session,
          workoutSummary: buildNormalizedWorkoutSummary(state.session, summary, [...mergedExercises, ...appendedExercises]),
          backendWorkoutSessionId: summary.workoutSessionId ?? state.session.backendWorkoutSessionId,
          backendWorkoutSaved: saved,
        },
      }
    }),
  applyLoadAdjustment: (exerciseSlug, adjustment) =>
    set((state) => {
      if (!state.session) {
        return state
      }

      const exerciseSummary = state.session.exerciseSummary?.exerciseSlug === exerciseSlug
        ? {
            ...state.session.exerciseSummary,
            nextLoad: adjustment.loadLabel,
            nextWeightKg: adjustment.weightKg ?? null,
            nextReps: adjustment.reps ?? null,
            nextSets: adjustment.sets ?? null,
            nextRestSeconds: adjustment.restSeconds ?? null,
            trainingMode: adjustment.trainingMode ?? state.session.exerciseSummary.trainingMode ?? null,
            trainingDayType: adjustment.trainingDayType ?? state.session.exerciseSummary.trainingDayType ?? null,
          }
        : state.session.exerciseSummary

      const workoutSummary = {
        ...state.session.workoutSummary,
        exercises: state.session.workoutSummary.exercises.map((exercise) =>
          exercise.exerciseSlug === exerciseSlug
            ? {
                ...exercise,
                nextLoad: adjustment.loadLabel,
                nextWeightKg: adjustment.weightKg ?? null,
                nextReps: adjustment.reps ?? null,
                nextSets: adjustment.sets ?? null,
                nextRestSeconds: adjustment.restSeconds ?? null,
                trainingMode: adjustment.trainingMode ?? exercise.trainingMode ?? null,
                trainingDayType: adjustment.trainingDayType ?? exercise.trainingDayType ?? null,
              }
            : exercise,
        ),
      }

      return {
        session: {
          ...state.session,
          exerciseSummary,
          workoutSummary,
        },
      }
    }),
  resumeWorkoutExercise: (exerciseId) => {
    const session = get().session
    if (!session) {
      return null
    }

    const targetExercise = session.exercises.find((exercise) => exercise.id === exerciseId)
    if (!targetExercise) {
      return null
    }

    const completedSetCount = session.completedSets[exerciseId]?.length ?? 0
    const nextSetIndex = Math.min(completedSetCount, Math.max(0, targetExercise.plan.length - 1))
    const nextView = completedSetCount > 0 ? 'exercise-session' as const : 'exercise-setup' as const
    const exerciseOutcomes = { ...(session.exerciseOutcomes ?? {}) }
    delete exerciseOutcomes[exerciseId]

    const nextSession: RuntimeWorkoutSession = {
      ...session,
      currentExerciseId: exerciseId,
      currentSetIndex: nextSetIndex,
      completedExerciseIds: session.completedExerciseIds.filter((id) => id !== exerciseId),
      exerciseOutcomes,
      exerciseSummary: undefined,
      restState: undefined,
      view: nextView,
      backendWorkoutSaved: false,
    }

    const nextWorkoutSummary = buildWorkoutSummary(nextSession.workoutSummary.muscleLoad, 'partial', nextSession)
    set({
      session: {
        ...nextSession,
        workoutSummary: nextWorkoutSummary,
        sessionState: nextView === 'exercise-session' ? buildExerciseSession(nextSession) : nextSession.sessionState,
      },
    })

    return nextView
  },
  setBackendWorkoutSessionId: (workoutSessionId) =>
    set((state) => (state.session ? { session: { ...state.session, backendWorkoutSessionId: workoutSessionId } } : state)),
  setBackendExerciseSessionId: (exerciseId, exerciseSessionId) =>
    set((state) => (
      state.session
        ? {
            session: {
              ...state.session,
              backendExerciseSessionIds: { ...(state.session.backendExerciseSessionIds ?? {}), [exerciseId]: exerciseSessionId },
            },
          }
        : state
    )),
  markExerciseSaved: (exerciseId, exerciseSessionId, outcome) =>
    set((state) => {
      if (!state.session) {
        return state
      }

      return {
        session: {
          ...state.session,
          backendExerciseSessionIds: exerciseSessionId
            ? { ...(state.session.backendExerciseSessionIds ?? {}), [exerciseId]: exerciseSessionId }
            : state.session.backendExerciseSessionIds,
          exerciseOutcomes: { ...(state.session.exerciseOutcomes ?? {}), [exerciseId]: outcome },
          backendWorkoutSaved: false,
        },
      }
    }),
  continueAfterExerciseSummary: () =>
    set((state) => {
      if (!state.session || !state.session.exerciseSummary) {
        return state
      }

      const currentExercise = getCurrentExercise(state.session)
      const nextExercise = state.session.exercises[currentExercise.order]

      if (!nextExercise || state.session.source === 'quick-start' || state.session.source === 'catalog') {
        const exerciseOutcomes = state.session.exerciseOutcomes ?? {}
        const hasIncompleteExercise = state.session.completedExerciseIds.some((exerciseId) => exerciseOutcomes[exerciseId] && exerciseOutcomes[exerciseId] !== 'completed')
        const workoutOutcome = state.session.exerciseSummary.outcome === 'aborted'
          ? 'aborted'
          : hasIncompleteExercise
            ? 'partial'
            : 'completed'
        const workoutSummary = buildWorkoutSummary(
          state.session.workoutSummary.muscleLoad,
          workoutOutcome,
          state.session,
        )

        return {
          session: {
            ...state.session,
            exerciseSummary: undefined,
            workoutSummary,
            backendWorkoutSaved: false,
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
              backendWorkoutSaved: false,
              workoutSummary: buildWorkoutSummary(state.session.workoutSummary.muscleLoad, outcome, state.session),
            },
          }
        : state,
    ),
  resetSession: () => set({ session: null, sessionSignature: null }),
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