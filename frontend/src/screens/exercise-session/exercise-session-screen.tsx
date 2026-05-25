import { Activity, Gauge, PauseCircle, TimerReset } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import type { HardwareMotionTelemetry } from '@/features/hardware/model/types'
import type { RuntimeExerciseSummaryState, RuntimeSetResult, RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { hasMovableMachineLoad } from '@/features/runtime/lib/runtime-exercise'
import { getRuntimeInitOptions, withSearch } from '@/features/runtime/lib/runtime-query'
import { getSetTypeLabel } from '@/features/strength/lib/strength-plan'
import { useHardwareStore } from '@/stores/hardware-store'
import { apiPost } from '@/shared/api/client'
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
  const replaceExerciseSummary = useRuntimeStore((state) => state.replaceExerciseSummary)
  const completeWorkout = useRuntimeStore((state) => state.completeWorkout)
  const snapshot = useHardwareStore((state) => state.snapshot)
  const hardwareError = useHardwareStore((state) => state.errorMessage)
  const runCommand = useHardwareStore((state) => state.runCommand)
  const lastRepCountRef = useRef<number | null>(null)
  const autoFinishTriggeredRef = useRef(false)
  const [actualReps, setActualReps] = useState(0)
  const [actualWeight, setActualWeight] = useState(0)
  const [rir, setRir] = useState(2)
  const [subjectiveEffort, setSubjectiveEffort] = useState(7)
  const [pain, setPain] = useState(false)
  const [techniqueBreakdown, setTechniqueBreakdown] = useState(false)
  const [setComment, setSetComment] = useState('')
  const [saveError, setSaveError] = useState<string | null>(null)

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

  const activeSession = session
  const exercise = activeSession.exercises.find((item) => item.id === activeSession.currentExerciseId) ?? activeSession.exercises[0]
  const state = session.sessionState
  const setPlan = exercise.plan[session.currentSetIndex] ?? exercise.plan[exercise.plan.length - 1]
  const liveMotion = hasMovableMachineLoad(exercise) ? snapshot?.motion : null
  const syncDeltaMm = liveMotion ? liveMotion.syncDeltaMm ?? Math.abs(liveMotion.leftPositionMm - liveMotion.rightPositionMm) : null
  const progressPercent = liveMotion
    ? Math.round((liveMotion.repetitionCount / Math.max(1, liveMotion.targetReps)) * 100)
    : Math.round(((state.setNumber - 1) / Math.max(1, state.totalSets)) * 100)
  const techniquePercent = state.kind === 'timed' ? state.currentValue : Math.round(Math.min(100, 74 + progressPercent / 3))
  const liveMetrics = liveMotion
    ? [
        { label: 'Повторы', value: `${liveMotion.repetitionCount}/${liveMotion.targetReps}`, tone: 'good' as const },
        { label: 'Амплитуда', value: `${liveMotion.amplitudePercent}%`, tone: liveMotion.amplitudePercent >= 70 ? 'good' as const : 'warning' as const },
        { label: 'Позиция', value: `${Math.round(liveMotion.barPositionMm)} мм`, tone: 'neutral' as const },
        { label: 'Синхронность', value: `${syncDeltaMm?.toFixed(1) ?? '0.0'} мм`, tone: (syncDeltaMm ?? 0) <= 5 ? 'good' as const : 'warning' as const },
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

  useEffect(() => {
    autoFinishTriggeredRef.current = false
    setSaveError(null)
    setActualReps(liveMotion?.repetitionCount ?? state.targetMaxReps ?? state.targetValue)
    setActualWeight(setPlan.recommendedWeightKg ?? parseWeightLabel(state.weightLabel))
    setRir(parseRirLabel(state.rirLabel))
    setSubjectiveEffort(state.setType === 'failure' ? 9 : 7)
    setPain(false)
    setTechniqueBreakdown(false)
    setSetComment('')
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
    if (!liveMotion || state.kind === 'timed') {
      return
    }

    if (autoFinishTriggeredRef.current) {
      return
    }

    if (liveMotion.repetitionCount < liveMotion.targetReps) {
      return
    }

    autoFinishTriggeredRef.current = true
    void handleFinishCurrentSet()
  }, [liveMotion, state.kind])

  async function handleFinishCurrentSet() {
    const result = buildCurrentSetResult({
      state,
      setPlan,
      liveMotion,
      actualReps,
      actualWeight,
      rir,
      subjectiveEffort,
      pain,
      techniqueBreakdown,
      setComment,
    })
    const completedForExercise = [...(activeSession.completedSets[exercise.id] ?? []), result]
    const isLastSet = activeSession.currentSetIndex >= exercise.plan.length - 1

    if (hasMovableMachineLoad(exercise) && selectedUserId) {
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

    finishCurrentSet(result)
    const nextView = useRuntimeStore.getState().session?.view

    if (isLastSet) {
      try {
        const summary = await saveExerciseResultToBackend(exercise, completedForExercise, selectedUserId ?? 'alexey')
        replaceExerciseSummary(summary)
      } catch (error) {
        setSaveError(error instanceof Error ? error.message : 'Не удалось сохранить результат упражнения на backend.')
      }
    }

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
        description={`Упражнение ${exercise.order} из ${session.exercises.length} · ${exercise.strengthMode.title} · ${state.targetLabel}`}
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
              <div className="mt-2 inline-flex rounded-full border border-[#d6b05f]/24 bg-[#d6b05f]/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] text-[#f2cf87]">{getSetTypeLabel(state.setType)}</div>
              <div className="mt-2 font-display text-6xl font-bold text-white">{state.kind === 'timed' ? `${state.currentValue} сек` : `${liveMotion?.repetitionCount ?? state.currentValue}`}</div>
              <div className="mt-2 text-xl text-white/45">{state.targetLabel}</div>
              <div className="mt-2 text-sm text-white/45">Рекомендуемый вес: {state.weightLabel} · отдых {setPlan.restSeconds} сек · {state.rirLabel ?? '1–3 в запасе'}</div>
            </div>
            <div className="flex h-48 w-48 items-center justify-center rounded-full border border-[#d6b05f]/20 bg-[radial-gradient(circle_at_top,rgba(214,176,95,0.18),transparent_44%),linear-gradient(180deg,#171b22,#090c11)]">
              <div className="text-center">
                <div className="font-display text-5xl font-bold text-white">{state.kind === 'timed' ? `${techniquePercent}` : `${techniquePercent}%`}</div>
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
          {saveError ? <div className="mt-6 rounded-[24px] border border-[#eb5345]/25 bg-[#1b0f10] px-5 py-4 text-sm text-[#ffb4a7]">{saveError}</div> : null}

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

          <div className="mt-6 rounded-[28px] border border-white/8 bg-white/4 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="text-sm uppercase tracking-[0.24em] text-white/35">Факт подхода</div>
                <div className="mt-2 text-sm text-white/55">Запишите фактический вес, повторы, запас и самочувствие перед переходом к отдыху.</div>
              </div>
              {state.setWarning ? <div className="rounded-2xl border border-[#f0d08c]/22 bg-[#d6b05f]/10 px-3 py-2 text-sm text-[#f2cf87]">{state.setWarning}</div> : null}
            </div>
            <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <SessionNumberControl label="Фактические повторы" value={actualReps} suffix="повт." min={0} onChange={setActualReps} />
              <SessionNumberControl label="Фактический вес" value={actualWeight} suffix="кг" min={0} step={1} onChange={setActualWeight} />
              <SessionNumberControl label="Повторы в запасе" value={rir} suffix="RIR" min={0} max={5} onChange={setRir} />
              <SessionNumberControl label="Тяжесть" value={subjectiveEffort} suffix="из 10" min={1} max={10} onChange={setSubjectiveEffort} />
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button type="button" onClick={() => setPain((value) => !value)} className={cn('rounded-full border px-4 py-2 text-sm transition', pain ? 'border-[#eb5345]/35 bg-[#eb5345]/12 text-[#ffb1a8]' : 'border-white/8 bg-white/4 text-white/55 hover:text-white')}>Была боль</button>
              <button type="button" onClick={() => setTechniqueBreakdown((value) => !value)} className={cn('rounded-full border px-4 py-2 text-sm transition', techniqueBreakdown ? 'border-[#f0d08c]/35 bg-[#d6b05f]/12 text-[#f2cf87]' : 'border-white/8 bg-white/4 text-white/55 hover:text-white')}>Техника ломалась</button>
            </div>
            <textarea
              value={setComment}
              onChange={(event) => setSetComment(event.target.value)}
              aria-label="Комментарий к фактическому подходу"
              title="Комментарий к фактическому подходу"
              placeholder="Комментарий к подходу"
              className="mt-4 min-h-20 w-full rounded-[22px] border border-white/8 bg-[#0f1217] px-4 py-3 text-sm text-white outline-none placeholder:text-white/24"
            />
          </div>

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
              <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Режим</span><span>{exercise.strengthMode.title}</span></div>
              <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Тип подхода</span><span>{getSetTypeLabel(state.setType)}</span></div>
              <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Цель</span><span>{state.targetLabel}</span></div>
              <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Нагрузка</span><span>{state.weightLabel}</span></div>
              <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Настройка</span><span>{exercise.loadSettings.mode}</span></div>
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

function parseWeightLabel(value: string) {
  return Number(value.replace(',', '.').match(/\d+(?:\.\d+)?/)?.[0] ?? '0')
}

function parseRirLabel(value?: string) {
  return Number(value?.match(/\d+/)?.[0] ?? '2')
}

function buildCurrentSetResult({ state, setPlan, liveMotion, actualReps, actualWeight, rir, subjectiveEffort, pain, techniqueBreakdown, setComment }: {
  state: NonNullable<RuntimeWorkoutSession['sessionState']>
  setPlan: RuntimeWorkoutSession['exercises'][number]['plan'][number]
  liveMotion: HardwareMotionTelemetry | null | undefined
  actualReps: number
  actualWeight: number
  rir: number
  subjectiveEffort: number
  pain: boolean
  techniqueBreakdown: boolean
  setComment: string
}): RuntimeSetResult {
  const actualValue = state.kind === 'timed' ? Math.max(0, actualReps || state.currentValue) : Math.max(0, actualReps)
  const weightKg = Math.max(0, actualWeight)

  return {
    setNumber: state.setNumber,
    plannedValue: state.targetMaxReps ?? state.targetValue,
    actualValue,
    setType: state.setType ?? setPlan.setType,
    targetMinReps: state.targetMinReps ?? setPlan.targetMinReps,
    targetMaxReps: state.targetMaxReps ?? setPlan.targetMaxReps ?? setPlan.targetReps,
    reps: state.kind === 'timed' ? null : actualValue,
    weightKg,
    rir,
    subjectiveEffort,
    discomfortLevel: pain ? 6 : 0,
    pain,
    techniqueBreakdown,
    comment: setComment.trim() || null,
    volumeKg: state.kind === 'timed' ? 0 : weightKg * actualValue,
    amplitudePercent: liveMotion?.amplitudePercent,
    tempoLabel: techniqueBreakdown ? 'техника просела' : 'хорошо',
    syncLabel: liveMotion ? `${(liveMotion.syncDeltaMm ?? Math.abs(liveMotion.leftPositionMm - liveMotion.rightPositionMm)).toFixed(1)} мм` : undefined,
  }
}

async function saveExerciseResultToBackend(exercise: RuntimeWorkoutSession['exercises'][number], completedSets: RuntimeSetResult[], userId: string) {
  return apiPost<RuntimeExerciseSummaryState>('/api/runtime/exercises', {
    userId,
    exerciseSlug: exercise.slug,
    exerciseName: exercise.name,
    exerciseSecondaryName: exercise.secondaryName,
    kind: exercise.kind,
    orderIndex: exercise.order,
    status: 'completed',
    startedAt: new Date(Date.now() - Math.max(completedSets.length, 1) * 90_000).toISOString(),
    finishedAt: new Date().toISOString(),
    calibrationState: exercise.calibrationState,
    targetSets: exercise.plan.length,
    trainingMode: exercise.strengthMode.id,
    trainingDayType: exercise.strengthMode.dayType,
    muscles: exercise.muscles.map((name, index) => ({ muscleId: name, name, role: index === 0 ? 'primary' : 'secondary' })),
    sets: completedSets.map((result) => ({
      setNumber: result.setNumber,
      plannedValue: result.plannedValue,
      actualValue: result.actualValue,
      setType: result.setType,
      targetMinReps: result.targetMinReps,
      targetMaxReps: result.targetMaxReps,
      reps: result.reps ?? result.actualValue,
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
      },
    })),
  })
}

function SessionNumberControl({ label, value, suffix, min, max, step = 1, onChange }: { label: string; value: number; suffix: string; min: number; max?: number; step?: number; onChange: (value: number) => void }) {
  function update(delta: number) {
    const next = value + delta * step
    onChange(Math.min(max ?? Number.POSITIVE_INFINITY, Math.max(min, next)))
  }

  return (
    <div className="rounded-[22px] border border-white/8 bg-[#0f1217] p-4">
      <div className="text-sm text-white/45">{label}</div>
      <div className="mt-3 flex items-center justify-between gap-3">
        <button type="button" onClick={() => update(-1)} className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/4 text-white/72">-</button>
        <div className="text-center">
          <div className="font-display text-3xl font-bold text-white">{value}</div>
          <div className="text-xs text-white/35">{suffix}</div>
        </div>
        <button type="button" onClick={() => update(1)} className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/4 text-white/72">+</button>
      </div>
    </div>
  )
}