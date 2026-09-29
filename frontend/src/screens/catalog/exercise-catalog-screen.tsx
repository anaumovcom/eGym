import * as Dialog from '@radix-ui/react-dialog'
import { useQuery } from '@tanstack/react-query'
import { ArrowUp, Search, SlidersHorizontal, Star, X } from 'lucide-react'
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { WorkoutBuilderData } from '@/entities/builder/model/types'
import { difficultyLabel, forceLabel, mechanicLabel } from '@/entities/exercise/lib/labels'
import type { ExerciseCatalogResponse, ExerciseDetails } from '@/entities/exercise/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import { apiGet } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { BlockingAlert, WarningBanner } from '@/shared/ui/status/status-components'
import { ExerciseDetailsModal, ExercisePreviewCard } from '@/shared/ui/stage2/screen-components'
import { useAppStore } from '@/stores/app-store'

type FilterKey = 'muscles' | 'equipment' | 'difficulty' | 'force' | 'mechanic' | 'grips'
type FilterSection = 'muscles' | 'equipment' | 'all'

const FILTER_KEYS: FilterKey[] = ['muscles', 'equipment', 'difficulty', 'force', 'mechanic', 'grips']
const FILTER_TITLES: Record<FilterKey, string> = { muscles: 'Мышцы', equipment: 'Оборудование', difficulty: 'Сложность', force: 'Тип усилия', mechanic: 'Механика', grips: 'Хват' }
const PAGE_SIZE = 24
const SCROLL_STORAGE_KEY = 'egym-catalog-position'

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

function parseList(value: string | null) {
  return value ? value.split(',').filter(Boolean) : []
}

