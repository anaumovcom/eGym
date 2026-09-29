export function positionFeedback(low: number, high: number): number {
  return ((high & 0xffff) << 16) | (low & 0xffff)
}

/** Mechanical travel per encoder pulse. */
export const MM_PER_PULSE = 0.0032

export function pulsesToMm(pulses: number): number {
  return pulses * MM_PER_PULSE
}
