import * as Dialog from '@radix-ui/react-dialog'
import { ArrowRight, CheckCircle2, CircleAlert, ListChecks, Sparkles } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import type { MachineHealth } from '@/entities/machine/model/types'
import { adjustExerciseLoadOnBackend } from '@/features/runtime/lib/runtime-persistence'
import { getRuntimeInitOptions, withSearch } from '@/features/runtime/lib/runtime-query'
import { getBestSetLabel, getSetTypeLabel } from '@/features/strength/lib/strength-plan'
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

export function ExerciseSummaryScreen() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const session = useRuntimeStore((state) => state.session)
  const ensureSession = useRuntimeStore((state) => state.ensureSession)
  const continueAfterExerciseSummary = useRuntimeStore((state) => state.continueAfterExerciseSummary)
  const completeWorkout = useRuntimeStore((state) => state.completeWorkout)
  const applyLoadAdjustment = useRuntimeStore((state) => state.applyLoadAdjustment)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [pendingAdjustment, setPendingAdjustment] = useState<'decrease' | 'increase' | null>(null)
  const [adjustmentRecommendation, setAdjustmentRecommendation] = useState<string | null>(null)
  const [detailsOpen, setDetailsOpen] = useState(false)

  const initOptions = getRuntimeInitOptions(searchParams)

  useEffect(() => {
    if (!session) {
      ensureSession(initOptions)
    }
  }, [ensureSession, initOptions, session])

  if (!session || !session.exerciseSummary) {
    return (
      <FormaShell userName={getUserName(selectedUserId)} machine={session?.machine ?? fallbackMachine} hideNavigation onStop={() => setEmergencyStopActive(true)}>
        <FormaState tone="loading" title="Считаем итог упражнения…" />
      </FormaShell>
    )
  }

  const summary = session.exerciseSummary
  const currentExercise = session.exercises.find((item) => item.id === session.currentExerciseId) ?? session.exercises[0]
  const hasNextExercise = Boolean(currentExercise && session.exercises[currentExercise.order])
  const nextStepLabel = hasNextExercise ? 'Перейти к следующему упражнению' : 'Открыть итог тренировки'
  const bestSet = summary.totals.bestSet ?? getBestSetLabel(summary.setResults)
  const hasWarning = summary.setResults.some((result) => result.pain || result.techniqueBreakdown || (result.discomfortLevel ?? 0) >= 5)
  const currentLoadLabel = summary.currentLoad ?? '—'
  const nextLoadLabel = summary.nextLoad ?? summary.currentLoad ?? '—'

  async function handleAdjustLoad(direction: 'decrease' | 'increase') {
    if (!summary.exerciseSlug || pendingAdjustment) {
      return
    }

    setPendingAdjustment(direction)
    setSaveError(null)

    try {
      const result = await adjustExerciseLoadOnBackend({
        userId: selectedUserId ?? 'alexey',
        exerciseSlug: summary.exerciseSlug,
        direction,
        trainingMode: summary.trainingMode,
        trainingDayType: summary.trainingDayType,
        kind: summary.kind,
        currentWeightKg: summary.nextWeightKg ?? summary.currentWeightKg,
        currentReps: summary.nextReps ?? summary.currentReps,
        currentSets: summary.nextSets ?? summary.currentSets,
        restSeconds: summary.nextRestSeconds ?? summary.restSeconds,
      })
      applyLoadAdjustment(summary.exerciseSlug, result)
      setAdjustmentRecommendation(result.recommendation)
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'Не удалось изменить нагрузку. Попробуйте ещё раз.')
    } finally {
      setPendingAdjustment(null)
    }
  }

  const outcomeTone = summary.outcome === 'aborted' ? 'aborted' : summary.outcome === 'partial' || summary.outcome === 'skipped' ? 'partial' : 'done'
  const outcomeLabel = summary.outcome === 'aborted' ? 'Упражнение прервано' : summary.outcome === 'skipped' ? 'Упражнение пропущено' : summary.outcome === 'partial' ? 'Выполнено частично' : 'Результат сохранён'

  function handleContinue() {
    continueAfterExerciseSummary()
    const nextView = useRuntimeStore.getState().session?.view
    navigate(withSearch(nextView === 'workout-summary' ? '/workout-summary' : '/exercise-setup', location.search))
  }

  return (
    <FormaShell userName={getUserName(selectedUserId)} machine={session.machine} hideNavigation onStop={() => setEmergencyStopActive(true)}>
      <div className="rt-screen">
        <header className="rt-header">
          <div className="rt-chips" style={{ justifyContent: 'flex-start' }} aria-label="Место в тренировке">
            {currentExercise ? <span className="rt-chip">Упражнение {currentExercise.order} из {session.exercises.length}</span> : null}
          </div>
          <div className="rt-title">
            <h1 className="font-display font-bold tracking-[-0.04em] text-white">{summary.title}</h1>
            <p><span>{summary.subtitle}</span></p>
          </div>
          <div className="rt-chips" aria-label="Итог упражнения">
            <span className="rt-outcome-badge" data-tone={outcomeTone}>
              {outcomeTone === 'done' ? <CheckCircle2 aria-hidden="true" /> : <CircleAlert aria-hidden="true" />}
              {outcomeLabel}
            </span>
          </div>
        </header>

        <div className="rt-body rt-summary-body">
          <div className="rt-summary-metrics" role="list" aria-label="Итоги упражнения">
            <article role="listitem"><span>Подходы</span><strong>{summary.totals.setsCompleted}</strong></article>
            <article role="listitem"><span>Повторы / время</span><strong>{summary.totals.repsOrTime}</strong></article>
            <article role="listitem"><span>Объём</span><strong>{summary.totals.volume}</strong></article>
            <article role="listitem" data-accent="true"><span>Лучший подход</span><strong>{bestSet}</strong></article>
          </div>

          {saveError ? (
            <div className="rt-alert" data-tone="danger" role="alert">
              <CircleAlert aria-hidden="true" />
              <div>
                <strong>Не удалось изменить нагрузку</strong>
                <p>{saveError}</p>
              </div>
              <Button variant="secondary" onClick={() => setSaveError(null)}>Скрыть</Button>
            </div>
          ) : hasWarning ? (
            <div className="rt-alert" data-tone="danger" role="alert">
              <CircleAlert aria-hidden="true" />
              <div>
                <strong>Отмечена боль или потеря техники</strong>
                <p>Не увеличивайте вес на следующей тренировке.</p>
              </div>
              <span />
            </div>
          ) : (
            <div className="rt-alert" role="note">
              <Sparkles aria-hidden="true" />
              <div>
                <strong>Рекомендация Forma</strong>
                <p>{adjustmentRecommendation ?? summary.recommendation}</p>
              </div>
              <span />
            </div>
          )}

          <div className="rt-load">
            <div>
              <span>Нагрузка в следующий раз</span>
              <strong>{nextLoadLabel}</strong>
              <span>Сейчас: {currentLoadLabel}</span>
            </div>
            <div className="rt-load-actions">
              <Button variant="secondary" disabled={!summary.exerciseSlug || pendingAdjustment !== null} onClick={() => void handleAdjustLoad('decrease')}>
                {pendingAdjustment === 'decrease' ? 'Сохраняю…' : 'Понизить нагрузку'}
              </Button>
              <Button variant="secondary" disabled={!summary.exerciseSlug || pendingAdjustment !== null} onClick={() => void handleAdjustLoad('increase')}>
                {pendingAdjustment === 'increase' ? 'Сохраняю…' : 'Повысить нагрузку'}
              </Button>
            </div>
          </div>
        </div>

        <div className="rt-actions" role="group" aria-label="Действия после упражнения">
          <div className="rt-actions-group">
            <Button variant="secondary" iconLeft={<ListChecks aria-hidden="true" />} onClick={() => setDetailsOpen(true)}>
              Подробно
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                completeWorkout('partial')
                navigate(withSearch('/workout-summary', location.search))
              }}
            >
              Завершить тренировку сейчас
            </Button>
          </div>
          <div className="rt-actions-note">{hasNextExercise ? <>Дальше: <strong>{session.exercises[currentExercise.order]?.name}</strong></> : 'Это было последнее упражнение тренировки'}</div>
          <Button className="rt-primary" iconLeft={<ArrowRight aria-hidden="true" />} onClick={handleContinue}>
            {nextStepLabel}
          </Button>
        </div>
      </div>

      <Dialog.Root open={detailsOpen} onOpenChange={setDetailsOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
          <SafetyDialogContent className="rt-details-panel">
            <Dialog.Title className="font-display text-3xl font-bold">Подробно: {summary.title}</Dialog.Title>
            <Dialog.Description className="mt-2 text-sm text-white/70">Все подходы, план и факт, темп и амплитуда.</Dialog.Description>
            <div className="rt-details-body">
              <section aria-label="Подходы">
                <h3>Подходы</h3>
                <div className="rt-table">
                  <div><span>Сет</span><span>Тип</span><span>План</span><span>Факт</span><span>Вес / объём</span><span>Качество</span></div>
                  {summary.setResults.map((result) => (
                    <div key={result.setNumber}>
                      <strong>#{result.setNumber}</strong>
                      <span>{getSetTypeLabel(result.setType)}</span>
                      <span>{formatSummaryPlan(result)}</span>
                      <strong>{result.reps ?? result.actualValue}{typeof result.rir === 'number' ? ` • RIR ${result.rir}` : ''}</strong>
                      <span>{result.weightKg ? `${result.weightKg} кг` : '—'}{result.volumeKg ? ` • ${Math.round(result.volumeKg)} кг` : ''}</span>
                      <span>{result.tempoLabel}{result.amplitudePercent ? ` • ${result.amplitudePercent}%` : ''}{result.pain ? ' • боль' : ''}{result.techniqueBreakdown ? ' • техника' : ''}</span>
                    </div>
                  ))}
                </div>
              </section>
              <section aria-label="План и факт">
                <h3>План и факт</h3>
                <div className="rt-plan-fact">
                  {summary.planVsFact.map((item) => (
                    <div key={item.label}>
                      <strong>{item.label}</strong>
                      План: {item.plan} · Факт: {item.fact} · Δ {item.delta}
                    </div>
                  ))}
                  <div><strong>Амплитуда</strong>{summary.totals.averageAmplitude ?? '—'}</div>
                  <div><strong>Темп</strong>{summary.totals.tempo}</div>
                </div>
              </section>
              <p className="text-sm text-white/70">{summary.recommendation}</p>
            </div>
            <div className="builder-dialog-actions">
              <Dialog.Close asChild><Button>Закрыть</Button></Dialog.Close>
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

function formatSummaryPlan(result: { targetMinReps?: number | null; targetMaxReps?: number | null; plannedValue: number }) {
  if (result.targetMinReps && result.targetMaxReps && result.targetMinReps !== result.targetMaxReps) {
    return `${result.targetMinReps}–${result.targetMaxReps}`
  }

  return `${result.targetMaxReps ?? result.plannedValue}`
}