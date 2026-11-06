import type { AchievementCatalog, AchievementLine, AchievementOverview, AchievementRarity, AchievementReceipt, WorkoutAwards } from '@/entities/achievement/model/types'
import { apiGet, apiPost } from '@/shared/api/client'

export type AchievementFilters = {
  category?: string
  status?: string
  rarity?: AchievementRarity
  query?: string
  cursor?: number
  limit?: number
}

function query(filters: AchievementFilters) {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== '') params.set(key, String(value))
  }
  const result = params.toString()
  return result ? `&${result}` : ''
}

export const achievementsApi = {
  overview: (userId: string) => apiGet<AchievementOverview>(`/api/achievements/overview?userId=${encodeURIComponent(userId)}`),
  catalog: (userId: string, filters: AchievementFilters = {}) =>
    apiGet<AchievementCatalog>(`/api/achievements/catalog?userId=${encodeURIComponent(userId)}${query(filters)}`),
  detail: (userId: string, definitionId: string) =>
    apiGet<AchievementLine>(`/api/achievements/${encodeURIComponent(definitionId)}?userId=${encodeURIComponent(userId)}`),
  recordReceipt: (userId: string, definitionId: string, surface: 'detail' | 'audio', tier?: number) =>
    apiPost<AchievementReceipt>(`/api/achievements/${encodeURIComponent(definitionId)}/receipts/${surface}?userId=${encodeURIComponent(userId)}${tier ? `&tier=${tier}` : ''}`, {}),
  workoutAwards: (userId: string, workoutId: number) =>
    apiGet<WorkoutAwards>(`/api/runtime/workouts/${workoutId}/awards?userId=${encodeURIComponent(userId)}`),
}
