import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Ban, Clock3, Play, Star } from 'lucide-react'
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
import { BuilderWarningPanel, CalibrationStatusBlock, ExerciseActionBar, ExerciseVideoPlayer, FilterChip, LoadSettingsControl, MuscleMapCompact, MuscleStatusList } from '@/shared/ui/stage2/screen-components'
import { useAppStore } from '@/stores/app-store'

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
  const [selectedGender, setSelectedGender] = useState<'male' | 'female'>('male')
  const [selectedView, setSelectedView] = useState<'side' | 'front'>('side')

  useEffect(() => {
    setSettings(data?.loadSettings ?? null)
    if (slug) {
      setSelectedExerciseSlug(slug)
    }
  }, [data?.loadSettings, setSelectedExerciseSlug, slug])

  useEffect(() => {
    if (data?.videos.length) {
      setSelectedGender(data.videos[0].gender)
      setSelectedView(data.videos[0].view)
    }
  }, [data?.videos])

  if (!data || !machine) {
    return null
  }

  const hasVideo = scenario !== 'no-video' && data.videos.length > 0
  const blocked = machine.machineState === 'blocked'
  const availableGenders = Array.from(new Set(data.videos.map((video) => video.gender)))
  const availableViews = Array.from(new Set(data.videos.filter((video) => video.gender === selectedGender).map((video) => video.view)))
  const activeVideo = hasVideo ? data.videos.find((video) => video.gender === selectedGender && video.view === selectedView) ?? data.videos[0] : null

  return (
    <FormaShell userName={getUserName(resolvedUserId)} machine={machine} onStop={() => setEmergencyStopActive(true)}>
      {data.blacklisted ? <WarningBanner title="Упражнение в чёрном списке" description="Пользователь ранее отметил упражнение как нежелательное. Экран остаётся доступным, но старт лучше заменить альтернативой." /> : null}
      {blocked ? <BlockingAlert title="Старт упражнения заблокирован" description="Полноэкранная карточка доступна, но запуск временно недоступен из-за состояния тренажёра." /> : null}

      <div className="glass-panel rounded-[34px] p-6 xl:p-8">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <Button variant="ghost" iconLeft={<ArrowLeft className="h-4 w-4" />} onClick={() => navigate('/catalog')}>
              Назад
            </Button>
            <div className="mt-4 text-sm uppercase tracking-[0.24em] text-white/35">Карточка упражнения</div>
            <h1 className="mt-3 font-display text-6xl font-bold tracking-[-0.07em] text-white">{data.name}</h1>
            <div className="mt-2 text-3xl text-white/45">{data.secondaryName}</div>
            <div className="mt-5 flex flex-wrap gap-2">
              {data.muscles.map((item) => (
                <FilterChip key={item} label={item} active />
              ))}
              <FilterChip label={data.difficultyLabel} active />
              <FilterChip label={data.equipment} active />
              <FilterChip label={data.grips} active />
            </div>
            <div className="mt-6 flex flex-wrap gap-3">
              <Button iconLeft={<Play className="h-4 w-4" />} disabled={blocked} onClick={() => navigate(`/exercise-setup?source=catalog&slug=${encodeURIComponent(data.slug)}`)}>
                Начать упражнение
              </Button>
              <Button variant="secondary" onClick={() => navigate('/builder')}>Добавить в тренировку</Button>
              <Button variant="secondary" iconLeft={<Star className="h-4 w-4" />} onClick={() => toggleFavoriteExercise(data.slug)}>
                {data.favorite ? 'В избранном' : 'В избранное'}
              </Button>
              <Button variant="secondary" iconLeft={<Ban className="h-4 w-4" />} onClick={() => toggleBlacklistedExercise(data.slug)}>
                {data.blacklisted ? 'Убрать из чёрного списка' : 'В чёрный список'}
              </Button>
            </div>
          </div>

          <div className="grid w-full gap-6 xl:max-w-[720px]">
            <div className="overflow-hidden rounded-[32px] border border-[#d6b05f]/20 bg-[#0d1116]">
              <div className="bg-[radial-gradient(circle_at_top,rgba(214,176,95,0.18),transparent_38%),linear-gradient(180deg,#161b22,#0a0c0f)] p-5">
                {hasVideo && activeVideo ? (
                  <ExerciseVideoPlayer videoUrl={activeVideo.url} videoLabel={activeVideo.label} />
                ) : (
                  <div className="flex aspect-video items-center rounded-[24px] border border-white/8 bg-[linear-gradient(180deg,#161b22,#0a0c0f)] p-5">
                    <WarningBanner title="Видео недоступно" description="Для этого упражнения в stage 2 включено состояние без локального видео. Вместо него доступны техника выполнения и текстовые подсказки." />
                  </div>
                )}
              </div>
              <div className="grid gap-3 border-t border-white/8 p-4 md:grid-cols-2">
                <div className="flex flex-wrap gap-2">
                  {(['male', 'female'] as const).map((gender) => (
                    <FilterChip key={gender} label={gender === 'male' ? 'Мужчина' : 'Женщина'} active={selectedGender === gender} onClick={() => setSelectedGender(gender)} />
                  ))}
                </div>
                <div className="flex flex-wrap gap-2">
                  {(['side', 'front'] as const).map((view) => (
                    <FilterChip key={view} label={view === 'side' ? 'Сбоку' : 'Спереди'} active={selectedView === view} onClick={() => setSelectedView(view)} />
                  ))}
                </div>
              </div>
              {hasVideo ? (
                <div className="px-4 pb-4 text-sm text-white/45">
                  Доступные варианты: {availableGenders.map((gender) => (gender === 'male' ? 'мужчина' : 'женщина')).join(', ')}; {availableViews.map((view) => (view === 'side' ? 'сбоку' : 'спереди')).join(', ')}.
                </div>
              ) : null}
            </div>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap gap-2 border-t border-white/8 pt-5">
          {tabs.map((tab) => (
            <FilterChip key={tab.id} label={tab.label} active={tab.id === activeTab} onClick={() => setSearchParams((current) => {
              const next = new URLSearchParams(current)
              next.set('tab', tab.id)
              return next
            })} />
          ))}
        </div>

        <div className="mt-6">
          {activeTab === 'overview' ? <OverviewTab details={data} /> : null}
          {activeTab === 'technique' ? <TechniqueTab details={data} /> : null}
          {activeTab === 'muscles' ? <MusclesTab details={data} /> : null}
          {activeTab === 'load' ? <LoadTab details={data} settings={settings ?? data.loadSettings} onChange={setSettings} /> : null}
          {activeTab === 'history' ? <HistoryTab details={data} /> : null}
          {activeTab === 'similar' ? <SimilarTab details={data} onOpen={(nextSlug) => navigate(`/catalog/${encodeURIComponent(nextSlug)}`)} /> : null}
        </div>
      </div>

      <ExerciseActionBar onStart={() => navigate(`/exercise-setup?source=catalog&slug=${encodeURIComponent(data.slug)}`)} onAdd={() => navigate('/builder')} onOpenFullScreen={() => navigate('/catalog')} />

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}

