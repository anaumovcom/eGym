import { useQuery } from '@tanstack/react-query'
import { Award, Check, ChevronDown, RotateCcw, Search, SearchX, SlidersHorizontal, Trophy, X } from 'lucide-react'
import { useId, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { AchievementRarity } from '@/entities/achievement/model/types'
import { rarityLabels } from '@/entities/achievement/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import { achievementsApi } from '@/features/achievements/lib/achievements-api'
import {
  type CollectionFilters, type CollectionItem, type CollectionTab, collectionItems, emptyCollectionFilters, isDiscovered, matchesFilters,
} from '@/features/achievements/lib/collection-filters'
import { AchievementCard } from '@/features/achievements/ui/achievement-card'
import { CollectionSpotlight } from '@/features/achievements/ui/collection-spotlight'
import { EarnedAwardCard } from '@/features/achievements/ui/earned-award-card'
import { plural } from '@/shared/lib/ru-format'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { FormaState } from '@/shared/ui/status/forma-state'
import { useAppStore } from '@/stores/app-store'
import '@/shared/ui/training/exercise-discovery.css'
import './achievements-screen.css'

const fallbackMachine: MachineHealth = { machineState: 'ready', machineLabel: 'Тренажёр готов', leftDrive: 'connected', rightDrive: 'connected', safety: 'enabled', calibration: '—' }
const PAGE_SIZE = 24
const TABS: Array<{ id: CollectionTab; label: string }> = [
  { id: 'all', label: 'Все серии' }, { id: 'nearby', label: 'Ближайшие' }, { id: 'earned', label: 'Мои награды' },
  { id: 'new', label: 'Новые' }, { id: 'unknown', label: 'Не открыты' }, { id: 'archive', label: 'Архив' },
]
const RARITIES: AchievementRarity[] = ['common', 'rare', 'epic', 'legendary']

function toggle<T>(values: T[], value: T): T[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value]
}

async function loadCollection(userId: string) {
  const first = await achievementsApi.catalog(userId, { limit: 200 })
  const lines = [...first.lines]
  let cursor = first.nextCursor
  while (cursor !== null) {
    const page = await achievementsApi.catalog(userId, { cursor, limit: 200 })
    lines.push(...page.lines)
    cursor = page.nextCursor
  }
  return { ...first, lines }
}

