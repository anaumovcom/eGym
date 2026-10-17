import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import type { CoachEvent, CoachPhase, CoachScope, CoachSpeechIdentity } from '../model/contracts'

export type SpeechContext = Readonly<{
  scope: CoachScope | null; phase: CoachPhase; planRevision: number; contextVersion: number; blocked: boolean
}>
export const sameRun = (a: CoachScope, b: CoachScope) => a.userId === b.userId && a.runId === b.runId
export const sameScope = (a: CoachScope, b: CoachScope) => sameRun(a, b) && a.exerciseId === b.exerciseId &&
  a.setOrdinal === b.setOrdinal && a.scopeEpoch === b.scopeEpoch

/** Explicit policy: pending is exact phase/epoch, except these one-way persisted-result
 * handoffs. Started speech may finish across phase/plan edits, never a gate or owner change.
 * Call on EVERY transition; invalidation is terminal, not a comparison at receipt time. */
export function speechSurvives(kind: CoachEvent['kind'], previous: SpeechContext, next: SpeechContext, started: boolean,
  confirmedResult = false): boolean {
  const a = previous.scope, b = next.scope
  if (!a || !b || previous.blocked || next.blocked ||
    ['disabled', 'paused-set', 'suspended'].includes(previous.phase) || ['disabled', 'paused-set', 'suspended'].includes(next.phase) ||
    !sameRun(a, b)) return false
  if (started) return true
  // Edits invalidate pending facts, not words that are already being spoken.
  if (previous.planRevision !== next.planRevision) return false
  const path: readonly CoachPhase[] = kind === 'set_persisted' ? ['active-set', 'finalizing-set', 'rest'] :
    kind === 'exercise_finalized' ? ['active-set', 'finalizing-set', 'exercise-summary'] :
      kind === 'workout_finalized' ? ['workout-summary'] : []
  if (path.length && !path.includes(previous.phase)) return false
  if (sameScope(a, b) && previous.phase === next.phase) return true
  if (!confirmedResult || !path.length || a.exerciseId !== b.exerciseId || a.setOrdinal !== b.setOrdinal ||
    b.scopeEpoch < a.scopeEpoch) return false
  const from = path.indexOf(previous.phase), to = path.indexOf(next.phase)
  // Strict rank progression permits skipped rendering ticks, never A→B→A.
  // Same-phase epoch remaps are summary-only and bounded by the validation cursor.
  return to > from || (to === from && ['exercise-summary', 'workout-summary'].includes(next.phase) && b.scopeEpoch > a.scopeEpoch)
}

export function speechIdentity(event: CoachEvent): CoachSpeechIdentity {
  return Object.freeze({ schemaVersion: 1, eventId: event.id, scope: Object.freeze({ ...event.scope }),
    planRevision: event.planRevision, contextVersion: event.contextVersion, createdAtMs: event.createdAtMs,
    startDeadlineMs: event.startDeadlineMs, factDependencies: Object.freeze([...event.factDependencies]) })
}

/** Compare known fields explicitly, independent of JSON property order; no coercion. */
export function matchesIdentity(value: unknown, expected: CoachSpeechIdentity): boolean {
  if (!value || typeof value !== 'object') return false
  const v = value as CoachSpeechIdentity, s = v.scope
  return v.schemaVersion === 1 && v.eventId === expected.eventId && !!s && s.schemaVersion === 1 && sameScope(s, expected.scope) &&
    v.planRevision === expected.planRevision && v.contextVersion === expected.contextVersion && v.createdAtMs === expected.createdAtMs &&
    v.startDeadlineMs === expected.startDeadlineMs && Array.isArray(v.factDependencies) &&
    v.factDependencies.length === expected.factDependencies.length && v.factDependencies.every((id, i) => id === expected.factDependencies[i])
}

/** Bounded traversal + fixed-size digest. Relevant plan/load/calibration/mode only;
 * excludes current exercise, completed sets, timers, reps, machine telemetry and summaries.
 * Overflow fails closed via the caller's blocked gate, not a truncated plan signature. */
export function planSignature(session: RuntimeWorkoutSession, mode: string): string | null {
  let remaining = 250_000, a = 2166136261, b = 5381
  const write = (text: string) => { for (const c of text) { if (--remaining < 0) throw new Error('plan_capacity'); a = Math.imul(a ^ c.charCodeAt(0), 16777619); b = Math.imul(b, 33) ^ c.charCodeAt(0) } }
  const visit = (value: unknown, depth = 0): void => {
    if (--remaining < 0 || depth > 16) throw new Error('plan_capacity')
    if (value === null || typeof value !== 'object') { write(JSON.stringify(value) ?? 'undefined'); return }
    if (Array.isArray(value)) { write('['); for (const item of value) { visit(item, depth + 1); write(',') } write(']'); return }
    write('{')
    for (const key of Object.keys(value).sort()) { write(key); write(':'); visit((value as Record<string, unknown>)[key], depth + 1); write(',') }
    write('}')
  }
  try {
    visit(mode)
    if (session.exercises.length > 100) return null
    for (const e of session.exercises) {
      if (e.plan.length > 100) return null
      // Guide/catalog content is not sent by this protocol (U04 is separate).
      // Explicit set projection also excludes unrelated notes and warning prose.
      visit([e.id, e.slug, e.order, e.name, e.kind, e.perSide,
      e.plan.map(p => [p.setNumber, p.side, p.roundNumber, p.setType, p.targetReps, p.targetMinReps,
        p.targetMaxReps, p.targetSeconds, p.weightLabel, p.recommendedWeightKg, p.restSeconds, p.rirLabel]),
      e.loadSettings && [e.loadSettings.weight, e.loadSettings.sets, e.loadSettings.reps, e.loadSettings.restSeconds,
        e.loadSettings.mode, e.loadSettings.tempo, e.loadSettings.safeRange, e.loadSettings.calibration],
      e.calibrationState, e.movementRangeLabel, e.movementRangeSaved, e.strengthMode,
      e.groupMeta && [e.groupMeta.groupName, e.groupMeta.totalRounds, e.groupMeta.totalSteps]])
    }
    return `${a >>> 0}:${b >>> 0}`
  } catch { return null }
}