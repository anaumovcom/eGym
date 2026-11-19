import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Ban, Clock3, Dumbbell, Gauge, Play, Plus, Star, Target } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import type { ExerciseDetails } from '@/entities/exercise/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import { apiGet } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { BlockingAlert, WarningBanner } from '@/shared/ui/status/status-components'
import { BuilderWarningPanel, CalibrationStatusBlock, CompactBodyMapMini, ExerciseVideoPlayer, FilterChip, LoadSettingsControl, MuscleMapCompact, MuscleStatusList } from '@/shared/ui/stage2/screen-components'
import { ExerciseTechniqueSteps } from '@/shared/ui/training/exercise-technique-steps'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import './exercise-details-broadcast.css'

const tabs = [
  { id: 'overview', label: 'Обзор' },
  { id: 'technique', label: 'Техника' },
  { id: 'muscles', label: 'Мышцы' },
  { id: 'load', label: 'Нагрузка' },
  { id: 'history', label: 'История' },
  { id: 'similar', label: 'Похожие' },
] as const

function getProgressWidthClass(value: number) {
  if (value >= 45) {
    return 'w-full'
  }

  if (value >= 40) {
    return 'w-11/12'
  }

  if (value >= 35) {
    return 'w-4/5'
  }

  if (value >= 30) {
    return 'w-3/4'
  }

  if (value >= 25) {
    return 'w-2/3'
  }

  return 'w-1/2'
}

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

