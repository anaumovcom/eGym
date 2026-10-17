export const OPPORTUNITY_STATES = ['pending', 'preparing', 'ready', 'started', 'completed', 'interrupted', 'expired', 'rejected'] as const
export type OpportunityState = typeof OPPORTUNITY_STATES[number]
const NEXT: Partial<Record<OpportunityState, readonly OpportunityState[]>> = {
  pending: ['preparing', 'expired', 'rejected'], preparing: ['ready', 'expired', 'rejected'],
  ready: ['started', 'expired', 'rejected'], started: ['completed', 'interrupted'],
}
export function transitionOpportunity(current: OpportunityState, target: OpportunityState): OpportunityState {
  return NEXT[current]?.includes(target) ? target : current
}