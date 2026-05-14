import { CheckCircle2, CircleAlert } from 'lucide-react'
import { useEffect } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { getRuntimeInitOptions, withSearch } from '@/features/runtime/lib/runtime-query'
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

  const initOptions = getRuntimeInitOptions(searchParams)

  useEffect(() => {
    if (!session) {
      ensureSession(initOptions)
    }
  }, [ensureSession, initOptions, session])

  if (!session || !session.exerciseSummary) {
    return null
  }

  const summary = session.exerciseSummary

  return (
    <FormaShell userName={getUserName(selectedUserId)} machine={session.machine} onStop={() => setEmergencyStopActive(true)}>
      <SectionIntro
        title={summary.title}
        description={summary.subtitle}
        actions={
          <div className={cn('rounded-[22px] px-4 py-3 text-sm', summary.outcome === 'aborted' ? 'border border-[#b83d38]/30 bg-[#311615] text-[#ffb3a9]' : 'border border-[#57c968]/18 bg-[#122b1d] text-[#92e09a]')}>
            {summary.outcome === 'aborted' ? 'Упражнение завершено частично' : 'Результат сохранён'}
          </div>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <section className="glass-panel rounded-[34px] p-6 xl:p-8">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <Metric label="Подходы" value={summary.totals.setsCompleted} />
            <Metric label="Повторы / время" value={summary.totals.repsOrTime} />
            <Metric label="Объём" value={summary.totals.volume} />
            <Metric label="Амплитуда" value={summary.totals.averageAmplitude ?? '—'} />
            <Metric label="Темп" value={summary.totals.tempo} />
          </div>

          <div className="mt-6 overflow-hidden rounded-[28px] border border-white/8">
            <div className="grid grid-cols-[120px_1fr_1fr_1fr] bg-white/4 px-4 py-3 text-sm text-white/45">
              <div>Сет</div>
              <div>План</div>
              <div>Факт</div>
              <div>Качество</div>
            </div>
            {summary.setResults.map((result) => (
              <div key={result.setNumber} className="grid grid-cols-[120px_1fr_1fr_1fr] border-t border-white/8 px-4 py-4 text-sm text-white/72">
                <div className="font-semibold text-white">#{result.setNumber}</div>
                <div>{result.plannedValue}</div>
                <div>{result.actualValue}</div>
                <div>{result.tempoLabel}{result.amplitudePercent ? ` • ${result.amplitudePercent}%` : ''}</div>
              </div>
            ))}
          </div>
        </section>

        <aside className="space-y-6">
          <section className="glass-panel rounded-[32px] p-5">
            <div className="font-display text-3xl font-bold text-white">План и факт</div>
            <div className="mt-4 space-y-3">
              {summary.planVsFact.map((item) => (
                <div key={item.label} className="rounded-[24px] border border-white/8 bg-white/4 px-4 py-4 text-white/74">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium text-white">{item.label}</span>
                    <span className="text-sm text-white/45">Δ {item.delta}</span>
                  </div>
                  <div className="mt-2 text-sm">План: {item.plan}</div>
                  <div className="mt-1 text-sm">Факт: {item.fact}</div>
                </div>
              ))}
            </div>
          </section>

          <section className="glass-panel rounded-[32px] p-5">
            <div className="flex items-center gap-3 text-[#f2cf87]"><CircleAlert className="h-5 w-5" />Рекомендация Forma</div>
            <div className="mt-3 text-sm leading-7 text-white/65">{summary.recommendation}</div>
            <div className="mt-5 flex flex-col gap-3">
              <Button
                iconLeft={<CheckCircle2 className="h-4 w-4" />}
                onClick={() => {
                  continueAfterExerciseSummary()
                  const nextView = useRuntimeStore.getState().session?.view
                  navigate(withSearch(nextView === 'workout-summary' ? '/workout-summary' : '/exercise-setup', location.search))
                }}
              >
                {summary.nextStepLabel}
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

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[22px] border border-white/8 bg-white/4 p-4">
      <div className="text-sm text-white/45">{label}</div>
      <div className="mt-2 font-display text-3xl font-bold text-white">{value}</div>
    </div>
  )
}