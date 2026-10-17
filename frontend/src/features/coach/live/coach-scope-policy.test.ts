import { describe, expect, it } from 'vitest'
import type { RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import type { CoachEvent, CoachScope } from '../model/contracts'
import { matchesIdentity, planSignature, speechIdentity, speechSurvives, type SpeechContext } from './coach-scope-policy'

const scope: CoachScope = { schemaVersion: 1, userId: 'user', runId: 'run', exerciseId: 'exercise', setOrdinal: 1, scopeEpoch: 1 }
const context: SpeechContext = { scope, phase: 'active-set', blocked: false, planRevision: 1, contextVersion: 1 }
const session = () => ({ exercises: [{ id: 'exercise', name: 'Name', kind: 'machine', plan: [{ targetReps: 10 }],
  details: { description: 'Definition', guide: { setup: ['Sit'] }, equipment: 'machine' }, loadSettings: { weight: 20, mode: 'standard' },
  calibrationState: 'saved', strengthMode: { id: 'standard' } }] }) as unknown as RuntimeWorkoutSession

describe('scope policy table', () => {
  it('requires exact pending phase and epoch, including same-user/run constraints for started audio', () => {
    expect(speechSurvives('rep_milestone', context, context, false)).toBe(true)
    for (const patch of [{ phase: 'rest' }, { scope: { ...scope, scopeEpoch: 2 } }] as const) {
      expect(speechSurvives('rep_milestone', context, { ...context, ...patch }, false)).toBe(false)
      expect(speechSurvives('rep_milestone', context, { ...context, ...patch }, true)).toBe(true)
    }
    for (const patch of [{ blocked: true }, { scope: null },
      { scope: { ...scope, userId: 'other' } }, { scope: { ...scope, runId: 'other' } }]) {
      expect(speechSurvives('rep_milestone', context, { ...context, ...patch }, true)).toBe(false)
    }
    for (const phase of ['disabled', 'paused-set', 'suspended'] as const) {
      expect(speechSurvives('rep_milestone', context, { ...context, phase }, true)).toBe(false)
    }
  })

  it('preserves started speech across plan edits but rejects stale pending speech', () => {
    const edited = { ...context, planRevision: 2, contextVersion: 2 }
    expect(speechSurvives('workout_started', context, edited, true)).toBe(true)
    expect(speechSurvives('workout_started', context, edited, false)).toBe(false)
    expect(speechSurvives('workout_started', context, { ...edited, blocked: true }, true)).toBe(false)
  })

  it('allows only the persisted result transition table', () => {
    const nextScope = { ...scope, scopeEpoch: 2 }
    expect(speechSurvives('set_persisted', { ...context, phase: 'finalizing-set' }, { ...context, scope: nextScope, phase: 'rest' }, false, true)).toBe(true)
    expect(speechSurvives('set_persisted', context, { ...context, phase: 'rest' }, false)).toBe(false)
    expect(speechSurvives('set_persisted', context, { ...context, phase: 'rest' }, false, true)).toBe(true)
    expect(speechSurvives('set_persisted', { ...context, phase: 'finalizing-set' }, { ...context, phase: 'exercise-summary' }, false)).toBe(false)
    expect(speechSurvives('exercise_finalized', { ...context, phase: 'exercise-summary' },
      { ...context, scope: nextScope, phase: 'exercise-summary' }, false, true)).toBe(true)
    expect(speechSurvives('exercise_finalized', { ...context, phase: 'exercise-summary' },
      { ...context, scope: { ...nextScope, setOrdinal: null }, phase: 'exercise-summary' }, false, true)).toBe(false)
    expect(speechSurvives('workout_finalized', { ...context, phase: 'workout-summary' },
      { ...context, scope: nextScope, phase: 'workout-summary' }, false, true)).toBe(true)
    expect(speechSurvives('exercise_finalized', { ...context, phase: 'exercise-summary' },
      { ...context, scope: { ...nextScope, exerciseId: 'other' }, phase: 'exercise-summary' }, false)).toBe(false)
  })

  it.each(['set_persisted', 'exercise_finalized'] as const)('requires confirmed refs and increasing phase ranks for %s', kind => {
    const finalizing = { ...context, phase: 'finalizing-set' as const, scope: { ...scope, scopeEpoch: 2 } }
    const result = { ...context, phase: kind === 'set_persisted' ? 'rest' as const : 'exercise-summary' as const,
      scope: { ...scope, scopeEpoch: 3 } }
    expect(speechSurvives(kind, context, finalizing, false, true)).toBe(true)
    expect(speechSurvives(kind, finalizing, result, false, true)).toBe(true)
    expect(speechSurvives(kind, result, finalizing, false, true)).toBe(false)
    expect(speechSurvives(kind, context, finalizing, false)).toBe(false)
    expect(speechSurvives('rep_milestone', context, finalizing, false, true)).toBe(false)
    expect(speechSurvives(kind, context, { ...context, scope: finalizing.scope }, false, true)).toBe(false)
  })
})

describe('bounded semantic plan signature', () => {
  it('excludes progress, timer, machine telemetry and summary state', () => {
    const a = session(), b = session()
    Object.assign(b, { currentExerciseId: 'other', completedSets: { exercise: [{ actualValue: 10 }] },
      restState: { remainingSeconds: 3 }, sessionState: { currentValue: 8 }, machine: { position: 123 }, workoutSummary: {} })
    expect(planSignature(a, 'hybrid')).toBe(planSignature(b, 'hybrid'))
  })

  it.each(['plan', 'load', 'calibration', 'mode', 'range', 'name', 'kind', 'order'])('includes %s changes', field => {
    const a = session(), b = session(), e = b.exercises[0]
    if (field === 'definition') e.details.description = 'New definition'
    if (field === 'plan') e.plan[0].targetReps = 12
    if (field === 'load') e.loadSettings.weight = 30
    if (field === 'calibration') e.calibrationState = 'missing'
    if (field === 'mode') e.strengthMode.id = 'negative'
    if (field === 'range') e.movementRangeLabel = 'New range'
    if (field === 'name') e.name = 'New name'
    if (field === 'kind') e.kind = 'timed'
    if (field === 'order') e.order = 2
    expect(planSignature(a, 'hybrid')).not.toBe(planSignature(b, 'hybrid'))
  })

  it('includes coach mode and ignores object property ordering', () => {
    const a = session(), b = session()
    b.exercises[0].loadSettings = { mode: 'standard', weight: 20 } as typeof b.exercises[0]['loadSettings']
    expect(planSignature(a, 'hybrid')).toBe(planSignature(b, 'hybrid'))
    expect(planSignature(a, 'hybrid')).not.toBe(planSignature(a, 'text-only'))
  })

  it('ignores huge unrelated guides/catalog prose in a realistic multi-exercise workout', () => {
    const a = session(), b = session()
    b.exercises[0].details.description = 'x'.repeat(600_000)
    b.exercises[0].details.guide = { setup: ['x'.repeat(600_000)] } as typeof b.exercises[0]['details']['guide']
    expect(planSignature(a, 'hybrid')).toBe(planSignature(b, 'hybrid'))
    b.exercises = Array.from({ length: 30 }, (_, i) => ({ ...b.exercises[0], id: `exercise-${i}`,
      plan: Array.from({ length: 12 }, () => ({ ...b.exercises[0].plan[0] })) }))
    expect(planSignature(b, 'hybrid')).not.toBeNull()
  })

  it('fails closed rather than silently truncating oversized relevant plans', () => {
    const a = session(); a.exercises[0].name = 'x'.repeat(260_000)
    expect(planSignature(a, 'hybrid')).toBeNull()
  })
})

describe('browser source identity', () => {
  it('deep freezes a detached identity and ignores wire property ordering', () => {
    const mutableScope = { ...scope }, dependencies = ['result.actualValue']
    const event: CoachEvent = { schemaVersion: 1, id: 'event', scope: mutableScope, kind: 'set_persisted', phase: 'finalizing-set',
      source: 'runtime_ack', exerciseKind: 'machine', controlMode: null, progressUnit: 'reps', ordinal: 0,
      planRevision: 3, contextVersion: 4, createdAtMs: 100, startDeadlineMs: 200, factDependencies: dependencies, facts: [] }
    const identity = speechIdentity(event)
    mutableScope.scopeEpoch = 2; dependencies.push('invented')
    expect(identity.scope.scopeEpoch).toBe(1); expect(identity.factDependencies).toEqual(['result.actualValue'])
    expect(Object.isFrozen(identity)).toBe(true); expect(Object.isFrozen(identity.scope)).toBe(true); expect(Object.isFrozen(identity.factDependencies)).toBe(true)
    expect(matchesIdentity({ factDependencies: ['result.actualValue'], startDeadlineMs: 200, createdAtMs: 100,
      contextVersion: 4, planRevision: 3, scope, eventId: 'event', schemaVersion: 1 }, identity)).toBe(true)
  })
})