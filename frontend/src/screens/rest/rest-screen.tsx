import { Minus, PauseCircle, Plus } from 'lucide-react'
import { useEffect } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { getRuntimeInitOptions, withSearch } from '@/features/runtime/lib/runtime-query'
import { useHardwareStore } from '@/stores/hardware-store'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { SectionIntro } from '@/shared/ui/stage2/screen-components'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

export function RestScreen() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const session = useRuntimeStore((state) => state.session)
  const ensureSession = useRuntimeStore((state) => state.ensureSession)
  const beginNextStep = useRuntimeStore((state) => state.beginNextStep)
  const adjustRestSeconds = useRuntimeStore((state) => state.adjustRestSeconds)
  const pauseRestTimer = useRuntimeStore((state) => state.pauseRestTimer)
  const completeWorkout = useRuntimeStore((state) => state.completeWorkout)
  const snapshot = useHardwareStore((state) => state.snapshot)
  const hardwareError = useHardwareStore((state) => state.errorMessage)
  const runCommand = useHardwareStore((state) => state.runCommand)

  const initOptions = getRuntimeInitOptions(searchParams)

  useEffect(() => {
    if (!session) {
      ensureSession(initOptions)
    }
  }, [ensureSession, initOptions, session])

  useEffect(() => {
    if (snapshot?.safety.state === 'emergency_stop') {
      setEmergencyStopActive(true)
    }
  }, [setEmergencyStopActive, snapshot?.safety.state])

  if (!session || !session.restState) {
    return null
  }

  const activeSession = session
  const rest = session.restState
  const currentExercise = activeSession.exercises.find((item) => item.id === activeSession.currentExerciseId) ?? activeSession.exercises[0]
  const hasNextSet = activeSession.currentSetIndex < currentExercise.plan.length - 1
  const nextExercisePlan = hasNextSet ? currentExercise : activeSession.exercises[currentExercise.order]

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
        targetReps: nextExercisePlan.loadSettings.reps,
      })
    }

    beginNextStep()
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
      <SectionIntro title={rest.title} description={rest.subtitle} />

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <section className="glass-panel rounded-[34px] p-6 xl:p-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="text-sm uppercase tracking-[0.24em] text-white/35">Таймер отдыха</div>
              <div className="mt-3 font-display text-7xl font-bold text-white">{rest.remainingSeconds}с</div>
              <div className="mt-2 text-base text-white/55">Рекомендуемый отдых: {rest.totalSeconds} секунд</div>
            </div>
            <div className="flex gap-3">
              <button type="button" title="Уменьшить отдых на 15 секунд" aria-label="Уменьшить отдых на 15 секунд" onClick={() => adjustRestSeconds(-15)} className="inline-flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-white/4 text-white/72"><Minus className="h-4 w-4" /></button>
              <button type="button" title="Увеличить отдых на 15 секунд" aria-label="Увеличить отдых на 15 секунд" onClick={() => adjustRestSeconds(15)} className="inline-flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-white/4 text-white/72"><Plus className="h-4 w-4" /></button>
            </div>
          </div>

          <div className="mt-6 rounded-[28px] border border-white/8 bg-white/4 p-5">
            <div className="text-sm uppercase tracking-[0.24em] text-white/35">Завершённый подход</div>
            <div className="mt-4 grid gap-4 md:grid-cols-4">
              <Metric label="План" value={`${rest.completedSet.plannedValue}`} />
              <Metric label="Факт" value={`${rest.completedSet.actualValue}`} />
              <Metric label="Темп" value={rest.completedSet.tempoLabel} />
              <Metric label="Амплитуда" value={snapshot?.motion ? `${snapshot.motion.amplitudePercent}%` : rest.completedSet.amplitudePercent ? `${rest.completedSet.amplitudePercent}%` : '—'} />
            </div>
          </div>

          {hardwareError ? <div className="mt-6 rounded-[24px] border border-[#eb5345]/25 bg-[#1b0f10] px-5 py-4 text-sm text-[#ffb4a7]">{hardwareError}</div> : null}

          <div className="mt-6 flex flex-wrap gap-3">
            <Button iconLeft={<PauseCircle className="h-4 w-4" />} variant="secondary" onClick={pauseRestTimer}>
              Пауза таймера
            </Button>
            <Button onClick={() => void handleBeginNextStep()}>
              {rest.nextActionLabel}
            </Button>
          </div>
        </section>

        <aside className="space-y-6">
          <section className="glass-panel rounded-[32px] p-5">
            <div className="font-display text-3xl font-bold text-white">Что дальше</div>
            <div className="mt-4 rounded-[24px] border border-[#d6b05f]/18 bg-[#18140b] p-4 text-[#f2cf87]">
              <div className="font-semibold">{rest.nextExercise?.name ?? 'Следующий подход'}</div>
              <div className="mt-2 text-sm">Цель: {rest.nextExercise?.target ?? 'повторить текущую нагрузку'}</div>
              <div className="mt-1 text-sm">Отдых: {rest.nextExercise?.restLabel ?? `${rest.totalSeconds} сек`}</div>
            </div>
            <div className="mt-4 text-sm leading-7 text-white/65">{rest.recommendation}</div>
          </section>

          {snapshot?.motion ? (
            <section className="glass-panel rounded-[32px] p-5">
              <div className="font-display text-3xl font-bold text-white">Live hardware</div>
              <div className="mt-4 space-y-3 text-sm text-white/72">
                <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Позиция</span><span>{Math.round(snapshot.motion.barPositionMm)} мм</span></div>
                <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Синхронность</span><span>{(snapshot.motion.syncDeltaMm ?? Math.abs(snapshot.motion.leftPositionMm - snapshot.motion.rightPositionMm)).toFixed(1)} мм</span></div>
                <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Профиль</span><span>{snapshot.motion.motionProfile}</span></div>
              </div>
            </section>
          ) : null}
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

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[22px] border border-white/8 bg-[#0f1217] p-4">
      <div className="text-sm text-white/45">{label}</div>
      <div className="mt-2 font-display text-3xl font-bold text-white">{value}</div>
    </div>
  )
}