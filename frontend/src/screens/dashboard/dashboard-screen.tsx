import { useQuery } from '@tanstack/react-query'
import { Activity, ArrowRight, ChevronRight, Replace, Trash2, TrendingUp } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { DashboardData, DashboardWorkoutExercise, DashboardWorkoutSnapshot } from '@/entities/dashboard/model/types'
import type { ExerciseDetails } from '@/entities/exercise/model/types'
import type { MuscleCard } from '@/entities/muscle/model/types'
import { apiGet, apiPut } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { BlockingAlert, WarningBanner } from '@/shared/ui/status/status-components'
import { CompactBodyMapGrid, ExerciseVideoPlayer, type CompactBodyMapHover } from '@/shared/ui/stage2/screen-components'
import { ExerciseDetailsDialog } from '@/shared/ui/training/exercise-details-dialog'
import { ExercisePickerModal } from '@/shared/ui/training/exercise-picker-modal'
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

const recommendationTone: Record<string, string> = {
  'Рекомендуется': 'text-[#8ce48b]',
  'Можно выполнить': 'text-[#f0d08c]',
}

export type DashboardViewProps = {
  data: DashboardData
  userId: string
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
      userId={userId}
      userName={selectedUserId === 'elena' ? 'Елена' : selectedUserId === 'guest' ? 'Гость' : 'Алексей'}
      figureGender={selectedUserId === 'elena' ? 'female' : 'male'}
      emergencyStopActive={emergencyStopActive}
      onEmergencyStopChange={setEmergencyStopActive}
      onStop={() => setEmergencyStopActive(true)}
    />
  )
}

