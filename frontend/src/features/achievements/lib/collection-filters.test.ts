import { describe, expect, it } from 'vitest'
import type { AchievementLine } from '@/entities/achievement/model/types'
import { emptyCollectionFilters, matchesFilters, matchesTab } from './collection-filters'

function make(id: string, group: string, earned: boolean, isNew = false): AchievementLine {
  return {
    id, group, groupName: group === 'a' ? 'Начало пути' : 'Практика', metric: 'm', unit: 'u',
    description: earned ? 'Секретное условие' : '', thresholds: [1], applicability: 'available', currentValue: 0,
    highestTier: earned ? 1 : 0, state: 'available', nextTierId: null, progressPercent: 0, isNew,
    tiers: [{
      id: `${id}:t1`, tier: 1, tierName: 'Начало', threshold: 1, title: earned ? 'Рычаг старта' : '', phrase: '',
      rarity: 'epic', imageUrl: null, thumbnailUrl: null, audioUrl: null, imageState: 'x', audioState: 'x',
      earned, earnedAt: null, awardedAt: null, status: earned ? 'earned' : 'not_started',
    }],
  }
}

describe('collection filters', () => {
  const known = make('a.one', 'a', true, true)
  const unknown = make('b.two', 'b', false)

  it('splits lines into new, earned and unknown tabs', () => {
    expect(matchesTab(known, 'new')).toBe(true)
    expect(matchesTab(unknown, 'new')).toBe(false)
    expect(matchesTab(known, 'earned')).toBe(true)
    expect(matchesTab(unknown, 'earned')).toBe(false)
    expect(matchesTab(unknown, 'unknown')).toBe(true)
    expect(matchesTab(known, 'all') && matchesTab(unknown, 'all')).toBe(true)
  })

  it('searches revealed text of earned lines but only the section name of hidden ones', () => {
    expect(matchesFilters(known, { ...emptyCollectionFilters, search: 'секретное' })).toBe(true)
    expect(matchesFilters(known, { ...emptyCollectionFilters, search: 'рычаг' })).toBe(true)
    expect(matchesFilters(unknown, { ...emptyCollectionFilters, search: 'секретное' })).toBe(false)
    expect(matchesFilters(unknown, { ...emptyCollectionFilters, search: 'практика' })).toBe(true)
  })

  it('combines section and rarity; rarity only matches earned lines', () => {
    expect(matchesFilters(known, { ...emptyCollectionFilters, groups: ['a'], rarities: ['epic'] })).toBe(true)
    expect(matchesFilters(known, { ...emptyCollectionFilters, groups: ['b'] })).toBe(false)
    expect(matchesFilters(unknown, { ...emptyCollectionFilters, rarities: ['epic'] })).toBe(false)
  })
})
