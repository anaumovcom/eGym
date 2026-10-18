import type { ExerciseCatalogResponse } from './types'
import { difficultyLabel, forceLabel, mechanicLabel } from '../lib/labels'

export type CatalogFilterKey = keyof ExerciseCatalogResponse['availableFilters']
export type CatalogSelection = Record<CatalogFilterKey, string[]>
export const CATALOG_FILTER_KEYS: CatalogFilterKey[] = ['equipment', 'muscles', 'difficulty', 'force', 'mechanic', 'grips']
export const CATALOG_FILTER_TITLES: Record<CatalogFilterKey, string> = {
  muscles: 'Мышцы', equipment: 'Оборудование', difficulty: 'Сложность', force: 'Тип усилия', mechanic: 'Механика', grips: 'Хват',
}
export const emptyCatalogSelection = (): CatalogSelection => ({ muscles: [], equipment: [], difficulty: [], force: [], mechanic: [], grips: [] })

// Bundled vocabulary makes filters usable on the very first render, even before
// the startup request resolves. Live catalog values extend it without another API call.
export const DEFAULT_CATALOG_FILTERS: ExerciseCatalogResponse['availableFilters'] = {
  muscles: ['Hips', 'Бицепс', 'Бицепс бедра', 'Грудь', 'Задние дельты', 'Икры', 'Квадрицепсы', 'Косые мышцы живота', 'Низ спины', 'Передние дельты', 'Предплечья', 'Пресс', 'Средняя трапеция', 'Трапеции', 'Трицепс', 'Широчайшие', 'Ягодицы'],
  equipment: ['Босу', 'Восстановление', 'Гантели', 'Гири', 'Диск', 'Йога', 'Кардио', 'Кроссовер', 'Машина Смита', 'Медбол', 'Петли TRX', 'Растяжка', 'Резина', 'Собственный вес', 'Тренажёр', 'Штанга'],
  difficulty: ['Beginner', 'Intermediate', 'Advanced'],
  force: ['Push', 'Pull', 'Static', 'Stretch'],
  mechanic: ['Compound', 'Isolation', 'Mobility'],
  grips: ['Без хвата', 'Вращающийся', 'Нейтральный', 'Нейтральный, Без хвата', 'Обратный', 'Обратный, Нейтральный', 'Прямой', 'Прямой, Без хвата', 'Прямой, Нейтральный', 'Прямой, Обратный', 'Прямой, Обратный, Без хвата', 'Прямой, Обратный, Нейтральный', 'Прямой, Обратный, Смешанный', 'Прямой, Смешанный', 'Смешанный', 'Щипковый'],
}

export function catalogFilterLabel(key: CatalogFilterKey, value: string) {
  if (key === 'difficulty') return difficultyLabel(value)
  if (key === 'force') return forceLabel(value)
  if (key === 'mechanic') return mechanicLabel(value)
  return value === 'Hips' ? 'Тазобедренные мышцы' : value
}

export function catalogFilterOptions(key: CatalogFilterKey, available?: ExerciseCatalogResponse['availableFilters'], selected: string[] = []) {
  return [...new Set([...DEFAULT_CATALOG_FILTERS[key], ...(available?.[key] ?? []), ...selected])]
}