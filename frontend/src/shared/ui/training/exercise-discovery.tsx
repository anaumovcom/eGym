import { Activity, ArrowDownUp, Check, ChevronDown, Dumbbell, Hand, Layers3, RotateCcw, Search, SlidersHorizontal, Star, Target, X } from 'lucide-react'
import { useId, useState } from 'react'
import { CATALOG_FILTER_KEYS, CATALOG_FILTER_TITLES, catalogFilterLabel, catalogFilterOptions, type CatalogFilterKey, type CatalogSelection } from '@/entities/exercise/model/catalog-filters'
import type { ExerciseCatalogResponse } from '@/entities/exercise/model/types'
import { cn } from '@/shared/lib/cn'
import './exercise-discovery.css'

const FILTER_ICONS = { muscles: Target, equipment: Dumbbell, difficulty: Activity, force: ArrowDownUp, mechanic: Layers3, grips: Hand }
const MUSCLE_GROUPS = [
  { title: 'Грудь и руки', values: ['Грудь', 'Бицепс', 'Трицепс', 'Предплечья'] },
  { title: 'Спина и плечи', values: ['Широчайшие', 'Трапеции', 'Средняя трапеция', 'Низ спины', 'Передние дельты', 'Задние дельты'] },
  { title: 'Пресс и ноги', values: ['Пресс', 'Косые мышцы живота', 'Ягодицы', 'Квадрицепсы', 'Бицепс бедра', 'Икры', 'Hips'] },
]
const EQUIPMENT_GROUPS = [
  { title: 'Тренажёры и инвентарь', values: ['Тренажёр', 'Кроссовер', 'Машина Смита', 'Резина', 'Петли TRX', 'Босу'] },
  { title: 'Свободные веса', values: ['Гантели', 'Штанга', 'Гири', 'Диск', 'Медбол'] },
  { title: 'Без отягощений', values: ['Собственный вес', 'Растяжка', 'Йога', 'Кардио', 'Восстановление'] },
]

export function ExerciseDiscoveryToolbar({ search, onSearch, favoritesOnly, onFavoritesChange, favoriteCount, count, loading }: {
  search: string; onSearch: (value: string) => void; favoritesOnly: boolean; onFavoritesChange: () => void; favoriteCount: number; count: number; loading: boolean
}) {
  return <div className="discovery-toolbar">
    <label className="discovery-search"><Search aria-hidden="true" /><input type="search" aria-label="Поиск упражнения" placeholder="Найти упражнение..." value={search} onChange={(event) => onSearch(event.target.value)} />
      {search ? <button type="button" aria-label="Очистить поиск" onClick={() => onSearch('')}><X aria-hidden="true" /></button> : <span className="discovery-search-hint">Название, мышца или инвентарь</span>}
    </label>
    <div className="discovery-toolbar-bottom">
      <div className="discovery-tabs" role="group" aria-label="Подборка упражнений">
        <button type="button" aria-pressed={!favoritesOnly} onClick={() => { if (favoritesOnly) onFavoritesChange() }}><Layers3 aria-hidden="true" />Все упражнения</button>
        <button type="button" aria-pressed={favoritesOnly} onClick={onFavoritesChange}><Star aria-hidden="true" />Избранное <span>{favoriteCount}</span></button>
      </div>
      <span className="discovery-count" role="status">{loading ? 'Загрузка упражнений…' : `Найдено: ${count}`}</span>
    </div>
  </div>
}

export function ExerciseDiscoveryFilters({ selected, available, onToggle, onClear }: {
  selected: CatalogSelection; available?: ExerciseCatalogResponse['availableFilters']; onToggle: (key: CatalogFilterKey, value: string) => void; onClear: () => void
}) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const id = useId()
  const count = CATALOG_FILTER_KEYS.reduce((sum, key) => sum + selected[key].length, 0)
  const chip = (key: CatalogFilterKey, value: string) => <button type="button" key={value} aria-pressed={selected[key].includes(value)} className="discovery-option" onClick={() => onToggle(key, value)}>{selected[key].includes(value) ? <Check aria-hidden="true" /> : null}{catalogFilterLabel(key, value)}</button>
  return <aside className={cn('discovery-filters', mobileOpen && 'discovery-filters-open')} aria-label="Фильтры упражнений">
    <button type="button" className="discovery-mobile-toggle" aria-expanded={mobileOpen} aria-controls={id} onClick={() => setMobileOpen((value) => !value)}><SlidersHorizontal aria-hidden="true" />Фильтры{count ? ` · ${count}` : ''}<ChevronDown aria-hidden="true" /></button>
    <div className="discovery-filter-body" id={id}>
      <div className="discovery-filter-heading"><span><SlidersHorizontal aria-hidden="true" />Фильтры</span>{count ? <button type="button" onClick={onClear} aria-label="Сбросить фильтры"><RotateCcw aria-hidden="true" /></button> : null}</div>
      <p className="discovery-filter-help">Внутри группы — любой вариант.<br />Между группами — совпадение всех.</p>
      {CATALOG_FILTER_KEYS.map((key) => {
        const Icon = FILTER_ICONS[key]
        const options = catalogFilterOptions(key, available, selected[key])
        const groups = key === 'muscles' ? MUSCLE_GROUPS : key === 'equipment' ? EQUIPMENT_GROUPS : null
        const other = groups ? options.filter((value) => !groups.some((group) => group.values.includes(value))) : []
        return <details className="discovery-filter-section" key={key} open={key === 'muscles' || key === 'equipment' || selected[key].length > 0}>
          <summary><Icon aria-hidden="true" /><span>{CATALOG_FILTER_TITLES[key]}</span>{selected[key].length ? <b>{selected[key].length}</b> : null}<ChevronDown aria-hidden="true" /></summary>
          {groups ? [...groups, ...(other.length ? [{ title: 'Другие', values: other }] : [])].map((group) => <div className="discovery-option-group" key={group.title}><h3>{group.title}</h3><div className="discovery-options">{group.values.filter((value) => options.includes(value)).map((value) => chip(key, value))}</div></div>) : <div className="discovery-options">{options.map((value) => chip(key, value))}</div>}
        </details>
      })}
    </div>
  </aside>
}

export function ExerciseDiscoveryActiveFilters({ selected, onToggle, onClear }: { selected: CatalogSelection; onToggle: (key: CatalogFilterKey, value: string) => void; onClear: () => void }) {
  const active = CATALOG_FILTER_KEYS.flatMap((key) => selected[key].map((value) => ({ key, value })))
  if (!active.length) return null
  return <div className="discovery-active" aria-label="Активные фильтры">{active.map(({key, value}) => <button type="button" key={`${key}-${value}`} aria-label={`Убрать фильтр ${CATALOG_FILTER_TITLES[key]}: ${catalogFilterLabel(key, value)}`} onClick={() => onToggle(key, value)}>{catalogFilterLabel(key, value)}<X aria-hidden="true" /></button>)}<button type="button" className="discovery-reset" onClick={onClear}><RotateCcw aria-hidden="true" />Сбросить всё</button></div>
}