export function positionFeedback(low: number, high: number): number {
  return ((high & 0xffff) << 16) | (low & 0xffff)
}

/** Travel millimetres per pulse above the session zero, not the absolute encoder. */
export const MM_PER_PULSE = 1703 / 6980387

export function pulsesToMm(pulses: number): number {
  return pulses * MM_PER_PULSE
}
