import * as Dialog from '@radix-ui/react-dialog'
import { AlertTriangle, ArrowRight, Check, CheckCircle2, Pause, Play, Plus, Repeat2, Square } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { RuntimeRestState, RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { getRuntimeInitOptions, withSearch } from '@/features/runtime/lib/runtime-query'
import { supportsFixedBarSetup } from '@/features/runtime/lib/runtime-exercise'
import { WorkoutNavigator } from '@/features/runtime/ui/workout-navigator'
import { useHardwareStore } from '@/stores/hardware-store'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { FormaState } from '@/shared/ui/status/forma-state'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import { SetFeedback } from './set-feedback'

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

const fallbackMachine: MachineHealth = {
  machineState: 'ready',
  machineLabel: 'Тренажёр готов',
  leftDrive: 'connected',
  rightDrive: 'connected',
  safety: 'enabled',
  calibration: '—',
}

export function RestScreen() {
  const [searchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const session = useRuntimeStore((state) => state.session)
  const ensureSession = useRuntimeStore((state) => state.ensureSession)
  const snapshot = useHardwareStore((state) => state.snapshot)
  const initOptions = getRuntimeInitOptions(searchParams)

  useEffect(() => {
    if (!session) {
      ensureSession(initOptions)
    }
  }, [ensureSession, initOptions, session])

  if (!session || !session.restState) {
    return (
      <FormaShell userName={getUserName(selectedUserId)} machine={snapshot?.machine ?? session?.machine ?? fallbackMachine} hideNavigation onStop={() => setEmergencyStopActive(true)}>
        <FormaState tone="loading" title="Загружаем отдых…" />
      </FormaShell>
    )
  }

  return <RestView session={session} rest={session.restState} />
}

function RestView({ session, rest }: { session: RuntimeWorkoutSession; rest: RuntimeRestState }) {
  const navigate = useNavigate()
  const location = useLocation()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const beginNextStep = useRuntimeStore((state) => state.beginNextStep)
  const adjustRestSeconds = useRuntimeStore((state) => state.adjustRestSeconds)
  const tickRestTimer = useRuntimeStore((state) => state.tickRestTimer)
  const pauseRestTimer = useRuntimeStore((state) => state.pauseRestTimer)
  const completeWorkout = useRuntimeStore((state) => state.completeWorkout)
  const snapshot = useHardwareStore((state) => state.snapshot)
  const hardwareError = useHardwareStore((state) => state.errorMessage)
  const runCommand = useHardwareStore((state) => state.runCommand)
  const loadCurrentCalibration = useHardwareStore((state) => state.loadCurrentCalibration)
  const setHardwareError = useHardwareStore((state) => state.setErrorMessage)
  const autoAdvanceTriggeredRef = useRef(false)
  const beginNextStepPendingRef = useRef(false)
  const [startingNextStep, setStartingNextStep] = useState(false)
  const [finishDialogOpen, setFinishDialogOpen] = useState(false)
  const [navigatorOpen, setNavigatorOpen] = useState(false)

  useEffect(() => {
    if (snapshot?.safety.state === 'emergency_stop') {
      setEmergencyStopActive(true)
    }
  }, [setEmergencyStopActive, snapshot?.safety.state])

  const activeSession = session
  const currentExercise = activeSession.exercises.find((item) => item.id === activeSession.currentExerciseId) ?? activeSession.exercises[0]
  const hasNextSet = activeSession.currentSetIndex < currentExercise.plan.length - 1
  const nextExercisePlan = hasNextSet ? currentExercise : activeSession.exercises[currentExercise.order]
  const isSideChange = Boolean(currentExercise.perSide && currentExercise.plan[activeSession.currentSetIndex]?.side === 'left')
  const upcomingPlan = nextExercisePlan?.plan[hasNextSet ? activeSession.currentSetIndex + 1 : 0]
  const interactionBlocked = finishDialogOpen || emergencyStopActive || snapshot?.safety.state === 'emergency_stop' || navigatorOpen

  useEffect(() => {
    autoAdvanceTriggeredRef.current = false
  }, [activeSession.currentExerciseId, activeSession.currentSetIndex, rest.mode])

  useEffect(() => {
    if (rest.timerPaused || rest.remainingSeconds <= 0 || interactionBlocked || startingNextStep) {
      return
    }

    const timeoutId = window.setTimeout(() => {
      tickRestTimer()
    }, 1000)

    return () => window.clearTimeout(timeoutId)
  }, [interactionBlocked, rest.remainingSeconds, rest.timerPaused, startingNextStep, tickRestTimer])

  useEffect(() => {
    // While the workout plan is open the user is choosing where to go: the set does not start by itself.
    if (isSideChange || rest.timerPaused || rest.remainingSeconds > 0 || autoAdvanceTriggeredRef.current || interactionBlocked) {
      return
    }

    autoAdvanceTriggeredRef.current = true
    void handleBeginNextStep().then((started) => {
      if (!started) {
        // No automatic command retry loop: keep the rest screen available for an explicit retry.
        autoAdvanceTriggeredRef.current = false
        if (!useRuntimeStore.getState().session?.restState?.timerPaused) {
          pauseRestTimer()
        }
      }
    })
  }, [isSideChange, interactionBlocked, rest.remainingSeconds, rest.timerPaused])

  async function handleBeginNextStep() {
    if (beginNextStepPendingRef.current || interactionBlocked) return false
    beginNextStepPendingRef.current = true
    setStartingNextStep(true)
    try {
      return await startNextStep()
    } finally {
      beginNextStepPendingRef.current = false
      setStartingNextStep(false)
    }
  }

  async function startNextStep() {
    if (nextExercisePlan && supportsFixedBarSetup(nextExercisePlan)) {
      if (!selectedUserId) {
        setHardwareError('Для запуска упражнения нужно выбрать пользователя.')
        return false
      }
      try {
        const setup = await loadCurrentCalibration(selectedUserId, nextExercisePlan.slug)
        if (!setup) {
          setHardwareError('Настройка грифа не найдена. Откройте настройку упражнения.')
          return false
        }
        await runCommand({
          action: setup.setupType === 'fixed_position' ? 'start_fixed_position' : 'start_motion',
          userId: selectedUserId,
          exerciseSlug: nextExercisePlan.slug,
          calibrationRequired: true,
          rangeConfirmed: setup.setupType === 'bar_range',
          weightKg: nextExercisePlan.plan[hasNextSet ? activeSession.currentSetIndex + 1 : 0]?.recommendedWeightKg ?? nextExercisePlan.loadSettings.weight,
          mode: 'machine',
          targetSet: hasNextSet ? activeSession.currentSetIndex + 2 : 1,
          loadDirection: setup.loadDirection ?? 'down',
          targetReps: nextExercisePlan.plan[hasNextSet ? activeSession.currentSetIndex + 1 : 0]?.targetMaxReps ?? nextExercisePlan.plan[hasNextSet ? activeSession.currentSetIndex + 1 : 0]?.targetReps ?? nextExercisePlan.loadSettings.reps,
          ...(setup.setupType === 'fixed_position' ? { positionMm: setup.fixedPositionMm ?? undefined, repCountSource: 'load' } : {}),
        })
      } catch (error) {
        setHardwareError(error instanceof Error ? error.message : 'Не удалось запустить тренажёр.')
        return false
      }
    }

    beginNextStep()
    navigate(withSearch('/exercise-session', location.search))
    return true
  }

  const progressPercent = rest.totalSeconds > 0 ? Math.min(100, Math.max(0, Math.round(((rest.totalSeconds - rest.remainingSeconds) / rest.totalSeconds) * 100))) : 100
  const nextTitle = rest.nextExercise?.name ?? nextExercisePlan?.name ?? 'Следующий подход'
  const nextTarget = upcomingPlan?.targetSeconds != null ? `${upcomingPlan.targetSeconds} сек` : rest.nextExercise?.target ?? 'повторить текущую нагрузку'
  // Rest telemetry describes the idle machine, not the completed set.
  const completedAmplitude = rest.completedSet.amplitudePercent != null ? `${rest.completedSet.amplitudePercent}%` : null
  const nextWeight = upcomingPlan?.recommendedWeightKg ?? nextExercisePlan?.loadSettings.weight
  const resultUnit = currentExercise.kind === 'timed' || currentExercise.kind === 'stretch' ? 'сек' : 'повт.'
  const completedCount = Object.values(session.completedSets).flat().filter((set) => set.completionStatus !== 'skipped').length
  const totalCount = session.exercises.reduce((sum, exercise) => sum + exercise.plan.length, 0)
  const nextSetLabel = nextExercisePlan?.perSide && upcomingPlan?.side
    ? `Подход ${upcomingPlan.roundNumber} из ${nextExercisePlan.plan.length / 2} · ${upcomingPlan.side === 'left' ? 'Левая сторона' : 'Правая сторона'}`
    : `Подход ${hasNextSet ? activeSession.currentSetIndex + 2 : 1} из ${nextExercisePlan?.plan.length ?? 1}`
  const startLabel = startingNextStep ? 'Запускаем…' : isSideChange ? rest.nextActionLabel : hasNextSet ? 'Начать подход сейчас' : 'Начать упражнение'
  const timerStatus = startingNextStep ? 'Подготовка тренажёра' : isSideChange ? 'Без отсчёта' : interactionBlocked || rest.timerPaused ? 'Таймер на паузе' : 'До следующего подхода'

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
      <div className="rt-screen rt-rest">
        <header className="rt-rest-header">
          <div className="rt-title">
            <h1 className="font-display font-bold tracking-[-0.04em] text-white">{rest.title}</h1>
            <p>{currentExercise.name}</p>
          </div>
          <div className="rt-rest-workout" aria-label="Место в тренировке">
            <span>Упражнение {currentExercise.order} из {activeSession.exercises.length} · Выполнено {completedCount} из {totalCount} подходов{currentExercise.perSide ? ' по сторонам' : ''}</span>
            <div className="rt-chips">
              {activeSession.exercises.length > 1 ? <WorkoutNavigator session={activeSession} disabled={startingNextStep} onOpenChange={setNavigatorOpen} /> : null}
              <Button variant="ghost" disabled={startingNextStep} iconLeft={<Square aria-hidden="true" />} onClick={() => setFinishDialogOpen(true)}>
                Завершить тренировку
              </Button>
            </div>
          </div>
        </header>

        <div className="rt-rest-body">
          <section className="rt-rest-center" aria-label="Таймер отдыха" data-paused={rest.timerPaused || interactionBlocked}>
            <div className="rt-rest-dial" data-side-change={isSideChange}>
              {!isSideChange ? <svg className="rt-rest-ring" viewBox="0 0 240 240" role="progressbar" aria-label="Прогресс отдыха" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progressPercent}>
                <circle className="rt-rest-ring-track" cx="120" cy="120" r="110" />
                <circle className="rt-rest-ring-value" cx="120" cy="120" r="110" pathLength="100" strokeDasharray="100" strokeDashoffset={100 - progressPercent} />
              </svg> : null}
              <div className="rt-rest-dial-content">
                {isSideChange ? <Repeat2 className="rt-rest-side-icon" aria-hidden="true" /> : null}
                <span className="rt-rest-eyebrow" role="status">{timerStatus}</span>
                {isSideChange ? <strong className="rt-rest-side-title">Правая сторона</strong> : <div className="rt-rest-timer" role="timer" aria-live="off" aria-label={`Осталось ${rest.remainingSeconds} секунд`}>
                  {formatTimer(rest.remainingSeconds)}
                </div>}
                <span className="rt-rest-dial-caption">{isSideChange ? 'Продолжите, когда будете готовы' : `Отдых · ${rest.totalSeconds} сек`}</span>
              </div>
            </div>
            <p className="rt-rest-start-hint">{isSideChange ? 'Автозапуска нет. Смените сторону и нажмите кнопку начала.' : rest.timerPaused || interactionBlocked ? 'Отсчёт остановлен. Продолжите таймер или начните подход вручную.' : 'После отсчёта подход начнётся автоматически. Подготовьтесь к нагрузке.'}</p>
            {!isSideChange ? <div className="rt-rest-timer-controls">
              <Button variant="secondary" disabled={startingNextStep} iconLeft={rest.timerPaused ? <Play aria-hidden="true" /> : <Pause aria-hidden="true" />} onClick={pauseRestTimer}>
                {rest.timerPaused ? 'Продолжить таймер' : 'Пауза таймера'}
              </Button>
              <Button variant="secondary" disabled={startingNextStep} iconLeft={<Plus aria-hidden="true" />} onClick={() => adjustRestSeconds(30)}>+30 сек</Button>
            </div> : null}
          </section>

          <div className="rt-rest-details">
            <section className="rt-rest-next" aria-label="Следующее действие">
              <span className="rt-rest-eyebrow">{isSideChange ? 'Смена стороны' : hasNextSet ? 'Следующий подход' : 'Следующее упражнение'}</span>
              <h2>{nextTitle}</h2>
              <p className="rt-rest-set-label">{nextSetLabel}{upcomingPlan?.setType === 'warmup' ? ' · Разминка' : ''}</p>
              <div className="rt-rest-target">
                <div><span>Цель</span><strong>{nextTarget}</strong></div>
                {nextExercisePlan?.kind === 'machine' && nextWeight != null ? <div><span>Нагрузка</span><strong>{nextWeight} кг</strong></div> : null}
              </div>
              <div className="rt-rest-set-track" aria-label="Подходы текущего упражнения">
                {currentExercise.plan.map((plan, index) => {
                  const done = (session.completedSets[currentExercise.id] ?? []).some((set) => set.setNumber === index + 1 && set.completionStatus !== 'skipped')
                  const next = hasNextSet && index === activeSession.currentSetIndex + 1
                  return <span key={index} data-done={done} data-next={next} aria-label={`${plan.roundNumber ? `Подход ${plan.roundNumber} · ${plan.side === 'left' ? 'левая' : 'правая'} сторона` : `Подход ${index + 1}`}: ${done ? 'выполнен' : next ? 'следующий' : 'впереди'}`}>
                    {done ? <Check aria-hidden="true" /> : index + 1}
                  </span>
                })}
              </div>
              <p className="rt-rest-recommendation" role="note">{rest.recommendation}</p>
            </section>

            <section className="rt-rest-result" aria-label="Завершённый подход">
              <h2><CheckCircle2 aria-hidden="true" />Подход {rest.completedSet.roundNumber ?? rest.completedSet.setNumber} завершён{rest.completedSet.side ? ` · ${rest.completedSet.side === 'left' ? 'левая' : 'правая'} сторона` : ''}</h2>
              <dl className="rt-rest-facts">
                <div><dt>Результат</dt><dd>{rest.completedSet.actualValue} <small>/ {rest.completedSet.plannedValue} {resultUnit}</small></dd></div>
                {rest.completedSet.weightKg != null && rest.completedSet.weightKg > 0 ? <div><dt>Нагрузка</dt><dd>{rest.completedSet.weightKg} <small>кг</small></dd></div> : null}
                {completedAmplitude ? <div><dt>Амплитуда</dt><dd>{completedAmplitude}</dd></div> : null}
                <div><dt>Темп</dt><dd>{rest.completedSet.tempoLabel}</dd></div>
              </dl>
            </section>
            {session.dataSource === 'backend' && selectedUserId && rest.completedSet.backendSetId ?
              <SetFeedback key={`${session.id}:${selectedUserId}:${rest.completedSet.backendSetId}`} session={session} userId={selectedUserId} /> : null}
            {hardwareError ? (
              <div className="rt-alert" data-tone="danger" role="alert">
                <AlertTriangle aria-hidden="true" />
                <div><strong>Не удалось начать подход</strong><p>{hardwareError}</p><p>После устранения причины нажмите кнопку начала, чтобы повторить.</p></div>
              </div>
            ) : null}
          </div>
        </div>

        <footer className="rt-rest-actions" role="group" aria-label="Действия во время отдыха">
          <p>{isSideChange ? 'Сначала удобно расположитесь на другой стороне.' : 'Нужно больше времени? Добавьте 30 секунд или поставьте таймер на паузу.'}</p>
          <Button disabled={startingNextStep || interactionBlocked} onClick={() => void handleBeginNextStep()}>
            {startLabel}<ArrowRight aria-hidden="true" />
          </Button>
        </footer>
      </div>

      <Dialog.Root open={finishDialogOpen} onOpenChange={setFinishDialogOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
          <SafetyDialogContent className="builder-dialog">
            <Dialog.Title className="font-display text-3xl font-bold">Завершить тренировку сейчас?</Dialog.Title>
            <Dialog.Description className="mt-2 text-sm text-white/70">Выполненные подходы сохранятся, оставшиеся упражнения останутся незавершёнными.</Dialog.Description>
            <div className="builder-dialog-actions">
              <Dialog.Close asChild><Button variant="secondary">Продолжить отдых</Button></Dialog.Close>
              <Button
                onClick={() => {
                  setFinishDialogOpen(false)
                  completeWorkout('partial')
                  navigate(withSearch('/workout-summary', location.search))
                }}
              >
                Завершить тренировку
              </Button>
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

function formatTimer(totalSeconds: number) {
  const seconds = Math.max(0, totalSeconds)
  if (seconds < 60) {
    return <>{seconds}<small> сек</small></>
  }

  const minutes = Math.floor(seconds / 60)
  return <>{minutes}:{String(seconds % 60).padStart(2, '0')}</>
}