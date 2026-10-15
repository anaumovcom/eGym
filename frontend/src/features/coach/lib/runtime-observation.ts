import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { coachRunId, type CoachSource } from '../model/contracts'
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
    return { userId: useAppStore.getState().selectedUserId, runId: session ? coachRunId(session) : null,
      exerciseId: session?.currentExerciseId ?? null, setOrdinal: session ? session.currentSetIndex + 1 : null,
      scopeEpoch, mock: session?.dataSource !== 'backend' }
  },
})

/** Timed-set clock of the exercise screen (wall-clock ms). The coach reads it to voice timed sets. */
export type CoachSetTimer = Readonly<{ exerciseId: string; setOrdinal: number; elapsedMs: number; startedAtMs: number | null }>
let setTimer: CoachSetTimer | null = null
const setTimerListeners = new Set<() => void>()
export const coachSetTimer = {
  get: (): CoachSetTimer | null => setTimer,
  publish(value: CoachSetTimer | null): void {
    if (value === setTimer || (value && setTimer && value.exerciseId === setTimer.exerciseId && value.setOrdinal === setTimer.setOrdinal &&
      value.elapsedMs === setTimer.elapsedMs && value.startedAtMs === setTimer.startedAtMs)) return
    setTimer = value
    for (const listener of setTimerListeners) listener()
  },
  subscribe(listener: () => void): () => void { setTimerListeners.add(listener); return () => { setTimerListeners.delete(listener) } },
}

export function captureRuntimeLifecycle(session: RuntimeWorkoutSession, userId: string | null, workoutOnly = false, source: CoachSource = 'user_input') {
  const current = useRuntimeStore.getState().session
  if (!userId || useAppStore.getState().selectedUserId !== userId || current?.id !== session.id ||
      (!workoutOnly && (current.currentExerciseId !== session.currentExerciseId || current.currentSetIndex !== session.currentSetIndex))) return null
  const kind = workoutOnly ? null : session.exercises.find(item => item.id === session.currentExerciseId)?.kind ?? null
  return coachLifecycle.capture(kind, workoutOnly, source)
}