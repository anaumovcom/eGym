/** One step size for every weight / time stepper in the app. */
export const WEIGHT_STEP_KG = 0.5
export const SECONDS_STEP = 10
/** The backend keeps rest at 15 s or more. */
export const MIN_REST_SECONDS = 15
export const MIN_DURATION_SECONDS = 10

/**
 * Moves to the next point of the `step` grid in `delta`'s direction, so an
 * off-grid value (15 s, 47.3 kg) lands on the grid instead of staying off it.
 */
function stepOnGrid(current: number, delta: number, step: number, min: number) {
  const units = current / step
  // Float noise (47.5 / 0.5 = 94.99999) must not count as "between" grid points.
  const base = delta > 0 ? Math.floor(units + 1e-9) : Math.ceil(units - 1e-9)
  const next = (base + delta) * step
  return Math.max(min, Math.round(next * 100) / 100)
}

export function stepWeightKg(current: number, delta: number) {
  return stepOnGrid(current, delta, WEIGHT_STEP_KG, 0)
}

export function stepRestSeconds(current: number, delta: number) {
  return stepOnGrid(current, delta, SECONDS_STEP, MIN_REST_SECONDS)
}

export function stepDurationSeconds(current: number, delta: number) {
  return stepOnGrid(current, delta, SECONDS_STEP, MIN_DURATION_SECONDS)
}
