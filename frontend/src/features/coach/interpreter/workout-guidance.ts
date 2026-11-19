import type { RuntimeExercisePlan } from '@/entities/runtime/model/types'
import catalog from './workout-guidance.generated.json'

export type TipPhase = 'setup' | 'active' | 'rest'
type Profile = Readonly<{ equipment: readonly string[]; variants: Readonly<Record<string, string>>; activeControl: string | null }>
const profiles: Readonly<Record<string, Profile>> = catalog.profiles
const movements = new Map(catalog.movements.map(row => [row.slug, row]))
export const MOTIVATION_IDS: readonly string[] = catalog.motivation
const PHASE_LABELS: Record<TipPhase, string> = { setup: 'Подготовка', active: 'В движении', rest: 'Следующий подход' }
const modes = new Map([['Обычный вес', 'constant'], ['constant', 'constant'], ['Темповый режим', 'timer'], ['timer', 'timer'],
  ['Без тренажёра', 'unloaded'], ['unloaded', 'unloaded']])

type Movement = typeof catalog.movements[number]
export const movementClip = (movement: Movement, phase: TipPhase): string => `tip-${movement.key}-${phase}`
const clipInfo = new Map<string, { movement: Movement; phase: TipPhase }>()
for (const movement of movements.values()) for (const phase of ['setup', 'active', 'rest'] as const) {
  clipInfo.set(movementClip(movement, phase), { movement, phase })
}

export function movementFor(ex: RuntimeExercisePlan) {
  const movement = movements.get(ex.slug)
  if (!movement || ex.summary?.slug !== ex.slug || ex.details?.slug !== ex.slug) return null
  const profile = profiles[movement.profile], mode = modes.get(ex.loadSettings?.mode)
  if (!mode || profile.variants[ex.kind] !== mode || !profile.equipment.includes(ex.details.equipment) ||
    (ex.summary.equipment && !profile.equipment.includes(ex.summary.equipment)) ||
    (mode === 'unloaded' && ex.loadSettings.weight !== 0)) return null
  return { movement, activeControl: profile.activeControl }
}

export function workoutTipMetadata(id: string, raw: unknown) {
  const info = clipInfo.get(id)
  if (!info || !raw || typeof raw !== 'object') return null
  const tip = raw as Record<string, unknown>, { movement, phase } = info
  const only = (v: unknown, expected: string) => Array.isArray(v) && v.length === 1 && v[0] === expected
  if (tip.kind !== 'workout' || tip.version !== catalog.version || tip.profile !== movement.profile ||
      !only(tip.exerciseSlugs, movement.slug) || !only(tip.phases, phase) ||
      Object.keys(tip).some(k => !['kind', 'version', 'profile', 'exerciseSlugs', 'phases'].includes(k))) return null
  return { kind: 'workout', version: catalog.version, profile: movement.profile, exerciseSlugs: [movement.slug], phases: [phase] } as const
}

export function movementClipLabel(id: string): string | null {
  const info = clipInfo.get(id)
  return info ? `${info.movement.label} · ${PHASE_LABELS[info.phase]}` : null
}