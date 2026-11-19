import type { RuntimeExercisePlan, RuntimeWorkoutSession } from '@/entities/runtime/model/types'

// ReviewedTip v1 in services/coach/tips.py. These are exact pack IDs, not text to synthesize.
export const ACTIVE_MACHINE_TIP = 'tip-machine-no-jerks'
export const REST_MACHINE_TIP = 'tip-machine-prepare'
const slug = 'machine-pulldown'
const prerequisites = ['loaded-catalog-machine', 'known-mode', 'no-discomfort']
const exclusions = ['body-observation', 'cable-variant-inference', 'pain', 'load-change']

/** Fail closed for a revised review, an unknown prerequisite or a different phase.
 * Return only the supported metadata so a verified manifest can round-trip through CacheStorage. */
export function reviewedTipMetadata(id: string, raw: unknown) {
  const phases = id === ACTIVE_MACHINE_TIP ? ['active'] : id === REST_MACHINE_TIP ? ['setup', 'rest'] : null
  if (!phases || !raw || typeof raw !== 'object') return null
  const t = raw as Record<string, unknown>
  const same = (value: unknown, expected: string[]) => Array.isArray(value) && value.length === expected.length && expected.every(s => value.includes(s))
  if (t.kind !== 'machine' || t.version !== '1' || !same(t.exerciseSlugs, [slug]) || !same(t.loadModes, ['constant']) ||
    !same(t.phases, phases) || !same(t.prerequisites, prerequisites) || !same(t.exclusions, exclusions)) return null
  return { kind: 'machine', version: '1', exerciseSlugs: [slug], loadModes: ['constant'], phases, prerequisites, exclusions } as const
}

export function reviewedMachineExercise(session: RuntimeWorkoutSession, exercise: RuntimeExercisePlan): boolean {
  return session.dataSource === 'backend' && exercise.kind === 'machine' && exercise.slug === slug &&
    exercise.summary?.slug === slug && exercise.details?.slug === slug && ['Machine', 'Тренажёр'].includes(exercise.details.equipment) &&
    ['constant', 'Обычный вес'].includes(exercise.loadSettings?.mode) &&
    !(session.completedSets[exercise.id] ?? []).some(set => set.pain || (set.discomfortLevel != null && set.discomfortLevel !== 0))
}