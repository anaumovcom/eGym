import { useQuery } from '@tanstack/react-query'
import * as Dialog from '@radix-ui/react-dialog'
import { AlertTriangle, ArrowLeft, CheckCircle2, Play, RotateCcw, SlidersHorizontal } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import type { ExerciseDetails } from '@/entities/exercise/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import type { StrengthTrainingMode } from '@/entities/strength/model/types'
import { buildBackendBuilderRuntimeSession } from '@/features/runtime/lib/backend-builder-session'
import { getRuntimeResumeView, runtimeViewPath } from '@/features/runtime/lib/runtime-day'
import { requiresMachineCalibration, supportsFixedBarSetup } from '@/features/runtime/lib/runtime-exercise'
import { getRuntimeInitOptions, withSearch } from '@/features/runtime/lib/runtime-query'
import { HoldToJog } from '@/features/hardware/ui/hold-to-jog'
import { useHardwareStore } from '@/stores/hardware-store'
import { apiGet } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { FormaState } from '@/shared/ui/status/forma-state'
import { ExerciseVideoPlayer, LoadModeSelector } from '@/shared/ui/stage2/screen-components'
import { ValueStepper } from '@/shared/ui/training/value-stepper'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

const exerciseKindLabels: Record<RuntimeWorkoutSession['exercises'][number]['kind'], string> = {
  machine: 'Тренажёр',
  bodyweight: 'Своим весом',
  timed: 'На время',
  stretch: 'Растяжка',
  group: 'Группа / суперсет',
}

const fallbackMachine: MachineHealth = {
  machineState: 'ready',
  machineLabel: 'Тренажёр готов',
  leftDrive: 'connected',
  rightDrive: 'connected',
  safety: 'enabled',
  calibration: 'Калибровка: перед упражнением',
}

function formatMillimeters(value?: number | null) {
  if (value == null) {
    return '—'
  }

  return `${(value / 10).toFixed(1).replace('.0', '').replace('.', ',')} см`
}

function formatRange(lowerPointMm?: number | null, upperPointMm?: number | null) {
  if (lowerPointMm == null || upperPointMm == null || upperPointMm <= lowerPointMm) {
    return 'Не зафиксирован'
  }

  return `${formatMillimeters(lowerPointMm)} - ${formatMillimeters(upperPointMm)}`
}

function areBackendBuilderSessionsEquivalent(currentSession: RuntimeWorkoutSession, nextSession: RuntimeWorkoutSession) {
  if (currentSession.workoutTitle !== nextSession.workoutTitle || currentSession.exercises.length !== nextSession.exercises.length) {
    return false
  }

  return currentSession.exercises.every((exercise, index) => {
    const nextExercise = nextSession.exercises[index]
    if (!nextExercise) {
      return false
    }

    if (exercise.id !== nextExercise.id || exercise.slug !== nextExercise.slug || exercise.kind !== nextExercise.kind || exercise.plan.length !== nextExercise.plan.length) {
      return false
    }

    return exercise.plan.every((setPlan, setIndex) => {
      const nextSetPlan = nextExercise.plan[setIndex]
      return Boolean(nextSetPlan)
        && setPlan.targetReps === nextSetPlan.targetReps
        && setPlan.targetMinReps === nextSetPlan.targetMinReps
        && setPlan.targetMaxReps === nextSetPlan.targetMaxReps
        && setPlan.targetSeconds === nextSetPlan.targetSeconds
        && setPlan.recommendedWeightKg === nextSetPlan.recommendedWeightKg
        && setPlan.restSeconds === nextSetPlan.restSeconds
        && (setPlan.setType ?? null) === (nextSetPlan.setType ?? null)
    })
  })
}

