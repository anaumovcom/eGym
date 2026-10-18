import { queryOptions, useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { difficultyLabel, forceLabel, mechanicLabel } from '@/entities/exercise/lib/labels'
import type { ExerciseCatalogResponse, ExerciseSummary } from './types'
import { apiGet } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'

export type ExerciseCatalogFilters = Partial<Record<'muscles' | 'equipment' | 'difficulty' | 'force' | 'mechanic' | 'grips', string[]>> & { search?: string }

// One unfiltered catalog per user for the lifetime of the application. User-specific
// readiness and preview videos must never leak between profiles.
export function exerciseCatalogOptions(userId: string) {
  return queryOptions({
    queryKey: ['exercise-catalog', userId],
    queryFn: () => apiGet<ExerciseCatalogResponse>(`/api/exercises?userId=${encodeURIComponent(userId)}&favorites=&blacklist=`),
    staleTime: Infinity,
    gcTime: Infinity,
  })
}

const normalize = (value: string) => value.toLocaleLowerCase().replaceAll('ё', 'е').trim()

export function filterExerciseCatalog(catalog: ExerciseCatalogResponse, filters: ExerciseCatalogFilters): ExerciseCatalogResponse {
  const search = normalize(filters.search ?? '')
  const items = catalog.items.filter((item) => {
    if (search && !normalize([
      item.slug, item.name, item.secondaryName, item.equipment, item.difficulty,
      item.difficultyLabel, difficultyLabel(item.difficulty), item.force, forceLabel(item.force),
      item.mechanic, mechanicLabel(item.mechanic), item.grips, ...item.muscles,
    ].join(' ')).includes(search)) return false
    if (filters.muscles?.length && !filters.muscles.some((muscle) => item.muscles.includes(muscle))) return false
    return (['equipment', 'difficulty', 'force', 'mechanic', 'grips'] as const)
      .every((key) => !filters[key]?.length || filters[key]!.includes(item[key]))
  })
  return { ...catalog, items, total: items.length }
}

function withPreferences(item: ExerciseSummary, favorites: Set<string>, blacklist: Set<string>): ExerciseSummary {
  const favorite = favorites.has(item.slug)
  const blacklisted = blacklist.has(item.slug)
  return {
    ...item,
    favorite,
    blacklisted,
    recommended: !blacklisted && item.recommended,
    compatibilityTone: blacklisted ? 'blocked' : item.compatibilityTone,
    badges: [
      ...(favorite ? ['Избранное'] : []),
      ...(blacklisted ? ['В чёрном списке'] : []),
      ...item.badges.filter((badge) => badge !== 'Избранное' && badge !== 'В чёрном списке' && (!blacklisted || badge !== 'Рекомендуется')),
    ],
  }
}

export function useExerciseCatalog(userId: string, filters: ExerciseCatalogFilters = {}, enabled = true) {
  const query = useQuery({ ...exerciseCatalogOptions(userId), enabled })
  const favorites = useAppStore((state) => state.favoriteExerciseSlugs)
  const blacklist = useAppStore((state) => state.blacklistedExerciseSlugs)
  const catalog = useMemo(() => {
    if (!query.data) return undefined
    const favoriteSet = new Set(favorites)
    const blacklistSet = new Set(blacklist)
    return { ...query.data, items: query.data.items.map((item) => withPreferences(item, favoriteSet, blacklistSet)) }
  }, [query.data, favorites, blacklist])
  const data = useMemo(() => catalog ? filterExerciseCatalog(catalog, filters) : undefined, [catalog, filters])
  return { ...query, data }
}