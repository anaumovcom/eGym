import * as Dialog from '@radix-ui/react-dialog'
import { ArrowDown, CheckCircle2, CircleDashed, Clock3, Dumbbell, Flame, House, ListChecks, Play, SkipForward, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { RuntimeWorkoutSummaryState } from '@/entities/runtime/model/types'
import { getRuntimeInitOptions, withSearch } from '@/features/runtime/lib/runtime-query'
import { adjustExerciseLoadOnBackend, resolveWorkoutSaveStatus, saveWorkoutToBackend } from '@/features/runtime/lib/runtime-persistence'
import { captureRuntimeLifecycle, coachLifecycle } from '@/features/coach/lib/runtime-observation'
import type { LoadAdjustmentDirection, LoadAdjustmentResponse } from '@/features/runtime/lib/runtime-persistence'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { FormaState } from '@/shared/ui/status/forma-state'
import { CompactBodyMapMini } from '@/shared/ui/stage2/screen-components'
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

export function WorkoutSummaryScreen() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const session = useRuntimeStore((state) => state.session)
  const ensureSession = useRuntimeStore((state) => state.ensureSession)
  const replaceWorkoutSummary = useRuntimeStore((state) => state.replaceWorkoutSummary)
  const applyLoadAdjustment = useRuntimeStore((state) => state.applyLoadAdjustment)
  const resumeWorkoutExercise = useRuntimeStore((state) => state.resumeWorkoutExercise)
  const saveTriggeredRef = useRef(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [pendingAdjustment, setPendingAdjustment] = useState<string | null>(null)
  const [adjustmentResults, setAdjustmentResults] = useState<Record<string, LoadAdjustmentResponse>>({})
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [retryToken, setRetryToken] = useState(0)

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
    const coachCapture = captureRuntimeLifecycle(session, selectedUserId, true)
    void saveWorkoutToBackend(session, selectedUserId ?? 'alexey', resolveWorkoutSaveStatus(session))
      .then((summary) => {
        coachLifecycle.publish(coachCapture, 'workout_finalized', { outcome: summary.outcome, backendWorkoutId: summary.workoutSessionId })
        replaceWorkoutSummary(summary, true)
      })
      .catch((error) => {
        saveTriggeredRef.current = false
        setSaveError(error instanceof Error ? error.message : 'Не удалось сохранить итог тренировки. Попробуйте ещё раз.')
      })
  }, [replaceWorkoutSummary, retryToken, selectedUserId, session])

  if (!session) {
    return (
      <FormaShell userName={getUserName(selectedUserId)} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
        <FormaState tone="loading" title="Считаем итог тренировки…" />
      </FormaShell>
    )
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
      setSaveError(error instanceof Error ? error.message : 'Не удалось изменить нагрузку. Попробуйте ещё раз.')
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

  const outcomeTone = summary.outcome === 'aborted' ? 'aborted' : summary.outcome === 'partial' ? 'partial' : 'done'
  const outcomeLabel = summary.outcome === 'aborted' ? 'Тренировка прервана' : summary.outcome === 'partial' ? 'Завершена частично' : 'Тренировка выполнена'
  const doneCount = summary.exercises.filter((exercise) => exercise.status === 'done').length
  const primaryMetrics = summary.metrics.slice(0, 4)

  return (
    <FormaShell userName={getUserName(selectedUserId)} machine={session.machine} onStop={() => setEmergencyStopActive(true)}>
      <div className="rt-screen">
        <header className="rt-header">
          <div className="rt-chips" style={{ justifyContent: 'flex-start' }} aria-label="Тренировка">
            <span className="rt-chip">{session.workoutTitle}</span>
          </div>
          <div className="rt-title">
            <h1 className="font-display font-bold tracking-[-0.04em] text-white">{summary.title}</h1>
            <p><span>{summary.subtitle}</span></p>
          </div>
          <div className="rt-chips" aria-label="Итог тренировки">
            <span className="rt-outcome-badge" data-tone={outcomeTone}>
              {outcomeTone === 'done' ? <CheckCircle2 aria-hidden="true" /> : <CircleDashed aria-hidden="true" />}
              {outcomeLabel} · {doneCount} из {summary.exercises.length}
            </span>
          </div>
        </header>

        <div className="rt-body rt-summary-body">
          <div className="rt-summary-metrics" role="list" aria-label="Итоги тренировки">
            {primaryMetrics.map((metric) => (
              <article key={metric.label} role="listitem">
                <span>{metric.label}</span>
                <strong>{metric.value}</strong>
                <small>{metric.hint}</small>
              </article>
            ))}
          </div>

          {saveError ? (
            <div className="rt-alert" data-tone="danger" role="alert">
              <CircleDashed aria-hidden="true" />
              <div>
                <strong>Не удалось сохранить</strong>
                <p>{saveError}</p>
              </div>
              <Button variant="secondary" onClick={() => { setSaveError(null); saveTriggeredRef.current = false; setRetryToken((current) => current + 1) }}>Повторить</Button>
            </div>
          ) : (
            <div className="rt-alert" role="note">
              <Sparkles aria-hidden="true" />
              <div>
                <strong>{summary.nextWorkout}</strong>
                <p>{summary.recommendation}</p>
              </div>
              <span />
            </div>
          )}

          {resumableExercises.length > 0 ? (
            <section className="rt-summary-list" aria-label="Незавершённые упражнения">
              {resumableExercises.map((exercise, index) => {
                const statusMeta = getWorkoutStatusMeta(exercise.status)
                return (
                  <div key={exercise.exerciseId ?? `${exercise.exerciseSlug ?? exercise.name}-${index}`} className="rt-summary-item" data-status={exercise.status}>
                    <div className="rt-summary-item-icon" aria-hidden="true"><statusMeta.icon /></div>
                    <div className="rt-summary-item-body">
                      <strong>{exercise.name}</strong>
                      <span>{statusMeta.label} · осталось {exercise.remainingSetCount} {pluralizeSets(exercise.remainingSetCount ?? 0)}</span>
                    </div>
                    <div className="rt-summary-item-actions">
                      <Button variant="secondary" iconLeft={<Play aria-hidden="true" />} onClick={() => handleResumeExercise(exercise.exerciseId)}>
                        {getResumeLabel(exercise)}
                      </Button>
                    </div>
                  </div>
                )
              })}
            </section>
          ) : null}
        </div>

        <div className="rt-actions" role="group" aria-label="Действия после тренировки">
          <div className="rt-actions-group">
            <Button variant="secondary" iconLeft={<ListChecks aria-hidden="true" />} onClick={() => setDetailsOpen(true)}>
              Подробно
            </Button>
            <Button variant="secondary" iconLeft={<Flame aria-hidden="true" />} onClick={() => navigate('/fatigue')}>
              Усталость и восстановление
            </Button>
          </div>
          <div className="rt-actions-note">
            {session.backendWorkoutSaved ? 'Результат сохранён в календаре' : saveError ? 'Результат пока не сохранён' : 'Сохраняем результат…'}
          </div>
          <Button className="rt-primary" iconLeft={<House aria-hidden="true" />} onClick={() => navigate('/dashboard')}>
            На главную
          </Button>
        </div>
      </div>

      <Dialog.Root open={detailsOpen} onOpenChange={setDetailsOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
          <SafetyDialogContent className="rt-details-panel">
            <Dialog.Title className="font-display text-3xl font-bold">Подробно: {summary.title}</Dialog.Title>
            <Dialog.Description className="mt-2 text-sm text-white/70">Упражнения, нагрузка на следующий раз и усталость мышц по выполненным подходам.</Dialog.Description>
            <div className="rt-details-body">
              <section aria-label="Упражнения тренировки">
                <h3>Упражнения</h3>
                <div className="rt-summary-list" style={{ overflow: 'visible' }}>
                  {summary.exercises.map((exercise, index) => {
                    const adjustedLoad = exercise.exerciseSlug ? adjustmentResults[exercise.exerciseSlug] : undefined
                    const statusMeta = getWorkoutStatusMeta(exercise.status)
                    const canAdjustLoad = Boolean(exercise.exerciseSlug) && exercise.status !== 'skipped'
                    const nextLoadLabel = exercise.nextLoad ?? exercise.currentLoad ?? adjustedLoad?.loadLabel
                    return (
                      <div key={exercise.exerciseId ?? (exercise.exerciseSessionId != null ? `session-${exercise.exerciseSessionId}` : `${exercise.exerciseSlug ?? exercise.name}-${index}`)} className="rt-summary-item" data-status={exercise.status}>
                        <div className="rt-summary-item-icon" aria-hidden="true"><statusMeta.icon /></div>
                        <div className="rt-summary-item-body">
                          <strong>{exercise.name}</strong>
                          <span>{statusMeta.label}{exercise.result && exercise.result !== 'пропущено' ? ` · ${exercise.result}` : ''}</span>
                          {exercise.status !== 'skipped' && (exercise.currentLoad || nextLoadLabel) ? <span>Сейчас: {exercise.currentLoad ?? '—'} · В следующий раз: {nextLoadLabel ?? '—'}</span> : null}
                          {adjustedLoad ? <span>{adjustedLoad.recommendation}</span> : null}
                        </div>
                        <div className="rt-summary-item-actions">
                          {canAdjustLoad ? (
                            <>
                              <Button variant="secondary" disabled={pendingAdjustment !== null} iconLeft={<ArrowDown aria-hidden="true" />} onClick={() => void handleAdjustLoad(exercise, 'decrease')}>
                                {pendingAdjustment === `${exercise.exerciseSlug}:decrease` ? 'Сохраняю…' : 'Снизить'}
                              </Button>
                              <Button variant="secondary" disabled={pendingAdjustment !== null} iconLeft={<Dumbbell aria-hidden="true" />} onClick={() => void handleAdjustLoad(exercise, 'increase')}>
                                {pendingAdjustment === `${exercise.exerciseSlug}:increase` ? 'Сохраняю…' : 'Повысить'}
                              </Button>
                            </>
                          ) : null}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </section>
              <section aria-label="Усталость мышц">
                <h3>Усталость мышц · {totalFatigueScore}</h3>
                <div className="rt-muscle-load">
                  <CompactBodyMapMini
                    muscles={highlightedMuscles}
                    label="Суммарная усталость мышц за выполненные подходы"
                    className="rounded-[var(--ui-radius)] border-white/6 bg-[#0b1017] p-2"
                    figureContainerClassName="h-[240px] p-0"
                    figureMarkupClassName="max-w-[120px]"
                  />
                  <div className="rt-muscle-list">
                    {summary.muscleLoad.length > 0 ? summary.muscleLoad.map((muscle) => (
                      <div key={muscle.name} data-tone={muscle.status} style={{ ['--recovery-tone' as string]: getFatigueColor(muscle.status) }}>
                        <span>{muscle.name}</span>
                        <strong>{muscle.score}</strong>
                        <div><div style={{ width: `${Math.max(4, Math.min(100, muscle.score))}%` }} /></div>
                      </div>
                    )) : <p className="text-sm text-white/60">Пока нет выполненных подходов, которые создают заметную усталость мышц.</p>}
                  </div>
                </div>
                <p className="mt-3 text-sm text-white/60">Учитываются только фактически выполненные подходы. Пропущенные упражнения и не сделанные подходы в расчёт не входят.</p>
              </section>
            </div>
            <div className="builder-dialog-actions">
              <Dialog.Close asChild><Button>Закрыть</Button></Dialog.Close>
            </div>
          </SafetyDialogContent>
        </Dialog.Portal>
      </Dialog.Root>

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}

function pluralizeSets(count: number) {
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return 'подход'
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'подхода'
  return 'подходов'
}

function getFatigueColor(status: 'ready' | 'light' | 'medium' | 'high' | 'critical' | 'no_data') {
  return {
    ready: '#57c968',
    light: '#b9d94b',
    medium: '#f0bf43',
    high: '#f08b2e',
    critical: '#eb5345',
    no_data: '#8793a6',
  }[status]
}

function getWorkoutStatusMeta(status: RuntimeWorkoutSummaryState['exercises'][number]['status']) {
  if (status === 'done') {
    return { label: 'Выполнено', icon: CheckCircle2 }
  }

  if (status === 'partial') {
    return { label: 'Не закончено', icon: CircleDashed }
  }

  if (status === 'skipped') {
    return { label: 'Пропущено', icon: SkipForward }
  }

  return { label: 'Не начато', icon: Clock3 }
}

function getResumeLabel(exercise: RuntimeWorkoutSummaryState['exercises'][number]) {
  if (exercise.status === 'skipped' || (exercise.completedSetCount ?? 0) === 0) {
    return 'Выполнить упражнение'
  }

  const remaining = exercise.remainingSetCount ?? 0
  return remaining > 1 ? `Доделать ${remaining} подхода` : 'Доделать подход'
}