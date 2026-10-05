import { describe, expect, it } from 'vitest'
import { positionFeedback, pulsesToMm } from './position-feedback'

describe('positionFeedback', () => {
  it('combines low/high words as a signed 32-bit position', () => {
    expect(positionFeedback(42, 0)).toBe(42)
    expect(positionFeedback(0xfffe, 0xffff)).toBe(-2)
    expect(positionFeedback(0, 1)).toBe(65536)
  })

  it('converts signed pulses to millimetres at 0.0032 mm per pulse', () => {
    expect(pulsesToMm(positionFeedback(10000, 0))).toBe(32)
    expect(pulsesToMm(positionFeedback(0xfffe, 0xffff))).toBe(-0.0064)
    expect(pulsesToMm(0.5)).toBe(0.0016)
  })

  it('converts pulses using the tape-measured 1703 mm / 6980387 pulse scale', () => {
    expect(pulsesToMm(6980387)).toBeCloseTo(1703, 6)
    expect(pulsesToMm(10000)).toBeCloseTo(2.4397, 3)
    expect(pulsesToMm(-2)).toBeCloseTo(-0.00048794, 6)
  })
})
