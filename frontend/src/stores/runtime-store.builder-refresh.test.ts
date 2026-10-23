import { beforeEach, describe, expect, it } from 'vitest'
import type { RuntimeExercisePlan, RuntimeWorkoutSession } from '@/entities/runtime/model/types'
import { getBuilderExerciseSignatures, getBuilderPlanSignature, getStoredBuilderPlanSignature } from '@/features/runtime/lib/builder-plan-signature'
import { createRuntimeSession } from '@/mocks/stage3-data'
import { useRuntimeStore } from './runtime-store'

function withWeight(exercise: RuntimeExercisePlan, weight: number): RuntimeExercisePlan {
  return {
    ...exercise,
    loadSettings: { ...exercise.loadSettings, weight },
    plan: exercise.plan.map((plan) => ({ ...plan, recommendedWeightKg: weight, weightLabel: `${weight} кг` })),
  }
}

function signed(session: RuntimeWorkoutSession): RuntimeWorkoutSession {
  return { ...session, builderPlanSignature: getBuilderPlanSignature(session), builderExerciseSignatures: getBuilderExerciseSignatures(session) }
}

/** A builder run with the same exercise (one shared profile) first and third. */
function builderRun() {
  const base = createRuntimeSession({ source: 'catalog', slug: 'barbell-floor-press' })
  const template = base.exercises[0]
  const exercises = [
    { ...withWeight(template, 40), id: 'press-1', order: 1, nextExerciseId: 'other-2' },
    { ...withWeight(template, 30), id: 'other-2', slug: 'machine-pulldown', order: 2, nextExerciseId: 'press-3' },
    { ...withWeight(template, 40), id: 'press-3', order: 3, nextExerciseId: undefined },
  ]
  return signed({
    ...base, source: 'builder', programId: 'back-biceps', dataSource: 'backend',
    exercises, currentExerciseId: 'press-1', currentSetIndex: 0, view: 'exercise-setup',
  })
}

function serverWith(session: RuntimeWorkoutSession, weights: Record<string, number>) {
  return signed({ ...session, exercises: session.exercises.map((exercise) => weights[exercise.id] === undefined ? exercise : withWeight(exercise, weights[exercise.id])) })
}

describe('runtime store builder refresh', () => {
  beforeEach(() => {
    localStorage.clear()
    useRuntimeStore.setState({ session: null, sessionSignature: null })
  })

  it('keeps the plan identity when only loads change', () => {
    const run = builderRun()
    expect(getStoredBuilderPlanSignature(serverWith(run, { 'press-3': 42.5 }))).toBe(getStoredBuilderPlanSignature(run))
    // Runs persisted before this release signed loads; their structure is derived from the run itself.
    expect(getStoredBuilderPlanSignature({ ...run, builderPlanSignature: '{"title":"old"}' })).toBe(run.builderPlanSignature)
  })

  it('takes a new shared weight for a later entry of the same exercise without losing progress', () => {
    const run = builderRun()
    useRuntimeStore.getState().initializeBackendSession(run, { source: 'builder', programId: 'back-biceps' })
    useRuntimeStore.getState().startExercise()
    useRuntimeStore.getState().finishCurrentSet()
    const inProgress = useRuntimeStore.getState().session!
    expect(inProgress.completedSets['press-1']).toHaveLength(1)

    // The weight changed during the first entry; the server now plans 42.5 kg for every entry.
    useRuntimeStore.getState().refreshBuilderExercises(serverWith(run, { 'press-1': 42.5, 'press-3': 42.5 }))
    const session = useRuntimeStore.getState().session!
    expect(session.completedSets['press-1']).toHaveLength(1)
    expect(session.currentExerciseId).toBe(inProgress.currentExerciseId)
    // The started entry keeps its own plan, the not yet started one follows the profile.
    expect(session.exercises[0].plan).toEqual(inProgress.exercises[0].plan)
    expect(session.exercises[2].loadSettings.weight).toBe(42.5)
    expect(session.exercises[2].plan.every((plan) => plan.recommendedWeightKg === 42.5)).toBe(true)
    expect(session.exercises[1]).toEqual(inProgress.exercises[1])
  })

  it('keeps local setup edits when the server load did not change', () => {
    const run = builderRun()
    useRuntimeStore.getState().initializeBackendSession(run, { source: 'builder', programId: 'back-biceps' })
    useRuntimeStore.getState().updateLoadSettings({ weight: 47.5 })
    useRuntimeStore.getState().refreshBuilderExercises(run)
    expect(useRuntimeStore.getState().session!.exercises[0].loadSettings.weight).toBe(47.5)

    // A real server change of the current, not yet started exercise is applied.
    useRuntimeStore.getState().refreshBuilderExercises(serverWith(run, { 'press-1': 50 }))
    expect(useRuntimeStore.getState().session!.exercises[0].loadSettings.weight).toBe(50)
    // Applied once: the same server snapshot again does not override newer local edits.
    useRuntimeStore.getState().updateLoadSettings({ weight: 52.5 })
    useRuntimeStore.getState().refreshBuilderExercises(serverWith(run, { 'press-1': 50 }))
    expect(useRuntimeStore.getState().session!.exercises[0].loadSettings.weight).toBe(52.5)
  })

  it('never touches the active set or completed exercises', () => {
    const run = builderRun()
    useRuntimeStore.getState().initializeBackendSession(run, { source: 'builder', programId: 'back-biceps' })
    useRuntimeStore.getState().startExercise()
    const active = useRuntimeStore.getState().session!
    expect(active.view).toBe('exercise-session')
    useRuntimeStore.getState().refreshBuilderExercises(serverWith(run, { 'press-1': 60 }))
    expect(useRuntimeStore.getState().session!.exercises[0]).toEqual(active.exercises[0])
    expect(useRuntimeStore.getState().session!.sessionState).toEqual(active.sessionState)
  })

  it('ignores non-builder runs', () => {
    const run = { ...builderRun(), source: 'catalog' as const }
    useRuntimeStore.getState().initializeBackendSession(run, { source: 'catalog' })
    useRuntimeStore.getState().refreshBuilderExercises(serverWith(run, { 'press-3': 99 }))
    expect(useRuntimeStore.getState().session!.exercises[2].loadSettings.weight).toBe(40)
  })
})
