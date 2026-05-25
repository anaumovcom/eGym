import { useQuery } from '@tanstack/react-query'
import { Activity, ArrowRightLeft, Camera, Play, Replace, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { ExerciseDetails } from '@/entities/exercise/model/types'
import type { TodayWorkoutData } from '@/entities/workout/model/types'
import { apiGet, apiPut } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { BlockingAlert, WarningBanner } from '@/shared/ui/status/status-components'
import { BuilderWarningPanel, CalibrationStatusBlock, LoadSettingsControl, MuscleMapCompact, WorkoutPlanList } from '@/shared/ui/stage2/screen-components'
import { ExercisePickerModal } from '@/shared/ui/training/exercise-picker-modal'
import { useAppStore } from '@/stores/app-store'

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

export function TodayWorkoutScreen() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const selectedExerciseSlug = useAppStore((state) => state.selectedExerciseSlug)
  const favoriteExerciseSlugs = useAppStore((state) => state.favoriteExerciseSlugs)
  const blacklistedExerciseSlugs = useAppStore((state) => state.blacklistedExerciseSlugs)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const setSelectedExerciseSlug = useAppStore((state) => state.setSelectedExerciseSlug)

  const scenario = searchParams.get('scenario') ?? 'planned'
  const selected = searchParams.get('selected') ?? selectedExerciseSlug ?? 'machine-pulldown'
  const resolvedUserId = selectedUserId ?? 'alexey'

  const { data } = useQuery({
    queryKey: ['today-workout', resolvedUserId, scenario, selected, favoriteExerciseSlugs.join(','), blacklistedExerciseSlugs.join(',')],
    queryFn: () =>
      apiGet<TodayWorkoutData>(
        `/api/today?userId=${encodeURIComponent(resolvedUserId)}&scenario=${encodeURIComponent(scenario)}&selected=${encodeURIComponent(selected)}&favorites=${encodeURIComponent(favoriteExerciseSlugs.join(','))}&blacklist=${encodeURIComponent(blacklistedExerciseSlugs.join(','))}`,
      ),
  })

  const [exerciseRows, setExerciseRows] = useState(data?.exerciseRows ?? [])
  const [selectedExercise, setSelectedExercise] = useState(data?.selectedExercise ?? null)
  const [settings, setSettings] = useState(data?.selectedExercise.settings ?? null)
  const [replaceModalOpen, setReplaceModalOpen] = useState(false)

  useEffect(() => {
    setExerciseRows(data?.exerciseRows ?? [])
    setSelectedExercise(data?.selectedExercise ?? null)
    setSettings(data?.selectedExercise.settings ?? null)
    setSelectedExerciseSlug(selected)
  }, [data?.exerciseRows, data?.selectedExercise, data?.selectedExercise.settings, selected, setSelectedExerciseSlug])

  if (!data || !selectedExercise) {
    return null
  }

  async function handleReplaceExercise(details: ExerciseDetails) {
    const primaryMuscles = details.primaryMuscles.length > 0 ? details.primaryMuscles : details.muscles
    const latestHistory = details.history[0]
    const nextLastResult = latestHistory
      ? `${latestHistory.weight} • ${latestHistory.reps} • ${latestHistory.sets} ${latestHistory.sets === 1 ? 'подход' : latestHistory.sets < 5 ? 'подхода' : 'подходов'}`
      : 'Нет истории'
    const nextLoad = details.loadSettings.weight > 0 ? `${details.loadSettings.weight} кг × ${details.loadSettings.reps}` : `${details.loadSettings.reps} повторений`

    const nextRows = exerciseRows.map((row) =>
      row.id === selected
        ? {
            ...row,
            id: details.slug,
            slug: details.slug,
            name: details.name,
            muscles: primaryMuscles.join(', '),
            load: nextLoad,
            rest: `${details.loadSettings.restSeconds} сек`,
            note: details.loadSettings.recommendation,
          }
        : row,
    )

    await apiPut('/api/today/plan', {
      userId: resolvedUserId,
      slugs: nextRows.map((row) => row.slug),
    })

    setExerciseRows(nextRows)
    setSelectedExercise((current) =>
      current
        ? {
            ...current,
            id: details.slug,
            ...current,
            slug: details.slug,
            name: details.name,
            muscles: primaryMuscles.join(', '),
            lastResult: nextLastResult,
            formaRecommendation: details.loadSettings.recommendation,
            settings: details.loadSettings,
            alerts: details.compatibility.description ? [details.compatibility.description] : [],
          }
        : current,
    )
    setSettings(details.loadSettings)
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.set('selected', details.slug)
      return next
    })
    setSelectedExerciseSlug(details.slug)
    setReplaceModalOpen(false)
  }

  return (
    <FormaShell userName={getUserName(resolvedUserId)} machine={data.machine} onStop={() => setEmergencyStopActive(true)}>
      {data.warnings.map((warning) =>
        warning.tone === 'blocked' ? <BlockingAlert key={warning.title} title={warning.title} description={warning.description} /> : <WarningBanner key={warning.title} title={warning.title} description={warning.description} />,
      )}

      <div className="grid gap-6 xl:grid-cols-[1.25fr_0.75fr]">
        <section className="glass-panel rounded-[34px] p-6 xl:p-8">
          <div className="grid gap-6 xl:grid-cols-[220px_1fr]">
            <div className="flex flex-col justify-between rounded-[30px] border border-[#d6b05f]/18 bg-[linear-gradient(180deg,rgba(214,176,95,0.12),rgba(255,255,255,0.03))] p-5">
              <div>
                <div className="text-sm uppercase tracking-[0.24em] text-white/35">Готовность</div>
                <div className="mt-4 font-display text-6xl font-bold text-white">{data.readinessPercent}%</div>
                <div className="mt-2 text-white/55">{data.readinessPercent >= 70 ? 'Хорошая готовность' : data.readinessPercent >= 50 ? 'Нужен контроль' : 'Восстановление'}</div>
              </div>
              <div className="mt-5 text-sm text-white/48">План построен с учётом целей, усталости мышц и последних результатов.</div>
            </div>

            <div>
              <div className="text-sm uppercase tracking-[0.24em] text-white/35">Сегодняшняя тренировка</div>
              <div className="mt-2 font-display text-5xl font-bold tracking-[-0.06em] text-white">{data.title}</div>
              <p className="mt-3 max-w-3xl text-base leading-8 text-white/68">{data.subtitle}</p>
              <div className="mt-5 grid gap-4 md:grid-cols-3">
                <MetricBlock value={`${data.summary.exercises}`} label="упражнений" />
                <MetricBlock value={`${data.summary.sets}`} label="подходов" />
                <MetricBlock value={data.summary.duration} label="длительность" />
              </div>
              <div className="mt-5 flex flex-wrap gap-3">
                <Button iconLeft={<Play className="h-4 w-4" />} disabled={data.startState === 'blocked'} onClick={() => navigate(`/exercise-setup?source=today&slug=${encodeURIComponent(data.selectedExercise.slug)}&photo=before`)}>
                  {data.mainAction}
                </Button>
                <Button variant="secondary" iconLeft={<Camera className="h-4 w-4" />} onClick={() => navigate('/photo-progress?source=today&photo=manual')}>
                  Фотофиксация
                </Button>
                <Button variant="secondary" iconLeft={<ArrowRightLeft className="h-4 w-4" />} onClick={() => navigate('/calendar')}>
                  Открыть в календаре
                </Button>
              </div>
            </div>
          </div>
        </section>

        <aside className="glass-panel rounded-[34px] p-6">
          <div className="text-sm uppercase tracking-[0.24em] text-white/35">Состояние тренажёра</div>
          <div className="mt-3 rounded-[24px] border border-[#57c968]/18 bg-[#122b1d] p-4 text-[#92e09a]">{data.machine.machineLabel}</div>
          <div className="mt-4 space-y-3 text-sm text-white/72">
            <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Левый привод</span><span>{data.machine.leftDrive === 'connected' ? 'Подключён' : data.machine.leftDrive}</span></div>
            <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Правый привод</span><span>{data.machine.rightDrive === 'connected' ? 'Подключён' : data.machine.rightDrive}</span></div>
            <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Безопасность</span><span>{data.machine.safety === 'enabled' ? 'Активна' : data.machine.safety}</span></div>
            <div className="rounded-2xl border border-white/8 bg-white/4 px-4 py-3">{data.machine.calibration}</div>
          </div>
        </aside>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <WorkoutPlanList
          rows={exerciseRows}
          activeId={selectedExercise.id}
          onSelect={(id) =>
            setSearchParams((current) => {
              const next = new URLSearchParams(current)
              next.set('selected', id)
              return next
            })
          }
          footer={
            <div className="flex flex-wrap gap-3">
              {data.quickActions.map((action) => (
                <Button key={action} variant="secondary">{action}</Button>
              ))}
            </div>
          }
        />

        <aside className="space-y-6">
          <section className="glass-panel rounded-[32px] p-5">
            <div className="text-sm uppercase tracking-[0.24em] text-white/35">Выбранное упражнение</div>
            <div className="mt-3 font-display text-4xl font-bold text-white">{selectedExercise.name}</div>
            <div className="mt-1 text-white/45">{selectedExercise.muscles}</div>

            <div className="mt-5 grid gap-3 md:grid-cols-2">
              <MetricBlock value={selectedExercise.lastResult} label="последний результат" />
              <MetricBlock value={selectedExercise.formaRecommendation} label="рекомендация Forma" />
            </div>

            {selectedExercise.alerts.length > 0 ? (
              <div className="mt-4 space-y-3">
                {selectedExercise.alerts.map((alert) => (
                  <BuilderWarningPanel key={alert} title="Внимание к упражнению" description={alert} tone="warning" />
                ))}
              </div>
            ) : null}

            {settings ? (
              <div className="mt-5 space-y-5">
                <LoadSettingsControl
                  settings={settings}
                  onAdjustWeight={(delta) => setSettings((state) => (state ? { ...state, weight: Math.max(0, state.weight + delta) } : state))}
                  onAdjustSets={(delta) => setSettings((state) => (state ? { ...state, sets: Math.max(1, state.sets + delta) } : state))}
                  onAdjustReps={(delta) => setSettings((state) => (state ? { ...state, reps: Math.max(1, state.reps + delta) } : state))}
                  onAdjustRest={(delta) => setSettings((state) => (state ? { ...state, restSeconds: Math.max(15, state.restSeconds + delta) } : state))}
                  onModeChange={(mode) => setSettings((state) => (state ? { ...state, mode } : state))}
                />
                <CalibrationStatusBlock calibration={settings.calibration} />
              </div>
            ) : null}

            <div className="mt-5 grid gap-3 md:grid-cols-2">
              <Button variant="secondary" iconLeft={<Replace className="h-4 w-4" />} onClick={() => setReplaceModalOpen(true)}>
                Заменить упражнение
              </Button>
              <Button variant="secondary" iconLeft={<Activity className="h-4 w-4" />} onClick={() => navigate(`/catalog/${encodeURIComponent(selectedExercise.slug)}`)}>
                Открыть карточку
              </Button>
            </div>
          </section>

          <section className="glass-panel rounded-[32px] p-5">
            <div className="text-sm uppercase tracking-[0.24em] text-white/35">Мышцы тренировки</div>
            <div className="mt-3 font-display text-3xl font-bold text-white">Баланс нагрузки</div>
            <div className="mt-5">
              <MuscleMapCompact primary={['Спина', 'Бицепс']} secondary={['Предплечья']} stabilizers={['Кор']} figureGender={resolvedUserId === 'elena' ? 'female' : 'male'} />
            </div>
          </section>

          <section className="glass-panel rounded-[32px] p-5">
            <div className="text-sm uppercase tracking-[0.24em] text-white/35">Прогресс тренировки</div>
            <div className="mt-4 rounded-[26px] border border-[#d6b05f]/18 bg-[#18140b] p-5 text-[#f2cf87]">
              <div className="font-display text-5xl font-bold">{data.progress.percent}%</div>
              <div className="mt-2 text-sm">Выполнено {data.progress.completedExercises} из {data.progress.totalExercises} упражнений</div>
              <div className="mt-2 text-sm">Осталось около {data.progress.minutesLeft} минут</div>
              <div className="mt-4">Следующий шаг: {data.progress.nextStep}</div>
            </div>
            {data.startState === 'planned' ? <BuilderWarningPanel title="Тренировка ещё не начата" description="Основная кнопка запустит первую позицию плана. При необходимости можно открыть карточку выбранного упражнения или заменить его." tone="success" /> : null}
            {data.startState === 'recovery' ? <BuilderWarningPanel title="Высокая усталость" description="Сценарий recovery показывает необходимость облегчить нагрузку, сократить объём или выбрать восстановительный день." tone="warning" /> : null}
            {data.startState === 'blocked' ? <BuilderWarningPanel title="Старт недоступен" description="Пока не восстановится готовность тренажёра, экран остаётся только в режиме просмотра плана и замены упражнений." tone="blocked" /> : null}
          </section>
        </aside>
      </div>

      {data.startState === 'planned' ? <WarningBanner title="Фото прогресса" description="В потоке этапа 2 уже заложен переход к логике фотофиксации перед первым упражнением, но без отдельного экрана выполнения." /> : null}
      {data.startState === 'completed' ? <WarningBanner title="Тренировка завершена" description="Тренировка завершена: старт больше не активен, но история и карточки упражнений остаются доступны." /> : null}
      {data.startState === 'in-progress' ? <div className="rounded-[28px] border border-[#d6b05f]/20 bg-[#21180d] px-5 py-4 text-[#f2cf87]"><div className="flex items-center gap-3 font-semibold"><TriangleAlert className="h-4 w-4" />Тренировка уже идёт</div><div className="mt-2 text-sm">Можно продолжить текущую сессию, быстро скорректировать нагрузку или заменить следующее упражнение.</div></div> : null}

      <ExercisePickerModal
        open={replaceModalOpen}
        onOpenChange={setReplaceModalOpen}
        userId={resolvedUserId}
        mode="replace"
        currentExerciseSlug={selectedExercise.slug}
        currentExerciseName={selectedExercise.name}
        onSelect={handleReplaceExercise}
      />

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}

function MetricBlock({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-[24px] border border-white/8 bg-white/4 p-4">
      <div className="font-display text-3xl font-bold text-white">{value}</div>
      <div className="mt-2 text-sm text-white/45">{label}</div>
    </div>
  )
}