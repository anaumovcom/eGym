import type { CoachEvent, CoachScope } from '../model/contracts'
import type { LocalCue } from '../interpreter/coach-interpreter'

/** Fixed pack meanings: set-end has no count; workout-done closes the session,
 * not a certification that the entire plan was completed. */
export const COMPLETION_IDEAS = {
  'set-end': 'set_closed', 'set-partial': 'set_partial', 'set-skipped': 'set_skipped',
  'last-set-next': 'last_set_remaining', 'exercise-done': 'exercise_full',
  'exercise-partial': 'exercise_partial', 'exercise-skipped': 'exercise_skipped',
  'workout-done': 'workout_closed', 'workout-partial': 'workout_partial',
} as const
export type CompletionCue = keyof typeof COMPLETION_IDEAS
export type LocalCompletion = Readonly<{ cueIds: readonly CompletionCue[]; acknowledged: readonly (typeof COMPLETION_IDEAS)[CompletionCue][] }>

/** Run-local ownership reservations, not a claim of hearing. Cancellations still
 * have mixer receipts; consumed local outcomes are never replayed. */
export class LocalCompletions {
  private entries = new Map<string, CompletionCue[]>()
  private key(scope: CoachScope, level: string): string {
    return JSON.stringify([scope.userId, scope.runId, level, level === 'workout' ? null : scope.exerciseId,
      level === 'set' ? scope.setOrdinal : null])
  }
  clear(): void { this.entries.clear() }
  note(cue: LocalCue): void {
    if (!cue.clipId || !(cue.clipId in COMPLETION_IDEAS)) return
    const id = cue.clipId as CompletionCue
    const level = id.startsWith('exercise-') ? 'exercise' : id.startsWith('workout-') ? 'workout' : 'set'
    const key = this.key(cue.scope, level), ids = id === 'last-set-next' ? this.entries.get(key) ?? [] : []
    if (!ids.includes(id)) ids.push(id)
    this.entries.set(key, ids)
    if (this.entries.size > 128) this.entries.delete(this.entries.keys().next().value!)
  }
  forEvent(event: CoachEvent): LocalCompletion | null {
    const level = event.kind === 'set_persisted' ? 'set' : event.kind === 'exercise_finalized' ? 'exercise' :
      event.kind === 'workout_finalized' ? 'workout' : null
    const ids = level ? this.entries.get(this.key(event.scope, level)) : undefined
    return ids?.length ? { cueIds: [...ids], acknowledged: ids.map(id => COMPLETION_IDEAS[id]) } : null
  }
}