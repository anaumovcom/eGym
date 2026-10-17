import { describe, expect, it } from 'vitest'
import { OPPORTUNITY_STATES, transitionOpportunity, type OpportunityState } from './opportunity'

describe('opportunity FSM', () => {
  it.each(['completed', 'interrupted', 'expired', 'rejected'] as const)('never resurrects %s or double counts a transition', terminal => {
    let state: OpportunityState = 'pending'
    expect(transitionOpportunity(state, 'completed')).toBe('pending')
    state = transitionOpportunity(state, 'preparing')
    expect(transitionOpportunity(state, 'preparing')).toBe(state)
    if (terminal === 'completed' || terminal === 'interrupted') {
      state = transitionOpportunity(state, 'ready')
      state = transitionOpportunity(state, 'started')
    }
    state = transitionOpportunity(state, terminal)
    for (const next of OPPORTUNITY_STATES) expect(transitionOpportunity(state, next)).toBe(terminal)
  })
})