export function ExerciseSetupScreen() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const resolvedUserId = selectedUserId ?? 'alexey'
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const session = useRuntimeStore((state) => state.session)
  const ensureSession = useRuntimeStore((state) => state.ensureSession)
  const updateCatalogExerciseMedia = useRuntimeStore((state) => state.updateCatalogExerciseMedia)
  const initializeBackendSession = useRuntimeStore((state) => state.initializeBackendSession)
  const updateCalibrationState = useRuntimeStore((state) => state.updateCalibrationState)
  const updateLoadSettings = useRuntimeStore((state) => state.updateLoadSettings)
  const selectStrengthMode = useRuntimeStore((state) => state.selectStrengthMode)
  const setView = useRuntimeStore((state) => state.setView)
  const startExercise = useRuntimeStore((state) => state.startExercise)
  const completeWorkout = useRuntimeStore((state) => state.completeWorkout)
  const snapshot = useHardwareStore((state) => state.snapshot)
  const currentCalibration = useHardwareStore((state) => state.currentCalibration)
  const hardwareError = useHardwareStore((state) => state.errorMessage)
  const setHardwareError = useHardwareStore((state) => state.setErrorMessage)
  const loadCurrentCalibration = useHardwareStore((state) => state.loadCurrentCalibration)
  const saveCalibration = useHardwareStore((state) => state.saveCalibration)
  const deleteCalibration = useHardwareStore((state) => state.deleteCalibration)
  const checkSafetyGate = useHardwareStore((state) => state.checkSafetyGate)
  const runCommand = useHardwareStore((state) => state.runCommand)
  const [capturedLowerPointMm, setCapturedLowerPointMm] = useState<number | null>(null)
  const [capturedUpperPointMm, setCapturedUpperPointMm] = useState<number | null>(null)
  const [capturedFixedPositionMm, setCapturedFixedPositionMm] = useState<number | null>(null)
  const [setupType, setSetupType] = useState<'bar_range' | 'fixed_position'>('bar_range')
  const [loadedSetupKey, setLoadedSetupKey] = useState<string | null>(null)
  const [calibrationOpen, setCalibrationOpen] = useState(false)
  const [modeDialogOpen, setModeDialogOpen] = useState(false)
  const [jogPending, setJogPending] = useState(false)

  const initOptions = useMemo(() => getRuntimeInitOptions(searchParams), [searchParams])
  const { data: catalogExerciseDetails } = useQuery({
    queryKey: ['runtime-catalog-exercise-media', resolvedUserId, initOptions.slug],
    queryFn: () => apiGet<ExerciseDetails>(`/api/exercises/${encodeURIComponent(initOptions.slug!)}?userId=${encodeURIComponent(resolvedUserId)}`),
    enabled: initOptions.source === 'catalog' && Boolean(initOptions.slug),
  })
  const usesBackendBuilderSession = initOptions.source === 'builder' && Boolean(initOptions.programId)
  const hasMatchingRuntimeBuilderSession = usesBackendBuilderSession
    ? session?.source === 'builder' && session.programId === initOptions.programId && session.dataSource === 'backend' && (!initOptions.runId || session.runId === initOptions.runId)
    : true
  const { data: backendBuilderSession, error: backendBuilderSessionError } = useQuery({
    queryKey: ['runtime-builder-session', resolvedUserId, initOptions.programId, initOptions.runId, initOptions.calibrationState],
    queryFn: () => buildBackendBuilderRuntimeSession({
      userId: resolvedUserId,
      programId: initOptions.programId!,
      runId: initOptions.runId,
      calibrationState: initOptions.calibrationState,
    }),
    enabled: usesBackendBuilderSession,
    staleTime: 0,
  })
  const isStaleRuntimeBuilderSession = Boolean(
    usesBackendBuilderSession
    && hasMatchingRuntimeBuilderSession
    && session
    && backendBuilderSession
    && !areBackendBuilderSessionsEquivalent(session, backendBuilderSession),
  )
  const shouldInitializeBackendBuilderSession = Boolean(
    usesBackendBuilderSession
    && backendBuilderSession
    && (!hasMatchingRuntimeBuilderSession || isStaleRuntimeBuilderSession),
  )
  const hasActiveBackendBuilderSession = usesBackendBuilderSession
    ? hasMatchingRuntimeBuilderSession && !isStaleRuntimeBuilderSession
    : true
  const { data: strengthModes = [] } = useQuery({
    queryKey: ['strength-modes'],
    queryFn: () => apiGet<StrengthTrainingMode[]>('/api/strength-modes'),
    staleTime: 5 * 60 * 1000,
  })

  useEffect(() => {
    if (usesBackendBuilderSession) {
      return
    }

    ensureSession(initOptions)
  }, [ensureSession, initOptions, usesBackendBuilderSession])

  useEffect(() => {
    if (catalogExerciseDetails && catalogExerciseDetails.slug === initOptions.slug) {
      updateCatalogExerciseMedia(catalogExerciseDetails)
    }
  }, [catalogExerciseDetails, initOptions.slug, updateCatalogExerciseMedia])

  useEffect(() => {
    if (!shouldInitializeBackendBuilderSession || !backendBuilderSession) {
      return
    }

    initializeBackendSession(backendBuilderSession, initOptions)
  }, [backendBuilderSession, initOptions, initializeBackendSession, shouldInitializeBackendBuilderSession])

  const exercise = shouldInitializeBackendBuilderSession
    ? undefined
    : hasActiveBackendBuilderSession
    ? session?.exercises.find((item) => item.id === session.currentExerciseId) ?? session?.exercises[0]
    : undefined

  useEffect(() => {
    if (!session || !exercise || session.view !== 'exercise-setup') {
      return
    }

    if (supportsFixedBarSetup(exercise)) {
      return
    }

    startExercise()
    navigate(withSearch('/exercise-session', location.search), { replace: true })
  }, [exercise, location.search, navigate, session, startExercise])

  useEffect(() => {
    if (session?.view === 'photo-progress') {
      const nextView = getRuntimeResumeView(session)
      setView(nextView)
      if (nextView === 'workout-summary') {
        navigate(withSearch(runtimeViewPath(nextView), location.search), { replace: true })
      }
    }
  }, [location.search, navigate, session, setView])

  useEffect(() => {
    if (snapshot?.safety.state === 'emergency_stop') {
      setEmergencyStopActive(true)
    }
  }, [setEmergencyStopActive, snapshot?.safety.state])

  useEffect(() => {
    if (!exercise) {
      return
    }

    if (!supportsFixedBarSetup(exercise)) {
      updateCalibrationState('not-needed')
      return
    }

    if (!selectedUserId) {
      updateCalibrationState('missing')
      return
    }

    let cancelled = false
    void loadCurrentCalibration(selectedUserId, exercise.slug)
      .then((calibration) => {
        if (!cancelled) {
          setLoadedSetupKey(`${selectedUserId}:${exercise.slug}`)
          updateCalibrationState(calibration ? 'saved' : 'missing')
        }
      })
      .catch(() => { if (!cancelled) setLoadedSetupKey(null) })
    return () => { cancelled = true }
  }, [exercise?.slug, loadCurrentCalibration, selectedUserId, updateCalibrationState])

  useEffect(() => {
    if (!exercise || !supportsFixedBarSetup(exercise)) {
      setCapturedLowerPointMm(null)
      setCapturedUpperPointMm(null)
      setCapturedFixedPositionMm(null)
      return
    }

    setCapturedLowerPointMm(null)
    setCapturedUpperPointMm(null)
    setCapturedFixedPositionMm(null)
    setSetupType(requiresMachineCalibration(exercise) ? 'bar_range' : 'fixed_position')
    setLoadedSetupKey(null)
  }, [exercise?.slug, selectedUserId])

  useEffect(() => {
    if (!exercise || !selectedUserId || loadedSetupKey !== `${selectedUserId}:${exercise.slug}`) {
      return
    }

    const saved = currentCalibration?.userId === selectedUserId && currentCalibration.exerciseSlug === exercise.slug ? currentCalibration : null
    setCapturedLowerPointMm(saved?.lowerPointMm ?? null)
    setCapturedUpperPointMm(saved?.upperPointMm ?? null)
    setCapturedFixedPositionMm(saved?.fixedPositionMm ?? null)
    setSetupType(saved?.setupType ?? (requiresMachineCalibration(exercise) ? 'bar_range' : 'fixed_position'))
  }, [currentCalibration, exercise?.slug, loadedSetupKey, selectedUserId])

  if (usesBackendBuilderSession && backendBuilderSessionError) {
    const message = backendBuilderSessionError instanceof Error ? backendBuilderSessionError.message : 'Попробуйте открыть тренировку ещё раз.'
    return (
      <FormaShell userName={getUserName(selectedUserId)} machine={session?.machine ?? fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
        <FormaState tone="error" title="Не удалось загрузить тренировку" description={message} action={{ label: 'К моим тренировкам', onClick: () => navigate('/builder') }} />
      </FormaShell>
    )
  }

  if (!session || !exercise) {
    return (
      <FormaShell userName={getUserName(selectedUserId)} machine={session?.machine ?? fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
        <FormaState tone="loading" title="Готовим упражнение…" />
      </FormaShell>
    )
  }

  const currentExercise = exercise
  const settings = exercise.loadSettings
  const currentStrengthMode = currentExercise.strengthMode ?? { id: 'basic', title: 'Базовый режим', dayType: null }
  const calibrationRequired = supportsFixedBarSetup(currentExercise)
  const savedCalibration = loadedSetupKey === `${selectedUserId}:${currentExercise.slug}` && currentCalibration?.userId === selectedUserId && currentCalibration.exerciseSlug === currentExercise.slug ? currentCalibration : null
  const setupVideo = currentExercise.details.videos.find((video) => video.gender === 'male' && video.view === 'side')
    ?? currentExercise.details.videos[0]
    ?? (currentExercise.summary.previewVideoUrl
      ? { url: currentExercise.summary.previewVideoUrl, label: `${currentExercise.name} · превью` }
      : null)
  const startBlocked = calibrationRequired && (!savedCalibration || !selectedUserId || savedCalibration.setupType !== setupType ||
    (setupType === 'bar_range' && (savedCalibration.lowerPointMm !== capturedLowerPointMm || savedCalibration.upperPointMm !== capturedUpperPointMm)) ||
    (setupType === 'fixed_position' && savedCalibration.fixedPositionMm !== capturedFixedPositionMm))
  const livePositionMm = snapshot?.motion.barPositionMm ?? null
  const controlMode = snapshot?.control?.mode ?? snapshot?.motion.controlMode
  const weightlessActive = controlMode === 'weightless'
  const barMoving = jogPending || controlMode === 'moving' || snapshot?.motion.moving === true
  const barStill = (snapshot?.control?.stillMs ?? 0) >= 500
  const liveLowerBoundMm = snapshot?.motion.lowerBoundMm ?? null
  const liveUpperBoundMm = snapshot?.motion.upperBoundMm ?? null
  const lowerPointMm = capturedLowerPointMm ?? null
  const upperPointMm = capturedUpperPointMm ?? null
  const fixedPositionMm = capturedFixedPositionMm
  const hasCompleteCalibrationRange = lowerPointMm != null && upperPointMm != null && upperPointMm > lowerPointMm
  const calibrationRangeLabel = savedCalibration?.setupType === 'fixed_position'
    ? `Фиксация: ${formatMillimeters(savedCalibration.fixedPositionMm)}`
    : formatRange(savedCalibration?.lowerPointMm, savedCalibration?.upperPointMm)

  function resetCalibrationDraft() {
    if (savedCalibration) {
      setCapturedLowerPointMm(savedCalibration.lowerPointMm)
      setCapturedUpperPointMm(savedCalibration.upperPointMm)
      setCapturedFixedPositionMm(savedCalibration.fixedPositionMm)
      setSetupType(savedCalibration.setupType)
      return
    }

    setCapturedLowerPointMm(null)
    setCapturedUpperPointMm(null)
    setCapturedFixedPositionMm(null)
  }

  function captureCalibrationPoint(point: 'lower' | 'upper' | 'fixed') {
    if (barMoving) return
    if (livePositionMm == null) {
      setHardwareError('Нет данных о положении грифа. Проверьте подключение тренажёра и повторите попытку.')
      return
    }

    setHardwareError(null)

    if (weightlessActive) {
      // the controller validates stillness and records the point with the drives compensated
      void runCommand({ action: 'capture_point', which: point, userId: selectedUserId })
        .then((response) => {
          const captured = response.capturedPositionMm ?? livePositionMm
          if (point === 'lower') setCapturedLowerPointMm(captured)
          else if (point === 'upper') setCapturedUpperPointMm(captured)
          else setCapturedFixedPositionMm(captured)
        })
        .catch((error: unknown) => setHardwareError(error instanceof Error ? error.message : 'Не удалось зафиксировать точку.'))
      return
    }

    if (point === 'lower') {
      setCapturedLowerPointMm(livePositionMm)
      return
    }

    if (point === 'upper') setCapturedUpperPointMm(livePositionMm)
    else setCapturedFixedPositionMm(livePositionMm)
  }

  async function toggleWeightless() {
    setHardwareError(null)
    try {
      if (weightlessActive) {
        await runCommand({ action: 'hold', userId: selectedUserId })
      } else {
        await runCommand({ action: 'enter_weightless', userId: selectedUserId, exerciseSlug: currentExercise.slug, mode: 'service' })
      }
    } catch (error) {
      setHardwareError(error instanceof Error ? error.message : 'Не удалось переключить режим невесомого грифа.')
    }
  }

  async function handleCalibrationSave() {
    if (!selectedUserId) {
      setHardwareError('Сначала выберите пользователя перед сохранением калибровки.')
      return
    }

    if (setupType === 'bar_range' && !hasCompleteCalibrationRange) {
      setHardwareError('Сначала зафиксируйте нижнюю и верхнюю точку амплитуды.')
      return
    }

    if (setupType === 'fixed_position' && fixedPositionMm == null) {
      setHardwareError('Сначала зафиксируйте высоту грифа.')
      return
    }

    try {
      await saveCalibration({
        userId: selectedUserId,
        exerciseSlug: currentExercise.slug,
        setupType,
        lowerPointMm: setupType === 'bar_range' ? lowerPointMm : null,
        upperPointMm: setupType === 'bar_range' ? upperPointMm : null,
        fixedPositionMm: setupType === 'fixed_position' ? fixedPositionMm : null,
        zeroPositionMm: setupType === 'bar_range' ? Math.round((lowerPointMm! + upperPointMm!) / 2) : fixedPositionMm!,
        movementRangeConfirmed: setupType === 'bar_range',
        calibrationRequired: true,
      })
      setHardwareError(null)
      updateCalibrationState('saved')
    } catch (error) {
      setHardwareError(error instanceof Error ? error.message : 'Не удалось сохранить настройку грифа.')
    }
  }

  async function handleCalibrationDelete() {
    try {
      if (savedCalibration) await deleteCalibration(savedCalibration.id, selectedUserId)
      setCapturedLowerPointMm(null)
      setCapturedUpperPointMm(null)
      setCapturedFixedPositionMm(null)
      updateCalibrationState('missing')
    } catch (error) {
      setHardwareError(error instanceof Error ? error.message : 'Не удалось удалить настройку грифа.')
    }
  }

  async function handleStartExercise() {
    if (startBlocked || barMoving) return
    if (calibrationRequired) {
      if (!selectedUserId) {
        setHardwareError('Для запуска тренажёрного упражнения нужно выбрать пользователя.')
        return
      }

      try {
        const safetyGate = await checkSafetyGate({
          userId: selectedUserId,
          exerciseSlug: currentExercise.slug,
          calibrationRequired: true,
          rangeConfirmed: setupType === 'bar_range',
          weightKg: settings.weight,
          mode: 'machine',
        })

        if (!safetyGate.allowed) {
          return
        }

        await runCommand({
          action: setupType === 'fixed_position' ? 'start_fixed_position' : 'start_motion',
          userId: selectedUserId,
          exerciseSlug: currentExercise.slug,
          calibrationRequired: true,
          rangeConfirmed: setupType === 'bar_range',
          weightKg: settings.weight,
          mode: 'machine',
          targetSet: 1,
          targetReps: currentExercise.plan[0]?.targetMaxReps ?? currentExercise.plan[0]?.targetReps ?? settings.reps,
          ...(setupType === 'fixed_position' ? { positionMm: savedCalibration?.fixedPositionMm ?? undefined, repCountSource: 'load' } : {}),
        })
      } catch (error) {
        setHardwareError(error instanceof Error ? error.message : 'Не удалось запустить тренажёр.')
        return
      }
    }

    startExercise()
    navigate(withSearch('/exercise-session', location.search))
  }

  const showCalibrationPanel = calibrationRequired && (startBlocked || calibrationOpen)
  const readyNote = (
    <>
      Готово к старту: <strong>{settings.sets} × {settings.reps}</strong> · вес {settings.weight} кг · отдых {settings.restSeconds} с
    </>
  )

  return (
    <FormaShell
      userName={getUserName(selectedUserId)}
      machine={snapshot?.machine ?? session.machine}
      onStop={() => {
        void runCommand({ action: 'trigger_emergency_stop', userId: selectedUserId })
        setEmergencyStopActive(true)
      }}
    >
      <div className="rt-screen">
        <header className="rt-header">
          <Button variant="secondary" iconLeft={<ArrowLeft aria-hidden="true" />} onClick={() => navigate(-1)}>
            Назад
          </Button>
          <div className="rt-title">
            <h1 className="font-display font-bold tracking-[-0.04em] text-white">Настройка упражнения</h1>
            <p>
              <span>{session.workoutTitle}</span>
              <span>Упражнение {exercise.order} из {session.exercises.length}</span>
              <span>{exerciseKindLabels[exercise.kind]}</span>
            </p>
          </div>
          <div className="rt-chips" role="group" aria-label="Готовность к старту">
            {calibrationRequired ? (
              savedCalibration ? (
                <button type="button" className="rt-chip" data-tone={startBlocked ? 'warning' : 'good'} aria-pressed={calibrationOpen} onClick={() => setCalibrationOpen((current) => !current)}>
                  {startBlocked ? <AlertTriangle aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />}
                  {startBlocked ? 'Есть несохранённые изменения' : savedCalibration.setupType === 'fixed_position' ? calibrationRangeLabel : `Калибровка: ${calibrationRangeLabel}`}
                </button>
              ) : (
                <span className="rt-chip" data-tone="warning"><AlertTriangle aria-hidden="true" />Нужна настройка грифа</span>
              )
            ) : (
              <span className="rt-chip" data-tone="good"><CheckCircle2 aria-hidden="true" />Калибровка не нужна</span>
            )}
          </div>
        </header>

        <div className="rt-body rt-setup-body">
          <div className="rt-setup-media">
            <div className="rt-media">
              <div className="rt-media-frame">
                {setupVideo ? (
                  <ExerciseVideoPlayer videoUrl={setupVideo.url} videoLabel={setupVideo.label} wrapperClassName="rounded-[var(--ui-radius)] border border-white/8" />
                ) : (
                  <div className="flex aspect-video items-center justify-center rounded-[var(--ui-radius)] border border-white/8 bg-[#0b1017] text-white/45">Видео упражнения недоступно</div>
                )}
                <div className="rt-media-caption" aria-hidden="true">
                  <span>{exercise.muscles.slice(0, 2).join(' · ') || exerciseKindLabels[exercise.kind]}</span>
                  <span>План: <strong>{settings.sets} × {settings.reps}</strong></span>
                </div>
              </div>
            </div>

          </div>

          <div className="rt-setup-right">
          <section className="rt-panel" aria-label="Параметры упражнения">
            <div className="rt-setup-parameters-head">
            <div className="rt-exercise">
              <h2 title={exercise.name}>{exercise.name}</h2>
              {exercise.secondaryName ? <p>{exercise.secondaryName}</p> : null}
              {exercise.muscles.length ? <div className="rt-muscles">{exercise.muscles.slice(0, 4).map((item) => <span key={item}>{item}</span>)}</div> : null}
            </div>
            <Button variant="secondary" iconLeft={<SlidersHorizontal aria-hidden="true" />} onClick={() => setModeDialogOpen(true)}>
              Режим тренировки
            </Button>
            </div>

            {hardwareError ? (
              <div className="rt-alert" data-tone="danger" role="alert">
                <AlertTriangle aria-hidden="true" />
                <div>
                  <strong>Ошибка тренажёра</strong>
                  <p>{hardwareError}</p>
                </div>
                <Button variant="secondary" onClick={() => setHardwareError(null)}>Скрыть</Button>
              </div>
            ) : null}

            <div className="rt-steppers">
              <ValueStepper
                label="Вес"
                unit="кг"
                value={settings.weight}
                onChange={(delta) => updateLoadSettings({ weight: Math.max(0, settings.weight + delta * 2.5) })}
                onValueCommit={(value) => updateLoadSettings({ weight: Math.max(0, value ?? 0) })}
              />
              <ValueStepper
                label="Подходы"
                value={settings.sets}
                onChange={(delta) => updateLoadSettings({ sets: Math.max(1, settings.sets + delta) })}
                onValueCommit={(value) => updateLoadSettings({ sets: Math.max(1, value ?? 1) })}
              />
              <ValueStepper
                label={exercise.kind === 'timed' ? 'Секунды' : 'Повторы'}
                value={settings.reps}
                onChange={(delta) => updateLoadSettings({ reps: Math.max(1, settings.reps + delta) })}
                onValueCommit={(value) => updateLoadSettings({ reps: Math.max(1, value ?? 1) })}
              />
              <ValueStepper
                label="Отдых"
                unit="сек"
                value={settings.restSeconds}
                onChange={(delta) => updateLoadSettings({ restSeconds: Math.max(15, settings.restSeconds + delta * 15) })}
                onValueCommit={(value) => updateLoadSettings({ restSeconds: Math.max(15, value ?? 15) })}
              />
            </div>

            <p className="rt-setup-parameters-note">{currentStrengthMode.title} · {settings.mode} · безопасный диапазон {settings.safeRange[0]}–{settings.safeRange[1]} кг</p>
          </section>
          {showCalibrationPanel ? (
            <section className="rt-calibration" data-saved={Boolean(savedCalibration)} aria-label="Настройка грифа">
              <header>
                <div>
                  <h3>{savedCalibration ? 'Настройка грифа сохранена' : 'Настройка грифа'}</h3>
                  <p>
                    {setupType === 'fixed_position'
                      ? 'Выставьте высоту грифа и сохраните положение.'
                      : hasCompleteCalibrationRange
                        ? 'Точки зафиксированы — сохраните амплитуду.'
                        : 'Выставьте гриф и зафиксируйте нижнюю и верхнюю точки.'}
                  </p>
                </div>
                <div className="rt-calibration-links">
                  <Button variant="ghost" iconLeft={<RotateCcw aria-hidden="true" />} onClick={resetCalibrationDraft}>Сбросить изменения</Button>
                  {savedCalibration ? <Button variant="ghost" onClick={() => void handleCalibrationDelete()}>Удалить настройку</Button> : null}
                  {savedCalibration ? <Button variant="ghost" onClick={() => setCalibrationOpen(false)}>Свернуть</Button> : null}
                </div>
              </header>
              <div className="rt-calibration-actions" role="group" aria-label="Тип настройки грифа">
                <Button variant={setupType === 'bar_range' ? 'primary' : 'secondary'} aria-pressed={setupType === 'bar_range'} onClick={() => setSetupType('bar_range')}>Амплитуда движения</Button>
                <Button variant={setupType === 'fixed_position' ? 'primary' : 'secondary'} aria-pressed={setupType === 'fixed_position'} onClick={() => setSetupType('fixed_position')}>Фиксированное положение</Button>
              </div>
              <dl className="rt-calibration-values" data-mode={setupType}>
                <div><dt>Текущая позиция</dt><dd>{formatMillimeters(livePositionMm)}</dd><small>Гриф сейчас</small></div>
                {setupType === 'bar_range' ? (
                  <>
                    <div><dt>Нижняя точка</dt><dd>{formatMillimeters(lowerPointMm)}</dd><small>Live-низ: {formatMillimeters(liveLowerBoundMm)}</small></div>
                    <div><dt>Верхняя точка</dt><dd>{formatMillimeters(upperPointMm)}</dd><small>Live-верх: {formatMillimeters(liveUpperBoundMm)}</small></div>
                  </>
                ) : (
                  <div><dt>Фиксированная высота</dt><dd>{formatMillimeters(fixedPositionMm)}</dd><small>Гриф удерживается на этой высоте</small></div>
                )}
              </dl>
              <div className="rt-calibration-actions rt-calibration-controls" data-mode={setupType}>
                <Button variant={weightlessActive ? 'primary' : 'secondary'} disabled={barMoving} onClick={() => void toggleWeightless()}>
                  {weightlessActive ? 'Невесомый гриф: вкл — удержать' : 'Невесомый гриф'}
                </Button>
                <HoldToJog userId={selectedUserId} exerciseSlug={currentExercise.slug}
                  disabled={barMoving || livePositionMm == null} onHoldingChange={setJogPending} />
                {setupType === 'bar_range' ? (
                  <>
                    <Button variant="secondary" aria-label="Зафиксировать нижнюю точку" disabled={barMoving || (weightlessActive && !barStill)} onClick={() => captureCalibrationPoint('lower')}>Запомнить низ</Button>
                    <Button variant="secondary" aria-label="Зафиксировать верхнюю точку" disabled={barMoving || (weightlessActive && !barStill)} onClick={() => captureCalibrationPoint('upper')}>Запомнить верх</Button>
                  </>
                ) : (
                  <Button variant="secondary" disabled={barMoving || (weightlessActive && !barStill)} onClick={() => captureCalibrationPoint('fixed')}>Зафиксировать высоту грифа</Button>
                )}
                <Button disabled={barMoving || (setupType === 'bar_range' ? !hasCompleteCalibrationRange : fixedPositionMm == null)} onClick={() => void handleCalibrationSave()}>
                  {setupType === 'bar_range' ? 'Сохранить амплитуду' : 'Сохранить положение'}
                </Button>
              </div>
              {weightlessActive ? (
                <p className="rt-calibration-hint">
                  Гриф скомпенсирован — переместите его руками в нужную точку и отпустите. {barStill ? 'Гриф неподвижен — можно фиксировать точку.' : 'Дождитесь остановки грифа.'}
                </p>
              ) : null}
            </section>
          ) : null}
          </div>
        </div>

        <div className="rt-actions" role="group" aria-label="Действия с упражнением">
          <Button
            variant="secondary"
            onClick={() => {
              completeWorkout('aborted')
              navigate(withSearch('/workout-summary', location.search))
            }}
          >
            Завершить тренировку
          </Button>
          <div className="rt-actions-note">{startBlocked ? 'Сначала сохраните настройку грифа — после этого старт откроется.' : readyNote}</div>
          <Button className="rt-primary" disabled={startBlocked || barMoving} iconLeft={<Play aria-hidden="true" />} onClick={() => void handleStartExercise()}>
            {startBlocked ? 'Старт недоступен' : 'Запустить упражнение'}
          </Button>
        </div>
      </div>

      <Dialog.Root open={modeDialogOpen} onOpenChange={setModeDialogOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
          <SafetyDialogContent className="rt-details-panel">
            <Dialog.Title className="font-display text-3xl font-bold">Режим тренировки</Dialog.Title>
            <Dialog.Description className="mt-2 text-sm text-white/70">{exercise.name} · {settings.recommendation}</Dialog.Description>
            <div className="rt-details-body">
              <StrengthModeSelector
                modes={strengthModes}
                selectedModeId={currentStrengthMode.id}
                selectedDayType={currentStrengthMode.dayType}
                onSelect={(modeId, dayType) => selectStrengthMode(modeId, dayType)}
              />
              <div>
                <h3>Режим нагрузки</h3>
                <LoadModeSelector value={settings.mode} options={['Обычный вес', 'Контроль техники', 'Лёгкий режим']} onChange={(mode) => updateLoadSettings({ mode })} />
              </div>
            </div>
            <div className="builder-dialog-actions">
              <Dialog.Close asChild><Button>Готово</Button></Dialog.Close>
            </div>
          </SafetyDialogContent>
        </Dialog.Portal>
      </Dialog.Root>

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

function StrengthModeSelector({ modes, selectedModeId, selectedDayType, onSelect }: { modes: StrengthTrainingMode[]; selectedModeId: string; selectedDayType?: string | null; onSelect: (modeId: string, dayType?: string | null) => void }) {
  if (modes.length === 0) {
    return null
  }

  const selectedMode = modes.find((mode) => mode.id === selectedModeId)

  return (
    <div className="rounded-[28px] border border-white/8 bg-white/4 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm uppercase tracking-[0.22em] text-white/35">Режим силовой тренировки</div>
          <div className="mt-2 font-display text-3xl font-bold text-white">Выберите структуру подходов</div>
        </div>
        <div className="rounded-[18px] border border-[#d6b05f]/18 bg-[#18140b] px-4 py-3 text-sm text-[#f2cf87]">
          {selectedMode?.title ?? 'Базовый режим'}
        </div>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {modes.map((mode) => {
          const active = mode.id === selectedModeId
          return (
            <button
              key={mode.id}
              type="button"
              onClick={() => onSelect(mode.id, mode.defaultDayType ?? null)}
              className={cn(
                'rounded-[24px] border p-4 text-left transition',
                active ? 'border-[#d6b05f]/35 bg-[#d6b05f]/12 text-white' : 'border-white/8 bg-[#0f1217] text-white/64 hover:border-white/16 hover:text-white',
              )}
            >
              <div className="font-display text-2xl font-bold text-white">{mode.title}</div>
              <div className="mt-2 text-sm leading-6">{mode.shortDescription}</div>
              <div className="mt-3 grid gap-2 text-xs text-white/45">
                <div><span className="text-white/70">Цель:</span> {mode.goal}</div>
                <div><span className="text-white/70">Сложность:</span> {mode.level}</div>
                <div><span className="text-white/70">Для кого:</span> {mode.audience}</div>
              </div>
              {mode.safetyNote ? <div className="mt-3 rounded-2xl border border-[#f0d08c]/20 bg-[#d6b05f]/8 px-3 py-2 text-xs text-[#f2cf87]">{mode.safetyNote}</div> : null}
            </button>
          )
        })}
      </div>

      {selectedMode?.dayOptions.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {selectedMode.dayOptions.map((option) => (
            <button
              key={option.id}
              type="button"
              onClick={() => onSelect(selectedMode.id, option.id)}
              className={cn(
                'rounded-full border px-4 py-2 text-sm transition',
                selectedDayType === option.id ? 'border-[#d6b05f]/35 bg-[#d6b05f]/14 text-[#f2cf87]' : 'border-white/8 bg-white/4 text-white/55 hover:text-white',
              )}
              title={option.description}
            >
              {option.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  )
}