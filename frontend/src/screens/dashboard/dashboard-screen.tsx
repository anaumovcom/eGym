import { useQuery } from '@tanstack/react-query'
import { Activity, ChevronRight, Clock3, Dumbbell, ListChecks, TrendingUp } from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { MuscleCard } from '@/entities/muscle/model/types'
import type { DashboardData } from '@/entities/dashboard/model/types'
import { apiGet } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { BlockingAlert, WarningBanner } from '@/shared/ui/status/status-components'
import { CompactBodyMapGrid, type CompactBodyMapHover } from '@/shared/ui/stage2/screen-components'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { useAppStore } from '@/stores/app-store'

const statusColors: Record<MuscleCard['status'], string> = {
  ready: 'bg-[#6ed36d]',
  light: 'bg-[#d7c748]',
  medium: 'bg-[#e7903b]',
  high: 'bg-[#eb5345]',
  critical: 'bg-[#832f32]',
  no_data: 'bg-[#677084]',
}

const statusLabels: Record<MuscleCard['status'], string> = {
  ready: 'Готова к нагрузке',
  light: 'Лёгкая усталость',
  medium: 'Умеренная усталость',
  high: 'Высокая усталость',
  critical: 'Критическая усталость',
  no_data: 'Нет данных',
}

export type DashboardViewProps = {
  data: DashboardData
  userName: string
  figureGender: 'male' | 'female'
  emergencyStopActive: boolean
  onStop: () => void
  onEmergencyStopChange: (open: boolean) => void
}

export function DashboardScreen() {
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const [searchParams] = useSearchParams()
  const scenario = searchParams.get('scenario') ?? 'default'
  const userId = selectedUserId ?? 'alexey'

  const { data } = useQuery({
    queryKey: ['dashboard', userId, scenario],
    queryFn: () => apiGet<DashboardData>(`/api/dashboard?userId=${encodeURIComponent(userId)}&scenario=${encodeURIComponent(scenario)}`),
  })

  if (!data) {
    return null
  }

  return (
    <DashboardView
      data={data}
      userName={selectedUserId === 'elena' ? 'Елена' : selectedUserId === 'guest' ? 'Гость' : 'Алексей'}
      figureGender={selectedUserId === 'elena' ? 'female' : 'male'}
      emergencyStopActive={emergencyStopActive}
      onEmergencyStopChange={setEmergencyStopActive}
      onStop={() => setEmergencyStopActive(true)}
    />
  )
}

