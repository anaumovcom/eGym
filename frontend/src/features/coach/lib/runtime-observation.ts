import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import type { CoachSource } from '../model/contracts'
import { CoachLifecycleObserver } from './lifecycle-observer'

export const isCoachFoundationEnabled = () => import.meta.env.VITE_COACH_ENABLED === 'true'
let scopeEpoch = 0

// Read-only subscriptions invalidate captures even for A→B→A during an await.
useAppStore.subscribe((current, previous) => {
  if (current.selectedUserId !== previous.selectedUserId) {
    scopeEpoch++
    coachLifecycle.clear()
  }
})
useRuntimeStore.subscribe((current, previous) => {
  const a = current.session, b = previous.session
  if (a?.id !== b?.id || a?.currentExerciseId !== b?.currentExerciseId || a?.currentSetIndex !== b?.currentSetIndex) {
    scopeEpoch++
    if (a?.id !== b?.id) coachLifecycle.clear()
  }
})

export const coachLifecycle = new CoachLifecycleObserver({
  enabled: isCoachFoundationEnabled,
  clock: { nowMs: () => performance.now() },
  current: () => {
    const session = useRuntimeStore.getState().session
    return { userId: useAppStore.getState().selectedUserId, runId: session?.id ?? null,
      exerciseId: session?.currentExerciseId ?? null, setOrdinal: session ? session.currentSetIndex + 1 : null,
      scopeEpoch, mock: session?.dataSource !== 'backend' }
  },
})

export function captureRuntimeLifecycle(session: RuntimeWorkoutSession, userId: string | null, workoutOnly = false, source: CoachSource = 'user_input') {
  const current = useRuntimeStore.getState().session
  if (!userId || useAppStore.getState().selectedUserId !== userId || current?.id !== session.id ||
      (!workoutOnly && (current.currentExerciseId !== session.currentExerciseId || current.currentSetIndex !== session.currentSetIndex))) return null
  const kind = workoutOnly ? null : session.exercises.find(item => item.id === session.currentExerciseId)?.kind ?? null
  return coachLifecycle.capture(kind, workoutOnly, source)
}