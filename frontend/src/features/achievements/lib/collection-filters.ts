import type { AchievementLine, AchievementRarity } from '@/entities/achievement/model/types'

export type CollectionTab = 'all' | 'new' | 'earned' | 'unknown'

export type CollectionFilters = { search: string; groups: string[]; rarities: AchievementRarity[] }

export const emptyCollectionFilters: CollectionFilters = { search: '', groups: [], rarities: [] }

export const isDiscovered = (line: AchievementLine) => line.tiers.some((tier) => tier.earned)

/** Highest earned tier, or undefined while the whole line is still unknown. */
export const currentTier = (line: AchievementLine) => [...line.tiers].reverse().find((tier) => tier.earned)

/** Hidden lines can be found only by their section name, never by text that is not yet revealed. */
export function matchesFilters(line: AchievementLine, filters: CollectionFilters): boolean {
  if (filters.groups.length > 0 && !filters.groups.includes(line.group)) return false
  if (filters.rarities.length > 0) {
    const tier = currentTier(line)
    if (!tier || !filters.rarities.includes(tier.rarity)) return false
  }
  const query = filters.search.trim().toLocaleLowerCase('ru')
  if (!query) return true
  const text = isDiscovered(line)
    ? [line.groupName, line.description, ...line.tiers.filter((tier) => tier.earned).flatMap((tier) => [tier.title, tier.phrase])]
    : [line.groupName]
  return text.join('\n').toLocaleLowerCase('ru').includes(query)
}

export function matchesTab(line: AchievementLine, tab: CollectionTab): boolean {
  if (tab === 'new') return isDiscovered(line) && line.isNew === true
  if (tab === 'earned') return isDiscovered(line)
  if (tab === 'unknown') return !isDiscovered(line)
  return true
}
