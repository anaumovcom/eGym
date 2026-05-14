import { Activity, Gauge, PauseCircle, TimerReset } from 'lucide-react'
import { useEffect } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { getRuntimeInitOptions, withSearch } from '@/features/runtime/lib/runtime-query'
import { useHardwareStore } from '@/stores/hardware-store'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { SectionIntro } from '@/shared/ui/stage2/screen-components'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

function progressWidthClass(progressPercent: number) {
  if (progressPercent >= 75) {
    return 'w-[92%]'
  }

  if (progressPercent >= 50) {
    return 'w-[68%]'
  }

  if (progressPercent >= 25) {
    return 'w-[44%]'
  }

  return 'w-[18%]'
}

function motionBarHeightClass(value: number) {
  if (value >= 84) {
    return 'h-40'
  }

  if (value >= 78) {
    return 'h-36'
  }

  if (value >= 72) {
    return 'h-32'
  }

  if (value >= 68) {
    return 'h-28'
  }

  return 'h-24'
}

export function ExerciseSessionScreen() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const session = useRuntimeStore((state) => state.session)
  const ensureSession = useRuntimeStore((state) => state.ensureSession)
  const startExercise = useRuntimeStore((state) => state.startExercise)
  const finishCurrentSet = useRuntimeStore((state) => state.finishCurrentSet)
  const completeExercise = useRuntimeStore((state) => state.completeExercise)
  const completeWorkout = useRuntimeStore((state) => state.completeWorkout)
  const snapshot = useHardwareStore((state) => state.snapshot)
  const hardwareError = useHardwareStore((state) => state.errorMessage)
  const runCommand = useHardwareStore((state) => state.runCommand)

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

  useEffect(() => {
    if (snapshot?.safety.state === 'emergency_stop') {
      setEmergencyStopActive(true)
    }
  }, [setEmergencyStopActive, snapshot?.safety.state])

  if (!session || !session.sessionState) {
    return null
  }

  const exercise = session.exercises.find((item) => item.id === session.currentExerciseId) ?? session.exercises[0]
  const state = session.sessionState
  const liveMotion = exercise.kind === 'machine' ? snapshot?.motion : null
  const progressPercent = liveMotion
    ? Math.round((liveMotion.repetitionCount / Math.max(1, liveMotion.targetReps)) * 100)
    : Math.round(((state.setNumber - 1) / Math.max(1, state.totalSets)) * 100)
  const liveMetrics = liveMotion
    ? [
        { label: 'Повторы', value: `${liveMotion.repetitionCount}/${liveMotion.targetReps}`, tone: 'good' as const },
        { label: 'Амплитуда', value: `${liveMotion.amplitudePercent}%`, tone: liveMotion.amplitudePercent >= 70 ? 'good' as const : 'warning' as const },
        { label: 'Позиция', value: `${Math.round(liveMotion.barPositionMm)} мм`, tone: 'neutral' as const },
        { label: 'Синхронность', value: `${liveMotion.syncDeltaMm.toFixed(1)} мм`, tone: liveMotion.syncDeltaMm <= 5 ? 'good' as const : 'warning' as const },
      ]
    : state.metrics
  const liveMotionTrack = liveMotion
    ? {
        minLabel: `${Math.round(liveMotion.lowerBoundMm ?? 0)} мм`,
        currentLabel: `${Math.round(liveMotion.barPositionMm)} мм`,
        maxLabel: `${Math.round(liveMotion.upperBoundMm ?? 1400)} мм`,
        points: [20, 38, 56, liveMotion.amplitudePercent, 72, 52, 34, 18].map((value, index) => ({
          phase: index === 3 ? 'current' as const : index < 3 ? 'up' as const : 'down' as const,
          value,
        })),
      }
    : state.motionTrack

  async function handleFinishCurrentSet() {
    if (exercise.kind === 'machine' && selectedUserId) {
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

    finishCurrentSet()
    const nextView = useRuntimeStore.getState().session?.view
    navigate(withSearch(nextView === 'exercise-summary' ? '/exercise-summary' : '/rest', location.search))
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
        title={exercise.name}
        description={`Упражнение ${exercise.order} из ${session.exercises.length} · ${state.targetLabel}`}
        actions={
          <div className="rounded-[22px] border border-[#d6b05f]/18 bg-[#18140b] px-4 py-3 text-[#f2cf87]">
            Подход {state.setNumber} из {state.totalSets}
          </div>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <section className="glass-panel rounded-[34px] p-6 xl:p-8">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm uppercase tracking-[0.24em] text-white/35">Выполнение</div>
              <div className="mt-2 font-display text-6xl font-bold text-white">{state.kind === 'timed' ? `${state.currentValue} сек` : `${liveMotion?.repetitionCount ?? state.currentValue}`}</div>
              <div className="mt-2 text-xl text-white/45">{state.targetLabel}</div>
            </div>
            <div className="flex h-48 w-48 items-center justify-center rounded-full border border-[#d6b05f]/20 bg-[radial-gradient(circle_at_top,rgba(214,176,95,0.18),transparent_44%),linear-gradient(180deg,#171b22,#090c11)]">
              <div className="text-center">
                <div className="font-display text-5xl font-bold text-white">{state.kind === 'timed' ? `${state.currentValue}` : `${Math.min(100, 74 + progressPercent / 3)}%`}</div>
                <div className="mt-2 text-sm text-white/45">{state.kind === 'timed' ? 'удержание' : 'техника'}</div>
              </div>
            </div>
          </div>

          <div className="mt-6 h-3 overflow-hidden rounded-full bg-white/6">
            <div className={cn('h-full rounded-full bg-linear-to-r from-[#b5852f] via-[#d6b05f] to-[#f1d391]', progressWidthClass(progressPercent))} />
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {liveMetrics.map((metric) => (
              <div key={metric.label} className="rounded-[24px] border border-white/8 bg-white/4 p-4">
                <div className="text-sm text-white/45">{metric.label}</div>
                <div className={cn('mt-2 font-display text-3xl font-bold', metric.tone === 'good' ? 'text-[#92e09a]' : metric.tone === 'warning' ? 'text-[#f2cf87]' : 'text-white')}>
                  {metric.value}
                </div>
              </div>
            ))}
          </div>

          {hardwareError ? <div className="mt-6 rounded-[24px] border border-[#eb5345]/25 bg-[#1b0f10] px-5 py-4 text-sm text-[#ffb4a7]">{hardwareError}</div> : null}

          {liveMotionTrack ? (
            <div className="mt-6 rounded-[28px] border border-white/8 bg-white/4 p-5">
              <div className="flex items-center gap-3 text-white/45"><Gauge className="h-4 w-4" />Амплитуда движения</div>
              <div className="mt-5 flex items-end gap-2">
                {liveMotionTrack.points.map((point, index) => (
                  <div key={`${point.phase}-${index}`} className="flex-1">
                    <div className={cn('rounded-t-full', motionBarHeightClass(point.value), point.phase === 'current' ? 'bg-[#f2cf87]' : point.phase === 'up' ? 'bg-[#92e09a]' : 'bg-white/18')} />
                  </div>
                ))}
              </div>
              <div className="mt-3 flex items-center justify-between text-sm text-white/45">
                <span>{liveMotionTrack.minLabel}</span>
                <span>{liveMotionTrack.currentLabel}</span>
                <span>{liveMotionTrack.maxLabel}</span>
              </div>
            </div>
          ) : null}

          <div className="mt-6 flex flex-wrap gap-3">
            <Button
              iconLeft={<Activity className="h-4 w-4" />}
              onClick={() => void handleFinishCurrentSet()}
            >
              {state.kind === 'timed' ? 'Завершить интервал' : state.kind === 'group' ? 'Завершить шаг' : 'Завершить подход'}
            </Button>
            <Button
              variant="secondary"
              iconLeft={<PauseCircle className="h-4 w-4" />}
              onClick={() => {
                completeExercise('aborted')
                navigate(withSearch('/exercise-summary', location.search))
              }}
            >
              Завершить упражнение досрочно
            </Button>
          </div>
        </section>

        <aside className="space-y-6">
          <section className="glass-panel rounded-[32px] p-5">
            <div className="font-display text-3xl font-bold text-white">Подсказки в реальном времени</div>
            <div className="mt-4 space-y-3">
              {state.hints.map((hint) => (
                <div key={hint} className="rounded-[22px] border border-white/8 bg-white/4 px-4 py-3 text-white/74">{hint}</div>
              ))}
            </div>
          </section>

          {state.groupMeta ? (
            <section className="glass-panel rounded-[32px] p-5">
              <div className="font-display text-3xl font-bold text-white">Группа / суперсет</div>
              <div className="mt-4 rounded-[24px] border border-[#d6b05f]/18 bg-[#18140b] p-4 text-[#f2cf87]">
                <div>{state.groupMeta.groupName}</div>
                <div className="mt-2 text-sm">Круг {state.groupMeta.currentRound} из {state.groupMeta.totalRounds}</div>
                <div className="mt-1 text-sm">Следующий шаг: {state.groupMeta.nextStepLabel}</div>
              </div>
            </section>
          ) : null}

          <section className="glass-panel rounded-[32px] p-5">
            <div className="flex items-center gap-3 text-white/45"><TimerReset className="h-4 w-4" />Параметры</div>
            <div className="mt-4 space-y-3 text-sm text-white/72">
              <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Нагрузка</span><span>{state.weightLabel}</span></div>
              <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Режим</span><span>{exercise.loadSettings.mode}</span></div>
              <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Амплитуда</span><span>{exercise.movementRangeLabel}</span></div>
            </div>
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