export function DashboardView({ data, userId, userName, figureGender, emergencyStopActive, onStop, onEmergencyStopChange }: DashboardViewProps) {
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
        <DashboardWorkoutSection userId={userId} todayWorkout={data.todayWorkout} recommendedExercises={data.recommendedExercises} />
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

function DashboardWorkoutSection({
  userId,
  todayWorkout,
  recommendedExercises,
}: {
  userId: string
  todayWorkout: DashboardData['todayWorkout']
  recommendedExercises: DashboardData['recommendedExercises']
}) {
  const navigate = useNavigate()
  const [workoutState, setWorkoutState] = useState(todayWorkout)
  const [replaceTarget, setReplaceTarget] = useState<DashboardWorkoutExercise | null>(null)
  const [detailsTarget, setDetailsTarget] = useState<DashboardWorkoutExercise | null>(null)

  useEffect(() => {
    setWorkoutState(todayWorkout)
  }, [todayWorkout])

  function updateWorkoutItems(items: DashboardWorkoutExercise[]) {
    setWorkoutState((current) => {
      if (!current) {
        return current
      }

      return {
        ...current,
        exercises: items.length,
        sets: sumWorkoutSets(items),
        list: items,
      }
    })
  }

  async function handleDeleteExercise(slug: string) {
    if (!workoutState) {
      return
    }

    const nextItems = workoutState.list.filter((item) => item.slug !== slug)
    if (nextItems.length === 0) {
      return
    }

    await apiPut('/api/today/plan', {
      userId,
      slugs: nextItems.map((item) => item.slug),
    })
    updateWorkoutItems(nextItems)
  }

  async function handleReplaceExercise(nextExercise: DashboardWorkoutExercise) {
    if (!replaceTarget || !workoutState) {
      return
    }

    const nextItems = workoutState.list.map((item) => (item.slug === replaceTarget.slug ? nextExercise : item))
    await apiPut('/api/today/plan', {
      userId,
      slugs: nextItems.map((item) => item.slug),
    })
    updateWorkoutItems(nextItems)
    setReplaceTarget(null)
  }

  return (
    <section className="glass-panel rounded-[34px] p-6">
      {workoutState ? (
        <>
          <div className="mb-4 flex items-center justify-between">
            <div>
              <div className="text-sm uppercase tracking-[0.25em] text-white/35">Сегодняшняя тренировка</div>
              <div className="mt-2 font-display text-3xl font-bold text-white">{workoutState.title}</div>
            </div>
          </div>
          <div className="mb-4 grid grid-cols-3 gap-3 text-sm text-white/65">
            <div>{workoutState.exercises} упражнений</div>
            <div>{workoutState.sets} подходов</div>
            <div>{workoutState.duration}</div>
          </div>
          {workoutState.list.length > 0 ? (
            <div className="space-y-3">
              {workoutState.list.map((item, index) => (
                <div
                  key={`${item.slug}-${index}`}
                  onClick={() => setDetailsTarget(item)}
                  className="cursor-pointer rounded-[22px] border border-white/8 bg-white/[0.045] px-4 py-3 text-sm text-white/80 transition hover:border-white/14 hover:bg-white/[0.06]"
                >
                <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_164px] md:items-center">
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white/8 text-xs">{index + 1}</span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate font-semibold text-white">{item.name}</div>
                        </div>
                        <ChevronRight className="mt-0.5 h-4 w-4 shrink-0 text-white/30" />
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <DashboardWorkoutSnapshotLine snapshot={item.previous} />
                        <DashboardWorkoutSnapshotLine snapshot={item.planned} emphasize />
                      </div>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation()
                            setReplaceTarget(item)
                          }}
                          className="inline-flex min-h-9 items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold text-white/72 transition hover:border-[#d6b05f]/30 hover:bg-white/8 hover:text-white"
                        >
                          <Replace className="h-3.5 w-3.5" />
                          Заменить
                        </button>
                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation()
                            void handleDeleteExercise(item.slug)
                          }}
                          className="inline-flex min-h-9 items-center gap-2 rounded-full border border-[#eb5345]/22 bg-[#eb5345]/8 px-3 py-2 text-xs font-semibold text-[#ffb1a8] transition hover:border-[#eb5345]/40 hover:bg-[#eb5345]/14"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          Удалить
                        </button>
                      </div>
                    </div>
                  </div>
                  <DashboardWorkoutVideoPreview videoUrl={item.previewVideoUrl} title={item.name} />
                </div>
              </div>
              ))}
            </div>
          ) : (
            <div className="rounded-[24px] border border-dashed border-white/10 bg-white/[0.03] px-5 py-6 text-sm text-white/55">
              В тренировке не осталось упражнений.
            </div>
          )}
          <div className="mt-5 flex gap-3">
            <Button className="flex-1">Начать</Button>
            <Button variant="secondary" className="flex-1">Открыть план</Button>
          </div>
          <ExercisePickerModal
            open={Boolean(replaceTarget)}
            onOpenChange={(open) => {
              if (!open) {
                setReplaceTarget(null)
              }
            }}
            userId={userId}
            mode="replace"
            currentExerciseSlug={replaceTarget?.slug}
            currentExerciseName={replaceTarget?.name ?? ''}
            onSelect={(details) => handleReplaceExercise(buildDashboardWorkoutExercise(details))}
          />
          <ExerciseDetailsDialog
            open={Boolean(detailsTarget)}
            onOpenChange={(open) => {
              if (!open) {
                setDetailsTarget(null)
              }
            }}
            userId={userId}
            exerciseSlug={detailsTarget?.slug}
            exerciseName={detailsTarget?.name}
            preferredVideoGender={userId === 'elena' ? 'female' : 'male'}
            onOpenFullScreen={detailsTarget ? () => navigate(`/catalog/${encodeURIComponent(detailsTarget.slug)}`) : undefined}
          />
        </>
      ) : (
        <div className="flex h-full min-h-[280px] flex-col justify-between">
          <div>
            <div className="text-sm uppercase tracking-[0.25em] text-white/35">Сегодняшняя тренировка</div>
            <div className="mt-2 font-display text-3xl font-bold text-white">Сегодня нет тренировки</div>
            <div className="mt-6 flex items-center justify-between">
              <div className="font-display text-2xl font-bold text-white">Рекомендовано сегодня</div>
              <ArrowRight className="h-5 w-5 text-white/30" />
            </div>
            <div className="mt-4 space-y-3">
              {recommendedExercises.map((item) => (
                <div key={item.name} className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3 text-sm text-white/82">
                  <div>
                    <div className="font-semibold text-white">{item.name}</div>
                    <div className="text-white/45">{item.muscles}</div>
                  </div>
                  <div className={cn('font-medium', recommendationTone[item.status] ?? 'text-white/65')}>{item.status}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="mt-5 flex gap-3">
            <Button variant="secondary" className="flex-1">Открыть каталог</Button>
          </div>
        </div>
      )}
    </section>
  )
}

