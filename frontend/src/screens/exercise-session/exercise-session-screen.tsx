import { CheckCircle2, Dumbbell, Minus, Plus, SkipForward, Timer } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import type { HardwareCalibration, HardwareMotionTelemetry } from '@/features/hardware/model/types'
import type { RuntimeExerciseOutcome, RuntimeExerciseSessionState, RuntimeExerciseSummaryState, RuntimeSetResult, RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { hasMovableMachineLoad } from '@/features/runtime/lib/runtime-exercise'
import { getRuntimeInitOptions, withSearch } from '@/features/runtime/lib/runtime-query'
import { saveWorkoutToBackend } from '@/features/runtime/lib/runtime-persistence'
import { getSetTypeLabel } from '@/features/strength/lib/strength-plan'
import { useHardwareStore } from '@/stores/hardware-store'
import { apiPost } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { FormaState } from '@/shared/ui/status/forma-state'
import { ExerciseVideoPlayer } from '@/shared/ui/stage2/screen-components'
import { ValueStepper } from '@/shared/ui/training/value-stepper'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'

type CompletionStatus = 'completed' | 'partial' | 'skipped'
type ExerciseVideoGender = RuntimeWorkoutSession['exercises'][number]['details']['videos'][number]['gender']
type ExerciseVideoAsset = RuntimeWorkoutSession['exercises'][number]['details']['videos'][number]
type ExerciseSaveStatus = CompletionStatus | 'aborted'
type ExercisePersistStatus = ExerciseSaveStatus | 'in_progress'
type ExerciseSetSaveMode = 'replace' | 'preserve'
type SavedSetResponse = { setId: number; exerciseSessionId: number }
type MotionRailTone = 'lower' | 'neutral' | 'upper'
type MotionRail = {
  lowerLabel: string
  currentLabel: string
  upperLabel: string
  currentPercent: number
  lowerPercent: number
  upperPercent: number
  currentTone: MotionRailTone
}
const MOTION_RAIL_PADDING_MM = 200
const FAST_PULSE_CLASS = 'animate-[pulse_700ms_ease-in-out_infinite]'
const RAIL_BOTTOM_CLASSES = [
  'bottom-[4%]',
  'bottom-[8%]',
  'bottom-[12%]',
  'bottom-[16%]',
  'bottom-[20%]',
  'bottom-[24%]',
  'bottom-[28%]',
  'bottom-[32%]',
  'bottom-[36%]',
  'bottom-[40%]',
  'bottom-[44%]',
  'bottom-[48%]',
  'bottom-[52%]',
  'bottom-[56%]',
  'bottom-[60%]',
  'bottom-[64%]',
  'bottom-[68%]',
  'bottom-[72%]',
  'bottom-[76%]',
  'bottom-[80%]',
  'bottom-[84%]',
  'bottom-[88%]',
  'bottom-[92%]',
  'bottom-[96%]',
] as const
const RAIL_HEIGHT_CLASSES = [
  'h-0',
  'h-[4%]',
  'h-[8%]',
  'h-[12%]',
  'h-[16%]',
  'h-[20%]',
  'h-[24%]',
  'h-[28%]',
  'h-[32%]',
  'h-[36%]',
  'h-[40%]',
  'h-[44%]',
  'h-[48%]',
  'h-[52%]',
  'h-[56%]',
  'h-[60%]',
  'h-[64%]',
  'h-[68%]',
  'h-[72%]',
  'h-[76%]',
  'h-[80%]',
  'h-[84%]',
  'h-[88%]',
  'h-[92%]',
] as const

const currentRailStyles: Record<MotionRailTone, { fill: string; knob: string; ping: string; badge: string; value: string; line: string; leftArrow: string; rightArrow: string }> = {
  lower: {
    fill: `${FAST_PULSE_CLASS} bg-[#00ff66] shadow-[0_0_26px_rgba(0,255,102,0.72)]`,
    knob: `scale-125 ${FAST_PULSE_CLASS} border-[#c8ffd8]/90 bg-[#00ff66] shadow-[0_0_44px_rgba(0,255,102,0.85)]`,
    ping: 'bg-[#00ff66]',
    badge: `scale-105 ${FAST_PULSE_CLASS} border-[#00ff66]/70 bg-[#062d17]/92 text-[#c8ffd8] shadow-[0_0_24px_rgba(0,255,102,0.45)]`,
    value: `scale-105 ${FAST_PULSE_CLASS} text-[#c8ffd8] drop-shadow-[0_0_18px_rgba(0,255,102,0.45)]`,
    line: `${FAST_PULSE_CLASS} bg-[#00ff66] shadow-[0_0_18px_rgba(0,255,102,0.72)]`,
    leftArrow: `scale-125 ${FAST_PULSE_CLASS} border-l-[#00ff66] drop-shadow-[0_0_18px_rgba(0,255,102,0.85)]`,
    rightArrow: `scale-125 ${FAST_PULSE_CLASS} border-r-[#00ff66] drop-shadow-[0_0_18px_rgba(0,255,102,0.85)]`,
  },
  neutral: {
    fill: 'bg-linear-to-t from-[#8edb92] via-[#d6b05f] to-[#f2cf87]',
    knob: 'border-[#f2cf87]/70 bg-[#f2cf87] shadow-[0_0_30px_rgba(242,207,135,0.45)]',
    ping: 'bg-[#f2cf87]',
    badge: 'border-[#f2cf87]/30 bg-[#141009]/88 text-[#f2cf87]',
    value: 'text-[#f6d995] drop-shadow-[0_0_14px_rgba(242,207,135,0.28)]',
    line: 'bg-[#f2cf87] shadow-[0_0_12px_rgba(242,207,135,0.45)]',
    leftArrow: 'border-l-[#f2cf87] drop-shadow-[0_0_12px_rgba(242,207,135,0.55)]',
    rightArrow: 'border-r-[#f2cf87] drop-shadow-[0_0_12px_rgba(242,207,135,0.55)]',
  },
  upper: {
    fill: `${FAST_PULSE_CLASS} bg-[#00ff66] shadow-[0_0_26px_rgba(0,255,102,0.72)]`,
    knob: `scale-125 ${FAST_PULSE_CLASS} border-[#c8ffd8]/90 bg-[#00ff66] shadow-[0_0_44px_rgba(0,255,102,0.85)]`,
    ping: 'bg-[#00ff66]',
    badge: `scale-105 ${FAST_PULSE_CLASS} border-[#00ff66]/70 bg-[#062d17]/92 text-[#c8ffd8] shadow-[0_0_24px_rgba(0,255,102,0.45)]`,
    value: `scale-105 ${FAST_PULSE_CLASS} text-[#c8ffd8] drop-shadow-[0_0_18px_rgba(0,255,102,0.45)]`,
    line: `${FAST_PULSE_CLASS} bg-[#00ff66] shadow-[0_0_18px_rgba(0,255,102,0.72)]`,
    leftArrow: `scale-125 ${FAST_PULSE_CLASS} border-l-[#00ff66] drop-shadow-[0_0_18px_rgba(0,255,102,0.85)]`,
    rightArrow: `scale-125 ${FAST_PULSE_CLASS} border-r-[#00ff66] drop-shadow-[0_0_18px_rgba(0,255,102,0.85)]`,
  },
}

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

const fallbackMachine: RuntimeWorkoutSession['machine'] = {
  machineState: 'ready',
  machineLabel: 'Тренажёр готов',
  leftDrive: 'connected',
  rightDrive: 'connected',
  safety: 'enabled',
  calibration: '—',
}

function getPreferredVideoGender(userId: string | null): ExerciseVideoGender {
  return userId === 'elena' ? 'female' : 'male'
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function railPercentToStep(progressPercent: number) {
  const value = clamp(progressPercent, 0, 100)
  if (value >= 94) return 23
  if (value >= 90) return 22
  if (value >= 86) return 21
  if (value >= 82) return 20
  if (value >= 78) return 19
  if (value >= 74) return 18
  if (value >= 70) return 17
  if (value >= 66) return 16
  if (value >= 62) return 15
  if (value >= 58) return 14
  if (value >= 54) return 13
  if (value >= 50) return 12
  if (value >= 46) return 11
  if (value >= 42) return 10
  if (value >= 38) return 9
  if (value >= 34) return 8
  if (value >= 30) return 7
  if (value >= 26) return 6
  if (value >= 22) return 5
  if (value >= 18) return 4
  if (value >= 14) return 3
  if (value >= 10) return 2
  if (value >= 6) return 1
  return 0
}

function railFillClass(currentPercent: number, lowerPercent: number) {
  const lowerStep = railPercentToStep(lowerPercent)
  const currentStep = railPercentToStep(currentPercent)
  const startStep = Math.min(lowerStep, currentStep)
  const endStep = Math.max(lowerStep, currentStep)

  return `${RAIL_BOTTOM_CLASSES[startStep]} ${RAIL_HEIGHT_CLASSES[endStep - startStep]}`
}

function railMarkerPositionClass(progressPercent: number) {
  return RAIL_BOTTOM_CLASSES[railPercentToStep(progressPercent)]
}

function playRepCountedSound() {
  if (typeof window === 'undefined' || typeof window.AudioContext === 'undefined') {
    return
  }

  try {
    const audioContext = new window.AudioContext()
    const oscillator = audioContext.createOscillator()
    const gainNode = audioContext.createGain()
    const startAt = audioContext.currentTime

    oscillator.type = 'triangle'
    oscillator.frequency.setValueAtTime(1046.5, startAt)
    oscillator.frequency.exponentialRampToValueAtTime(1318.5, startAt + 0.12)
    gainNode.gain.setValueAtTime(0.0001, startAt)
    gainNode.gain.exponentialRampToValueAtTime(0.18, startAt + 0.02)
    gainNode.gain.exponentialRampToValueAtTime(0.0001, startAt + 0.22)
    oscillator.connect(gainNode)
    gainNode.connect(audioContext.destination)

    if (audioContext.state === 'suspended') {
      void audioContext.resume()
    }

    oscillator.start(startAt)
    oscillator.stop(startAt + 0.22)
    oscillator.onended = () => {
      void audioContext.close().catch(() => undefined)
    }
  } catch {
    // Ignore browser audio errors; rep counting must continue without sound.
  }
}

export function ExerciseSessionScreen() {
  const [searchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const session = useRuntimeStore((state) => state.session)
  const ensureSession = useRuntimeStore((state) => state.ensureSession)
  const startExercise = useRuntimeStore((state) => state.startExercise)
  const snapshot = useHardwareStore((state) => state.snapshot)
  const initOptions = getRuntimeInitOptions(searchParams)

  useEffect(() => {
    if (!session) {
      ensureSession(initOptions)
      return
    }

    if (session.view === 'exercise-setup' || session.view === 'rest') {
      startExercise()
    }
  }, [ensureSession, initOptions, session, startExercise])

  if (!session || !session.sessionState) {
    return (
      <FormaShell userName={getUserName(selectedUserId)} machine={snapshot?.machine ?? session?.machine ?? fallbackMachine} hideNavigation onStop={() => setEmergencyStopActive(true)}>
        <FormaState tone="loading" title="Готовим подход…" />
      </FormaShell>
    )
  }

  return <ExerciseSessionView session={session} state={session.sessionState} />
}

function ExerciseSessionView({ session, state }: { session: RuntimeWorkoutSession; state: RuntimeExerciseSessionState }) {
  const navigate = useNavigate()
  const location = useLocation()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const finishCurrentSet = useRuntimeStore((state) => state.finishCurrentSet)
  const finishExerciseWithResults = useRuntimeStore((state) => state.finishExerciseWithResults)
  const replaceExerciseSummary = useRuntimeStore((state) => state.replaceExerciseSummary)
  const setBackendWorkoutSessionId = useRuntimeStore((state) => state.setBackendWorkoutSessionId)
  const setBackendExerciseSessionId = useRuntimeStore((state) => state.setBackendExerciseSessionId)
  const markExerciseSaved = useRuntimeStore((state) => state.markExerciseSaved)
  const completeWorkout = useRuntimeStore((state) => state.completeWorkout)
  const snapshot = useHardwareStore((state) => state.snapshot)
  const currentCalibration = useHardwareStore((state) => state.currentCalibration)
  const hardwareError = useHardwareStore((state) => state.errorMessage)
  const setHardwareError = useHardwareStore((state) => state.setErrorMessage)
  const loadCurrentCalibration = useHardwareStore((state) => state.loadCurrentCalibration)
  const runCommand = useHardwareStore((state) => state.runCommand)
  const lastRepCountRef = useRef<number | null>(null)
  const autoFinishTriggeredRef = useRef(false)
  const [actualReps, setActualReps] = useState(0)
  const [repAdjustment, setRepAdjustment] = useState(0)
  const [actualWeight, setActualWeight] = useState(0)
  const [pendingAction, setPendingAction] = useState<CompletionStatus | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [sessionVideoIndex, setSessionVideoIndex] = useState(0)

  useEffect(() => {
    if (snapshot?.safety.state === 'emergency_stop') {
      setEmergencyStopActive(true)
    }
  }, [setEmergencyStopActive, snapshot?.safety.state])

  const activeSession = session
  const exercise = activeSession.exercises.find((item) => item.id === activeSession.currentExerciseId) ?? activeSession.exercises[0]
  const setPlan = exercise.plan[session.currentSetIndex] ?? exercise.plan[exercise.plan.length - 1]
  const isFailureSet = (state.setType ?? setPlan.setType) === 'failure'
  const isMachineExercise = hasMovableMachineLoad(exercise)
  const activeCalibration = currentCalibration?.exerciseSlug === exercise.slug ? currentCalibration : null
  const preferredVideoGender = getPreferredVideoGender(selectedUserId)
  const sessionVideoSequence = resolveExerciseVideoSequence(exercise.details.videos, preferredVideoGender)
  const sessionVideo = sessionVideoSequence[sessionVideoIndex]
    ?? (exercise.summary.previewVideoUrl ? { url: exercise.summary.previewVideoUrl, label: `${exercise.name} · превью` } : null)
  const liveMotion = isMachineExercise ? snapshot?.motion : null
  const syncDeltaMm = liveMotion ? liveMotion.syncDeltaMm ?? Math.abs(liveMotion.leftPositionMm - liveMotion.rightPositionMm) : null
  const plannedValue = getPlannedValue(state, setPlan)
  const targetText = getTargetText(state, setPlan)
  const correctedLiveRepetitionCount = liveMotion
    ? isFailureSet
      ? Math.max(0, liveMotion.repetitionCount + repAdjustment)
      : clamp(liveMotion.repetitionCount + repAdjustment, 0, plannedValue)
    : null
  const factValue = state.kind !== 'timed' && correctedLiveRepetitionCount != null
    ? correctedLiveRepetitionCount
    : actualReps
  const taskValue = state.kind === 'timed' ? `${state.currentValue} сек` : targetText
  const progressPercent = state.kind === 'timed'
    ? Math.round(((plannedValue - state.currentValue) / Math.max(1, plannedValue)) * 100)
    : correctedLiveRepetitionCount != null && liveMotion
      ? Math.round((correctedLiveRepetitionCount / Math.max(1, plannedValue)) * 100)
      : Math.round((state.currentValue / Math.max(1, plannedValue)) * 100)
  const liveMetrics = liveMotion
    ? [
        { label: 'Амплитуда', value: `${liveMotion.amplitudePercent}%`, tone: liveMotion.amplitudePercent >= 70 ? 'good' as const : 'warning' as const },
        { label: 'Позиция', value: `${Math.round(liveMotion.barPositionMm)} мм`, tone: 'neutral' as const },
        { label: 'Синхронность', value: `${syncDeltaMm?.toFixed(1) ?? '0.0'} мм`, tone: (syncDeltaMm ?? 0) <= 5 ? 'good' as const : 'warning' as const },
      ]
    : state.metrics
  const motionRail = isMachineExercise ? buildMotionRail(liveMotion, activeCalibration) : null
  const showWeightControl = isMachineExercise || actualWeight > 0

  useEffect(() => {
    if (!isMachineExercise || !selectedUserId) {
      return
    }

    void loadCurrentCalibration(selectedUserId, exercise.slug).catch(() => undefined)
  }, [exercise.slug, isMachineExercise, loadCurrentCalibration, selectedUserId])

  useEffect(() => {
    setSessionVideoIndex(0)
  }, [exercise.id, preferredVideoGender])

  useEffect(() => {
    autoFinishTriggeredRef.current = false
    setSaveError(null)
    setPendingAction(null)
    setActualReps(liveMotion?.repetitionCount ?? state.currentValue)
    setRepAdjustment(0)
    setActualWeight(setPlan.recommendedWeightKg ?? parseWeightLabel(state.weightLabel))
  }, [exercise.id, state.setNumber])

  useEffect(() => {
    if (!liveMotion) {
      lastRepCountRef.current = null
      return
    }

    if (lastRepCountRef.current == null) {
      lastRepCountRef.current = liveMotion.repetitionCount
      return
    }

    if (liveMotion.repetitionCount > lastRepCountRef.current) {
      playRepCountedSound()
    }

    lastRepCountRef.current = liveMotion.repetitionCount
  }, [liveMotion])

  useEffect(() => {
    if (!liveMotion || state.kind === 'timed' || isFailureSet || autoFinishTriggeredRef.current || pendingAction) {
      return
    }

    if ((correctedLiveRepetitionCount ?? liveMotion.repetitionCount) >= plannedValue) {
      autoFinishTriggeredRef.current = true
      void handleAutoCompleteCurrentSet()
    }
  }, [correctedLiveRepetitionCount, isFailureSet, liveMotion, pendingAction, plannedValue, state.kind])

  async function ensureBackendWorkoutSession() {
    const latestSession = useRuntimeStore.getState().session ?? activeSession
    if (latestSession.backendWorkoutSessionId) {
      return latestSession.backendWorkoutSessionId
    }

    const summary = await saveWorkoutToBackend(latestSession, selectedUserId ?? 'alexey', 'in_progress')
    if (summary.workoutSessionId) {
      setBackendWorkoutSessionId(summary.workoutSessionId)
      return summary.workoutSessionId
    }

    throw new Error('Не удалось сохранить тренировку. Попробуйте ещё раз.')
  }

  async function ensureBackendExerciseSession(workoutSessionId: number) {
    const latestSession = useRuntimeStore.getState().session ?? activeSession
    const existingExerciseSessionId = latestSession.backendExerciseSessionIds?.[exercise.id]
    if (existingExerciseSessionId) {
      return existingExerciseSessionId
    }

    const summary = await saveExerciseResultToBackend(exercise, [], selectedUserId ?? 'alexey', 'in_progress', workoutSessionId, undefined, 'preserve')
    if (!summary.exerciseSessionId) {
      throw new Error('Не удалось сохранить упражнение. Попробуйте ещё раз.')
    }
    setBackendExerciseSessionId(exercise.id, summary.exerciseSessionId)
    return summary.exerciseSessionId
  }

  async function handleAutoCompleteCurrentSet() {
    if (pendingAction) {
      return
    }

    setPendingAction('completed')
    setSaveError(null)

    const result = buildCurrentSetResult({ state, setPlan, liveMotion, actualReps: plannedValue, actualWeight, completionStatus: 'completed' })
    const completedForExercise = [...(activeSession.completedSets[exercise.id] ?? []), result]
    const isLastSet = activeSession.currentSetIndex >= exercise.plan.length - 1
    const exerciseStatus = getExerciseSaveStatus('completed', completedForExercise, exercise)

    try {
      if (isMachineExercise && selectedUserId) {
        await runCommand({
          action: 'complete_set',
          userId: selectedUserId,
          exerciseSlug: exercise.slug,
          calibrationRequired: false,
          rangeConfirmed: true,
          weightKg: exercise.loadSettings.weight,
          mode: 'machine',
        })
      }

      const workoutSessionId = await ensureBackendWorkoutSession()
      const exerciseSessionId = await ensureBackendExerciseSession(workoutSessionId)
      await saveSetResultToBackend(exerciseSessionId, result, exercise)
      const summary = isLastSet ? await saveExerciseResultToBackend(exercise, completedForExercise, selectedUserId ?? 'alexey', exerciseStatus, workoutSessionId, exerciseSessionId, 'preserve') : null
      finishCurrentSet(result)
      const nextView = useRuntimeStore.getState().session?.view

      if (summary) {
        const exerciseOutcome: RuntimeExerciseOutcome = exerciseStatus === 'aborted' ? 'aborted' : exerciseStatus
        markExerciseSaved(exercise.id, summary.exerciseSessionId, exerciseOutcome)
        replaceExerciseSummary(summary)
      }

      navigate(withSearch(nextView === 'exercise-summary' ? '/exercise-summary' : '/rest', location.search))
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'Не удалось сохранить результат упражнения. Попробуйте ещё раз.')
      setPendingAction(null)
    }
  }

  async function handleRecordFact(completionStatus: CompletionStatus) {
    if (pendingAction) {
      return
    }

    setPendingAction(completionStatus)
    setSaveError(null)
    const currentResult = completionStatus === 'skipped'
      ? null
      : buildCurrentSetResult({
          state,
          setPlan,
          liveMotion,
          actualReps: completionStatus === 'completed'
            ? (isFailureSet ? Math.max(plannedValue, factValue) : plannedValue)
            : Math.max(0, Math.min(plannedValue, factValue)),
          actualWeight,
          completionStatus,
        })
    const completedForExercise: RuntimeSetResult[] = completionStatus === 'skipped'
      ? []
      : [...(activeSession.completedSets[exercise.id] ?? []), currentResult!]
    const isLastSet = activeSession.currentSetIndex >= exercise.plan.length - 1
    const exerciseStatus: RuntimeExerciseOutcome = completionStatus
    const resolvedExerciseStatus = completionStatus === 'skipped' ? exerciseStatus : getExerciseSaveStatus(completionStatus, completedForExercise, exercise)

    try {
      if (completionStatus !== 'skipped' && isMachineExercise && selectedUserId) {
        await runCommand({
          action: 'complete_set',
          userId: selectedUserId,
          exerciseSlug: exercise.slug,
          calibrationRequired: false,
          rangeConfirmed: true,
          weightKg: exercise.loadSettings.weight,
          mode: 'machine',
        })
      }

      const workoutSessionId = await ensureBackendWorkoutSession()
      const exerciseSessionId = await ensureBackendExerciseSession(workoutSessionId)
      if (currentResult && shouldSaveSetResult(currentResult)) {
        await saveSetResultToBackend(exerciseSessionId, currentResult, exercise)
      }

      if (!isLastSet && currentResult) {
        finishCurrentSet(currentResult)
        const nextView = useRuntimeStore.getState().session?.view
        navigate(withSearch(nextView === 'exercise-summary' ? '/exercise-summary' : '/rest', location.search))
        return
      }

      let summary: RuntimeExerciseSummaryState
      if (completionStatus === 'skipped') {
        summary = await saveExerciseResultToBackend(exercise, completedForExercise, selectedUserId ?? 'alexey', exerciseStatus, workoutSessionId, exerciseSessionId, 'replace')
      } else {
        summary = await saveExerciseResultToBackend(exercise, completedForExercise, selectedUserId ?? 'alexey', resolvedExerciseStatus, workoutSessionId, exerciseSessionId, 'preserve')
      }

      finishExerciseWithResults(completedForExercise, resolvedExerciseStatus)
      markExerciseSaved(exercise.id, summary.exerciseSessionId, resolvedExerciseStatus)
      replaceExerciseSummary(summary)
      navigate(withSearch('/exercise-summary', location.search))
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'Не удалось сохранить результат упражнения. Попробуйте ещё раз.')
      setPendingAction(null)
    }
  }

  function changeFactValue(nextValue: number) {
    const bounded = isFailureSet || state.kind === 'timed' ? Math.max(0, nextValue) : clamp(nextValue, 0, plannedValue)
    if (state.kind !== 'timed' && liveMotion) {
      setRepAdjustment(bounded - liveMotion.repetitionCount)
      return
    }

    setActualReps(bounded)
  }

  function handleFinishSet() {
    return handleRecordFact(factValue >= plannedValue ? 'completed' : 'partial')
  }

  const errorMessage = saveError ?? hardwareError
  const setTypeLabel = getSetTypeLabel(state.setType)
  const factLabel = state.kind === 'timed' ? 'Секунды' : 'Повторы'

  return (
    <FormaShell
      userName={getUserName(selectedUserId)}
      machine={snapshot?.machine ?? session.machine}
      hideNavigation
      onStop={() => {
        void runCommand({ action: 'trigger_emergency_stop', userId: selectedUserId })
        setEmergencyStopActive(true)
      }}
    >
      <div className="rt-screen">
        <header className="rt-header">
          <div className="rt-chips" style={{ justifyContent: 'flex-start' }} aria-label="Место в тренировке">
            <span className="rt-chip">Упражнение {exercise.order} из {session.exercises.length}</span>
            <span className="rt-chip">{exercise.strengthMode.title}</span>
          </div>
          <div className="rt-title">
            <h1 className="font-display font-bold tracking-[-0.04em] text-white">{exercise.name}</h1>
            <p>
              <span>Подход {state.setNumber} из {state.totalSets}</span>
              {setTypeLabel ? <span>{setTypeLabel}</span> : null}
              <span>Отдых после подхода {setPlan.restSeconds} с</span>
            </p>
          </div>
          <div className="rt-chips" aria-label="Текущий подход">
            <span className="rt-chip" data-tone="good"><Dumbbell aria-hidden="true" />{state.weightLabel}</span>
            {state.kind === 'timed' ? <span className="rt-chip"><Timer aria-hidden="true" />{taskValue}</span> : null}
          </div>
        </header>

        <div className="rt-body rt-session-body" data-rail={Boolean(motionRail)}>
          <div className="rt-media">
            <div className="rt-media-frame">
              {sessionVideo ? (
                <button
                  type="button"
                  onClick={() => {
                    if (sessionVideoSequence.length > 1) {
                      setSessionVideoIndex((currentIndex) => (currentIndex + 1) % sessionVideoSequence.length)
                    }
                  }}
                  className={cn('block w-full text-left', sessionVideoSequence.length > 1 ? 'cursor-pointer' : 'cursor-default')}
                  aria-label={sessionVideoSequence.length > 1 ? 'Переключить видео упражнения' : sessionVideo.label}
                  disabled={sessionVideoSequence.length <= 1}
                >
                  <ExerciseVideoPlayer videoUrl={sessionVideo.url} videoLabel={sessionVideo.label} wrapperClassName="rounded-[var(--ui-radius)] border border-white/8" />
                </button>
              ) : (
                <div className="flex aspect-video items-center justify-center rounded-[var(--ui-radius)] border border-white/8 bg-[#0b1017] text-white/45">Видео упражнения недоступно</div>
              )}
              <div className="rt-media-caption" aria-hidden="true">
                <span>Следите за темпом и амплитудой</span>
                <span>Цель: <strong>{targetText}</strong></span>
              </div>
            </div>
          </div>

          <section className="rt-panel rt-session-center" aria-label="Текущий подход">
            <RepCounter
              label={factLabel}
              value={factValue}
              targetText={targetText}
              onChange={changeFactValue}
            />
            <div className="rt-progress" role="progressbar" aria-label="Прогресс подхода" aria-valuemin={0} aria-valuemax={100} aria-valuenow={clamp(progressPercent, 0, 100)}>
              <div style={{ width: `${clamp(progressPercent, 0, 100)}%` }} />
            </div>
            <div className="rt-session-secondary">
              {showWeightControl ? (
                <ValueStepper
                  label="Вес"
                  unit="кг"
                  value={actualWeight}
                  onChange={(delta) => setActualWeight(Math.max(0, actualWeight + delta))}
                  onValueCommit={(value) => setActualWeight(Math.max(0, value ?? 0))}
                />
              ) : null}
              <div className="rt-metrics" aria-label="Показатели движения">
                {liveMetrics.slice(0, 3).map((metric) => (
                  <div key={metric.label} data-tone={metric.tone}>
                    <span>{metric.label}</span>
                    <strong>{metric.value}</strong>
                  </div>
                ))}
              </div>
            </div>
            {state.groupMeta ? <p className="rt-actions-note">{state.groupMeta.groupName} · круг {state.groupMeta.currentRound}/{state.groupMeta.totalRounds} · дальше {state.groupMeta.nextStepLabel}</p> : null}
            {errorMessage ? (
              <div className="rt-overlay" role="alert">
                <div>
                  <strong>Не удалось сохранить подход</strong>
                  <p>{errorMessage}</p>
                  <Button variant="secondary" onClick={() => { setSaveError(null); setHardwareError(null) }}>Понятно</Button>
                </div>
              </div>
            ) : null}
          </section>

          {motionRail ? <MachinePositionRail rail={motionRail} amplitudePercent={liveMotion?.amplitudePercent} syncDeltaMm={syncDeltaMm} /> : null}
        </div>

        <div className="rt-actions" role="group" aria-label="Действия с подходом">
          <Button variant="secondary" disabled={pendingAction !== null} iconLeft={<SkipForward aria-hidden="true" />} onClick={() => void handleRecordFact('skipped')}>
            {pendingAction === 'skipped' ? 'Сохраняю…' : 'Пропустить упражнение'}
          </Button>
          <div className="rt-actions-note">
            {state.setWarning ?? state.setNote ?? <>{state.rirLabel ?? '1–3 повтора в запасе'} · после подхода начнётся отдых <strong>{setPlan.restSeconds} с</strong></>}
          </div>
          <Button className="rt-primary" disabled={pendingAction !== null} iconLeft={<CheckCircle2 aria-hidden="true" />} onClick={() => void handleFinishSet()}>
            {pendingAction && pendingAction !== 'skipped' ? 'Сохраняю…' : 'Завершить подход'}
          </Button>
        </div>
      </div>

      <EmergencyStopOverlay
        open={emergencyStopActive}
        onOpenChange={setEmergencyStopActive}
        actionLabel="Завершить тренировку как прерванную"
        onAction={() => {
          completeWorkout('aborted')
          setEmergencyStopActive(false)
          navigate(withSearch('/workout-summary', location.search))
        }}
      />
    </FormaShell>
  )
}

function RepCounter({ label, value, targetText, onChange }: { label: string; value: number; targetText: string; onChange: (value: number) => void }) {
  const [draft, setDraft] = useState(String(value))
  const [isEditing, setIsEditing] = useState(false)

  useEffect(() => {
    if (!isEditing) {
      setDraft(String(value))
    }
  }, [isEditing, value])

  function commitDraft() {
    const parsed = Number(draft.replace(',', '.').trim())
    if (draft.trim() && Number.isFinite(parsed)) {
      onChange(Math.round(parsed))
    } else {
      setDraft(String(value))
    }
  }

  return (
    <div className="rt-counter" role="group" aria-label={label}>
      <button type="button" aria-label={`Уменьшить: ${label}`} onClick={() => onChange(value - 1)} disabled={value <= 0}><Minus aria-hidden="true" /></button>
      <label className="rt-counter-value">
        <input
          type="text"
          inputMode="numeric"
          aria-label={label}
          value={isEditing ? draft : String(value)}
          onFocus={(event) => { setIsEditing(true); event.currentTarget.select() }}
          onBlur={() => { setIsEditing(false); commitDraft() }}
          onChange={(event) => setDraft(event.target.value.replace(/[^\d]/g, ''))}
          onKeyDown={(event) => {
            if (event.key === 'Enter') event.currentTarget.blur()
            if (event.key === 'Escape') { setDraft(String(value)); event.currentTarget.blur() }
          }}
        />
        <span>{label.toLowerCase()} · цель <strong>{targetText}</strong></span>
      </label>
      <button type="button" aria-label={`Увеличить: ${label}`} onClick={() => onChange(value + 1)}><Plus aria-hidden="true" /></button>
    </div>
  )
}

function MachinePositionRail({ rail, amplitudePercent, syncDeltaMm }: { rail: MotionRail; amplitudePercent?: number; syncDeltaMm: number | null }) {
  const fillClassName = railFillClass(rail.currentPercent, rail.lowerPercent)
  const markerClassName = railMarkerPositionClass(rail.currentPercent)
  const lowerLimitClassName = railMarkerPositionClass(rail.lowerPercent)
  const upperLimitClassName = railMarkerPositionClass(rail.upperPercent)
  const currentStyle = currentRailStyles[rail.currentTone]

  return (
    <section className="rt-rail" aria-label="Положение грифа">
      <div className="relative flex h-full min-h-0 flex-col items-center">
        <div className="rt-rail-track w-full">
          <div className="absolute top-0 bottom-0 left-1/2 w-5 -translate-x-1/2 rounded-full border border-white/12 bg-white/7 shadow-[inset_0_0_18px_rgba(255,255,255,0.08)]">
            <div className={cn('absolute right-0 left-0 rounded-full transition-colors duration-200', currentStyle.fill, fillClassName)} />
          </div>
          <RailLimitMarker positionClassName={upperLimitClassName} tone="upper">Верх · {rail.upperLabel}</RailLimitMarker>
          <RailLimitMarker positionClassName={lowerLimitClassName} tone="lower">Низ · {rail.lowerLabel}</RailLimitMarker>
          <div className={cn('absolute left-0 right-0 z-20 h-0', markerClassName)}>
            <div className="absolute top-0 right-3 left-3 grid -translate-y-1/2 grid-cols-[18px_minmax(0,1fr)_18px] items-center gap-x-4">
              <div className={cn('justify-self-center h-0 w-0 border-y-[7px] border-l-[12px] border-y-transparent transition-transform duration-200', currentStyle.leftArrow)} />
              <div className={cn('h-[2px] rounded-full transition-all duration-200', currentStyle.line)} />
              <div className={cn('justify-self-center h-0 w-0 border-y-[7px] border-r-[12px] border-y-transparent transition-transform duration-200', currentStyle.rightArrow)} />
            </div>
            <div className="absolute top-3 right-3 left-3 grid grid-cols-[18px_minmax(0,1fr)_18px] items-start gap-x-4">
              <div className={cn('-translate-x-1/2 justify-self-start text-[11px] font-semibold uppercase tracking-[0.18em] transition-all duration-200', currentStyle.value)}>Гриф</div>
              <div className={cn('translate-x-1/2 justify-self-end text-right text-[13px] font-semibold tracking-[0.08em] transition-all duration-200', currentStyle.value)}>{rail.currentLabel}</div>
            </div>
          </div>
        </div>
        <div className="mt-3 grid w-full grid-cols-2 gap-2 text-center text-xs text-white/52"><div className="rounded-2xl border border-white/8 bg-white/4 px-2 py-2">Ампл. {amplitudePercent ?? '—'}%</div><div className="rounded-2xl border border-white/8 bg-white/4 px-2 py-2">Синхр. {syncDeltaMm?.toFixed(1) ?? '—'} мм</div></div>
      </div>
    </section>
  )
}

function RailLimitMarker({ positionClassName, tone, children }: { positionClassName: string; tone: 'upper' | 'lower'; children: ReactNode }) {
  const lineClassName = tone === 'upper' ? 'bg-[#92e09a]/55' : 'bg-[#ffb4a7]/55'
  const badgeClassName = tone === 'upper'
    ? 'border-[#92e09a]/24 bg-[#102015] text-[#bdf3c1]'
    : 'border-[#ffb4a7]/22 bg-[#2b1514] text-[#ffc2bb]'

  return (
    <div className={cn('absolute left-0 right-0 z-10 flex translate-y-1/2 items-center gap-2', positionClassName)}>
      <div className={cn('h-px flex-1', lineClassName)} />
      <div className={cn('rounded-2xl border px-2 py-1 text-center text-[10px] font-semibold uppercase tracking-[0.14em]', badgeClassName)}>{children}</div>
      <div className={cn('h-px flex-1', lineClassName)} />
    </div>
  )
}

function parseWeightLabel(value: string) {
  return Number(value.replace(',', '.').match(/\d+(?:\.\d+)?/)?.[0] ?? '0')
}

function parseRirLabel(value?: string) {
  return Number(value?.match(/\d+/)?.[0] ?? '2')
}

function getPlannedValue(state: NonNullable<RuntimeWorkoutSession['sessionState']>, setPlan: RuntimeWorkoutSession['exercises'][number]['plan'][number]) {
  return state.targetMaxReps ?? setPlan.targetMaxReps ?? setPlan.targetReps ?? setPlan.targetSeconds ?? state.targetValue
}

function getTargetText(state: NonNullable<RuntimeWorkoutSession['sessionState']>, setPlan: RuntimeWorkoutSession['exercises'][number]['plan'][number]) {
  if (state.kind === 'timed') {
    return `${setPlan.targetSeconds ?? state.targetValue} сек`
  }
  if (state.kind === 'group') {
    return state.targetLabel
  }
  if ((state.setType ?? setPlan.setType) === 'failure') {
    return `${state.targetMaxReps ?? setPlan.targetMaxReps ?? setPlan.targetReps ?? state.targetValue}+ повторов`
  }
  const targetMin = state.targetMinReps ?? setPlan.targetMinReps
  const targetMax = state.targetMaxReps ?? setPlan.targetMaxReps ?? setPlan.targetReps
  return targetMin && targetMax && targetMin !== targetMax ? `${targetMin}–${targetMax} повторов` : `${targetMax ?? state.targetValue} повторов`
}

function resolveExerciseVideoSequence(videos: ExerciseVideoAsset[], preferredVideoGender: ExerciseVideoGender) {
  const secondaryGender: ExerciseVideoGender = preferredVideoGender === 'female' ? 'male' : 'female'
  const orderedKeys = [
    `${preferredVideoGender}:side`,
    `${preferredVideoGender}:front`,
    `${secondaryGender}:side`,
    `${secondaryGender}:front`,
  ]
  const sequence: ExerciseVideoAsset[] = []

  for (const key of orderedKeys) {
    const [gender, view] = key.split(':') as [ExerciseVideoGender, ExerciseVideoAsset['view']]
    const match = videos.find((video) => video.gender === gender && video.view === view)
    if (match && !sequence.some((item) => item.url === match.url)) {
      sequence.push(match)
    }
  }

  for (const video of videos) {
    if (!sequence.some((item) => item.url === video.url)) {
      sequence.push(video)
    }
  }

  return sequence
}

function buildMotionRail(liveMotion: HardwareMotionTelemetry | null | undefined, calibration: HardwareCalibration | null): MotionRail {
  const exerciseLowerValue = liveMotion?.lowerBoundMm ?? calibration?.lowerPointMm ?? 640
  const exerciseUpperValue = liveMotion?.upperBoundMm ?? calibration?.upperPointMm ?? 1320
  const lowerValue = exerciseLowerValue - MOTION_RAIL_PADDING_MM
  const upperValue = exerciseUpperValue + MOTION_RAIL_PADDING_MM
  const currentValue = liveMotion?.barPositionMm ?? calibration?.zeroPositionMm ?? lowerValue + (upperValue - lowerValue) * 0.5
  const range = Math.max(1, upperValue - lowerValue)
  return {
    lowerLabel: `${Math.round(exerciseLowerValue)} мм`,
    currentLabel: `${Math.round(currentValue)} мм`,
    upperLabel: `${Math.round(exerciseUpperValue)} мм`,
    currentPercent: clamp(((currentValue - lowerValue) / range) * 100, 4, 96),
    lowerPercent: clamp(((exerciseLowerValue - lowerValue) / range) * 100, 4, 96),
    upperPercent: clamp(((exerciseUpperValue - lowerValue) / range) * 100, 4, 96),
    currentTone: currentValue >= exerciseUpperValue ? 'upper' : currentValue <= exerciseLowerValue ? 'lower' : 'neutral',
  }
}

function getExerciseSaveStatus(completionStatus: CompletionStatus, completedSets: RuntimeSetResult[], exercise: RuntimeWorkoutSession['exercises'][number]): ExerciseSaveStatus {
  if (completionStatus === 'skipped') {
    return 'skipped'
  }
  if (completionStatus === 'partial' || completedSets.length < exercise.plan.length) {
    return 'partial'
  }
  return completedSets.some((result) => result.completionStatus === 'partial' || result.actualValue < (result.targetMinReps ?? result.plannedValue)) ? 'partial' : 'completed'
}

function buildCurrentSetResult({ state, setPlan, liveMotion, actualReps, actualWeight, completionStatus }: { state: NonNullable<RuntimeWorkoutSession['sessionState']>; setPlan: RuntimeWorkoutSession['exercises'][number]['plan'][number]; liveMotion: HardwareMotionTelemetry | null | undefined; actualReps: number; actualWeight: number; completionStatus: CompletionStatus }): RuntimeSetResult {
  const actualValue = completionStatus === 'skipped' ? 0 : Math.max(0, actualReps)
  const weightKg = completionStatus === 'skipped' ? 0 : Math.max(0, actualWeight)
  const isPartial = completionStatus === 'partial'
  const isSkipped = completionStatus === 'skipped'
  return {
    setNumber: state.setNumber,
    plannedValue: getPlannedValue(state, setPlan),
    actualValue,
    completionStatus,
    setType: state.setType ?? setPlan.setType,
    targetMinReps: state.targetMinReps ?? setPlan.targetMinReps,
    targetMaxReps: state.targetMaxReps ?? setPlan.targetMaxReps ?? setPlan.targetReps,
    reps: state.kind === 'timed' ? null : actualValue,
    weightKg,
    rir: isSkipped ? null : isPartial ? 0 : parseRirLabel(state.rirLabel),
    subjectiveEffort: isSkipped ? null : isPartial ? 8 : state.setType === 'failure' ? 9 : 7,
    discomfortLevel: 0,
    pain: false,
    techniqueBreakdown: false,
    comment: isSkipped ? 'Пропуск упражнения' : isPartial ? 'Частично выполнено' : null,
    volumeKg: state.kind === 'timed' ? 0 : weightKg * actualValue,
    amplitudePercent: liveMotion?.amplitudePercent,
    tempoLabel: isSkipped ? 'пропуск' : isPartial ? 'частично' : 'хорошо',
    syncLabel: liveMotion ? `${(liveMotion.syncDeltaMm ?? Math.abs(liveMotion.leftPositionMm - liveMotion.rightPositionMm)).toFixed(1)} мм` : undefined,
  }
}

function shouldSaveSetResult(result: RuntimeSetResult) {
  return result.completionStatus !== 'skipped' && Math.max(result.actualValue, result.reps ?? 0) > 0
}

function toBackendSetPayload(exercise: RuntimeWorkoutSession['exercises'][number], result: RuntimeSetResult) {
  return {
    setNumber: result.setNumber,
    plannedValue: result.plannedValue,
    actualValue: result.actualValue,
    setType: result.setType,
    targetMinReps: result.targetMinReps,
    targetMaxReps: result.targetMaxReps,
    reps: result.reps,
    weightKg: result.weightKg,
    tempoLabel: result.tempoLabel,
    amplitudePercent: result.amplitudePercent,
    restDurationSeconds: exercise.plan[result.setNumber - 1]?.restSeconds,
    rir: result.rir,
    subjectiveEffort: result.subjectiveEffort,
    discomfortLevel: result.discomfortLevel,
    pain: result.pain,
    techniqueBreakdown: result.techniqueBreakdown,
    comment: result.comment,
    syncLabel: result.syncLabel,
    machineMetrics: {
      trainingMode: exercise.strengthMode.id,
      trainingDayType: exercise.strengthMode.dayType,
      completionStatus: result.completionStatus,
    },
  }
}

async function saveSetResultToBackend(exerciseSessionId: number, result: RuntimeSetResult, exercise: RuntimeWorkoutSession['exercises'][number]) {
  if (!shouldSaveSetResult(result)) {
    return null
  }

  return apiPost<SavedSetResponse>('/api/runtime/sets', {
    exerciseSessionId,
    ...toBackendSetPayload(exercise, result),
  })
}

async function saveExerciseResultToBackend(exercise: RuntimeWorkoutSession['exercises'][number], completedSets: RuntimeSetResult[], userId: string, status: ExercisePersistStatus, workoutSessionId?: number, exerciseSessionId?: number, setSaveMode: ExerciseSetSaveMode = 'replace') {
  return apiPost<RuntimeExerciseSummaryState>('/api/runtime/exercises', {
    exerciseSessionId,
    userId,
    workoutSessionId,
    exerciseSlug: exercise.slug,
    exerciseName: exercise.name,
    exerciseSecondaryName: exercise.secondaryName,
    kind: exercise.kind,
    orderIndex: exercise.order,
    status,
    startedAt: new Date(Date.now() - Math.max(completedSets.length, 1) * 90_000).toISOString(),
    finishedAt: new Date().toISOString(),
    calibrationState: exercise.calibrationState,
    targetSets: exercise.plan.length,
    trainingMode: exercise.strengthMode.id,
    trainingDayType: exercise.strengthMode.dayType,
    recommendation: status === 'skipped' ? 'Упражнение пропущено. Можно перейти к следующему упражнению без изменения нагрузки.' : undefined,
    muscles: exercise.muscles.map((name, index) => ({ muscleId: name, name, role: index === 0 ? 'primary' : 'secondary' })),
    sets: status === 'skipped' || setSaveMode === 'preserve'
      ? []
      : completedSets.filter(shouldSaveSetResult).map((result) => toBackendSetPayload(exercise, result)),
  })
}
