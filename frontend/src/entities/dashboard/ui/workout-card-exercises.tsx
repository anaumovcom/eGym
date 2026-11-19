import { Check, Dumbbell, Plus } from 'lucide-react'
import type { DashboardBuilderWorkout } from '@/entities/dashboard/model/types'

type CardExercise = Pick<DashboardBuilderWorkout['exercises'][number], 'slug' | 'name' | 'status'>

export function WorkoutCardExercises({ exercises, visibleCount = 7 }: { exercises: CardExercise[]; visibleCount?: number }) {
  if (!exercises.length) {
    return (
      <span className="home-card-exercises home-card-empty">
        <span className="home-card-empty-icon" aria-hidden="true"><Dumbbell /><Plus /></span>
        <span className="home-card-empty-title">Пока нет упражнений</span>
        <span className="home-card-empty-hint">Нажмите, чтобы добавить</span>
      </span>
    )
  }
  const count = exercises.length
  return (
    <span className="home-card-exercises">
      {exercises.slice(0, visibleCount).map((exercise, index) => (
        <span key={`${exercise.slug}-${index}`} className="home-card-exercise" data-status={exercise.status}>
          <span className="home-card-exercise-index" aria-hidden="true">{exercise.status === 'completed' ? <Check /> : index + 1}</span>
          <span className="home-card-exercise-name">{exercise.name}</span>
        </span>
      ))}
      {count > visibleCount ? <span className="home-card-more">+ ещё {count - visibleCount}</span> : null}
    </span>
  )
}
