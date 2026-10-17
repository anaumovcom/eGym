import { useRef, useState } from 'react'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { apiPost } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'

type Feedback = { subjectiveEffort?: number | null; discomfortLevel?: number | null }

/** Optional explicit input; no defaults, no equipment commands, no safety-latch writes. */
export function SetFeedback({ session, userId }: { session: RuntimeWorkoutSession; userId: string }) {
  const set = session.restState!.completedSet
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<Feedback>({})
  const saving = useRef(false)
  async function save(patch: Feedback) {
    if (saving.current || !set.backendSetId || useAppStore.getState().selectedUserId !== userId) return
    saving.current = true
    setPending(true)
    setError(null)
    try {
      const result = await apiPost<Feedback>(`/api/runtime/sets/${set.backendSetId}/feedback`, { userId, ...patch })
      if (useAppStore.getState().selectedUserId !== userId) return
      useRuntimeStore.setState(state => {
        const current = state.session
        const rest = current?.restState
        if (!current || !rest || current.id !== session.id || current.view !== 'rest'
          || current.currentExerciseId !== session.currentExerciseId
          || rest.completedSet.backendSetId !== set.backendSetId) return state
        const completedSet = { ...rest.completedSet, ...result }
        return { session: { ...current, restState: { ...rest, completedSet },
          completedSets: { ...current.completedSets, [current.currentExerciseId]:
            (current.completedSets[current.currentExerciseId] ?? []).map(item => item.backendSetId === set.backendSetId ? { ...item, ...result } : item) } } }
      })
      setSaved(result)
    } catch {
      setError('Оценка не сохранена. Можно повторить или пропустить.')
    } finally { saving.current = false; setPending(false) }
  }
  return <section aria-label="Необязательная оценка подхода" className="rt-rest-feedback">
    <p>Самочувствие после подхода · необязательно</p>
    <div role="group" aria-label="Усилие">
      {[[3, 'Легко · 3/10'], [6, 'Умеренно · 6/10'], [9, 'Тяжело · 9/10']].map(([value, label]) =>
        <button type="button" className="rt-chip" key={value} disabled={pending} aria-pressed={saved.subjectiveEffort === value}
          onClick={() => void save({ subjectiveEffort: Number(value) })}>{label}</button>)}
    </div>
    <div role="group" aria-label="Дискомфорт">
      {[[0, 'Нет дискомфорта · 0/10'], [1, 'Дискомфорт · 1/10'], [7, 'Дискомфорт · 7/10']].map(([value, label]) =>
        <button type="button" className="rt-chip" key={value} disabled={pending} aria-pressed={saved.discomfortLevel === value}
          onClick={() => void save({ discomfortLevel: Number(value) })}>{label}</button>)}
    </div>
    {saved.discomfortLevel != null && saved.discomfortLevel > 0 ? <p role="note">Не продолжайте через боль. Оценка не сбрасывает блокировку безопасности.</p> : null}
    {error ? <p role="alert">{error}</p> : null}
  </section>
}