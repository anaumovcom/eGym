import { useQueryClient } from '@tanstack/react-query'
import type { WorkoutBuilderData } from '@/entities/builder/model/types'
import type { DashboardData } from '@/entities/dashboard/model/types'
import { apiPut } from '@/shared/api/client'

function sortByIds<T extends { id: string }>(items: T[], ids: string[]) {
  const positions = new Map(ids.map((id, index) => [id, index]))
  return [...items].sort((left, right) => (positions.get(left.id) ?? ids.length) - (positions.get(right.id) ?? ids.length))
}

/** Saves the user's workout order; home and builder caches are reordered immediately. */
export function useWorkoutOrder(userId: string) {
  const queryClient = useQueryClient()

  return async function saveWorkoutOrder(programIds: string[]) {
    // A refetch already in flight would land with the old order on top of this one.
    await Promise.all([
      queryClient.cancelQueries({ queryKey: ['dashboard', userId] }),
      queryClient.cancelQueries({ queryKey: ['workout-builder', userId] }),
    ])
    queryClient.setQueriesData<DashboardData>({ queryKey: ['dashboard', userId] }, (current) => (
      current?.workouts ? { ...current, workouts: sortByIds(current.workouts, programIds) } : current
    ))
    queryClient.setQueriesData<WorkoutBuilderData>({ queryKey: ['workout-builder', userId] }, (current) => (
      current ? { ...current, programs: sortByIds(current.programs, programIds) } : current
    ))
    try {
      await apiPut('/api/programs/order', { userId, programIds })
    } catch {
      // Fall back to whatever order the server kept.
      void queryClient.invalidateQueries({ queryKey: ['dashboard', userId] })
      void queryClient.invalidateQueries({ queryKey: ['workout-builder', userId] })
    }
  }
}
