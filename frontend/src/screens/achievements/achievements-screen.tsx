import { useQuery } from '@tanstack/react-query'
import { Award, Check, ChevronDown, ChevronLeft, RotateCcw, Search, SearchX, SlidersHorizontal, Trophy, X } from 'lucide-react'
import { useId, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import type { AchievementRarity } from '@/entities/achievement/model/types'
import { rarityLabels } from '@/entities/achievement/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import { achievementsApi } from '@/features/achievements/lib/achievements-api'
import {
  type CollectionFilters, type CollectionTab, currentTier, emptyCollectionFilters, isDiscovered, matchesFilters, matchesTab,
} from '@/features/achievements/lib/collection-filters'
import { AchievementCard } from '@/features/achievements/ui/achievement-card'
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
  { id: 'all', label: 'Все' }, { id: 'new', label: 'Новые' }, { id: 'earned', label: 'Полученные' }, { id: 'unknown', label: 'Неизвестные' },
]
const RARITIES: AchievementRarity[] = ['common', 'rare', 'epic', 'legendary']

function toggle<T>(values: T[], value: T): T[] {
  return values.includes(value) ? values.filter((item) => item !== value) : [...values, value]
}

export function AchievementsScreen() {
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const userId = selectedUserId ?? 'alexey'
  const userName = userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
  const [tab, setTab] = useState<CollectionTab>('all')
  const [filters, setFilters] = useState<CollectionFilters>(emptyCollectionFilters)
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const [mobileOpen, setMobileOpen] = useState(false)
  const panelId = useId()
  const overview = useQuery({ queryKey: ['achievements', 'overview', userId], queryFn: () => achievementsApi.overview(userId) })
  // The whole collection is one small payload; filtering is local so counts stay honest.
  const catalog = useQuery({ queryKey: ['achievements', 'catalog', userId], queryFn: () => achievementsApi.catalog(userId, { limit: 200 }) })
  const lines = useMemo(() => catalog.data?.lines ?? [], [catalog.data])
  const scoped = useMemo(() => lines.filter((line) => matchesFilters(line, filters)), [lines, filters])
  const visible = useMemo(() => scoped.filter((line) => matchesTab(line, tab)), [scoped, tab])
  const tabCounts = useMemo(() => Object.fromEntries(TABS.map(({ id }) => [id, scoped.filter((line) => matchesTab(line, id)).length])) as Record<CollectionTab, number>, [scoped])
  const groupCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const line of lines) counts.set(line.group, (counts.get(line.group) ?? 0) + 1)
    return counts
  }, [lines])
  const rarityCounts = useMemo(() => {
    const counts = new Map<AchievementRarity, number>()
    for (const line of lines) {
      const tier = currentTier(line)
      if (tier) counts.set(tier.rarity, (counts.get(tier.rarity) ?? 0) + 1)
    }
    return counts
  }, [lines])
  const activeCount = filters.groups.length + filters.rarities.length + (filters.search.trim() ? 1 : 0) + (tab === 'all' ? 0 : 1)
  const groupName = (id: string) => catalog.data?.groups.find((group) => group.id === id)?.name ?? id
  const update = (next: CollectionFilters) => { setFilters(next); setVisibleCount(PAGE_SIZE) }
  const changeTab = (next: CollectionTab) => { setTab(next); setVisibleCount(PAGE_SIZE) }
  const reset = () => { setFilters(emptyCollectionFilters); setTab('all'); setVisibleCount(PAGE_SIZE) }
  const discoveredLines = useMemo(() => lines.filter(isDiscovered).length, [lines])

  const chip = (label: string, pressed: boolean, count: number | undefined, onClick: () => void) => (
    <button type="button" key={label} className="discovery-option" aria-pressed={pressed} onClick={onClick}>
      {pressed ? <Check aria-hidden="true" /> : null}{label}{count != null ? <span className="ach-chip-count">{count}</span> : null}
    </button>
  )

  return (
    <FormaShell userName={userName} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
      <section className="catalog catalog-discovery ach-discovery" aria-labelledby="ach-title">
        <header className="discovery-page-heading">
          <div>
            <div className="discovery-eyebrow"><Trophy aria-hidden="true" /> КОЛЛЕКЦИЯ ПРОГРЕССА</div>
            <h1 id="ach-title" className="font-display font-bold text-white">Достижения</h1>
            <p>Награды за реальную практику. Неполученные скрыты: их описание и озвучка откроются только после получения.</p>
          </div>
          {overview.data && <dl className="ach-summary" aria-label="Сводка коллекции">
            <div><dt>Наград получено</dt><dd>{overview.data.earnedTiers}<small> из {overview.data.totalTiers}</small></dd></div>
            <div><dt>Линий открыто</dt><dd>{discoveredLines}<small> из {overview.data.totalLines}</small></dd></div>
            <div><dt>Завершено линий</dt><dd>{overview.data.completedLines}</dd></div>
            <div><dt>Тренировочных дней</dt><dd>{overview.data.activeDays}</dd></div>
          </dl>}
          <span className="discovery-library-mark" aria-hidden="true"><Award /></span>
        </header>
        <div className="discovery-layout">
          <aside className={`discovery-filters${mobileOpen ? ' discovery-filters-open' : ''}`} aria-label="Фильтры достижений">
            <button type="button" className="discovery-mobile-toggle" aria-expanded={mobileOpen} aria-controls={panelId} onClick={() => setMobileOpen((value) => !value)}><SlidersHorizontal aria-hidden="true" />Фильтры{activeCount ? ` · ${activeCount}` : ''}<ChevronDown aria-hidden="true" /></button>
            <div className="discovery-filter-body" id={panelId}>
              <div className="discovery-filter-heading"><span><SlidersHorizontal aria-hidden="true" />Фильтры</span>{activeCount ? <button type="button" onClick={reset} aria-label="Сбросить фильтры"><RotateCcw aria-hidden="true" /></button> : null}</div>
              <p className="discovery-filter-help">Внутри группы — любой вариант.<br />Между группами — совпадение всех.</p>
              <details className="discovery-filter-section" open>
                <summary><Award aria-hidden="true" />Раздел{filters.groups.length ? <b>{filters.groups.length}</b> : null}<ChevronDown aria-hidden="true" /></summary>
                <div className="discovery-options">
                  {(catalog.data?.groups ?? []).filter((group) => groupCounts.has(group.id)).map((group) => chip(group.name, filters.groups.includes(group.id), groupCounts.get(group.id), () => update({ ...filters, groups: toggle(filters.groups, group.id) })))}
                </div>
              </details>
              <details className="discovery-filter-section" open>
                <summary><Trophy aria-hidden="true" />Редкость полученных{filters.rarities.length ? <b>{filters.rarities.length}</b> : null}<ChevronDown aria-hidden="true" /></summary>
                <div className="discovery-options">
                  {RARITIES.map((rarity) => chip(rarityLabels[rarity], filters.rarities.includes(rarity), rarityCounts.get(rarity) ?? 0, () => update({ ...filters, rarities: toggle(filters.rarities, rarity) })))}
                </div>
              </details>
            </div>
          </aside>
          <div className="discovery-content">
            <div className="discovery-toolbar">
              <label className="discovery-search"><Search aria-hidden="true" />
                <input type="search" aria-label="Поиск достижений" placeholder="Найти полученное достижение…" value={filters.search} onChange={(event) => update({ ...filters, search: event.target.value })} />
                {filters.search ? <button type="button" aria-label="Очистить поиск" onClick={() => update({ ...filters, search: '' })}><X aria-hidden="true" /></button> : <span className="discovery-search-hint">Название, раздел или условие</span>}
              </label>
              <div className="discovery-toolbar-bottom">
                <div className="discovery-tabs" role="group" aria-label="Подборка достижений">
                  {TABS.map(({ id, label }) => <button type="button" key={id} aria-pressed={tab === id} onClick={() => changeTab(id)}>{label}<span>{tabCounts[id]}</span></button>)}
                </div>
                <span className="discovery-count" role="status">{catalog.isPending ? 'Загрузка достижений…' : `Найдено: ${visible.length}`}</span>
              </div>
            </div>
            {activeCount > 0 && <div className="discovery-active" aria-label="Активные фильтры">
              {filters.groups.map((id) => <button type="button" key={id} aria-label={`Убрать фильтр Раздел: ${groupName(id)}`} onClick={() => update({ ...filters, groups: filters.groups.filter((item) => item !== id) })}>{groupName(id)}<X aria-hidden="true" /></button>)}
              {filters.rarities.map((rarity) => <button type="button" key={rarity} aria-label={`Убрать фильтр Редкость: ${rarityLabels[rarity]}`} onClick={() => update({ ...filters, rarities: filters.rarities.filter((item) => item !== rarity) })}>{rarityLabels[rarity]}<X aria-hidden="true" /></button>)}
              <button type="button" className="discovery-reset" onClick={reset}><RotateCcw aria-hidden="true" />Сбросить всё</button>
            </div>}
            {catalog.isError ? <FormaState tone="error" title="Не удалось загрузить достижения" action={<Button onClick={() => void catalog.refetch()}>Повторить</Button>} />
              : catalog.isPending ? <FormaState tone="loading" title="Открываем вашу коллекцию…" />
              : visible.length === 0 ? <div className="forma-state"><SearchX aria-hidden="true" /><p className="font-display text-3xl font-bold text-white">Ничего не найдено</p><p>Измените запрос или уберите часть фильтров.</p><Button variant="secondary" onClick={reset}>Сбросить фильтры</Button></div>
              : <div className="ach-grid">{visible.slice(0, visibleCount).map((line) => <AchievementCard key={line.id} line={line} />)}</div>}
            {visible.length > visibleCount && <div className="catalog-more"><Button variant="secondary" onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}>Показать ещё ({visible.length - visibleCount})</Button></div>}
            {catalog.data?.isRebuilding && <p className="ach-pending" role="status">Обновляем достижения по сохранённым результатам…</p>}
            <Link className="ach-back" to="/progress"><ChevronLeft aria-hidden="true" />Вернуться к прогрессу</Link>
          </div>
        </div>
      </section>
      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}
