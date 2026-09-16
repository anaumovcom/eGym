import type { ExerciseDifficulty, ExerciseForce, ExerciseMechanic } from '@/entities/exercise/model/types'

export const difficultyLabels: Record<ExerciseDifficulty, string> = { Beginner: 'Новичок', Intermediate: 'Средний', Advanced: 'Продвинутый' }
export const forceLabels: Record<ExerciseForce, string> = { Push: 'Жим / толчок', Pull: 'Тяга', Static: 'Статика', Stretch: 'Растяжка' }
export const mechanicLabels: Record<ExerciseMechanic, string> = { Compound: 'Базовое', Isolation: 'Изолирующее', Mobility: 'Мобильность' }

export function difficultyLabel(value: string) {
  return difficultyLabels[value as ExerciseDifficulty] ?? value
}

export function forceLabel(value: string) {
  return forceLabels[value as ExerciseForce] ?? value
}

export function mechanicLabel(value: string) {
  return mechanicLabels[value as ExerciseMechanic] ?? value
}
