import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Camera, Play, RotateCcw } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import type { StrengthTrainingMode } from '@/entities/strength/model/types'
import { buildBackendBuilderRuntimeSession } from '@/features/runtime/lib/backend-builder-session'
import { requiresMachineCalibration } from '@/features/runtime/lib/runtime-exercise'
import { getRuntimeInitOptions, withSearch } from '@/features/runtime/lib/runtime-query'
import { useHardwareStore } from '@/stores/hardware-store'
import { apiGet } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { WarningBanner } from '@/shared/ui/status/status-components'
import { CalibrationStatusBlock, ExerciseVideoPlayer, LoadSettingsControl, MuscleStatusList, SectionIntro } from '@/shared/ui/stage2/screen-components'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
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
  const initializeBackendSession = useRuntimeStore((state) => state.initializeBackendSession)
  const updateCalibrationState = useRuntimeStore((state) => state.updateCalibrationState)
  const updateLoadSettings = useRuntimeStore((state) => state.updateLoadSettings)
  const selectStrengthMode = useRuntimeStore((state) => state.selectStrengthMode)
  const openPhotoProgress = useRuntimeStore((state) => state.openPhotoProgress)
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

  const initOptions = useMemo(() => getRuntimeInitOptions(searchParams), [searchParams])
  const usesBackendBuilderSession = initOptions.source === 'builder' && Boolean(initOptions.programId)
  const hasMatchingRuntimeBuilderSession = usesBackendBuilderSession
    ? session?.source === 'builder' && session.programId === initOptions.programId && session.dataSource === 'backend' && (!initOptions.runId || session.runId === initOptions.runId)
    : true
  const { data: backendBuilderSession, error: backendBuilderSessionError } = useQuery({
    queryKey: ['runtime-builder-session', resolvedUserId, initOptions.programId, initOptions.runId, initOptions.photoMode, initOptions.calibrationState],
    queryFn: () => buildBackendBuilderRuntimeSession({
      userId: resolvedUserId,
      programId: initOptions.programId!,
      runId: initOptions.runId,
      photoMode: initOptions.photoMode,
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

    if (requiresMachineCalibration(exercise)) {
      return
    }

    startExercise()
    navigate(withSearch('/exercise-session', location.search), { replace: true })
  }, [exercise, location.search, navigate, session, startExercise])

  useEffect(() => {
    if (session?.view === 'photo-progress' && session.photoProgress.autoPrompt && !session.photoProgress.completed) {
      navigate(withSearch('/photo-progress', location.search), { replace: true })
    }
  }, [location.search, navigate, session])

  useEffect(() => {
    if (!exercise) {
      return
    }

    if (snapshot?.safety.state === 'emergency_stop') {
      setEmergencyStopActive(true)
    }

    if (!requiresMachineCalibration(exercise)) {
      updateCalibrationState('not-needed')
      return
    }

    if (!selectedUserId) {
      updateCalibrationState('missing')
      return
    }

    void loadCurrentCalibration(selectedUserId, exercise.slug)
      .then((calibration) => {
        updateCalibrationState(calibration ? 'saved' : 'missing')
      })
      .catch(() => {})
  }, [exercise, loadCurrentCalibration, selectedUserId, setEmergencyStopActive, snapshot?.safety.state, updateCalibrationState])

  useEffect(() => {
    if (!exercise || exercise.kind !== 'machine') {
      setCapturedLowerPointMm(null)
      setCapturedUpperPointMm(null)
      return
    }

    if (currentCalibration?.exerciseSlug === exercise.slug) {
      setCapturedLowerPointMm(currentCalibration.lowerPointMm)
      setCapturedUpperPointMm(currentCalibration.upperPointMm)
      return
    }

    setCapturedLowerPointMm(null)
    setCapturedUpperPointMm(null)
  }, [exercise?.kind, exercise?.slug])

  useEffect(() => {
    if (!exercise || exercise.kind !== 'machine') {
      return
    }

    if (!currentCalibration || currentCalibration.exerciseSlug !== exercise.slug) {
      return
    }

    setCapturedLowerPointMm(currentCalibration.lowerPointMm)
    setCapturedUpperPointMm(currentCalibration.upperPointMm)
  }, [currentCalibration, exercise?.kind, exercise?.slug])

  if (usesBackendBuilderSession && backendBuilderSessionError) {
    const message = backendBuilderSessionError instanceof Error ? backendBuilderSessionError.message : 'Проверьте доступность backend API.'
    return (
      <FormaShell userName={getUserName(selectedUserId)} machine={session?.machine ?? fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
        <WarningBanner title="Не удалось загрузить тренировку" description={message} />
      </FormaShell>
    )
  }

  if (!session || !exercise) {
    return null
  }

  const currentExercise = exercise
  const settings = exercise.loadSettings
  const currentStrengthMode = currentExercise.strengthMode ?? { id: 'basic', title: 'Базовый режим', dayType: null }
  const calibrationRequired = requiresMachineCalibration(currentExercise)
  const savedCalibration = currentCalibration?.exerciseSlug === currentExercise.slug ? currentCalibration : null
  const setupVideo = currentExercise.details.videos.find((video) => video.gender === 'male' && video.view === 'side')
    ?? currentExercise.details.videos[0]
    ?? (currentExercise.summary.previewVideoUrl
      ? { url: currentExercise.summary.previewVideoUrl, label: `${currentExercise.name} · превью` }
      : null)
  const startBlocked = calibrationRequired && (!savedCalibration || !selectedUserId)
  const livePositionMm = snapshot?.motion.barPositionMm ?? null
  const liveLowerBoundMm = snapshot?.motion.lowerBoundMm ?? null
  const liveUpperBoundMm = snapshot?.motion.upperBoundMm ?? null
  const lowerPointMm = capturedLowerPointMm ?? null
  const upperPointMm = capturedUpperPointMm ?? null
  const hasCompleteCalibrationRange = lowerPointMm != null && upperPointMm != null && upperPointMm > lowerPointMm
  const calibrationRangeLabel = calibrationRequired
    ? hasCompleteCalibrationRange
      ? formatRange(lowerPointMm, upperPointMm)
      : savedCalibration
        ? formatRange(savedCalibration.lowerPointMm, savedCalibration.upperPointMm)
        : currentExercise.movementRangeLabel
    : currentExercise.movementRangeLabel

  function resetCalibrationDraft() {
    if (savedCalibration) {
      setCapturedLowerPointMm(savedCalibration.lowerPointMm)
      setCapturedUpperPointMm(savedCalibration.upperPointMm)
      return
    }

    setCapturedLowerPointMm(null)
    setCapturedUpperPointMm(null)
  }

  function captureCalibrationPoint(point: 'lower' | 'upper') {
    if (livePositionMm == null) {
      setHardwareError('Нет данных о положении грифа. Проверьте подключение тренажёра и повторите попытку.')
      return
    }

    setHardwareError(null)

    if (point === 'lower') {
      setCapturedLowerPointMm(livePositionMm)
      return
    }

    setCapturedUpperPointMm(livePositionMm)
  }

  async function handleCalibrationSave() {
    if (!selectedUserId) {
      setHardwareError('Сначала выберите пользователя перед сохранением калибровки.')
      return
    }

    if (!hasCompleteCalibrationRange) {
      setHardwareError('Сначала зафиксируйте нижнюю и верхнюю точку амплитуды.')
      return
    }

    await saveCalibration({
      userId: selectedUserId,
      exerciseSlug: currentExercise.slug,
      lowerPointMm,
      upperPointMm,
      zeroPositionMm: Math.round((lowerPointMm + upperPointMm) / 2),
      movementRangeConfirmed: true,
      calibrationRequired: true,
    })
    setHardwareError(null)
    updateCalibrationState('saved')
  }

  async function handleCalibrationDelete() {
    if (savedCalibration) {
      await deleteCalibration(savedCalibration.id, selectedUserId)
    }
    setCapturedLowerPointMm(null)
    setCapturedUpperPointMm(null)
    updateCalibrationState('missing')
  }

  async function handleStartExercise() {
    if (calibrationRequired) {
      if (!selectedUserId) {
        setHardwareError('Для запуска тренажёрного упражнения нужно выбрать пользователя.')
        return
      }

      const safetyGate = await checkSafetyGate({
        userId: selectedUserId,
        exerciseSlug: currentExercise.slug,
        calibrationRequired: true,
        rangeConfirmed: true,
        weightKg: settings.weight,
        mode: 'machine',
      })

      if (!safetyGate.allowed) {
        return
      }

      await runCommand({
        action: 'start_motion',
        userId: selectedUserId,
        exerciseSlug: currentExercise.slug,
        calibrationRequired: true,
        rangeConfirmed: true,
        weightKg: settings.weight,
        mode: 'machine',
        targetSet: 1,
        targetReps: currentExercise.plan[0]?.targetMaxReps ?? currentExercise.plan[0]?.targetReps ?? settings.reps,
      })
    }

    startExercise()
    navigate(withSearch('/exercise-session', location.search))
  }

  return (
    <FormaShell
      userName={getUserName(selectedUserId)}
      machine={snapshot?.machine ?? session.machine}
      onStop={() => {
        void runCommand({ action: 'trigger_emergency_stop', userId: selectedUserId })
        setEmergencyStopActive(true)
      }}
    >
      <SectionIntro
        title="Настройка упражнения"
        description="Подтвердите параметры перед стартом, проверьте калибровку и при необходимости сделайте фотофиксацию перед упражнением."
        actions={
          <Button variant="ghost" iconLeft={<ArrowLeft className="h-4 w-4" />} onClick={() => navigate(-1)}>
            Назад
          </Button>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="glass-panel rounded-[34px] p-6 xl:p-8">
          <div className="text-sm uppercase tracking-[0.24em] text-white/35">Выбранное упражнение</div>
          <div className="mt-2 font-display text-5xl font-bold text-white">{exercise.name}</div>
          <div className="mt-2 text-2xl text-white/45">{exercise.secondaryName}</div>
          <div className="mt-5 flex flex-wrap gap-2">
            {exercise.muscles.map((item) => (
              <span key={item} className="inline-flex items-center rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/68">{item}</span>
            ))}
          </div>
          {setupVideo ? (
            <div className="mt-6 overflow-hidden rounded-[30px] border border-white/8">
              <ExerciseVideoPlayer videoUrl={setupVideo.url} videoLabel={setupVideo.label} wrapperClassName="rounded-[30px]" />
            </div>
          ) : null}
          <div className="mt-6 rounded-[30px] border border-white/8 bg-[radial-gradient(circle_at_top,rgba(214,176,95,0.18),transparent_35%),linear-gradient(180deg,#161b22,#0a0c0f)] p-6 text-white/62">
            {calibrationRequired
              ? 'Для тренажёрного упражнения важно проверить сохранённую амплитуду и только потом переходить к выполнению.'
              : exercise.kind === 'timed'
                ? 'Для упражнения на время калибровка не требуется. Важнее выбрать удобный режим и убедиться, что таймер вас не будет отвлекать.'
                : 'Для упражнения без тренажёра можно сразу переходить к выполнению. При желании сохраните фото до старта.'}
          </div>

          {session.photoProgress.completed ? <WarningBanner title="Фото сохранены" description="Фотофиксация перед тренировкой завершена, можно запускать упражнение." /> : null}
          {startBlocked ? <WarningBanner title="Нужна калибровка" description="Перед первым стартом переместите гриф в нижнюю и верхнюю безопасные точки, зафиксируйте их ниже и сохраните диапазон движения." /> : null}
          {hardwareError ? <WarningBanner title="Hardware API" description={hardwareError} /> : null}

          <div className="mt-6 space-y-5">
            <LoadSettingsControl
              settings={settings}
              onAdjustWeight={(delta) => updateLoadSettings({ weight: Math.max(0, settings.weight + delta) })}
              onAdjustSets={(delta) => updateLoadSettings({ sets: Math.max(1, settings.sets + delta) })}
              onAdjustReps={(delta) => updateLoadSettings({ reps: Math.max(1, settings.reps + delta) })}
              onAdjustRest={(delta) => updateLoadSettings({ restSeconds: Math.max(15, settings.restSeconds + delta) })}
              onModeChange={(mode) => updateLoadSettings({ mode })}
            />
            <StrengthModeSelector
              modes={strengthModes}
              selectedModeId={currentStrengthMode.id}
              selectedDayType={currentStrengthMode.dayType}
              onSelect={(modeId, dayType) => selectStrengthMode(modeId, dayType)}
            />
            <CalibrationStatusBlock calibration={settings.calibration} />
            {calibrationRequired ? (
              <div className="rounded-[28px] border border-[#d6b05f]/18 bg-[linear-gradient(180deg,rgba(214,176,95,0.10),rgba(255,255,255,0.02))] p-5 text-white">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="text-sm uppercase tracking-[0.22em] text-[#f2cf87]/70">Калибровка амплитуды</div>
                    <div className="mt-2 font-display text-3xl font-bold text-white">Зафиксируйте рабочий диапазон грифа</div>
                    <div className="mt-2 max-w-3xl text-sm leading-7 text-white/68">
                      Подведите гриф к нижней безопасной точке, нажмите кнопку фиксации, затем переместите его к верхней точке и сохраните диапазон. Если границы уже сохранены, их можно переснять или удалить.
                    </div>
                  </div>
                  <div className="rounded-[22px] border border-white/10 bg-black/20 px-4 py-3 text-right">
                    <div className="text-xs uppercase tracking-[0.2em] text-white/45">Диапазон</div>
                    <div className="mt-2 font-display text-3xl font-bold text-white">{calibrationRangeLabel}</div>
                  </div>
                </div>

                <div className="mt-5 grid gap-3 md:grid-cols-3">
                  <div className="rounded-[24px] border border-white/8 bg-white/4 px-4 py-4">
                    <div className="text-xs uppercase tracking-[0.2em] text-white/45">Текущая позиция</div>
                    <div className="mt-2 font-display text-3xl font-bold text-white">{formatMillimeters(livePositionMm)}</div>
                    <div className="mt-2 text-sm leading-6 text-white/58">Физически переместите гриф в нужную точку и затем зафиксируйте её кнопкой ниже.</div>
                  </div>
                  <div className="rounded-[24px] border border-white/8 bg-white/4 px-4 py-4">
                    <div className="text-xs uppercase tracking-[0.2em] text-white/45">Нижняя точка</div>
                    <div className="mt-2 font-display text-3xl font-bold text-white">{formatMillimeters(lowerPointMm)}</div>
                    <div className="mt-2 text-sm leading-6 text-white/58">Live-низ: {formatMillimeters(liveLowerBoundMm)}</div>
                  </div>
                  <div className="rounded-[24px] border border-white/8 bg-white/4 px-4 py-4">
                    <div className="text-xs uppercase tracking-[0.2em] text-white/45">Верхняя точка</div>
                    <div className="mt-2 font-display text-3xl font-bold text-white">{formatMillimeters(upperPointMm)}</div>
                    <div className="mt-2 text-sm leading-6 text-white/58">Live-верх: {formatMillimeters(liveUpperBoundMm)}</div>
                  </div>
                </div>

                <div className="mt-4 rounded-[24px] border border-white/8 bg-black/20 px-4 py-4 text-sm leading-7 text-white/68">
                  {hasCompleteCalibrationRange
                    ? 'Нижняя и верхняя точки зафиксированы. Теперь можно сохранить амплитуду и разблокировать старт упражнения.'
                    : 'Шаг 1: опустите гриф в нижнюю безопасную точку. Шаг 2: нажмите «Зафиксировать нижнюю точку». Шаг 3: переместите гриф в верхнюю точку и зафиксируйте её. Шаг 4: сохраните амплитуду.'}
                </div>

                <div className="mt-5 flex flex-wrap gap-3">
                  <Button variant="secondary" onClick={() => captureCalibrationPoint('lower')}>
                    Зафиксировать нижнюю точку
                  </Button>
                  <Button variant="secondary" onClick={() => captureCalibrationPoint('upper')}>
                    Зафиксировать верхнюю точку
                  </Button>
                  <Button disabled={!hasCompleteCalibrationRange} onClick={() => void handleCalibrationSave()}>
                    Сохранить амплитуду
                  </Button>
                  <Button variant="ghost" iconLeft={<RotateCcw className="h-4 w-4" />} onClick={resetCalibrationDraft}>
                    Сбросить точки
                  </Button>
                  {savedCalibration ? (
                    <Button variant="ghost" onClick={() => void handleCalibrationDelete()}>
                      Удалить калибровку
                    </Button>
                  ) : null}
                </div>
              </div>
            ) : null}
          </div>
        </section>

        <aside className="space-y-6">
          <section className="glass-panel rounded-[32px] p-5">
            <div className="font-display text-3xl font-bold text-white">Проверка совместимости</div>
            <div className="mt-4 rounded-[24px] border border-[#d6b05f]/18 bg-[#18140b] p-4 text-[#f2cf87]">
              <div className="font-semibold">{exercise.details.compatibility.title}</div>
              <div className="mt-2 text-sm leading-7">{exercise.details.compatibility.description}</div>
            </div>
            <div className="mt-4">
              <MuscleStatusList muscles={exercise.details.compatibility.affectedMuscles} />
            </div>
            <div className="mt-5 flex flex-col gap-3">
              <Button variant="secondary" iconLeft={<Camera className="h-4 w-4" />} onClick={() => {
                openPhotoProgress(session.photoProgress.mode === 'post-workout' ? 'manual' : session.photoProgress.mode || 'manual')
                navigate(withSearch('/photo-progress', location.search))
              }}>
                Фотофиксация
              </Button>
              <Button className="w-full" disabled={startBlocked} iconLeft={<Play className="h-4 w-4" />} onClick={() => void handleStartExercise()}>
                {startBlocked ? 'Старт недоступен' : 'Запустить упражнение'}
              </Button>
            </div>
          </section>

          <section className="glass-panel rounded-[32px] p-5">
            <div className="font-display text-3xl font-bold text-white">Текущий сценарий</div>
            <div className="mt-4 space-y-3 text-sm text-white/72">
              <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Источник</span><span>{session.source}</span></div>
              <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Режим</span><span>{exercise.kind}</span></div>
              <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Диапазон</span><span>{calibrationRangeLabel}</span></div>
            </div>
            <Button className="mt-5 w-full" variant="secondary" onClick={() => {
              completeWorkout('aborted')
              navigate(withSearch('/workout-summary', location.search))
            }}>
              Завершить тренировку сейчас
            </Button>
          </section>
        </aside>
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