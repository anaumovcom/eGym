import { canonicalCoachKey } from '../model/contracts'
import type { CoachEvent, CoachFact, CoachOutcome, CoachScope, CoachSource } from '../model/contracts'
import type { CoachClock } from './ports'

type LifecycleKind = 'set_stopped' | 'set_persisted' | 'exercise_finalized' | 'workout_finalized'
export type LifecycleContext = {
  userId: string | null; runId: string | null; exerciseId: string | null
  setOrdinal: number | null; scopeEpoch: number; mock: boolean
}
export type LifecycleCapture = Readonly<{
  scope: CoachScope; exerciseKind: CoachEvent['exerciseKind']; source: CoachSource
}>
export type LifecyclePayload = {
  outcome?: CoachOutcome; actualValue?: number; progressUnit?: 'reps' | 'seconds'
  backendSetId?: number; backendExerciseId?: number; backendWorkoutId?: number
}
export type LifecycleRefs = Readonly<{ backendSetId?: number; backendExerciseId?: number; backendWorkoutId?: number }>

/** No async callbacks, provider, playback, storage writes or hardware commands. */
export class CoachLifecycleObserver {
  private records: CoachEvent[] = []
  private consumed = new Set<string>()
  private aliases = new Map<string, string>()
  // Backend row IDs stay out of the event (no facts/provider); the live client sends them as refs.
  private refMap = new Map<string, LifecycleRefs>()
  private failures = 0
  private sequence = 0
  private userId: string | null = null
  private runId: string | null = null
  private options: { enabled: () => boolean; current: () => LifecycleContext; clock: CoachClock }

  constructor(
    options: { enabled: () => boolean; current: () => LifecycleContext; clock: CoachClock },
  ) { this.options = options }

  capture(exerciseKind: CoachEvent['exerciseKind'], workoutOnly = false, source: CoachSource = 'user_input'): LifecycleCapture | null {
    try {
      if (!this.options.enabled()) { this.clear(); return null }
      const current = this.options.current()
      if (current.userId !== this.userId || current.runId !== this.runId) {
        this.clear()
        this.userId = current.userId
        this.runId = current.runId
      }
      if (!current.userId || !current.runId || current.mock) return null
      return Object.freeze({
        scope: Object.freeze({ schemaVersion: 1, userId: current.userId, runId: current.runId,
          exerciseId: workoutOnly ? null : current.exerciseId,
          setOrdinal: workoutOnly ? null : current.setOrdinal, scopeEpoch: current.scopeEpoch }),
        exerciseKind, source,
      })
    } catch { this.failures++; return null }
  }

  publish(capture: LifecycleCapture | null, kind: LifecycleKind, payload: LifecyclePayload = {}): boolean {
    try {
      if (!capture || !this.options.enabled()) return false
      const current = this.options.current()
      const scope = capture.scope
      if (current.mock || current.userId !== scope.userId || current.runId !== scope.runId ||
          current.scopeEpoch !== scope.scopeEpoch ||
          (scope.exerciseId !== null && current.exerciseId !== scope.exerciseId) ||
          (scope.setOrdinal !== null && current.setOrdinal !== scope.setOrdinal)) return false
      if (kind.startsWith('set_') && (scope.exerciseId === null || scope.setOrdinal === null)) return false
      if (kind === 'set_persisted' && (!Number.isInteger(payload.backendSetId) || payload.backendSetId! <= 0)) return false
      if (kind === 'exercise_finalized' && (!Number.isInteger(payload.backendExerciseId) || payload.backendExerciseId! <= 0)) return false
      if (kind === 'workout_finalized' && (!Number.isInteger(payload.backendWorkoutId) || payload.backendWorkoutId! <= 0)) return false
      const now = this.options.clock.nowMs()
      if (!Number.isFinite(now) || now < 0) return false
      const facts: CoachFact[] = []
      const source = kind === 'set_stopped' ? capture.source : 'runtime_ack'
      const add = (id: string, value: number | string, unit: CoachFact['unit']) => facts.push(Object.freeze({
        schemaVersion: 1, id, value, unit, source, confidence: 'confirmed', observedAtMs: now,
        validUntilMs: now + 20_000, scopeEpoch: scope.scopeEpoch,
      }))
      if (payload.actualValue !== undefined) {
        if (!Number.isInteger(payload.actualValue) || payload.actualValue < 0) return false
        // Persisted client result: explicit provenance, not a newly measured hardware fact.
        add('result.actualValue', payload.actualValue, payload.progressUnit ?? 'reps')
      }
      if (payload.outcome) add('result.outcome', payload.outcome, 'text')
      const event: CoachEvent = Object.freeze({
        schemaVersion: 1, id: `lifecycle-${++this.sequence}`, scope, kind, source,
        phase: kind.startsWith('set_') ? 'finalizing-set' : kind === 'exercise_finalized' ? 'exercise-summary' : 'workout-summary',
        exerciseKind: capture.exerciseKind, controlMode: null, progressUnit: payload.progressUnit ?? null,
        ordinal: 0, planRevision: 0, contextVersion: 0, createdAtMs: now, startDeadlineMs: now + 20_000,
        facts: Object.freeze(facts), factDependencies: Object.freeze(facts.map(fact => fact.id)),
      })
      const key = canonicalCoachKey(event)
      // Bound dedup without evicting receipts and accidentally replaying old opportunities.
      if (this.consumed.has(key) || this.consumed.size >= 1024) return false
      if (payload.backendSetId) {
        const alias = JSON.stringify([scope.userId, 'set', payload.backendSetId])
        if (this.aliases.has(alias) && this.aliases.get(alias) !== key) return false
        this.aliases.set(alias, key)
      }
      this.consumed.add(key)
      this.records.push(event)
      const refs: Record<string, number> = {}
      for (const name of ['backendSetId', 'backendExerciseId', 'backendWorkoutId'] as const) {
        if (Number.isInteger(payload[name]) && payload[name]! > 0) refs[name] = payload[name]!
      }
      if (Object.keys(refs).length) this.refMap.set(event.id, Object.freeze(refs))
      if (this.records.length > 200) {
        for (const old of this.records.slice(0, -200)) this.refMap.delete(old.id)
        this.records = this.records.slice(-200)
      }
      return true
    } catch { this.failures++; return false }
  }

  snapshot(): readonly CoachEvent[] { return [...this.records] }
  refs(eventId: string): LifecycleRefs | null { return this.refMap.get(eventId) ?? null }
  failureCount(): number { return this.failures }
  clear(): void { this.records = []; this.consumed.clear(); this.aliases.clear(); this.refMap.clear() }
}