function DashboardWorkoutSnapshotLine({ snapshot, emphasize = false }: { snapshot: DashboardWorkoutSnapshot; emphasize?: boolean }) {
  return (
    <div className={cn('min-w-0 rounded-full border px-3 py-2', emphasize ? 'border-[#d6b05f]/20 bg-[#d6b05f]/10' : 'border-white/8 bg-white/5')}>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="text-[10px] uppercase tracking-[0.18em] text-white/38">{snapshot.label}</span>
        <span className={cn('text-sm font-semibold leading-none', emphasize ? 'text-[#f0d08c]' : 'text-white')}>
          {snapshot.primary}
        </span>
        <span className="text-xs text-white/62">{snapshot.secondary}</span>
        {snapshot.meta ? <span className="text-xs text-white/38">{snapshot.meta}</span> : null}
      </div>
    </div>
  )
}

function DashboardWorkoutVideoPreview({ videoUrl, title }: { videoUrl?: string | null; title: string }) {
  if (!videoUrl) {
    return <div className="hidden h-[92px] rounded-[18px] border border-white/8 bg-[#0b1017] md:block" />
  }

  return (
    <ExerciseVideoPlayer
      videoUrl={videoUrl}
      videoLabel={`${title} · превью`}
      lazyLoad
      wrapperClassName="hidden h-[92px] aspect-auto rounded-[18px] border border-white/8 bg-[#0b1017] md:block"
    />
  )
}

function buildDashboardWorkoutExercise(details: ExerciseDetails): DashboardWorkoutExercise {
  const latestHistory = details.history[0]
  const isStatic = details.force === 'Static'
  const primaryPlanned = isStatic ? `${details.loadSettings.reps} сек` : details.loadSettings.weight > 0 ? `${formatWeight(details.loadSettings.weight)} кг` : 'вес тела'
  const secondaryPlanned = isStatic ? 'вес тела' : `${details.loadSettings.reps} повторов`

  return {
    slug: details.slug,
    name: details.name,
    previewVideoUrl: details.previewVideoUrl,
    previous: latestHistory
      ? {
          label: 'Прошлый раз',
          primary: isStatic ? `${latestHistory.reps} сек` : latestHistory.weight,
          secondary: isStatic ? 'вес тела' : `${latestHistory.reps} повторов`,
          meta: `${latestHistory.sets} ${formatSetWord(latestHistory.sets)} • ${latestHistory.date}`,
        }
      : {
          label: 'Прошлый раз',
          primary: 'Нет истории',
          secondary: 'Ориентир появится после старта',
          meta: undefined,
        },
    planned: {
      label: 'План',
      primary: primaryPlanned,
      secondary: secondaryPlanned,
      meta: `${details.loadSettings.sets} ${formatSetWord(details.loadSettings.sets)} • новый выбор`,
    },
  }
}

function sumWorkoutSets(items: DashboardWorkoutExercise[]) {
  return items.reduce((total, item) => total + extractSetsFromMeta(item.planned.meta), 0)
}

function extractSetsFromMeta(meta?: string | null) {
  if (!meta) {
    return 0
  }

  const match = meta.match(/^(\d+)/)
  return match ? Number(match[1]) : 0
}

function formatSetWord(value: number) {
  const remainderTen = value % 10
  const remainderHundred = value % 100

  if (remainderTen === 1 && remainderHundred !== 11) {
    return 'подход'
  }
  if (remainderTen >= 2 && remainderTen <= 4 && (remainderHundred < 12 || remainderHundred > 14)) {
    return 'подхода'
  }
  return 'подходов'
}

function formatWeight(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, '')
}