import { describe, expect, it } from 'vitest'
import { stepDurationSeconds, stepRestSeconds, stepWeightKg } from '@/shared/lib/value-steps'

describe('value steps', () => {
  it('moves weight by 0.5 kg and snaps off-grid values onto the grid', () => {
    expect(stepWeightKg(15, 1)).toBe(15.5)
    expect(stepWeightKg(15, -1)).toBe(14.5)
    expect(stepWeightKg(47.3, 1)).toBe(47.5)
    expect(stepWeightKg(47.3, -1)).toBe(47)
    expect(stepWeightKg(0, -1)).toBe(0)
  })

  it('moves rest and duration by 10 s with their floors', () => {
    expect(stepRestSeconds(60, 1)).toBe(70)
    expect(stepRestSeconds(20, -1)).toBe(15)
    expect(stepRestSeconds(15, 1)).toBe(20)
    expect(stepRestSeconds(15, -1)).toBe(15)
    expect(stepDurationSeconds(45, 1)).toBe(50)
    expect(stepDurationSeconds(10, -1)).toBe(10)
  })
})
