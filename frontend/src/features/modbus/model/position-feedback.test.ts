import { describe, expect, it } from 'vitest'
import { positionFeedback, pulsesToMm } from './position-feedback'

describe('positionFeedback', () => {
  it('combines low/high words as a signed 32-bit position', () => {
    expect(positionFeedback(42, 0)).toBe(42)
    expect(positionFeedback(0xfffe, 0xffff)).toBe(-2)
    expect(positionFeedback(0, 1)).toBe(65536)
  })

  it('preserves the sign and fractional pulse at the measured scale', () => {
    expect(pulsesToMm(positionFeedback(0xfffe, 0xffff))).toBeCloseTo(-2 * 1703 / 6980387, 12)
    expect(pulsesToMm(0.5)).toBeCloseTo(0.5 * 1703 / 6980387, 12)
  })

  it('converts pulses using the tape-measured 1703 mm / 6980387 pulse scale', () => {
    expect(pulsesToMm(6980387)).toBeCloseTo(1703, 6)
    expect(pulsesToMm(10000)).toBeCloseTo(2.4397, 3)
    expect(pulsesToMm(-2)).toBeCloseTo(-0.00048794, 6)
  })
})
