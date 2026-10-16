import { describe, expect, it } from 'vitest'
import type { RuntimeSetPlan } from '@/entities/runtime/model/types'
import { expandPerSidePlan } from './per-side'

describe('expandPerSidePlan', () => {
  const base: RuntimeSetPlan[] = [{ targetReps: 10, weightLabel: '20 кг', restSeconds: 60, setType: 'work', note: 'note', warning: 'warning', recommendedWeightKg: 20 }]

  it('expands 1 × 10 into left 10 then right 10 without mutating the base', () => {
    expect(expandPerSidePlan(base, true)).toEqual([
      { ...base[0], setNumber: 1, side: 'left', roundNumber: 1, restSeconds: 0 },
      { ...base[0], setNumber: 2, side: 'right', roundNumber: 1 },
    ])
    expect(base[0]).not.toHaveProperty('side')
    expect(base[0].restSeconds).toBe(60)
  })

  it.each([false, undefined])('preserves unflagged behavior (%s)', (flag) => {
    expect(expandPerSidePlan(base, flag)).toBe(base)
  })

  it('expands warmups and timed sets exactly once, preserving targets and rest', () => {
    const plan: RuntimeSetPlan[] = [
      { targetSeconds: 15, setType: 'warmup', weightLabel: 'вес тела', restSeconds: 30 },
      { targetSeconds: 45, setType: 'work', weightLabel: 'вес тела', restSeconds: 90 },
    ]
    const expanded = expandPerSidePlan(plan, true)
    expect(expanded.map((set) => [set.setNumber, set.roundNumber, set.side, set.targetSeconds, set.restSeconds])).toEqual([
      [1, 1, 'left', 15, 0], [2, 1, 'right', 15, 30],
      [3, 2, 'left', 45, 0], [4, 2, 'right', 45, 90],
    ])
    expect(expanded.map((set) => set.setType)).toEqual(['warmup', 'warmup', 'work', 'work'])
    expect(expandPerSidePlan([], true)).toEqual([])
  })
})