import { Activity, ArrowDown, Camera, CheckCircle2, ChevronRight, CircleDashed, Clock3, Dumbbell, Flame, House, Play, SkipForward, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import type { RuntimeWorkoutSummaryState } from '@/entities/runtime/model/types'
import { getRuntimeInitOptions, withSearch } from '@/features/runtime/lib/runtime-query'
import { adjustExerciseLoadOnBackend, resolveWorkoutSaveStatus, saveWorkoutToBackend } from '@/features/runtime/lib/runtime-persistence'
import type { LoadAdjustmentDirection, LoadAdjustmentResponse } from '@/features/runtime/lib/runtime-persistence'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { CompactBodyMapMini, SectionIntro } from '@/shared/ui/stage2/screen-components'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

export function WorkoutSummaryScreen() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const session = useRuntimeStore((state) => state.session)
  const ensureSession = useRuntimeStore((state) => state.ensureSession)
  const openPhotoProgress = useRuntimeStore((state) => state.openPhotoProgress)
  const replaceWorkoutSummary = useRuntimeStore((state) => state.replaceWorkoutSummary)
  const applyLoadAdjustment = useRuntimeStore((state) => state.applyLoadAdjustment)
  const resumeWorkoutExercise = useRuntimeStore((state) => state.resumeWorkoutExercise)
  const saveTriggeredRef = useRef(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [pendingAdjustment, setPendingAdjustment] = useState<string | null>(null)
  const [adjustmentResults, setAdjustmentResults] = useState<Record<string, LoadAdjustmentResponse>>({})

  const initOptions = getRuntimeInitOptions(searchParams)

  useEffect(() => {
    if (!session) {
      ensureSession(initOptions)
    }
  }, [ensureSession, initOptions, session])

  useEffect(() => {
    if (!session || session.backendWorkoutSaved || saveTriggeredRef.current) {
      return
    }

    saveTriggeredRef.current = true
    setSaveError(null)
    void saveWorkoutToBackend(session, selectedUserId ?? 'alexey', resolveWorkoutSaveStatus(session))
      .then((summary) => replaceWorkoutSummary(summary, true))
      .catch((error) => {
        saveTriggeredRef.current = false
        setSaveError(error instanceof Error ? error.message : 'Не удалось сохранить итог тренировки на backend.')
      })
  }, [replaceWorkoutSummary, selectedUserId, session])

  if (!session) {
    return null
  }

  const summary = session.workoutSummary
  const resumableExercises = summary.exercises.filter((exercise) => exercise.status !== 'done' && (exercise.remainingSetCount ?? exercise.plannedSetCount ?? 0) > 0)
  const totalFatigueScore = summary.muscleLoad.reduce((total, muscle) => total + muscle.score, 0)
  const highlightedMuscles = summary.muscleLoad.map((muscle) => muscle.name)

  async function handleAdjustLoad(exercise: RuntimeWorkoutSummaryState['exercises'][number], direction: LoadAdjustmentDirection) {
    if (!exercise.exerciseSlug || pendingAdjustment) {
      return
    }

    const key = `${exercise.exerciseSlug}:${direction}`
    setPendingAdjustment(key)
    setSaveError(null)

    try {
      const result = await adjustExerciseLoadOnBackend({
        userId: selectedUserId ?? 'alexey',
        exerciseSlug: exercise.exerciseSlug,
        direction,
        trainingMode: exercise.trainingMode,
        trainingDayType: exercise.trainingDayType,
        kind: exercise.kind,
        currentWeightKg: exercise.nextWeightKg ?? exercise.currentWeightKg,
        currentReps: exercise.nextReps ?? exercise.currentReps,
        currentSets: exercise.nextSets ?? exercise.currentSets,
        restSeconds: exercise.nextRestSeconds ?? exercise.restSeconds,
      })
      applyLoadAdjustment(exercise.exerciseSlug, result)
      setAdjustmentResults((current) => ({ ...current, [exercise.exerciseSlug!]: result }))
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'Не удалось изменить нагрузку на backend.')
    } finally {
      setPendingAdjustment(null)
    }
  }

  function handleResumeExercise(exerciseId: string | null | undefined) {
    if (!exerciseId) {
      return
    }

    const nextView = resumeWorkoutExercise(exerciseId)
    if (!nextView) {
      return
    }

    navigate(withSearch(nextView === 'exercise-session' ? '/exercise-session' : '/exercise-setup', location.search))
  }

  return (
    <FormaShell userName={getUserName(selectedUserId)} machine={session.machine} onStop={() => setEmergencyStopActive(true)}>
      <SectionIntro title={summary.title} description={summary.subtitle} />
      {saveError ? <div className="mb-5 rounded-[22px] border border-[#eb5345]/25 bg-[#1b0f10] px-4 py-3 text-sm text-[#ffb4a7]">{saveError}</div> : null}
      {resumableExercises.length > 0 ? (
        <div className="mb-5 rounded-[24px] border border-[#f0bf43]/20 bg-[#18140b] px-5 py-4 text-sm text-[#f2cf87]">
          Можно вернуться к незавершённым подходам и пропущенным упражнениям прямо из этого экрана.
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <section className="glass-panel rounded-[34px] p-6 xl:p-8">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            {summary.metrics.map((metric) => (
              <div key={metric.label} className="rounded-[24px] border border-white/8 bg-white/4 p-4">
                <div className="text-sm text-white/45">{metric.label}</div>
                <div className="mt-2 font-display text-3xl font-bold text-white">{metric.value}</div>
                <div className="mt-1 text-xs text-white/35">{metric.hint}</div>
              </div>
            ))}
          </div>

          <div className="mt-6 overflow-hidden rounded-[28px] border border-white/8">
            <div className="bg-white/4 px-4 py-3 text-sm uppercase tracking-[0.24em] text-white/35">Упражнения тренировки</div>
            <div className="space-y-4 p-4">
              {summary.exercises.map((exercise, index) => {
                const adjustedLoad = exercise.exerciseSlug ? adjustmentResults[exercise.exerciseSlug] : undefined
                const decreaseKey = `${exercise.exerciseSlug}:decrease`
                const increaseKey = `${exercise.exerciseSlug}:increase`
                const currentLoadLabel = exercise.currentLoad ?? '—'
                const nextLoadLabel = exercise.nextLoad ?? exercise.currentLoad ?? adjustedLoad?.loadLabel ?? '—'
                const statusBadge = getWorkoutStatusMeta(exercise.status)
                const cardToneClass = getWorkoutCardToneClass(exercise.status)
                const canResume = exercise.status !== 'done' && (exercise.remainingSetCount ?? 0) > 0
                const canAdjustLoad = Boolean(exercise.exerciseSlug) && exercise.status !== 'skipped'
                const resumeLabel = getResumeLabel(exercise)
                const showResultLine = !(exercise.status === 'skipped' && exercise.result === 'пропущено')
                const showInfoChips = Boolean(exercise.completedSetCount || canResume)
                const showLoadMetrics = exercise.status !== 'skipped' && Boolean(exercise.currentLoad || exercise.nextLoad || adjustedLoad)

                return (
                  <div
                    key={exercise.exerciseId ?? (exercise.exerciseSessionId != null ? `session-${exercise.exerciseSessionId}` : `${exercise.exerciseSlug ?? exercise.name}-${index}`)}
                    className={cn('rounded-[24px] border p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]', cardToneClass)}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start gap-3">
                          <div className={cn('mt-0.5 flex h-11 w-11 shrink-0 items-center justify-center rounded-[16px] border', statusBadge.iconClass)}>
                            <statusBadge.icon className="h-5 w-5" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="font-semibold text-white">{exercise.name}</div>
                            {showResultLine ? <div className="mt-1 text-sm text-white/45">{exercise.result}</div> : null}
                          </div>
                        </div>
                      </div>
                      <div className={cn('inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium', statusBadge.badgeClass)}>
                        <statusBadge.icon className="h-3.5 w-3.5" />
                        {statusBadge.label}
                      </div>
                    </div>

                    {showInfoChips ? (
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        {exercise.completedSetCount ? <InfoChip icon={Activity} label={`Сделано ${exercise.completedSetCount} из ${exercise.plannedSetCount ?? exercise.completedSetCount} подходов`} /> : null}
                        {canResume ? <InfoChip icon={Play} label={`Осталось ${exercise.remainingSetCount} подхода`} accent /> : null}
                      </div>
                    ) : null}

                    <div className={cn('grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end', showInfoChips ? 'mt-3' : 'mt-2')}>
                      <div>
                        {showLoadMetrics ? (
                          <div className="grid gap-2 sm:grid-cols-2">
                            <LoadMetric label="Текущая нагрузка" value={currentLoadLabel} tone="muted" />
                            <LoadMetric label="Нагрузка в следующий раз" value={nextLoadLabel} tone="accent" />
                          </div>
                        ) : null}
                        {showLoadMetrics && adjustedLoad ? <div className="mt-2 text-xs leading-6 text-white/40">{adjustedLoad.recommendation}</div> : null}
                      </div>

                      <div className="flex flex-wrap items-center justify-start gap-2 xl:justify-end">
                        {canResume ? (
                          <Button variant="secondary" iconLeft={<Play className="h-4 w-4" />} onClick={() => handleResumeExercise(exercise.exerciseId)}>
                            {resumeLabel}
                          </Button>
                        ) : null}
                        {canAdjustLoad ? (
                          <div className="flex flex-col items-stretch gap-2">
                            <Button variant="secondary" disabled={pendingAdjustment !== null} iconLeft={<Dumbbell className="h-4 w-4" />} onClick={() => void handleAdjustLoad(exercise, 'increase')}>
                              {pendingAdjustment === increaseKey ? 'Сохраняю…' : 'Повысить'}
                            </Button>
                            <Button variant="secondary" disabled={pendingAdjustment !== null} iconLeft={<ArrowDown className="h-4 w-4" />} onClick={() => void handleAdjustLoad(exercise, 'decrease')}>
                              {pendingAdjustment === decreaseKey ? 'Сохраняю…' : 'Снизить'}
                            </Button>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </section>

        <aside className="space-y-6">
          <section className="glass-panel rounded-[32px] p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 text-sm text-white/45"><Flame className="h-4 w-4 text-[#f08b2e]" />Усталость мышц</div>
                <div className="mt-2 font-display text-4xl font-bold text-white">{totalFatigueScore}</div>
              </div>
              <div className="rounded-full border border-white/8 bg-white/5 px-3 py-1 text-xs text-white/58">{summary.muscleLoad.length} мышц</div>
            </div>

            <div className="mt-4 rounded-[26px] border border-white/6 bg-[#0b1017]/72 p-3">
              <CompactBodyMapMini
                muscles={highlightedMuscles}
                label="Суммарная усталость мышц за выполненные подходы"
                className="rounded-[26px] border-white/6 bg-transparent p-0"
                figureContainerClassName="h-[220px] p-0"
                figureMarkupClassName="max-w-[112px]"
              />
            </div>

            <div className="mt-4 text-sm leading-6 text-white/55">
              Учитываются только фактически выполненные подходы. Пропущенные упражнения и не сделанные подходы в расчёт не входят.
            </div>

            <div className="mt-4 grid gap-2">
              {summary.muscleLoad.length > 0 ? summary.muscleLoad.map((muscle) => (
                <div key={muscle.name} className="rounded-[18px] border border-white/8 bg-white/4 px-3 py-3">
                  <div className="flex items-center justify-between gap-3 text-sm">
                    <span className="truncate text-white/78">{muscle.name}</span>
                    <span className={cn('rounded-full px-2 py-0.5 text-xs font-medium', getFatigueToneClass(muscle.status))}>{muscle.score}</span>
                  </div>
                  <div className="mt-2 h-2 rounded-full bg-white/8">
                    <div className={cn('h-full rounded-full transition-all', getFatigueBarClass(muscle.status), getFatigueWidthClass(muscle.score))} />
                  </div>
                </div>
              )) : (
                <div className="rounded-[18px] border border-white/8 bg-white/4 px-3 py-4 text-sm text-white/45">
                  Пока нет выполненных подходов, которые создают заметную усталость мышц.
                </div>
              )}
            </div>
          </section>

          <section className="glass-panel rounded-[32px] p-5">
            <div className="flex items-center gap-3 text-[#f2cf87]"><Sparkles className="h-5 w-5" />Следующий шаг</div>
            <div className="mt-3 text-sm leading-7 text-white/65">{summary.recommendation}</div>
            <div className="mt-4 rounded-[24px] border border-white/8 bg-white/4 px-4 py-4 text-white/72">{summary.nextWorkout}</div>
            <div className="mt-5 flex flex-col gap-3">
              <Button
                iconLeft={<Camera className="h-4 w-4" />}
                onClick={() => {
                  openPhotoProgress('post-workout')
                  navigate(withSearch('/photo-progress', location.search))
                }}
              >
                Фото после тренировки
              </Button>
              <Button variant="secondary" iconLeft={<ChevronRight className="h-4 w-4" />} onClick={() => navigate('/today')}>
                Открыть план на сегодня
              </Button>
              <Button variant="secondary" iconLeft={<House className="h-4 w-4" />} onClick={() => navigate('/dashboard')}>
                На дашборд
              </Button>
            </div>
          </section>
        </aside>
      </div>

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}

function LoadMetric({ label, value, tone }: { label: string; value: string; tone: 'muted' | 'accent' }) {
  return (
    <div className={cn('rounded-[18px] border px-3 py-3 text-xs', tone === 'accent' ? 'border-[#d6b05f]/22 bg-[#18140b] text-[#f2cf87]' : 'border-white/8 bg-white/4 text-white/68')}>
      <div className="text-[10px] uppercase tracking-[0.18em] text-white/40">{label}</div>
      <div className="mt-1 text-sm font-semibold">{value}</div>
    </div>
  )
}

function InfoChip({ icon: Icon, label, accent = false }: { icon: typeof Activity; label: string; accent?: boolean }) {
  return (
    <div className={cn('inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs', accent ? 'border-[#d6b05f]/20 bg-[#18140b] text-[#f2cf87]' : 'border-white/8 bg-white/4 text-white/55')}>
      <Icon className="h-3.5 w-3.5" />
      {label}
    </div>
  )
}

function getWorkoutStatusMeta(status: RuntimeWorkoutSummaryState['exercises'][number]['status']) {
  if (status === 'done') {
    return {
      label: 'Выполнено',
      icon: CheckCircle2,
      badgeClass: 'border-[#57c968]/18 bg-[#122b1d] text-[#92e09a]',
      iconClass: 'border-[#57c968]/20 bg-[#122b1d] text-[#92e09a]',
    }
  }

  if (status === 'partial') {
    return {
      label: 'Не закончено',
      icon: CircleDashed,
      badgeClass: 'border-[#f0bf43]/18 bg-[#18140b] text-[#f2cf87]',
      iconClass: 'border-[#f0bf43]/18 bg-[#18140b] text-[#f2cf87]',
    }
  }

  if (status === 'skipped') {
    return {
      label: 'Пропущено',
      icon: SkipForward,
      badgeClass: 'border-[#eb5345]/18 bg-[#1b0f10] text-[#ffb4a7]',
      iconClass: 'border-[#eb5345]/18 bg-[#1b0f10] text-[#ffb4a7]',
    }
  }

  return {
    label: 'Не начато',
    icon: Clock3,
    badgeClass: 'border-white/10 bg-white/4 text-white/60',
    iconClass: 'border-white/10 bg-white/4 text-white/60',
  }
}

function getWorkoutCardToneClass(status: RuntimeWorkoutSummaryState['exercises'][number]['status']) {
  if (status === 'done') {
    return 'border-[#57c968]/18 bg-[#12201a]/90'
  }

  if (status === 'partial') {
    return 'border-[#f0bf43]/18 bg-[#21180c]/90'
  }

  if (status === 'skipped') {
    return 'border-[#eb5345]/18 bg-[#241113]/90'
  }

  return 'border-white/8 bg-[#0f151c]/86'
}

function getResumeLabel(exercise: RuntimeWorkoutSummaryState['exercises'][number]) {
  if (exercise.status === 'skipped' || (exercise.completedSetCount ?? 0) === 0) {
    return 'Выполнить упражнение'
  }

  const remaining = exercise.remainingSetCount ?? 0
  return remaining > 1 ? `Доделать ${remaining} подхода` : 'Доделать подход'
}

function getFatigueToneClass(status: 'ready' | 'light' | 'medium' | 'high' | 'critical' | 'no_data') {
  return {
    ready: 'bg-[#163720] text-[#9ef0a8]',
    light: 'bg-[#2e3316] text-[#dfe890]',
    medium: 'bg-[#3a2b14] text-[#f2cf87]',
    high: 'bg-[#3a2014] text-[#f5b17e]',
    critical: 'bg-[#3a1816] text-[#ffb4a7]',
    no_data: 'bg-white/8 text-white/45',
  }[status]
}

function getFatigueBarClass(status: 'ready' | 'light' | 'medium' | 'high' | 'critical' | 'no_data') {
  return {
    ready: 'bg-[#57c968]',
    light: 'bg-[#b9d94b]',
    medium: 'bg-[#f0bf43]',
    high: 'bg-[#f08b2e]',
    critical: 'bg-[#eb5345]',
    no_data: 'bg-white/20',
  }[status]
}

function getFatigueWidthClass(score: number) {
  if (score >= 95) {
    return 'w-full'
  }

  if (score >= 85) {
    return 'w-11/12'
  }

  if (score >= 75) {
    return 'w-10/12'
  }

  if (score >= 65) {
    return 'w-8/12'
  }

  if (score >= 55) {
    return 'w-7/12'
  }

  if (score >= 45) {
    return 'w-6/12'
  }

  if (score >= 35) {
    return 'w-5/12'
  }

  if (score >= 25) {
    return 'w-4/12'
  }

  if (score >= 15) {
    return 'w-3/12'
  }

  if (score >= 8) {
    return 'w-2/12'
  }

  return 'w-1/12'
}