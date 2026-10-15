import { describe, expect, it } from 'vitest'

import { buildStrengthPlan } from './strength-plan'

describe('buildStrengthPlan warm-up', () => {
  it('halves the reps for a bodyweight warm-up', () => {
    const plan = buildStrengthPlan('basic', null, { reps: 5, weight: 0, restSeconds: 60 }, 'bodyweight', { sets: 4 })
    expect(plan.map((set) => set.targetRepsLabel)).toEqual(['3', '5', '5', '5'])
  })

  it('keeps a lighter, longer warm-up when there is external weight', () => {
    const plan = buildStrengthPlan('basic', null, { reps: 5, weight: 40, restSeconds: 60 }, 'weighted', { sets: 4 })
    expect(plan[0]).toMatchObject({ targetRepsLabel: '8–10', recommendedWeightLabel: '20 кг' })
  })
})
