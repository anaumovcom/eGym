import { useQuery } from '@tanstack/react-query'
import { ArrowUp, SlidersHorizontal } from 'lucide-react'
import { useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { ExerciseCatalogResponse, ExerciseDetails } from '@/entities/exercise/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import { apiGet } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { BlockingAlert, WarningBanner } from '@/shared/ui/status/status-components'
import { ExerciseDetailsModal, ExercisePreviewCard, FilterChip, SearchField, SectionIntro, SupportCard, ViewModeToggle } from '@/shared/ui/stage2/screen-components'
import { useAppStore } from '@/stores/app-store'

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

function updateMultiParam(searchParams: URLSearchParams, key: string, value: string) {
  const current = (searchParams.get(key) ?? '').split(',').filter(Boolean)
  const nextValues = current.includes(value) ? current.filter((item) => item !== value) : [...current, value]

  if (nextValues.length === 0) {
    searchParams.delete(key)
  } else {
    searchParams.set(key, nextValues.join(','))
  }
}

function parseList(value: string | null) {
  return value ? value.split(',').filter(Boolean) : []
}

export function ExerciseCatalogScreen() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const favoriteExerciseSlugs = useAppStore((state) => state.favoriteExerciseSlugs)
  const blacklistedExerciseSlugs = useAppStore((state) => state.blacklistedExerciseSlugs)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const toggleFavoriteExercise = useAppStore((state) => state.toggleFavoriteExercise)
  const toggleBlacklistedExercise = useAppStore((state) => state.toggleBlacklistedExercise)

  const search = searchParams.get('search') ?? ''
  const viewMode = searchParams.get('view') === 'list' ? 'list' : 'grid'
  const selectedSlug = searchParams.get('selected')
  const machineScenario = searchParams.get('machine') ?? 'ready'
  const resolvedUserId = selectedUserId ?? 'alexey'
  const selectedMuscles = parseList(searchParams.get('muscles'))
  const selectedEquipment = parseList(searchParams.get('equipment'))
  const selectedDifficulty = parseList(searchParams.get('difficulty'))

  const queryString = useMemo(() => {
    const params = new URLSearchParams()
    params.set('userId', resolvedUserId)
    if (search) {
      params.set('search', search)
    }
    if (selectedMuscles.length > 0) {
      params.set('muscles', selectedMuscles.join(','))
    }
    if (selectedEquipment.length > 0) {
      params.set('equipment', selectedEquipment.join(','))
    }
    if (selectedDifficulty.length > 0) {
      params.set('difficulty', selectedDifficulty.join(','))
    }
    params.set('favorites', favoriteExerciseSlugs.join(','))
    params.set('blacklist', blacklistedExerciseSlugs.join(','))
    return params.toString()
  }, [blacklistedExerciseSlugs, favoriteExerciseSlugs, resolvedUserId, search, selectedDifficulty, selectedEquipment, selectedMuscles])

  const { data } = useQuery({
    queryKey: ['exercise-catalog', queryString],
    queryFn: () => apiGet<ExerciseCatalogResponse>(`/api/exercises?${queryString}`),
  })

  const { data: machine } = useQuery({
    queryKey: ['catalog-machine', machineScenario],
    queryFn: () => apiGet<MachineHealth>(`/api/machine/status?scenario=${encodeURIComponent(machineScenario)}`),
  })

  const { data: details } = useQuery({
    queryKey: ['exercise-details-modal', resolvedUserId, selectedSlug, favoriteExerciseSlugs.join(','), blacklistedExerciseSlugs.join(',')],
    queryFn: () =>
      apiGet<ExerciseDetails>(
        `/api/exercises/${encodeURIComponent(selectedSlug ?? '')}?userId=${encodeURIComponent(resolvedUserId)}&favorites=${encodeURIComponent(favoriteExerciseSlugs.join(','))}&blacklist=${encodeURIComponent(blacklistedExerciseSlugs.join(','))}`,
      ),
    enabled: Boolean(selectedSlug),
  })

  if (!data || !machine) {
    return null
  }

  return (
    <FormaShell userName={getUserName(resolvedUserId)} machine={machine} onStop={() => setEmergencyStopActive(true)}>
      {machine.machineState === 'blocked' ? <BlockingAlert title="Каталог доступен, старт заблокирован" description="Можно смотреть упражнения и собирать план, но запуск тренировок временно недоступен из-за состояния тренажёра." /> : null}
      {machine.machineState === 'warning' ? <WarningBanner title="Тренажёр требует внимания" description="В этом mock-сценарии каталог и карточка упражнения остаются доступны, но перед стартом понадобится диагностика." /> : null}

      <SectionIntro
        title="Каталог упражнений"
        description="Найдите упражнение, посмотрите технику и добавьте его в план. Поиск работает по русским и английским названиям, оборудованию, сложности и мышцам."
        actions={
          <div className="flex flex-wrap gap-3">
            <ViewModeToggle
              mode={viewMode}
              onChange={(mode) =>
                setSearchParams((current) => {
                  const next = new URLSearchParams(current)
                  next.set('view', mode)
                  return next
                })
              }
            />
            <Button variant="secondary" iconLeft={<SlidersHorizontal className="h-4 w-4" />}>
              Фильтры
            </Button>
          </div>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1.6fr_0.7fr]">
        <section className="space-y-6">
          <div className="glass-panel rounded-[32px] p-5">
            <div className="grid gap-4 xl:grid-cols-[1fr_auto] xl:items-center">
              <SearchField
                value={search}
                placeholder="Найти упражнение..."
                onChange={(value) =>
                  setSearchParams((current) => {
                    const next = new URLSearchParams(current)
                    if (value) {
                      next.set('search', value)
                    } else {
                      next.delete('search')
                    }
                    return next
                  })
                }
              />
              <div className="text-sm text-white/42">Найдено упражнений: {data.total}</div>
            </div>

            <div className="mt-4 space-y-3">
              <div className="flex flex-wrap gap-2">
                {['Все', 'Для меня', 'Избранные'].map((chip) => (
                  <FilterChip key={chip} label={chip} active={chip === 'Все'} />
                ))}
              </div>
              <div className="flex flex-wrap gap-2">
                {data.availableFilters.muscles.slice(0, 8).map((item) => (
                  <FilterChip
                    key={item}
                    label={item}
                    active={selectedMuscles.includes(item)}
                    onClick={() =>
                      setSearchParams((current) => {
                        const next = new URLSearchParams(current)
                        updateMultiParam(next, 'muscles', item)
                        return next
                      })
                    }
                  />
                ))}
              </div>
              <div className="flex flex-wrap gap-2">
                {data.availableFilters.equipment.slice(0, 8).map((item) => (
                  <FilterChip
                    key={item}
                    label={item}
                    active={selectedEquipment.includes(item)}
                    onClick={() =>
                      setSearchParams((current) => {
                        const next = new URLSearchParams(current)
                        updateMultiParam(next, 'equipment', item)
                        return next
                      })
                    }
                  />
                ))}
              </div>
              <div className="flex flex-wrap gap-2">
                {data.availableFilters.difficulty.map((item) => (
                  <FilterChip
                    key={item}
                    label={item === 'Beginner' ? 'Новичок' : item === 'Intermediate' ? 'Средний' : 'Продвинутый'}
                    active={selectedDifficulty.includes(item)}
                    onClick={() =>
                      setSearchParams((current) => {
                        const next = new URLSearchParams(current)
                        updateMultiParam(next, 'difficulty', item)
                        return next
                      })
                    }
                  />
                ))}
              </div>
            </div>
          </div>

          <div className={viewMode === 'grid' ? 'grid gap-4 md:grid-cols-2 2xl:grid-cols-3' : 'grid gap-4'}>
            {data.items.slice(0, 24).map((exercise) => (
              <ExercisePreviewCard
                key={exercise.slug}
                exercise={exercise}
                listMode={viewMode === 'list'}
                onOpen={() =>
                  setSearchParams((current) => {
                    const next = new URLSearchParams(current)
                    next.set('selected', exercise.slug)
                    return next
                  })
                }
                onFavorite={() => toggleFavoriteExercise(exercise.slug)}
              />
            ))}
          </div>
        </section>

        <aside className="space-y-6">
          <div className="glass-panel rounded-[32px] p-5">
            <div className="font-display text-3xl font-bold text-white">Состояние каталога</div>
            <div className="mt-4 space-y-3 text-sm text-white/72">
              <p>Поиск читает нормализованный индекс из 1778 упражнений, сгенерированный из папки exercises.</p>
              <p>Через query-параметры можно переключать view, selected и machine-сценарий для проверки разных состояний.</p>
            </div>
            <Button className="mt-5 w-full" iconLeft={<ArrowUp className="h-4 w-4" />} onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
              Наверх
            </Button>
          </div>

          <div className="glass-panel rounded-[32px] p-5">
            <div className="font-display text-3xl font-bold text-white">Быстрые действия</div>
            <div className="mt-4 flex flex-col gap-3">
              <Button variant="secondary" onClick={() => navigate('/quick-start')}>Открыть быстрый старт</Button>
              <Button variant="secondary" onClick={() => navigate('/builder')}>Добавить упражнение в конструктор</Button>
              <Button variant="secondary" onClick={() => selectedSlug && toggleBlacklistedExercise(selectedSlug)}>Переключить чёрный список</Button>
            </div>
          </div>

          <SupportCard />
        </aside>
      </div>

      {details ? (
        <ExerciseDetailsModal
          exercise={details}
          open={Boolean(selectedSlug)}
          onOpenChange={(open) => {
            if (!open) {
              setSearchParams((current) => {
                const next = new URLSearchParams(current)
                next.delete('selected')
                return next
              })
            }
          }}
          onStart={() => navigate(`/exercise-setup?source=catalog&slug=${encodeURIComponent(details.slug)}`)}
          onAdd={() => navigate('/builder')}
          onOpenFullScreen={() => navigate(`/catalog/${encodeURIComponent(details.slug)}`)}
        />
      ) : null}

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}