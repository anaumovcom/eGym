export type AchievementRarity = 'common' | 'rare' | 'epic' | 'legendary'

export type AchievementTier = {
  id: string
  tier: number
  tierName: string
  threshold: number
  minimumEvidenceDays?: number
  title: string
  phrase: string
  rarity: AchievementRarity
  imageUrl: string | null
  thumbnailUrl: string | null
  audioUrl: string | null
  imageState: string
  audioState: string
  earned: boolean
  earnedAt: string | null
  awardedAt: string | null
  status: string
}

export type AchievementLine = {
  id: string
  group: string
  groupName: string
  metric: string
  unit: string
  description: string
  thresholds: number[]
  applicability: string
  currentValue: number
  evidenceDays?: number
  highestTier: number
  state: string
  updatedAt?: string | null
  isNew?: boolean
  nextTierId: string | null
  progressPercent: number
  tiers: AchievementTier[]
}

export type AchievementReceipt = {
  definitionId: string
  tier: number
  surface: 'detail' | 'audio'
  viewedAt: string
  isNew: boolean
}

export type AchievementAward = {
  grantId: number
  definitionId: string
  group: string
  sourceWorkoutId: number | null
  status: string
  isNew?: boolean
  earnedAt: string | null
  awardedAt: string
  tier: AchievementTier
  unit: string
  description: string
}

export type MediaSummary = { lines: number; tiers: number; images: number; audio: number }

export type AchievementCatalog = {
  lines: AchievementLine[]
  total: number
  nextCursor: number | null
  computedThrough: string | null
  isRebuilding: boolean
  groups: Array<{ id: string; name: string }>
  media: MediaSummary
}

export type AchievementOverview = {
  earnedTiers: number
  totalTiers: number
  completedLines: number
  totalLines: number
  activeDays: number
  recent: AchievementAward[]
  upcoming: AchievementLine[]
  computedThrough: string | null
  isRebuilding: boolean
  media: MediaSummary
}

export type WorkoutAwards = { workoutId: number; awards: AchievementAward[]; isRebuilding: boolean }

export const rarityLabels: Record<AchievementRarity, string> = {
  common: 'Обычная', rare: 'Редкая', epic: 'Эпичная', legendary: 'Легендарная',
}

export const applicabilityLabels: Record<string, string> = {
  available: 'Сохранённые результаты',
  requires_plan: 'Нужен исходный план',
  requires_comparison: 'Нужна сопоставимая история',
  requires_reflection: 'Необязательный дневник ощущений',
  requires_story: 'Сюжетная коллекция',
  requires_sensor: 'Нужны данные тренажёра',
  requires_primary: 'Нужна подтверждённая основная роль мышцы',
}
