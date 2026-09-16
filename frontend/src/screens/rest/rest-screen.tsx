import * as Dialog from '@radix-ui/react-dialog'
import { AlertTriangle, CheckCircle2, Plus, SkipForward, Square } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { RuntimeRestState, RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { getRuntimeInitOptions, withSearch } from '@/features/runtime/lib/runtime-query'
import { useHardwareStore } from '@/stores/hardware-store'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { FormaState } from '@/shared/ui/status/forma-state'
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
  const completeWorkout = useRuntimeStore((state) => state.completeWorkout)
  const snapshot = useHardwareStore((state) => state.snapshot)
  const hardwareError = useHardwareStore((state) => state.errorMessage)
  const runCommand = useHardwareStore((state) => state.runCommand)
  const autoAdvanceTriggeredRef = useRef(false)
  const [finishDialogOpen, setFinishDialogOpen] = useState(false)

  useEffect(() => {
    if (snapshot?.safety.state === 'emergency_stop') {
      setEmergencyStopActive(true)
    }
  }, [setEmergencyStopActive, snapshot?.safety.state])

  const activeSession = session
  const currentExercise = activeSession.exercises.find((item) => item.id === activeSession.currentExerciseId) ?? activeSession.exercises[0]
  const hasNextSet = activeSession.currentSetIndex < currentExercise.plan.length - 1
  const nextExercisePlan = hasNextSet ? currentExercise : activeSession.exercises[currentExercise.order]

  useEffect(() => {
    autoAdvanceTriggeredRef.current = false
  }, [activeSession.currentExerciseId, activeSession.currentSetIndex, rest.mode])

  useEffect(() => {
    if (rest.timerPaused || rest.remainingSeconds <= 0) {
      return
    }

    const timeoutId = window.setTimeout(() => {
      tickRestTimer()
    }, 1000)

    return () => window.clearTimeout(timeoutId)
  }, [rest.remainingSeconds, rest.timerPaused, tickRestTimer])

  useEffect(() => {
    if (rest.timerPaused || rest.remainingSeconds > 0 || autoAdvanceTriggeredRef.current) {
      return
    }

    autoAdvanceTriggeredRef.current = true
    void handleBeginNextStep()
  }, [rest.remainingSeconds, rest.timerPaused])

  async function handleBeginNextStep() {
    if (nextExercisePlan?.kind === 'machine' && selectedUserId) {
      await runCommand({
        action: 'start_motion',
        userId: selectedUserId,
        exerciseSlug: nextExercisePlan.slug,
        calibrationRequired: true,
        rangeConfirmed: true,
        weightKg: nextExercisePlan.loadSettings.weight,
        mode: 'machine',
        targetSet: hasNextSet ? activeSession.currentSetIndex + 2 : 1,
        targetReps: nextExercisePlan.plan[hasNextSet ? activeSession.currentSetIndex + 1 : 0]?.targetMaxReps ?? nextExercisePlan.plan[hasNextSet ? activeSession.currentSetIndex + 1 : 0]?.targetReps ?? nextExercisePlan.loadSettings.reps,
      })
    }

    beginNextStep()
    navigate(withSearch('/exercise-session', location.search))
  }

  const progressPercent = rest.totalSeconds > 0 ? Math.round(((rest.totalSeconds - rest.remainingSeconds) / rest.totalSeconds) * 100) : 100
  const nextTitle = rest.nextExercise?.name ?? (hasNextSet ? `${currentExercise.name} · подход ${activeSession.currentSetIndex + 2} из ${currentExercise.plan.length}` : 'Следующий подход')
  const nextTarget = rest.nextExercise?.target ?? 'повторить текущую нагрузку'
  const completedAmplitude = snapshot?.motion ? `${snapshot.motion.amplitudePercent}%` : rest.completedSet.amplitudePercent ? `${rest.completedSet.amplitudePercent}%` : null

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
        <header className="rt-header">
          <div className="rt-chips" style={{ justifyContent: 'flex-start' }} aria-label="Место в тренировке">
            <span className="rt-chip">Упражнение {currentExercise.order} из {activeSession.exercises.length}</span>
          </div>
          <div className="rt-title">
            <h1 className="font-display font-bold tracking-[-0.04em] text-white">{rest.title}</h1>
            <p><span>{rest.subtitle}</span></p>
          </div>
          <div className="rt-chips" aria-label="Завершённый подход">
            <span className="rt-chip" data-tone={rest.completedSet.actualValue >= rest.completedSet.plannedValue ? 'good' : 'warning'}>
              <CheckCircle2 aria-hidden="true" />
              Подход {rest.completedSet.setNumber}: {rest.completedSet.actualValue} из {rest.completedSet.plannedValue}
            </span>
          </div>
        </header>

        <section className="rt-rest-center" aria-label="Таймер отдыха">
          <div className="rt-rest-timer" role="timer" aria-live="off" aria-label={`Осталось ${rest.remainingSeconds} секунд`}>
            {formatTimer(rest.remainingSeconds)}
          </div>
          <div className="rt-progress rt-rest-progress" role="progressbar" aria-label="Прогресс отдыха" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progressPercent}>
            <div style={{ width: `${progressPercent}%` }} />
          </div>
          <div className="rt-rest-next">
            <span>Дальше</span>
            <strong>{nextTitle}</strong>
            <p>Цель: {nextTarget}{rest.nextExercise?.restLabel ? ` · отдых ${rest.nextExercise.restLabel}` : ''}</p>
          </div>
          <div className="rt-rest-facts">
            <span>План <strong>{rest.completedSet.plannedValue}</strong></span>
            <span>Факт <strong>{rest.completedSet.actualValue}</strong></span>
            {rest.completedSet.weightKg ? <span>Вес <strong>{rest.completedSet.weightKg} кг</strong></span> : null}
            <span>Темп <strong>{rest.completedSet.tempoLabel}</strong></span>
            {completedAmplitude ? <span>Амплитуда <strong>{completedAmplitude}</strong></span> : null}
          </div>
          {hardwareError ? (
            <div className="rt-alert" data-tone="danger" role="alert" style={{ width: 'min(100%, 48rem)' }}>
              <AlertTriangle aria-hidden="true" />
              <div>
                <strong>Ошибка тренажёра</strong>
                <p>{hardwareError}</p>
              </div>
              <span />
            </div>
          ) : null}
        </section>

        <div className="rt-rest-actions" role="group" aria-label="Действия во время отдыха">
          <Button variant="secondary" iconLeft={<Plus aria-hidden="true" />} onClick={() => adjustRestSeconds(30)}>
            +30 сек
          </Button>
          <Button iconLeft={<SkipForward aria-hidden="true" />} onClick={() => void handleBeginNextStep()}>
            Пропустить
          </Button>
          <Button variant="secondary" iconLeft={<Square aria-hidden="true" />} onClick={() => setFinishDialogOpen(true)}>
            Завершить тренировку
          </Button>
        </div>
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