export function filterValueLabel(key: FilterKey, value: string) {
  if (key === 'difficulty') return difficultyLabel(value)
  if (key === 'force') return forceLabel(value)
  if (key === 'mechanic') return mechanicLabel(value)
  return value
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

  const search = searchParams.get('search') ?? ''
  const selectedSlug = searchParams.get('selected')
  const machineScenario = searchParams.get('machine') ?? 'ready'
  const favoritesOnly = searchParams.get('favorites') === '1'
  const resolvedUserId = selectedUserId ?? 'alexey'
  const selected = useMemo(() => Object.fromEntries(FILTER_KEYS.map((key) => [key, parseList(searchParams.get(key))])) as Record<FilterKey, string[]>, [searchParams])
  const [filterSection, setFilterSection] = useState<FilterSection | null>(null)
  const filterTriggerRef = useRef<HTMLElement | null>(null)
  const [addSlug, setAddSlug] = useState<string | null>(null)
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const [showBackToTop, setShowBackToTop] = useState(false)
  const sentinelRef = useRef<HTMLDivElement | null>(null)
  const restoredRef = useRef(false)
  const favoritesScrollRef = useRef<{ scrollTop: number; visibleCount: number } | null>(null)

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ userId: resolvedUserId })
    if (search) params.set('search', search)
    for (const key of FILTER_KEYS) if (selected[key].length) params.set(key, selected[key].join(','))
    params.set('favorites', favoriteExerciseSlugs.join(','))
    params.set('blacklist', blacklistedExerciseSlugs.join(','))
    return params.toString()
  }, [blacklistedExerciseSlugs, favoriteExerciseSlugs, resolvedUserId, search, selected])

  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ['exercise-catalog', queryString],
    queryFn: () => apiGet<ExerciseCatalogResponse>(`/api/exercises?${queryString}`),
    placeholderData: (previousData, previousQuery) => {
      const previousParams = new URLSearchParams(String(previousQuery?.queryKey[1] ?? ''))
      const nextParams = new URLSearchParams(queryString)
      previousParams.delete('favorites')
      nextParams.delete('favorites')
      return previousParams.toString() === nextParams.toString() ? previousData : undefined
    },
  })

  const { data: machine } = useQuery({
    queryKey: ['catalog-machine', machineScenario],
    queryFn: () => apiGet<MachineHealth>(`/api/machine/status?scenario=${encodeURIComponent(machineScenario)}`),
  })

  const { data: details } = useQuery({
    queryKey: ['exercise-details-modal', resolvedUserId, selectedSlug, favoriteExerciseSlugs.join(','), blacklistedExerciseSlugs.join(',')],
    queryFn: () => apiGet<ExerciseDetails>(`/api/exercises/${encodeURIComponent(selectedSlug ?? '')}?userId=${encodeURIComponent(resolvedUserId)}&favorites=${encodeURIComponent(favoriteExerciseSlugs.join(','))}&blacklist=${encodeURIComponent(blacklistedExerciseSlugs.join(','))}`),
    enabled: Boolean(selectedSlug),
  })

  const items = useMemo(() => (favoritesOnly ? (data?.items ?? []).filter((item) => item.favorite) : data?.items ?? []), [data?.items, favoritesOnly])
  const listKey = `${queryString}|${favoritesOnly}`
  const searchFilterKey = `${resolvedUserId}|${search}|${FILTER_KEYS.map((key) => selected[key].join(',')).join('|')}`

  // Keep the rendered window when favorites or favorite status changes so scrolling doesn't jump.
  useEffect(() => {
    if (restoredRef.current) {
      restoredRef.current = false
      return
    }
    favoritesScrollRef.current = null
    setVisibleCount(PAGE_SIZE)
  }, [searchFilterKey])

  useLayoutEffect(() => {
    const saved = favoritesScrollRef.current
    const main = document.querySelector<HTMLElement>('.forma-main')
    if (!saved || !main) return
    main.scrollTop = favoritesOnly ? Math.min(saved.scrollTop, Math.max(0, main.scrollHeight - main.clientHeight)) : saved.scrollTop
    if (!favoritesOnly) favoritesScrollRef.current = null
  }, [favoritesOnly])

  useLayoutEffect(() => {
    const raw = sessionStorage.getItem(SCROLL_STORAGE_KEY)
    if (!raw) return
    try {
      const saved = JSON.parse(raw) as { listKey: string; visibleCount: number; scrollTop: number }
      if (saved.listKey !== listKey) return
      restoredRef.current = true
      setVisibleCount(saved.visibleCount)
      requestAnimationFrame(() => {
        const main = document.querySelector<HTMLElement>('.forma-main')
        if (main) main.scrollTop = saved.scrollTop
      })
    } catch {
      sessionStorage.removeItem(SCROLL_STORAGE_KEY)
    }
    // Restore only on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    return () => {
      const main = document.querySelector<HTMLElement>('.forma-main')
      sessionStorage.setItem(SCROLL_STORAGE_KEY, JSON.stringify({ listKey, visibleCount, scrollTop: main?.scrollTop ?? 0 }))
    }
  }, [listKey, visibleCount])

  useEffect(() => {
    const sentinel = sentinelRef.current
    if (!sentinel || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) setVisibleCount((count) => count + PAGE_SIZE)
    }, { root: document.querySelector('.forma-main'), rootMargin: '400px' })
    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [items.length, visibleCount])

  useEffect(() => {
    const main = document.querySelector<HTMLElement>('.forma-main')
    if (!main) return
    const onScroll = () => setShowBackToTop(main.scrollTop > 400)
    onScroll()
    main.addEventListener('scroll', onScroll, { passive: true })
    return () => main.removeEventListener('scroll', onScroll)
  }, [])

  function updateParams(mutate: (next: URLSearchParams) => void) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      mutate(next)
      return next
    }, { replace: true })
  }

  function toggleFilter(key: FilterKey, value: string) {
    updateParams((next) => {
      const values = selected[key].includes(value) ? selected[key].filter((item) => item !== value) : [...selected[key], value]
      if (values.length) next.set(key, values.join(','))
      else next.delete(key)
    })
  }

  function clearFilters() {
    updateParams((next) => {
      for (const key of FILTER_KEYS) next.delete(key)
      next.delete('favorites')
      next.delete('search')
    })
  }

  function toggleFavoritesOnly() {
    if (!favoritesOnly) {
      favoritesScrollRef.current = { scrollTop: document.querySelector<HTMLElement>('.forma-main')?.scrollTop ?? 0, visibleCount }
    } else if (favoritesScrollRef.current) {
      setVisibleCount((count) => Math.max(count, favoritesScrollRef.current?.visibleCount ?? count))
    }
    updateParams((next) => { if (favoritesOnly) next.delete('favorites'); else next.set('favorites', '1') })
  }

  function openFilters(section: FilterSection, trigger: HTMLElement) {
    filterTriggerRef.current = trigger
    setFilterSection(section)
  }

  const activeFilters = FILTER_KEYS.flatMap((key) => selected[key].map((value) => ({ key, value })))
  const activeCount = activeFilters.length + (favoritesOnly ? 1 : 0)
  const visibleItems = items.slice(0, visibleCount)
  const machineHealth = machine ?? { machineState: 'ready', machineLabel: 'Загрузка статуса', leftDrive: 'connected', rightDrive: 'connected', safety: 'enabled', calibration: 'Проверка подключения...' } satisfies MachineHealth

  return (
    <FormaShell userName={getUserName(resolvedUserId)} machine={machineHealth} onStop={() => setEmergencyStopActive(true)}>
      {machine?.machineState === 'blocked' ? <BlockingAlert title="Каталог доступен, старт заблокирован" description="Можно смотреть упражнения и собирать план, но запуск тренировок временно недоступен из-за состояния тренажёра." /> : null}
      {machine?.machineState === 'warning' ? <WarningBanner title="Тренажёр требует внимания" description="Каталог и карточка упражнения остаются доступны, но перед стартом понадобится диагностика." /> : null}

      <section className="catalog" aria-labelledby="catalog-title">
        <header className="catalog-header">
          <h1 id="catalog-title" className="font-display font-bold text-white">Каталог упражнений</h1>
          <label className="catalog-search">
            <Search aria-hidden="true" />
            <input
              type="search"
              value={search}
              placeholder="Найти упражнение..."
              aria-label="Поиск упражнения"
              onChange={(event) => updateParams((next) => { if (event.target.value) next.set('search', event.target.value); else next.delete('search') })}
            />
            {search ? <button type="button" aria-label="Очистить поиск" onClick={() => updateParams((next) => next.delete('search'))}><X aria-hidden="true" /></button> : null}
          </label>
          <div className="catalog-filter-bar">
            <Button variant="secondary" aria-haspopup="dialog" aria-pressed={selected.muscles.length > 0} onClick={(event) => openFilters('muscles', event.currentTarget)}>Мышцы{selected.muscles.length ? ` · ${selected.muscles.length}` : ''}</Button>
            <Button variant="secondary" aria-haspopup="dialog" aria-pressed={selected.equipment.length > 0} onClick={(event) => openFilters('equipment', event.currentTarget)}>Оборудование{selected.equipment.length ? ` · ${selected.equipment.length}` : ''}</Button>
            <Button variant="secondary" aria-pressed={favoritesOnly} iconLeft={<Star aria-hidden="true" className={cn(favoritesOnly && 'fill-[#f3d18b] text-[#f3d18b]')} />} onClick={toggleFavoritesOnly}>Избранное</Button>
            <Button variant="secondary" aria-haspopup="dialog" iconLeft={<SlidersHorizontal aria-hidden="true" />} onClick={(event) => openFilters('all', event.currentTarget)}>Все фильтры</Button>
            <span className="catalog-count" role="status">{isPending ? 'Загрузка…' : `Найдено: ${items.length}`}</span>
          </div>
          {activeCount ? (
            <div className="catalog-active" aria-label="Активные фильтры">
              {favoritesOnly ? <button type="button" className="catalog-active-chip" onClick={() => updateParams((next) => next.delete('favorites'))}>Только избранное <X aria-hidden="true" /></button> : null}
              {activeFilters.map(({ key, value }) => (
                <button key={`${key}-${value}`} type="button" className="catalog-active-chip" aria-label={`Убрать фильтр ${FILTER_TITLES[key]}: ${filterValueLabel(key, value)}`} onClick={() => toggleFilter(key, value)}>
                  {filterValueLabel(key, value)} <X aria-hidden="true" />
                </button>
              ))}
              <button type="button" className="catalog-active-reset" onClick={clearFilters}>Сбросить всё</button>
            </div>
          ) : null}
        </header>

        {isError ? (
          <div className="forma-state" role="alert">
            <p>Не удалось загрузить каталог упражнений.</p>
            <Button variant="secondary" onClick={() => void refetch()}>Повторить</Button>
          </div>
        ) : null}
        {data && !items.length ? (
          <div className="forma-state">
            <p className="font-display text-3xl font-bold text-white">Ничего не найдено</p>
            <p>Измените запрос или уберите часть фильтров.</p>
            <Button variant="secondary" onClick={clearFilters}>Сбросить фильтры</Button>
          </div>
        ) : null}
        <div className="catalog-grid">
          {visibleItems.map((exercise) => (
            <ExercisePreviewCard
              key={exercise.slug}
              exercise={exercise}
              onOpen={() => updateParams((next) => next.set('selected', exercise.slug))}
              onFavorite={() => toggleFavoriteExercise(exercise.slug)}
            />
          ))}
        </div>
        {visibleCount < items.length ? (
          <div ref={sentinelRef} className="catalog-more">
            <Button variant="secondary" onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}>Показать ещё ({items.length - visibleCount})</Button>
          </div>
        ) : null}
      </section>

      {showBackToTop && createPortal(
        <button type="button" className="catalog-back-to-top" onClick={() => document.querySelector<HTMLElement>('.forma-main')?.scrollTo({ top: 0, behavior: 'smooth' })}>
          <ArrowUp aria-hidden="true" /> Наверх
        </button>,
        document.body,
      )}

      <Dialog.Root open={filterSection !== null} onOpenChange={(open) => { if (!open) setFilterSection(null) }}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
          <SafetyDialogContent className="catalog-filters-panel" onCloseAutoFocus={(event) => {
            event.preventDefault()
            if (filterTriggerRef.current?.isConnected) filterTriggerRef.current.focus()
          }}>
            <div className="catalog-filters-heading">
              <div>
                <Dialog.Title className="font-display text-3xl font-bold text-white">{filterSection === 'muscles' ? 'Мышцы' : filterSection === 'equipment' ? 'Оборудование' : 'Все фильтры'}</Dialog.Title>
                <Dialog.Description className="mt-1 text-sm text-white/60">{isPending ? 'Загрузка…' : `Найдено: ${items.length}`}</Dialog.Description>
              </div>
              <Dialog.Close asChild><Button>Готово</Button></Dialog.Close>
            </div>
            <div className="catalog-filters-body">
              {(filterSection === 'all' ? FILTER_KEYS : filterSection ? [filterSection] : []).map((key) => {
                const options = data?.availableFilters[key] ?? []
                if (!options.length) return null
                return (
                  <section key={key} className="catalog-filter-section" aria-labelledby={`filter-${key}`}>
                    <h3 id={`filter-${key}`}>{FILTER_TITLES[key]}</h3>
                    <div className="builder-chips">
                      {options.map((value) => (
                        <button key={value} type="button" aria-pressed={selected[key].includes(value)} className={cn('picker-chip', selected[key].includes(value) && 'picker-chip-active')} onClick={() => toggleFilter(key, value)}>
                          {filterValueLabel(key, value)}
                        </button>
                      ))}
                    </div>
                  </section>
                )
              })}
            </div>
            {activeCount ? <div className="catalog-filters-footer"><Button variant="secondary" onClick={clearFilters}>Сбросить всё</Button></div> : null}
          </SafetyDialogContent>
        </Dialog.Portal>
      </Dialog.Root>

      {details ? (
        <ExerciseDetailsModal
          exercise={details}
          open={Boolean(selectedSlug)}
          onOpenChange={(open) => { if (!open) updateParams((next) => next.delete('selected')) }}
          onStart={() => navigate(`/exercise-setup?source=catalog&slug=${encodeURIComponent(details.slug)}`)}
          onAdd={() => setAddSlug(details.slug)}
          onOpenFullScreen={() => navigate(`/catalog/${encodeURIComponent(details.slug)}`)}
          preferredVideoGender={resolvedUserId === 'elena' ? 'female' : 'male'}
        />
      ) : null}

      <AddToWorkoutDialog slug={addSlug} userId={resolvedUserId} onOpenChange={(open) => { if (!open) setAddSlug(null) }} />
      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}