export function AchievementsScreen() {
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const userId = selectedUserId ?? 'alexey'
  const userName = userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
  const [params, setParams] = useSearchParams()
  const tab = TABS.find(({ id }) => id === params.get('view'))?.id ?? 'all'
  const [filters, setFilters] = useState<CollectionFilters>(emptyCollectionFilters)
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const [mobileOpen, setMobileOpen] = useState(false)
  const panelId = useId()
  const catalog = useQuery({ queryKey: ['achievements', 'catalog', userId], queryFn: () => loadCollection(userId),
    refetchInterval: (query) => query.state.data?.isRebuilding ? 1500 : false })
  const lines = useMemo(() => catalog.data?.lines ?? [], [catalog.data])
  const activeLines = useMemo(() => lines.filter((line) => !line.archived), [lines])
  const views = useMemo(() => Object.fromEntries(TABS.map(({ id }) => [id, collectionItems(lines, id)])) as Record<CollectionTab, CollectionItem[]>, [lines])
  const visible = views[tab].filter(({ line, tier }) => matchesFilters(line, filters, tier))
  const tabCounts = Object.fromEntries(TABS.map(({ id }) => [id, views[id].filter(({ line, tier }) => matchesFilters(line, filters, tier)).length]))
  const awardView = tab === 'earned' || tab === 'new' || tab === 'archive'
  const groupCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const { line, tier } of views[tab]) {
      if (matchesFilters(line, { ...filters, groups: [] }, tier)) counts.set(line.group, (counts.get(line.group) ?? 0) + 1)
    }
    return counts
  }, [views, tab, filters])
  const rarityCounts = useMemo(() => {
    const counts = new Map<AchievementRarity, number>()
    for (const { line, tier } of views[tab]) {
      if (!matchesFilters(line, { ...filters, rarities: [] }, tier)) continue
      for (const rarity of new Set((tier ? [tier] : line.tiers).map((item) => item.rarity))) counts.set(rarity, (counts.get(rarity) ?? 0) + 1)
    }
    return counts
  }, [views, tab, filters])
  const activeCount = filters.groups.length + filters.rarities.length + (filters.search.trim() ? 1 : 0)
  const groupName = (id: string) => catalog.data?.groups.find((group) => group.id === id)?.name ?? id
  const update = (next: CollectionFilters) => { setFilters(next); setVisibleCount(PAGE_SIZE) }
  const changeTab = (next: CollectionTab) => {
    setParams(next === 'all' ? {} : { view: next }, { replace: true })
    if (next === 'archive' || tab === 'archive') setFilters({ ...filters, groups: [] })
    setVisibleCount(PAGE_SIZE)
  }
  const reset = () => { setFilters(emptyCollectionFilters); setVisibleCount(PAGE_SIZE) }
  const earnedCount = views.earned.length
  const tierCount = activeLines.reduce((sum, line) => sum + line.tiers.length, 0)

  const chip = (label: string, pressed: boolean, count: number | undefined, onClick: () => void) => (
    <button type="button" key={label} className="discovery-option" aria-pressed={pressed} onClick={onClick}>
      {pressed ? <Check aria-hidden="true" /> : null}{label}{count != null ? <span className="ach-chip-count">{count}</span> : null}
    </button>
  )

  return (
    <FormaShell userName={userName} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
      <section className="ach-discovery" aria-labelledby="ach-title">
        <header className="discovery-page-heading">
          <div className="ach-heading-copy">
            <h1 id="ach-title" className="font-display font-bold text-white">Достижения</h1>
            <p>У каждой награды своя история. Новые сцены открываются в конце тренировки.</p>
          </div>
          {catalog.data && <dl className="ach-summary" aria-label="Сводка коллекции">
            <div><dt>Наград в основной коллекции</dt><dd>{earnedCount}<small> из {tierCount}</small></dd><progress aria-label="Коллекция наград" value={earnedCount} max={tierCount || 1} /></div>
            <div><dt>Серий открыто</dt><dd>{activeLines.filter(isDiscovered).length}<small> из {activeLines.length}</small></dd></div>
            <div><dt>Тренировочных дней</dt><dd>{lines.find((line) => line.id === 'rhythm.active_days')?.currentValue ?? 0}</dd></div>
          </dl>}
        </header>
        <div className="discovery-layout">
          <aside className={`discovery-filters${mobileOpen ? ' discovery-filters-open' : ''}`} aria-label="Фильтры достижений">
            <button type="button" className="discovery-mobile-toggle" aria-expanded={mobileOpen} aria-controls={panelId} onClick={() => setMobileOpen((value) => !value)}><SlidersHorizontal aria-hidden="true" />Фильтры{activeCount ? ` · ${activeCount}` : ''}<ChevronDown aria-hidden="true" /></button>
            <div className="discovery-filter-body" id={panelId}>
              <div className="discovery-filter-heading"><span><SlidersHorizontal aria-hidden="true" />Фильтры</span>{activeCount ? <button type="button" onClick={reset} aria-label="Сбросить фильтры"><RotateCcw aria-hidden="true" /></button> : null}</div>
              <details className="discovery-filter-section" open>
                <summary><Award aria-hidden="true" />Раздел{filters.groups.length ? <b>{filters.groups.length}</b> : null}<ChevronDown aria-hidden="true" /></summary>
                <div className="discovery-options">
                  {(catalog.data?.groups ?? []).filter((group) => groupCounts.has(group.id) || filters.groups.includes(group.id)).map((group) => chip(group.name, filters.groups.includes(group.id), groupCounts.get(group.id) ?? 0, () => update({ ...filters, groups: toggle(filters.groups, group.id) })))}
                </div>
              </details>
              <details className="discovery-filter-section" open>
                <summary><Trophy aria-hidden="true" />Редкость{filters.rarities.length ? <b>{filters.rarities.length}</b> : null}<ChevronDown aria-hidden="true" /></summary>
                <div className="discovery-options">
                  {RARITIES.map((rarity) => chip(rarityLabels[rarity], filters.rarities.includes(rarity), rarityCounts.get(rarity) ?? 0, () => update({ ...filters, rarities: toggle(filters.rarities, rarity) })))}
                </div>
              </details>
            </div>
          </aside>
          <div className="discovery-content">
            {tab === 'all' && !activeCount && <CollectionSpotlight latest={views.earned[0]}
              next={views.nearby[0]?.line ?? (!earnedCount ? activeLines.find(line => line.id === 'start.first_workout') : undefined)} />}
            <section className="discovery-toolbar" aria-label="Поиск и подборка достижений">
              <label className="discovery-search"><Search aria-hidden="true" />
                <input type="search" aria-label="Поиск достижений" placeholder="Найти достижение…" value={filters.search} onChange={(event) => update({ ...filters, search: event.target.value })} />
                {filters.search ? <button type="button" aria-label="Очистить поиск" onClick={() => update({ ...filters, search: '' })}><X aria-hidden="true" /></button> : <span className="discovery-search-hint">Название, раздел или условие</span>}
              </label>
              <div className="discovery-toolbar-bottom">
                <div className="discovery-tabs" role="group" aria-label="Подборка достижений">
                  {TABS.filter(({ id }) => id !== 'archive' || views.archive.length > 0).map(({ id, label }) => <button type="button" key={id} aria-pressed={tab === id} onClick={() => changeTab(id)}>{label}<span>{tabCounts[id]}</span></button>)}
                </div>
                <span className="discovery-count" role="status">{catalog.isPending ? 'Загрузка достижений…' : `${visible.length} ${awardView ? plural(visible.length, 'награда', 'награды', 'наград') : plural(visible.length, 'серия', 'серии', 'серий')}`}</span>
              </div>
            </section>
            {activeCount > 0 && <div className="discovery-active" aria-label="Активные фильтры">
              {filters.groups.map((id) => <button type="button" key={id} aria-label={`Убрать фильтр Раздел: ${groupName(id)}`} onClick={() => update({ ...filters, groups: filters.groups.filter((item) => item !== id) })}>{groupName(id)}<X aria-hidden="true" /></button>)}
              {filters.rarities.map((rarity) => <button type="button" key={rarity} aria-label={`Убрать фильтр Редкость: ${rarityLabels[rarity]}`} onClick={() => update({ ...filters, rarities: filters.rarities.filter((item) => item !== rarity) })}>{rarityLabels[rarity]}<X aria-hidden="true" /></button>)}
              <button type="button" className="discovery-reset" onClick={reset}><RotateCcw aria-hidden="true" />Сбросить всё</button>
            </div>}
            {catalog.isError ? <FormaState tone="error" title="Не удалось загрузить достижения" action={<Button onClick={() => void catalog.refetch()}>Повторить</Button>} />
              : catalog.isPending ? <FormaState tone="loading" title="Открываем вашу коллекцию…" />
              : visible.length === 0 && activeCount === 0
                ? <div className="forma-state"><Award aria-hidden="true" /><h2>{tab === 'new' ? 'Новых наград пока нет' : tab === 'nearby' ? 'Пока нет начатых серий с прогрессом' : tab === 'unknown' ? 'Все серии уже открыты' : 'Пока нет полученных наград'}</h2><Button variant="secondary" onClick={() => changeTab('all')}>Посмотреть все серии</Button></div>
              : visible.length === 0 ? <div className="forma-state"><SearchX aria-hidden="true" /><p className="font-display text-3xl font-bold text-white">Ничего не найдено</p><p>Измените запрос или уберите часть фильтров.</p><Button variant="secondary" onClick={reset}>Сбросить фильтры</Button></div>
              : <div className={`ach-grid${awardView ? ' ach-gallery' : ''}`}>{visible.slice(0, visibleCount).map(({ line, tier }, index) => tier
                ? <EarnedAwardCard key={tier.id} line={line} tier={tier} eager={index < 12} />
                : <AchievementCard key={line.id} line={line} />)}</div>}
            {visible.length > visibleCount && <div className="catalog-more"><Button variant="secondary" onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}>Показать ещё ({visible.length - visibleCount})</Button></div>}
            {catalog.data?.isRebuilding && <p className="ach-pending" role="status">Обновляем достижения по сохранённым результатам…</p>}
          </div>
        </div>
      </section>
      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}
