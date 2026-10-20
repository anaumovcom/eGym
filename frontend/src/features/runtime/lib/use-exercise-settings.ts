import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react'
import type { ExerciseLoadSettings } from '@/entities/exercise/model/types'
import type { RuntimeExercisePlan, RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { apiGet, apiPut } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'

export type ExerciseSettingsSnapshot = Pick<ExerciseLoadSettings, 'weight' | 'sets' | 'reps' | 'restSeconds' | 'mode' | 'tempo'> & {
  trainingMode: string | null
  trainingDayType: string | null
}

export function getExerciseSettingsSnapshot(exercise: RuntimeExercisePlan): ExerciseSettingsSnapshot {
  const { weight, sets, reps, restSeconds, mode, tempo } = exercise.loadSettings
  return { weight, sets, reps, restSeconds, mode, tempo, trainingMode: exercise.strengthMode.id, trainingDayType: exercise.strengthMode.dayType ?? null }
}

// Serialize ALL writes for a user/slug, including writes from a different screen/session.
// A slow setup PUT must never finish after a newer session-weight PUT.
const writes = new Map<string, Promise<unknown>>()
export function saveExerciseSettings(userId: string, exerciseSlug: string, settings: ExerciseSettingsSnapshot) {
  const key = JSON.stringify([userId, exerciseSlug])
  const previous = writes.get(key) ?? Promise.resolve()
  const write = previous.catch(() => undefined).then(() => apiPut<ExerciseSettingsSnapshot>(
    '/api/runtime/exercises/settings', { userId, exerciseSlug, ...settings },
  ))
  writes.set(key, write)
  void write.finally(() => { if (writes.get(key) === write) writes.delete(key) }).catch(() => undefined)
  return write
}

type SettingsEntry = {
  status: 'idle' | 'loading' | 'ready' | 'error'
  read?: Promise<ExerciseSettingsSnapshot | null>
  initial?: ExerciseSettingsSnapshot
  saved?: string
  pending?: ExerciseSettingsSnapshot
  writing?: Promise<boolean>
  error: string | null
  listeners: Set<() => void>
}
const entries = new Map<string, SettingsEntry>()
const owners = new Map<string, string>()

/** Do not apply one user's settings to another user's persisted workout/counters. */
export function ownsExerciseSettingsSession(session: RuntimeWorkoutSession, userId: string | null) {
  if (!userId) return false
  // Honor an explicit owner when the runtime store provides one; also guard legacy sessions in this tab.
  const owner = (session as RuntimeWorkoutSession & { userId?: string }).userId ?? owners.get(session.id)
  if (owner && owner !== userId) return false
  owners.set(session.id, userId)
  return true
}

function notify(entry: SettingsEntry) { entry.listeners.forEach(listener => listener()) }
function message(error: unknown) { return error instanceof Error ? error.message : 'Не удалось сохранить настройки упражнения.' }

type Options = {
  session: RuntimeWorkoutSession | null
  exercise: RuntimeExercisePlan | undefined
  userId: string | null
  /** Session screens may write explicitly, but must never rehydrate an active set. */
  hydrate?: boolean
  debounceMs?: number
}

export function useExerciseSettings({ session, exercise, userId, hydrate = true, debounceMs = 500 }: Options) {
  const [, render] = useReducer(value => value + 1, 0)
  const mounted = useRef(false)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  const key = session && exercise && userId ? JSON.stringify([session.id, exercise.id, exercise.slug, userId]) : null
  const entry = useMemo(() => {
    if (!key) return null
    let value = entries.get(key)
    if (!value) {
      value = { status: 'idle', error: null, listeners: new Set() }
      entries.set(key, value)
    }
    return value
  }, [key])
  const owner = Boolean(session && ownsExerciseSettingsSession(session, userId))
  const sessionId = session?.id
  const exerciseId = exercise?.id
  const slug = exercise?.slug
  const serialized = exercise ? JSON.stringify(getExerciseSettingsSnapshot(exercise)) : null

  const currentExercise = useCallback(() => {
    if (!mounted.current) return undefined
    const current = useRuntimeStore.getState().session
    if (!current || current.id !== sessionId || current.currentExerciseId !== exerciseId
      || useAppStore.getState().selectedUserId !== userId || !ownsExerciseSettingsSession(current, userId)) return undefined
    return current.exercises.find(item => item.id === exerciseId)
  }, [exerciseId, sessionId, userId])

  useEffect(() => {
    if (!entry) return
    entry.listeners.add(render)
    return () => { entry.listeners.delete(render) }
  }, [entry])

  useEffect(() => {
    if (!entry || !owner || !userId || !slug || entry.status === 'ready' || entry.status === 'error') return
    const current = useRuntimeStore.getState().session
    const active = currentExercise()
    if (!current || !active) return
    // Builder targets belong to this workout, not the last use of the same slug in another workout.
    // Keep setup edits writable, but never hydrate them from global remembered settings.
    // Resumed sets also own their plans: restoring could truncate completed results/paired sides.
    if (!hydrate || current.source === 'builder' || current.view !== 'exercise-setup' || current.currentSetIndex > 0 || current.completedSets[active.id]?.length) {
      entry.status = 'ready'
      entry.saved = JSON.stringify(getExerciseSettingsSnapshot(active))
      notify(entry)
      return
    }
    let cancelled = false
    if (!entry.read) {
      entry.initial ??= getExerciseSettingsSnapshot(active)
      entry.status = 'loading'
      const pendingWrite = writes.get(JSON.stringify([userId, slug]))
      entry.read = Promise.resolve(pendingWrite).catch(() => undefined).then(() => apiGet<ExerciseSettingsSnapshot | null>(
        `/api/runtime/exercises/settings?userId=${encodeURIComponent(userId)}&exerciseSlug=${encodeURIComponent(slug)}`,
      ))
    }
    void entry.read.then(settings => {
      if (cancelled || entry.status === 'ready') return
      const latest = currentExercise()
      const runtime = useRuntimeStore.getState().session
      if (!latest || !runtime || runtime.view !== 'exercise-setup') return
      const editedDuringRead = JSON.stringify(getExerciseSettingsSnapshot(latest)) !== JSON.stringify(entry.initial)
      if (settings && runtime.currentSetIndex === 0 && !runtime.completedSets[latest.id]?.length) {
        // Preserve edits made while GET was in flight (including edits made outside this screen).
        const local = getExerciseSettingsSnapshot(latest)
        const merged = { ...settings }
        for (const field of Object.keys(local) as (keyof ExerciseSettingsSnapshot)[]) {
          if (local[field] !== entry.initial?.[field]) Object.assign(merged, { [field]: local[field] })
        }
        useRuntimeStore.getState().restoreExerciseSettings(merged)
      }
      const restored = currentExercise()
      if (!restored) return
      entry.saved = JSON.stringify(settings && editedDuringRead ? settings : getExerciseSettingsSnapshot(restored))
      entry.status = 'ready'
      entry.error = null
      notify(entry)
    }).catch(error => {
      if (cancelled || !currentExercise()) return
      entry.status = 'error'
      entry.error = error instanceof Error ? error.message : 'Не удалось загрузить настройки упражнения.'
      entry.read = undefined
      notify(entry)
    })
    return () => { cancelled = true }
  }, [currentExercise, entry, entry?.status, hydrate, owner, slug, userId])

  const writePending = useCallback(async (): Promise<boolean> => {
    if (!entry || !userId || !slug || !owner || entry.status !== 'ready' || !currentExercise()) return false
    if (entry.writing) {
      const ok = await entry.writing
      if (!ok) return false
    }
    const snapshot = entry.pending
    if (!snapshot) return true
    entry.error = null
    const write = saveExerciseSettings(userId, slug, snapshot).then(() => {
      entry.saved = JSON.stringify(snapshot)
      if (entry.pending === snapshot) entry.pending = undefined
      return true
    }).catch(error => {
      entry.error = message(error)
      return false
    })
    entry.writing = write
    notify(entry)
    const ok = await write
    if (entry.writing === write) entry.writing = undefined
    notify(entry)
    return ok
  }, [currentExercise, entry, owner, slug, userId])

  const flush = useCallback(async () => {
    const latest = currentExercise()
    if (!latest || !entry || entry.status !== 'ready') return false
    if (hydrate) {
      const snapshot = getExerciseSettingsSnapshot(latest)
      if (JSON.stringify(snapshot) !== entry.saved) entry.pending = snapshot
    }
    // Drain edits committed while an earlier PUT was in flight before allowing start.
    do {
      if (!await writePending()) return false
      const current = currentExercise()
      if (hydrate && current) {
        const snapshot = getExerciseSettingsSnapshot(current)
        if (JSON.stringify(snapshot) !== entry.saved) entry.pending = snapshot
      }
    } while (entry.pending && currentExercise())
    return Boolean(currentExercise())
  }, [currentExercise, entry, hydrate, writePending])

  const save = useCallback(async (snapshot: ExerciseSettingsSnapshot) => {
    if (!entry || !currentExercise()) return false
    entry.pending = snapshot
    return writePending()
  }, [currentExercise, entry, writePending])

  useEffect(() => {
    if (!hydrate || !entry || entry.status !== 'ready' || entry.error || !owner || serialized === entry.saved) return
    const timer = window.setTimeout(() => { void flush() }, debounceMs)
    // Never launch a delayed write belonging to a screen/exercise/user that was left behind.
    return () => window.clearTimeout(timer)
  }, [debounceMs, entry, entry?.status, entry?.error, flush, hydrate, owner, serialized])

  const retry = useCallback(async () => {
    if (!entry || !owner) return false
    if (entry.status === 'error') {
      entry.status = 'idle'
      entry.error = null
      notify(entry)
      return false
    }
    return flush()
  }, [entry, flush, owner])

  return {
    ready: owner && entry?.status === 'ready',
    error: !owner && session ? 'Выберите владельца тренировки или начните новую тренировку для этого пользователя.' : entry?.error ?? null,
    retry, flush, save,
  }
}