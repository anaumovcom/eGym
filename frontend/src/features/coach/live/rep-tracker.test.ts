import { describe, expect, it } from 'vitest'
import { RepTracker, telemetryContext, type LoadDirection } from './rep-tracker'

/** Synthetic bar: each rep = concentric (up) then eccentric (down) at the given peak speeds and durations. */
function drive(tracker: RepTracker, reps: Array<{ up: number; down: number; upMs: number; downMs: number; pauseMs?: number }>,
  load: LoadDirection = 'down', start = 0) {
  let t = start, count = 0, position = 100
  tracker.begin('e1:1', t, 0)
  for (const rep of reps) {
    for (let ms = 0; ms < rep.upMs; ms += 100) { t += 100; position += rep.up / 10; tracker.sample({ atMs: t, positionMm: position, velocityMmPerSec: rep.up, loadDirection: load }) }
    for (let ms = 0; ms < rep.downMs; ms += 100) { t += 100; position -= rep.down / 10; tracker.sample({ atMs: t, positionMm: position, velocityMmPerSec: -rep.down, loadDirection: load }) }
    count++
    tracker.rep(count, t)
    for (let ms = 0; ms < (rep.pauseMs ?? 0); ms += 100) { t += 100; tracker.sample({ atMs: t, positionMm: position, velocityMmPerSec: 0, loadDirection: load }) }
  }
  return t
}

describe('RepTracker', () => {
  it('needs four reps before judging speed and steadiness', () => {
    const tracker = new RepTracker()
    const t = drive(tracker, Array.from({ length: 3 }, () => ({ up: 300, down: 200, upMs: 1000, downMs: 1500 })))
    const metrics = tracker.snapshot(t)
    expect(metrics).toMatchObject({ reps: 3, velocityDropPct: null, steady: null })
    expect(metrics.avgConcentricS).toBeCloseTo(1.0, 1)
    expect(metrics.avgEccentricS).toBeCloseTo(1.5, 1)
  })
  it('measures a fading set and a steady one', () => {
    const fading = new RepTracker()
    const speeds = [400, 400, 390, 340, 300, 250, 240]
    const t = drive(fading, speeds.map(up => ({ up, down: 250, upMs: 1000 + (400 - up) * 5, downMs: 1200 })))
    expect(fading.snapshot(t).velocityDropPct).toBe(39)
    const steady = new RepTracker()
    const t2 = drive(steady, Array.from({ length: 6 }, () => ({ up: 350, down: 250, upMs: 1000, downMs: 1400 })))
    expect(steady.snapshot(t2)).toMatchObject({ velocityDropPct: 0, steady: true })
  })
  it('attributes phases by load direction and tracks pauses after the first rep', () => {
    const tracker = new RepTracker()
    const t = drive(tracker, [{ up: 300, down: 300, upMs: 800, downMs: 2000, pauseMs: 6000 }, { up: 300, down: 300, upMs: 800, downMs: 2000 }], 'up')
    const metrics = tracker.snapshot(t)
    // Load pushes up: moving down is the concentric (effort) phase.
    expect(metrics.avgConcentricS).toBeCloseTo(2.0, 1)
    expect(metrics.avgEccentricS).toBeCloseTo(0.8, 1)
    expect(metrics.longestPauseMs).toBeGreaterThanOrEqual(5_900)
    expect(tracker.snapshot(t + 5_000).stillMs).toBe(5_000)
  })
  it('keeps the finished set for its saved result and exposes only bounded numbers', () => {
    const tracker = new RepTracker()
    const t = drive(tracker, Array.from({ length: 5 }, () => ({ up: 300, down: 450, upMs: 1200, downMs: 600 })))
    tracker.begin('e1:2', t + 1000, 0)
    const finished = tracker.finishedSet('e1:1', t + 2000)
    expect(telemetryContext(finished)).toEqual({ reps: 5, longestPauseS: 0, velocityDropPct: 0, concentricS: 1.2, eccentricS: 0.6, steady: true })
    expect(telemetryContext(null)).toEqual({})
  })
})
