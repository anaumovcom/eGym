import type { DashboardBuilderWorkout } from '@/entities/dashboard/model/types'
import { plural } from '@/shared/lib/ru-format'

export type WorkoutBadge = { label: string; tone: 'good' | 'warning' | 'muted' }

function daysAgoLabel(iso: string) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  const startOf = (value: Date) => new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime()
  const days = Math.round((startOf(new Date()) - startOf(date)) / 86_400_000)
  if (days <= 0) return 'сегодня'
  if (days === 1) return 'вчера'
  if (days < 30) return `${days} ${plural(days, 'день', 'дня', 'дней')} назад`
  return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })
}

/** One short status for workout cards; full wording lives in dialogs. */
export function workoutBadge(workout: DashboardBuilderWorkout, resumable = false): WorkoutBadge {
  if (workout.todayStatus === 'completed') return { label: 'Сегодня выполнена', tone: 'good' }
  if (workout.todayStatus === 'partial') return { label: 'Сегодня частично', tone: 'warning' }
  if (workout.todayStatus === 'aborted') return { label: 'Сегодня прервана', tone: 'warning' }
  if (resumable || workout.todayStatus === 'in_progress') return { label: 'Не завершена', tone: 'warning' }
  const ago = workout.lastPerformedAt && workout.lastStatus ? daysAgoLabel(workout.lastPerformedAt) : null
  return ago ? { label: `Последний раз ${ago}`, tone: 'muted' } : { label: 'Ещё не выполнялась', tone: 'muted' }
}