function AddToWorkoutDialog({ slug, userId, onOpenChange }: { slug: string | null; userId: string; onOpenChange: (open: boolean) => void }) {
  const navigate = useNavigate()
  const { data, isPending, isError } = useQuery({
    queryKey: ['workout-builder', userId, null, null],
    queryFn: () => apiGet<WorkoutBuilderData>(`/api/builder?userId=${encodeURIComponent(userId)}`),
    enabled: Boolean(slug),
  })
  const encoded = slug ? encodeURIComponent(slug) : ''

  return (
    <Dialog.Root open={Boolean(slug)} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
        <SafetyDialogContent className="builder-dialog">
          <Dialog.Title className="font-display text-3xl font-bold text-white">В какую тренировку добавить?</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-white/60">Откроется редактор тренировки с настройкой подходов для этого упражнения.</Dialog.Description>
          <div className="catalog-workouts">
            {isPending ? <p className="text-white/60">Загрузка тренировок…</p> : null}
            {isError ? <p role="alert" className="text-[#ffb4a7]">Не удалось загрузить список тренировок.</p> : null}
            {data?.programs.map((program) => (
              <button key={program.id} type="button" className="builder-item" onClick={() => navigate(`/builder?programId=${encodeURIComponent(program.id)}&add=${encoded}`)}>
                <span className="builder-item-body"><span className="builder-item-name">{program.name}</span><span className="builder-item-summary">{program.subtitle}</span></span>
              </button>
            ))}
            {data && !data.programs.length ? <p className="text-white/60">Тренировок пока нет — создайте первую, и упражнение добавится в неё.</p> : null}
          </div>
          <div className="builder-dialog-actions">
            <Dialog.Close asChild><Button variant="secondary">Отмена</Button></Dialog.Close>
            {data && !data.programs.length ? <Button onClick={() => navigate(`/builder?create=new&add=${encoded}`)}>Создать тренировку</Button> : null}
          </div>
        </SafetyDialogContent>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
