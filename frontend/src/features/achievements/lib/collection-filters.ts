import type { AchievementLine, AchievementRarity, AchievementTier } from '@/entities/achievement/model/types'

export type CollectionTab = 'all' | 'nearby' | 'new' | 'earned' | 'unknown' | 'archive'
export type CollectionItem = { line: AchievementLine; tier?: AchievementTier }

export type CollectionFilters = { search: string; groups: string[]; rarities: AchievementRarity[] }

export const emptyCollectionFilters: CollectionFilters = { search: '', groups: [], rarities: [] }

export const isDiscovered = (line: AchievementLine) => line.tiers.some((tier) => tier.earned)

/** Highest earned tier, or undefined while the whole line is still unknown. */
export const currentTier = (line: AchievementLine) => [...line.tiers].reverse().find((tier) => tier.earned)

export function matchesFilters(line: AchievementLine, filters: CollectionFilters, tier?: AchievementTier): boolean {
  if (filters.groups.length > 0 && !filters.groups.includes(line.group)) return false
  const tiers = (tier ? [tier] : line.tiers).filter((item) => !filters.rarities.length || filters.rarities.includes(item.rarity))
  if (!tiers.length) return false
  const query = filters.search.trim().toLocaleLowerCase('ru')
  if (!query) return true
  const text = [line.name, line.groupName, line.description, ...tiers.filter((item) => item.earned).flatMap((item) => [item.title, item.phrase])]
  return text.join('\n').toLocaleLowerCase('ru').includes(query)
}

export function matchesTab(line: AchievementLine, tab: CollectionTab): boolean {
  if (line.archived || tab === 'archive') return Boolean(line.archived) && tab === 'archive'
  if (tab === 'nearby') return Boolean(line.nextTierId) && line.progressPercent > 0 && line.state === 'available'
  if (tab === 'new') return isDiscovered(line) && line.isNew === true
  if (tab === 'earned') return isDiscovered(line)
  if (tab === 'unknown') return !isDiscovered(line)
  return true
}

export function collectionItems(lines: AchievementLine[], tab: CollectionTab): CollectionItem[] {
  const entries = lines.filter((line) => matchesTab(line, tab))
  if (tab === 'nearby') entries.sort((a, b) => b.progressPercent - a.progressPercent)
  if (tab !== 'new' && tab !== 'earned' && tab !== 'archive') return entries.map((line) => ({ line }))
  return entries.flatMap((line) => line.tiers
    .filter((tier) => tier.earned && (tab !== 'new' || (tier.isNew ?? (line.isNew && currentTier(line)?.id === tier.id))))
    .map((tier) => ({ line, tier })))
    .sort((a, b) => (b.tier.earnedAt ?? b.tier.awardedAt ?? '').localeCompare(a.tier.earnedAt ?? a.tier.awardedAt ?? '')
      || b.tier.tier - a.tier.tier || a.tier.id.localeCompare(b.tier.id))
}