export function ExerciseDetailsScreen() {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const favoriteExerciseSlugs = useAppStore((state) => state.favoriteExerciseSlugs)
  const blacklistedExerciseSlugs = useAppStore((state) => state.blacklistedExerciseSlugs)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const toggleFavoriteExercise = useAppStore((state) => state.toggleFavoriteExercise)
  const toggleBlacklistedExercise = useAppStore((state) => state.toggleBlacklistedExercise)
  const setSelectedExerciseSlug = useAppStore((state) => state.setSelectedExerciseSlug)

  const resolvedUserId = selectedUserId ?? 'alexey'
  const activeTab = (searchParams.get('tab') ?? 'overview') as (typeof tabs)[number]['id']
  const scenario = searchParams.get('scenario') ?? 'default'
  const machineScenario = searchParams.get('machine') ?? (scenario === 'machine-blocked' ? 'blocked' : 'ready')

  const { data } = useQuery({
    queryKey: ['exercise-details-screen', slug, resolvedUserId, favoriteExerciseSlugs.join(','), blacklistedExerciseSlugs.join(',')],
    queryFn: () =>
      apiGet<ExerciseDetails>(
        `/api/exercises/${encodeURIComponent(slug ?? 'barbell-floor-press')}?userId=${encodeURIComponent(resolvedUserId)}&favorites=${encodeURIComponent(favoriteExerciseSlugs.join(','))}&blacklist=${encodeURIComponent(blacklistedExerciseSlugs.join(','))}`,
      ),
  })

  const { data: machine } = useQuery({
    queryKey: ['exercise-details-machine', machineScenario],
    queryFn: () => apiGet<MachineHealth>(`/api/machine/status?scenario=${encodeURIComponent(machineScenario)}`),
  })

  const [settings, setSettings] = useState(data?.loadSettings ?? null)
  const [preferredVideo, setPreferredVideo] = useState<Pick<ExerciseDetails['videos'][number], 'gender' | 'view'> | null>(null)

  useEffect(() => {
    setSettings(data?.loadSettings ?? null)
    if (slug) {
      setSelectedExerciseSlug(slug)
    }
  }, [data?.loadSettings, setSelectedExerciseSlug, slug])

  if (!data || !machine) {
    return null
  }

  const blocked = machine.machineState === 'blocked'
  const videos = scenario === 'no-video' ? [] : data.videos
  const activeVideo = videos.find(video => video.gender === preferredVideo?.gender && video.view === preferredVideo.view)
    ?? videos.find(video => video.gender === preferredVideo?.gender)
    ?? videos[0]
  const availableGenders = [...new Set(videos.map(video => video.gender))]
  const availableViews = [...new Set(videos.filter(video => video.gender === activeVideo?.gender).map(video => video.view))]
  const startFromCatalog = () => {
    // a start from the catalog is a new workout: the same exercise done earlier today must not be resumed
    useRuntimeStore.getState().resetSession()
    navigate(`/exercise-setup?source=catalog&slug=${encodeURIComponent(data.slug)}`)
  }

  return (
    <FormaShell userName={getUserName(resolvedUserId)} machine={machine} onStop={() => setEmergencyStopActive(true)}>
      <div className="exercise-detail-screen glass-panel rounded-[34px] p-6 xl:p-8" data-has-video={Boolean(activeVideo)}>
        <header className="exercise-detail-heading">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <h1 className="font-display text-4xl font-bold text-white">{data.name}</h1>
              {data.secondaryName && <p className="mt-1 text-lg text-white/65">{data.secondaryName}</p>}
            </div>
            <Button variant="ghost" iconLeft={<ArrowLeft className="h-4 w-4" />} onClick={() => navigate('/catalog')}>
              В каталог
            </Button>
          </div>
          {data.blacklisted && <WarningBanner title="Упражнение в чёрном списке" description="Вы отметили это упражнение как нежелательное. Замены есть в разделе «Похожие»." />}
          {blocked && <BlockingAlert title="Старт упражнения заблокирован" description="Запуск временно недоступен из-за состояния тренажёра." />}
        </header>

        <div className="exercise-detail-hero grid gap-4">
          <div className="exercise-detail-media min-w-0 overflow-hidden rounded-[24px] border border-white/10 bg-[#0d1116]">
            <div className="exercise-detail-video">
              {activeVideo ? (
                <ExerciseVideoPlayer videoUrl={activeVideo.url} videoLabel={activeVideo.label} videoClassName="object-contain" />
              ) : (
                <div className="flex items-center justify-center p-5 text-white/65">Видео для этого упражнения пока нет</div>
              )}
            </div>
            {activeVideo && (
              <div className="exercise-detail-video-controls flex flex-wrap items-center justify-between gap-3 border-t border-white/8 p-3" role="group" aria-label="Варианты видео">
                {availableGenders.length > 1 ? (
                  <div className="flex flex-wrap gap-2">
                    {availableGenders.map(gender => (
                      <FilterChip key={gender} label={gender === 'male' ? 'Мужчина' : 'Женщина'} active={activeVideo.gender === gender} onClick={() => setPreferredVideo({ gender, view: activeVideo.view })} />
                    ))}
                  </div>
                ) : <span>{activeVideo.gender === 'male' ? 'Мужчина' : 'Женщина'}</span>}
                {availableViews.length > 1 ? (
                  <div className="flex flex-wrap gap-2">
                    {availableViews.map(view => (
                      <FilterChip key={view} label={view === 'side' ? 'Сбоку' : 'Спереди'} active={activeVideo.view === view} onClick={() => setPreferredVideo({ gender: activeVideo.gender, view })} />
                    ))}
                  </div>
                ) : <span>{activeVideo.view === 'side' ? 'Сбоку' : 'Спереди'}</span>}
              </div>
            )}
          </div>
          <aside className="exercise-detail-facts min-w-0 rounded-[24px] border border-white/10 bg-[#111419] p-5" aria-label="Об упражнении">
            <dl>
              <div><Target aria-hidden="true" /><dt>Основные мышцы</dt><dd>{data.muscles.join(', ') || '—'}</dd></div>
              <div><Dumbbell aria-hidden="true" /><dt>Оборудование и хват</dt><dd>{[data.equipment, data.grips].filter(Boolean).join(' · ')}</dd></div>
              <div><Gauge aria-hidden="true" /><dt>Сложность</dt><dd>{data.difficultyLabel}</dd></div>
            </dl>
            {data.description && <p>{data.description}</p>}
          </aside>
        </div>

        <div className="exercise-detail-tabs flex flex-wrap gap-2" role="group" aria-label="Разделы упражнения">
          {tabs.map((tab) => (
            <FilterChip key={tab.id} label={tab.label} active={tab.id === activeTab} onClick={() => setSearchParams((current) => {
              const next = new URLSearchParams(current)
              next.set('tab', tab.id)
              return next
            })} />
          ))}
        </div>

        <div key={`${data.slug}-${activeTab}`} className="exercise-detail-tab-content">
          {activeTab === 'overview' ? <OverviewTab details={data} /> : null}
          {activeTab === 'technique' ? <TechniqueTab details={data} /> : null}
          {activeTab === 'muscles' ? <MusclesTab details={data} /> : null}
          {activeTab === 'load' ? <LoadTab details={data} settings={settings ?? data.loadSettings} onChange={setSettings} /> : null}
          {activeTab === 'history' ? <HistoryTab details={data} /> : null}
          {activeTab === 'similar' ? <SimilarTab details={data} onOpen={(nextSlug) => navigate(`/catalog/${encodeURIComponent(nextSlug)}`)} /> : null}
        </div>
        <div className="exercise-detail-actions flex flex-wrap gap-3" role="group" aria-label="Действия с упражнением">
          <Button variant="secondary" iconLeft={<Star aria-hidden="true" />} aria-pressed={data.favorite} onClick={() => toggleFavoriteExercise(data.slug)}>{data.favorite ? 'В избранном' : 'В избранное'}</Button>
          <Button variant="secondary" iconLeft={<Ban aria-hidden="true" />} aria-pressed={data.blacklisted} onClick={() => toggleBlacklistedExercise(data.slug)}>{data.blacklisted ? 'Убрать из чёрного списка' : 'В чёрный список'}</Button>
          <Button variant="secondary" iconLeft={<Plus aria-hidden="true" />} onClick={() => navigate('/builder')}>Добавить в тренировку</Button>
          <Button iconLeft={<Play aria-hidden="true" />} disabled={blocked} onClick={startFromCatalog}>Начать упражнение</Button>
        </div>
      </div>

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}

function OverviewTab({ details }: { details: ExerciseDetails }) {
  return (
    <div className="exercise-detail-overview">
      {details.shortSteps.length > 0 && <ExerciseTechniqueSteps steps={details.shortSteps} title="Кратко о технике" />}
      {details.muscles.length > 0 && (
        <section className="exercise-detail-muscle-preview">
          <h2>Основные мышцы</h2>
          <CompactBodyMapMini muscles={details.muscles} figureContainerClassName="h-[12rem] p-1" figureMarkupClassName="max-w-[6rem]" />
          <p>{details.muscles.join(' · ')}</p>
        </section>
      )}
      <section className="exercise-detail-compatibility" data-tone={details.compatibility.tone} aria-label="Совместимость сегодня">
        <h2>{details.compatibility.title}</h2>
        <p>{details.compatibility.description}</p>
        <MuscleStatusList muscles={details.compatibility.affectedMuscles} />
      </section>
    </div>
  )
}

function TechniqueTab({ details }: { details: ExerciseDetails }) {
  const sections = [
    { title: 'Подготовка', items: details.guide.setup },
    { title: 'Как выполнять', items: details.guide.howToPerform.length ? details.guide.howToPerform : details.shortSteps },
    { title: 'Техника', items: details.guide.technique },
    { title: 'Ключевые подсказки', items: details.guide.keyTips },
    { title: 'Чего избегать', items: details.guide.thingsToAvoid },
  ].filter(section => section.items.length)

  return (
    <div className="exercise-detail-technique grid content-start gap-4">
      {sections.map(section => <AccordionCard key={section.title} {...section} />)}
      {!sections.length && <p className="text-muted-foreground">Описание техники пока не добавлено.</p>}
    </div>
  )
}

function MusclesTab({ details }: { details: ExerciseDetails }) {
  return (
    <div className="space-y-4">
      <MuscleMapCompact primary={details.primaryMuscles} secondary={details.secondaryMuscles} stabilizers={details.stabilizers} />
      <p className="text-sm text-muted-foreground">{details.muscleRoleText}</p>
    </div>
  )
}

function LoadTab({ details, settings, onChange }: { details: ExerciseDetails; settings: ExerciseDetails['loadSettings']; onChange: (value: ExerciseDetails['loadSettings']) => void }) {
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
      <div className="space-y-6">
        <LoadSettingsControl
          settings={settings}
          onAdjustWeight={(delta) => onChange({ ...settings, weight: Math.max(0, settings.weight + delta) })}
          onAdjustSets={(delta) => onChange({ ...settings, sets: Math.max(1, settings.sets + delta) })}
          onAdjustReps={(delta) => onChange({ ...settings, reps: Math.max(1, settings.reps + delta) })}
          onAdjustRest={(delta) => onChange({ ...settings, restSeconds: Math.max(15, settings.restSeconds + delta) })}
          onModeChange={(mode) => onChange({ ...settings, mode })}
        />
        <CalibrationStatusBlock calibration={settings.calibration} />
      </div>
      <div className="space-y-6">
        <section className="rounded-[30px] border border-white/8 bg-[#111419] p-6">
          <div className="font-display text-3xl font-bold text-white">Прогресс рабочего веса</div>
          <div className="mt-5 space-y-3">
            {details.loadProgress.map((point) => (
              <div key={point.label} className="grid grid-cols-[72px_1fr_auto] items-center gap-4 text-sm text-white/72">
                <div>{point.label}</div>
                <div className="h-3 overflow-hidden rounded-full bg-white/8">
                  <div className={cn('h-full rounded-full bg-linear-to-r from-[var(--broadcast-accent,#b5852f)] to-[var(--broadcast-accent-light,#f0d08c)]', getProgressWidthClass(point.value))} />
                </div>
                <div>{point.value} кг</div>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}

function HistoryTab({ details }: { details: ExerciseDetails }) {
  const bestWeight = details.history[0]?.weight ?? '—'
  const totalVolume = details.history[0]?.volume ?? '—'

  return (
    <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
      <section className="rounded-[30px] border border-white/8 bg-[#111419] p-6">
        <div className="font-display text-3xl font-bold text-white">История тренировок</div>
        <div className="mt-5 overflow-hidden rounded-[24px] border border-white/8">
          <table className="min-w-full text-left text-sm text-white/72">
            <thead className="bg-white/4 text-white/45">
              <tr>
                <th className="px-4 py-3 font-medium">Дата</th>
                <th className="px-4 py-3 font-medium">Вес</th>
                <th className="px-4 py-3 font-medium">Повторы</th>
                <th className="px-4 py-3 font-medium">Подходы</th>
                <th className="px-4 py-3 font-medium">Объём</th>
                <th className="px-4 py-3 font-medium">RPE</th>
              </tr>
            </thead>
            <tbody>
              {details.history.map((entry) => (
                <tr key={entry.date} className="border-t border-white/8">
                  <td className="px-4 py-3">{entry.date}</td>
                  <td className="px-4 py-3">{entry.weight}</td>
                  <td className="px-4 py-3">{entry.reps}</td>
                  <td className="px-4 py-3">{entry.sets}</td>
                  <td className="px-4 py-3">{entry.volume}</td>
                  <td className="px-4 py-3">{entry.rpe}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <div className="space-y-6">
        <MetricCard title="Личный рекорд" value={bestWeight} caption="последняя лучшая сессия" />
        <MetricCard title="Лучший объём" value={totalVolume} caption="на последней неделе" />
        {details.loadProgress.length > 0 && <MetricCard title="Средний рабочий вес" value={`${Math.round(details.loadProgress.reduce((sum, point) => sum + point.value, 0) / details.loadProgress.length)} кг`} caption="по последним тренировкам" />}
      </div>
    </div>
  )
}

function SimilarTab({ details, onOpen }: { details: ExerciseDetails; onOpen: (slug: string) => void }) {
  return (
    <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
      <section className="space-y-4 rounded-[30px] border border-white/8 bg-[#111419] p-6">
        <div className="font-display text-3xl font-bold text-white">Альтернативные упражнения</div>
        {details.similar.map((item) => (
          <button key={item.slug} type="button" onClick={() => onOpen(item.slug)} className="flex w-full items-center justify-between rounded-[24px] border border-white/8 bg-white/4 px-4 py-4 text-left text-white/74 transition hover:border-white/14 hover:bg-white/6">
            <div>
              <div className="font-semibold text-white">{item.name}</div>
              <div className="mt-1 text-sm text-white/45">{item.secondaryName}</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {[...item.muscles, item.equipment].filter(Boolean).map((tag) => (
                  <span key={tag} className="rounded-xl border border-white/10 px-3 py-1 text-sm">{tag}</span>
                ))}
              </div>
            </div>
            <ArrowLeft className="h-4 w-4 rotate-180 text-white/35" />
          </button>
        ))}
      </section>
      <div className="space-y-4">
        <BuilderWarningPanel title="Когда выбрать альтернативу" description={details.whenToChooseAlternative.join(' ')} tone="warning" />
        <BuilderWarningPanel title="Замены по оборудованию" description={details.equipmentAlternatives.join(' · ')} tone="success" />
      </div>
    </div>
  )
}

function AccordionCard({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="rounded-[28px] border border-white/8 bg-[#111419] p-5">
      <div className="font-semibold text-white">{title}</div>
      <ul className="mt-4 space-y-3 text-sm leading-7 text-white/72">
        {items.map((item) => (
          <li key={item} className="flex gap-3">
            <span className="mt-[10px] inline-flex h-2 w-2 shrink-0 rounded-full bg-[var(--broadcast-accent,#d6b05f)]" />
            {item}
          </li>
        ))}
      </ul>
    </section>
  )
}

function MetricCard({ title, value, caption }: { title: string; value: string; caption: string }) {
  return (
    <section className="rounded-[28px] border border-white/8 bg-[#111419] p-5">
      <div className="flex items-center gap-2 text-white/45"><Clock3 className="h-4 w-4" />{title}</div>
      <div className="mt-3 font-display text-4xl font-bold text-white">{value}</div>
      <div className="mt-2 text-sm text-white/45">{caption}</div>
    </section>
  )
}