export function DashboardView({ data, userName, figureGender, emergencyStopActive, onStop, onEmergencyStopChange }: DashboardViewProps) {
  return (
    <FormaShell userName={userName} machine={data.machine} onStop={onStop}>
      {data.alerts.length > 0 ? (
        <div className="grid gap-4">
          {data.alerts.map((alert) =>
            alert.tone === 'blocked' ? (
              <BlockingAlert key={alert.title} title={alert.title} description={alert.description} />
            ) : (
              <WarningBanner key={alert.title} title={alert.title} description={alert.description} />
            ),
          )}
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <DashboardWorkoutsSection workouts={data.workouts ?? []} />
        <div className="grid gap-6">
          <DashboardMuscleMapSection muscles={data.muscles} figureGender={figureGender} />
          <DashboardStatsSection progress={data.progress} />
        </div>
      </div>

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={onEmergencyStopChange} />
    </FormaShell>
  )
}

function DashboardStatsSection({ progress }: { progress: DashboardData['progress'] }) {
  return (
    <section className="glass-panel rounded-[34px] p-6 xl:p-8">
      <div className="flex flex-col gap-6">
        <div>
          <div>
            <div className="text-sm uppercase tracking-[0.25em] text-white/35">Статистика</div>
          </div>
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-1">
          {progress.map((item, index) => (
            <div key={item.label} className="flex items-center gap-4 rounded-2xl border border-white/8 bg-white/4 px-4 py-4">
              {index % 2 === 0 ? <TrendingUp className="h-5 w-5 text-[#d6b05f]" /> : <Activity className="h-5 w-5 text-[#d6b05f]" />}
              <div>
                <div className="font-display text-3xl font-bold text-white">{item.value}</div>
                <div className="text-sm text-white/45">{item.label}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function DashboardMuscleMapSection({ muscles, figureGender }: { muscles: DashboardData['muscles']; figureGender: 'male' | 'female' }) {
  const [hoveredMuscle, setHoveredMuscle] = useState<DashboardData['muscles'][number] | null>(null)
  const highlights = useMemo(() => muscles.map((muscle) => ({ label: muscle.name, tone: muscle.status })), [muscles])

  const handleHighlightHover = useCallback((highlight: CompactBodyMapHover | null) => {
    if (!highlight) {
      setHoveredMuscle((current) => (current ? null : current))
      return
    }

    const muscle = muscles.find((item) => item.name === highlight.label)

    if (!muscle) {
      setHoveredMuscle((current) => (current ? null : current))
      return
    }

    setHoveredMuscle((current) => (current?.name === muscle.name && current.status === muscle.status && current.score === muscle.score ? current : muscle))
  }, [muscles])

  return (
    <section className="glass-panel rounded-[34px] p-6">
      <div className="mb-5 text-sm uppercase tracking-[0.25em] text-white/35">Карта усталости</div>
      <div className="relative">
        <CompactBodyMapGrid highlights={highlights} figureGender={figureGender} onHighlightHover={handleHighlightHover} showFigureTitles={false} plainFigures />
        {hoveredMuscle ? (
          <div className="pointer-events-none absolute right-4 top-4 z-30 w-[220px] rounded-[22px] border border-white/10 bg-[#0b1220]/96 p-4 text-white shadow-[0_24px_60px_rgba(0,0,0,0.4)]">
            <div className="flex items-center gap-3">
              <span className={`status-dot ${statusColors[hoveredMuscle.status]}`} />
              <div className="font-semibold text-white">{hoveredMuscle.name}</div>
            </div>
            <div className="mt-3 text-sm text-white/68">{statusLabels[hoveredMuscle.status]}</div>
            <div className="mt-2 text-lg font-semibold text-[#f0d08c]">{hoveredMuscle.score} из 100</div>
          </div>
        ) : null}
      </div>
    </section>
  )
}

function DashboardWorkoutsSection({ workouts }: { workouts: NonNullable<DashboardData['workouts']> }) {
  const navigate = useNavigate()
  const setSelectedProgramId = useAppStore((state) => state.setSelectedProgramId)

  function handleStartWorkout(workoutId: string) {
    const runId = Date.now().toString(36)
    setSelectedProgramId(workoutId)
    navigate(`/exercise-setup?source=builder&programId=${encodeURIComponent(workoutId)}&photo=before&runId=${encodeURIComponent(runId)}`)
  }

  return (
    <section className="glass-panel rounded-[34px] p-6">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <div className="text-sm uppercase tracking-[0.25em] text-white/35">Тренировки</div>
          <div className="mt-2 font-display text-3xl font-bold text-white">Выберите тренировку для старта</div>
        </div>
      </div>
      {workouts.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2">
          {workouts.map((workout) => {
            return (
              <button
                key={workout.id}
                type="button"
                onClick={() => handleStartWorkout(workout.id)}
                className="group relative isolate w-full cursor-pointer overflow-hidden rounded-[28px] border border-white/10 bg-[#0d1118] p-4 text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.045),0_18px_46px_rgba(0,0,0,0.22)] transition hover:-translate-y-0.5 hover:border-[#d6b05f]/36 hover:bg-[#10151d] hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.06),0_24px_64px_rgba(0,0,0,0.32)]"
              >
                <span className="pointer-events-none absolute -right-16 -top-20 h-44 w-44 rounded-full bg-[#d6b05f]/14 blur-3xl transition group-hover:bg-[#d6b05f]/22" />
                <span className="pointer-events-none absolute -bottom-24 left-8 h-44 w-44 rounded-full bg-[#6ed36d]/8 blur-3xl" />
                <div className="relative z-10 flex items-start gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-[20px] border border-[#d6b05f]/22 bg-[#d6b05f]/12 text-[#f0d08c] shadow-[0_12px_28px_rgba(214,176,95,0.12)]">
                      <Dumbbell className="h-5 w-5" />
                    </span>
                    <div className="min-w-0">
                      <div className="truncate font-display text-3xl font-bold tracking-[-0.05em] text-white">{workout.title}</div>
                    </div>
                  </div>
                </div>
                <div className="relative z-10 mt-4 grid gap-3">
                  <div className="inline-flex min-h-12 items-center gap-3 rounded-[20px] border border-white/8 bg-white/[0.055] px-3 text-sm text-white/68">
                    <Clock3 className="h-4 w-4 text-[#d6b05f]" />
                    <span>{workout.duration}</span>
                  </div>
                </div>
                <div className="relative z-10 mt-3 rounded-[22px] border border-white/8 bg-black/16 p-2.5">
                  <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-white/38">
                    <ListChecks className="h-3.5 w-3.5 text-[#d6b05f]" />
                    Упражнения
                  </div>
                  <div className="grid gap-2">
                    {workout.exercises.length > 0 ? workout.exercises.map((exercise, index) => (
                      <div key={`${workout.id}-${exercise}-${index}`} className="grid grid-cols-[auto_1fr_auto] items-center gap-2 rounded-[16px] border border-white/7 bg-white/[0.045] px-2.5 py-2 transition group-hover:border-white/10 group-hover:bg-white/[0.06]">
                        <span className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-white/10 bg-white/7 text-[10px] font-semibold text-white/58">{index + 1}</span>
                        <span className="truncate text-sm font-semibold text-white/78">{exercise}</span>
                        <Dumbbell className="h-3.5 w-3.5 text-white/28" />
                      </div>
                    )) : (
                      <div className="rounded-[18px] border border-dashed border-white/10 bg-white/[0.035] px-3 py-3 text-sm text-white/45">Нет упражнений</div>
                    )}
                  </div>
                </div>
                <div className="relative z-10 mt-4 ml-2 inline-flex items-center gap-2 text-sm font-semibold text-[#f0d08c]/78 transition group-hover:text-[#f0d08c]">
                  Нажмите, чтобы начать тренировку
                  <ChevronRight className="h-4 w-4 transition group-hover:translate-x-0.5" />
                </div>
              </button>
            )
          })}
        </div>
      ) : (
        <div className="flex h-full min-h-[280px] flex-col justify-between">
          <div>
            <div className="text-sm uppercase tracking-[0.25em] text-white/35">Тренировки</div>
            <div className="mt-2 font-display text-3xl font-bold text-white">Тренировки не найдены</div>
            <div className="mt-3 text-sm leading-6 text-white/48">Создайте тренировку в конструкторе, чтобы она появилась на главной странице.</div>
          </div>
          <div className="mt-5 flex gap-3">
            <Button variant="secondary" className="flex-1" onClick={() => navigate('/builder')}>Открыть конструктор</Button>
          </div>
        </div>
      )}
    </section>
  )
}
