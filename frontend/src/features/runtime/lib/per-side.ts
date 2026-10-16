import type { RuntimeSetPlan } from '@/entities/runtime/model/types'

/** Expand a base (not already expanded) plan. Rebuilds must generate the base first. */
export function expandPerSidePlan(plan: RuntimeSetPlan[], perSide?: boolean): RuntimeSetPlan[] {
  if (!perSide) return plan

  return plan.flatMap((set, index) => [
    { ...set, setNumber: index * 2 + 1, roundNumber: index + 1, side: 'left' as const, restSeconds: 0 },
    { ...set, setNumber: index * 2 + 2, roundNumber: index + 1, side: 'right' as const },
  ])
}