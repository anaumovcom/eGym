import { useQuery } from '@tanstack/react-query'
import { ArrowRight, CircleAlert, Search as SearchIcon, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { ExerciseCatalogResponse } from '@/entities/exercise/model/types'
import type { QuickStartData } from '@/entities/quick-start/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import { apiGet } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { BlockingAlert, WarningBanner } from '@/shared/ui/status/status-components'
import { CalibrationStatusBlock, ExerciseActionBar, ExercisePreviewCard, FilterChip, LoadSettingsControl, MuscleStatusList, SearchField, SectionIntro, SupportCard } from '@/shared/ui/stage2/screen-components'
import { useAppStore } from '@/stores/app-store'

type FilterMode = 'recommended' | 'recent' | 'favorites'

const audienceTabs: Array<{ id: FilterMode; label: string }> = [
  { id: 'recommended', label: 'Рекомендовано' },
  { id: 'recent', label: 'Последние' },
  { id: 'favorites', label: 'Избранные' },
]

function getUserName(userId: string | null) {
  if (userId === 'elena') {
    return 'Елена'
  }

  if (userId === 'guest') {
    return 'Гость'
  }

  return 'Алексей'
}

function isStartBlocked(machine: MachineHealth) {
  return machine.machineState !== 'ready' || machine.leftDrive === 'error' || machine.rightDrive === 'error' || machine.safety === 'emergency_stop'
}

function resolveCalibration(value: 'ready' | 'required' | 'unavailable' | 'recommended') {
  return value === 'unavailable' ? 'not-needed' : 'saved'
}

export function QuickStartScreen() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const selectedExerciseSlug = useAppStore((state) => state.selectedExerciseSlug)
  const favoriteExerciseSlugs = useAppStore((state) => state.favoriteExerciseSlugs)
  const blacklistedExerciseSlugs = useAppStore((state) => state.blacklistedExerciseSlugs)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const setSelectedExerciseSlug = useAppStore((state) => state.setSelectedExerciseSlug)
  const toggleFavoriteExercise = useAppStore((state) => state.toggleFavoriteExercise)

  const scenario = searchParams.get('scenario') ?? 'default'
  const machineScenario = scenario === 'machine-warning' ? 'warning' : scenario === 'machine-blocked' ? 'blocked' : 'ready'
  const resolvedUserId = scenario === 'guest' ? 'guest' : selectedUserId ?? 'alexey'
  const forcedSelected = scenario === 'blacklist' ? blacklistedExerciseSlugs[0] ?? 'smith-machine-bench-press' : selectedExerciseSlug

  const { data } = useQuery({
    queryKey: ['quick-start', resolvedUserId, forcedSelected, favoriteExerciseSlugs.join(','), blacklistedExerciseSlugs.join(',')],
    queryFn: () =>
      apiGet<QuickStartData>(
        `/api/quick-start?userId=${encodeURIComponent(resolvedUserId)}&selected=${encodeURIComponent(forcedSelected ?? '')}&favorites=${encodeURIComponent(favoriteExerciseSlugs.join(','))}&blacklist=${encodeURIComponent(blacklistedExerciseSlugs.join(','))}`,
      ),
  })

  const { data: machine } = useQuery({
    queryKey: ['quick-start-machine', machineScenario],
    queryFn: () => apiGet<MachineHealth>(`/api/machine/status?scenario=${encodeURIComponent(machineScenario)}`),
  })

  const search = searchParams.get('search') ?? ''
  const [activeTab, setActiveTab] = useState<FilterMode>('recommended')

  const { data: searchResults } = useQuery({
    queryKey: ['quick-start-search', resolvedUserId, search, favoriteExerciseSlugs.join(','), blacklistedExerciseSlugs.join(',')],
    queryFn: () =>
      apiGet<ExerciseCatalogResponse>(
        `/api/exercises?userId=${encodeURIComponent(resolvedUserId)}&search=${encodeURIComponent(search)}&favorites=${encodeURIComponent(favoriteExerciseSlugs.join(','))}&blacklist=${encodeURIComponent(blacklistedExerciseSlugs.join(','))}`,
      ),
    enabled: search.trim().length > 0,
  })

  const [settings, setSettings] = useState(data?.selectedExercise?.settings ?? null)

  useEffect(() => {
    setSettings(data?.selectedExercise?.settings ?? null)
  }, [data?.selectedExercise])

  const visibleExercises = useMemo(() => {
    if (search.trim().length > 0) {
      return searchResults?.items.slice(0, 6) ?? []
    }

    if (!data) {
      return []
    }

    switch (activeTab) {
      case 'recent':
        return data.recent
      case 'favorites':
        return data.favorites
      case 'recommended':
      default:
        return data.recommended
    }
  }, [activeTab, data, search, searchResults?.items])

  if (!data || !machine) {
    return null
  }

  const selectedExercise = data.selectedExercise
  const currentSettings = settings ?? selectedExercise?.settings ?? null
  const blocked = isStartBlocked(machine)

  return (
    <FormaShell userName={getUserName(resolvedUserId)} machine={machine} onStop={() => setEmergencyStopActive(true)}>
      <SectionIntro
        title="Быстрый старт"
        description="Выберите упражнение, подтвердите нагрузку и начните тренировку. Экран использует mock API и реальные slug'и упражнений из каталога."
        actions={
          <Button variant="secondary" iconLeft={<Sparkles className="h-4 w-4" />} onClick={() => navigate('/catalog')}>
            Открыть каталог
          </Button>
        }
      />

      {scenario === 'guest' ? (
        <WarningBanner title="Гостевой режим" description="Персональная история и адаптация по усталости ограничены. Можно выбрать упражнение и перейти к настройке без профиля." />
      ) : null}

      {blocked ? (
        <BlockingAlert title="Тренажёр не готов" description="Сценарий mock API блокирует старт: сначала нужно восстановить доступность приводов и системы безопасности." />
      ) : machine.machineState === 'warning' ? (
        <WarningBanner title="Тренажёр требует внимания" description="Один из приводов работает с предупреждением. Рекомендуется запустить диагностику перед стартом упражнения." />
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.45fr_0.95fr]">
        <section className="space-y-6">
          <div className="glass-panel rounded-[32px] p-5">
            <div className="rounded-[28px] border border-[#d6b05f]/18 bg-[linear-gradient(135deg,rgba(214,176,95,0.14),rgba(255,255,255,0.03))] p-5">
              <div className="text-sm uppercase tracking-[0.24em] text-white/38">Рекомендация дня</div>
              <div className="mt-3 font-display text-4xl font-bold text-white">{data.recommendation.title}</div>
              <p className="mt-3 max-w-3xl text-base leading-8 text-white/68">{data.recommendation.description}</p>
              <div className="mt-4">
                <Button variant="secondary" onClick={() => navigate('/today')}>{data.recommendation.cta}</Button>
              </div>
            </div>

            <div className="mt-5 grid gap-4 xl:grid-cols-[1fr_auto] xl:items-center">
              <SearchField value={search} placeholder="Найти упражнение..." onChange={(value) => setSearchParams((current) => {
                const next = new URLSearchParams(current)
                if (value) {
                  next.set('search', value)
                } else {
                  next.delete('search')
                }
                return next
              })} />
              <div className="flex flex-wrap gap-3">
                {audienceTabs.map((tab) => (
                  <FilterChip key={tab.id} label={tab.label} active={search ? false : activeTab === tab.id} onClick={() => setActiveTab(tab.id)} />
                ))}
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {data.filterGroups.muscleFocus.map((item) => (
                <FilterChip key={item} label={item} />
              ))}
              {data.filterGroups.equipment.map((item) => (
                <FilterChip key={item} label={item} />
              ))}
            </div>
          </div>

          <div>
            <div className="mb-4 flex items-center justify-between">
              <div>
                <div className="text-sm uppercase tracking-[0.24em] text-white/35">Список упражнений</div>
                <div className="mt-2 font-display text-3xl font-bold text-white">
                  {search ? `Результаты поиска: ${searchResults?.total ?? 0}` : activeTab === 'recommended' ? 'Рекомендовано сегодня' : activeTab === 'recent' ? 'Последние упражнения' : 'Избранные упражнения'}
                </div>
              </div>
              <div className="flex items-center gap-2 text-sm text-white/42">
                <SearchIcon className="h-4 w-4" />
                {search ? 'Поиск по русским и английским названиям' : 'Фильтры готовы для мокового сценария'}
              </div>
            </div>

            <div className="grid gap-4">
              {visibleExercises.map((exercise) => (
                <ExercisePreviewCard
                  key={exercise.slug}
                  exercise={exercise}
                  listMode
                  onOpen={() => setSelectedExerciseSlug(exercise.slug)}
                  onFavorite={() => toggleFavoriteExercise(exercise.slug)}
                />
              ))}
            </div>
          </div>
        </section>

        <aside className="space-y-6">
          <section className="glass-panel rounded-[32px] p-5">
            <div className="text-sm uppercase tracking-[0.24em] text-white/35">Выбранное упражнение</div>
            {selectedExercise ? (
              <>
                <div className="mt-3 font-display text-4xl font-bold text-white">{selectedExercise.exercise.name}</div>
                <div className="mt-1 text-white/45">{selectedExercise.exercise.secondaryName}</div>
                <div className="mt-4 flex flex-wrap gap-2">
                  {selectedExercise.exercise.muscles.slice(0, 3).map((item) => (
                    <FilterChip key={item} label={item} active />
                  ))}
                </div>

                <div className="mt-5 rounded-[26px] border border-white/8 bg-white/4 p-4">
                  <div className="text-sm uppercase tracking-[0.22em] text-white/34">Последний результат</div>
                  <div className="mt-2 text-2xl font-semibold text-white">{selectedExercise.lastResult}</div>
                  <div className="mt-3 text-sm leading-7 text-white/65">{selectedExercise.formaRecommendation}</div>
                </div>

                {selectedExercise.warnings.map((warning) =>
                  warning.tone === 'blocked' ? (
                    <BlockingAlert key={warning.title} title={warning.title} description={warning.description} />
                  ) : (
                    <WarningBanner key={warning.title} title={warning.title} description={warning.description} />
                  ),
                )}

                <div className="mt-5 rounded-[28px] border border-white/8 bg-white/4 p-4">
                  <div className="mb-3 text-sm uppercase tracking-[0.24em] text-white/35">Готовность мышц</div>
                  <MuscleStatusList
                    muscles={selectedExercise.readiness.map((item, index) => ({
                      name: item.label,
                      status: item.tone === 'recommended' ? 'ready' : item.tone === 'caution' ? 'medium' : 'light',
                      score: 100 - index * 18,
                    }))}
                  />
                </div>

                {currentSettings ? (
                  <div className="mt-5 space-y-5">
                    <LoadSettingsControl
                      settings={currentSettings}
                      onAdjustWeight={(delta) => setSettings((state) => (state ? { ...state, weight: Math.max(0, state.weight + delta) } : state))}
                      onAdjustSets={(delta) => setSettings((state) => (state ? { ...state, sets: Math.max(1, state.sets + delta) } : state))}
                      onAdjustReps={(delta) => setSettings((state) => (state ? { ...state, reps: Math.max(1, state.reps + delta) } : state))}
                      onAdjustRest={(delta) => setSettings((state) => (state ? { ...state, restSeconds: Math.max(15, state.restSeconds + delta) } : state))}
                      onModeChange={(mode) => setSettings((state) => (state ? { ...state, mode } : state))}
                    />
                    <CalibrationStatusBlock calibration={currentSettings.calibration} />
                  </div>
                ) : null}

                <div className="mt-5">
                  <ExerciseActionBar
                    onStart={() => {
                      if (!blocked && selectedExercise.exercise.slug) {
                        navigate(`/exercise-setup?source=quick-start&slug=${encodeURIComponent(selectedExercise.exercise.slug)}&calibration=${encodeURIComponent(resolveCalibration(currentSettings?.calibration ?? selectedExercise.settings.calibration))}`)
                      }
                    }}
                    onAdd={() => navigate('/builder')}
                    onOpenFullScreen={() => navigate(`/catalog/${encodeURIComponent(selectedExercise.exercise.slug)}`)}
                  />
                </div>

                <Button
                  className="mt-5 w-full"
                  disabled={blocked}
                  iconLeft={<ArrowRight className="h-4 w-4" />}
                  onClick={() => navigate(`/exercise-setup?source=quick-start&slug=${encodeURIComponent(selectedExercise.exercise.slug)}&calibration=${encodeURIComponent(resolveCalibration(currentSettings?.calibration ?? selectedExercise.settings.calibration))}`)}
                >
                  {blocked ? 'Старт временно недоступен' : `Начать: ${selectedExercise.exercise.name}`}
                </Button>
              </>
            ) : (
              <div className="rounded-[28px] border border-dashed border-white/10 bg-white/4 p-6 text-white/52">Выберите упражнение в списке слева.</div>
            )}
          </section>

          <SupportCard />
        </aside>
      </div>

      {scenario === 'blacklist' ? (
        <WarningBanner title="Сценарий чёрного списка" description="Через query-параметр показано состояние, когда выбранное упражнение помечено как нежелательное для пользователя." />
      ) : null}

      {scenario === 'machine-warning' ? (
        <div className={cn('rounded-[28px] border px-5 py-4 text-sm leading-7', blocked ? 'border-[#b83d38]/30 bg-[#311615] text-[#ffb3a9]' : 'border-[#d6b05f]/25 bg-[#241b0d] text-[#f2cf87]')}>
          <div className="flex items-center gap-3 font-semibold">
            <CircleAlert className="h-4 w-4" />
            Дополнительное предупреждение mock-сценария
          </div>
          <div className="mt-2">Состояния быстрого старта доступны через query параметр scenario: guest, blacklist, machine-warning, machine-blocked.</div>
        </div>
      ) : null}

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}