function OverviewTab({ details }: { details: ExerciseDetails }) {
  return (
    <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
      <div className="space-y-6">
        <section className="rounded-[30px] border border-white/8 bg-[#111419] p-6">
          <div className="font-display text-3xl font-bold text-white">Описание</div>
          <p className="mt-4 max-w-3xl text-base leading-8 text-white/68">{details.description}</p>
          <div className="mt-6 rounded-[26px] border border-white/8 bg-white/4 p-5">
            <div className="font-semibold text-white">Кратко</div>
            <ol className="mt-4 space-y-3 text-sm leading-7 text-white/72">
              {details.shortSteps.map((step, index) => (
                <li key={step} className="flex gap-3">
                  <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[#d6b05f]/28 text-xs text-[#f1d391]">{index + 1}</span>
                  {step}
                </li>
              ))}
            </ol>
          </div>
        </section>
      </div>

      <div className="space-y-6">
        <div className="rounded-[30px] border border-[#d6b05f]/18 bg-[#18140b] p-6 text-[#f2cf87]">
          <div className="text-sm uppercase tracking-[0.24em]">Совместимость сегодня</div>
          <div className="mt-3 text-3xl font-semibold">{details.compatibility.title}</div>
          <p className="mt-3 text-sm leading-7 text-[#f2cf87]/84">{details.compatibility.description}</p>
        </div>
        <MuscleStatusList muscles={details.compatibility.affectedMuscles} />
      </div>
    </div>
  )
}

function TechniqueTab({ details }: { details: ExerciseDetails }) {
  return (
    <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
      <div className="space-y-4">
        <AccordionCard title="Подготовка" items={details.guide.setup} />
        <AccordionCard title="Как выполнять" items={details.guide.howToPerform} />
        <AccordionCard title="Техника" items={details.guide.technique} />
        <AccordionCard title="Чего избегать" items={details.guide.thingsToAvoid} />
      </div>
      <div className="space-y-4">
        <BuilderWarningPanel title="Ключевые подсказки" description={details.guide.keyTips.join(' ')} tone="success" />
        <BuilderWarningPanel title="Частые ошибки" description={details.guide.thingsToAvoid.join(' ')} tone="warning" />
      </div>
    </div>
  )
}

function MusclesTab({ details }: { details: ExerciseDetails }) {
  return <MuscleMapCompact primary={details.primaryMuscles} secondary={details.secondaryMuscles} stabilizers={details.stabilizers} />
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
                  <div className={cn('h-full rounded-full bg-linear-to-r from-[#b5852f] to-[#f0d08c]', getProgressWidthClass(point.value))} />
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
        <MetricCard title="Средний рабочий вес" value={`${Math.round(details.loadProgress.reduce((sum, point) => sum + point.value, 0) / details.loadProgress.length)} кг`} caption="по 5 последним тренировкам" />
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
                {item.muscles.map((muscle) => (
                  <FilterChip key={`${item.slug}-${muscle}`} label={muscle} />
                ))}
                <FilterChip label={item.equipment} />
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
            <span className="mt-[10px] inline-flex h-2 w-2 shrink-0 rounded-full bg-[#d6b05f]" />
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