/** V2 rep telemetry from the machine's own bar position/velocity stream (no camera, no body inference).
 * Concentric = moving against the load (load pulls down → bar moving up). Durations come from sample
 * spacing, so they are relative measures (rounded, ±0.25 s), never a medical or form assessment. */
export type LoadDirection = 'down' | 'up'
export type TelemetrySample = Readonly<{ atMs: number; positionMm: number; velocityMmPerSec: number; loadDirection: LoadDirection }>
export type SetTelemetry = Readonly<{
  reps: number
  /** Peak speed of the last two reps vs the best of the first three, %; null before four reps. */
  velocityDropPct: number | null
  avgConcentricS: number | null
  avgEccentricS: number | null
  /** Rep durations vary by less than STEADY_CV: a «ровный темп» set. Null before four reps. */
  steady: boolean | null
  /** Time since the bar last moved (only after the first rep). */
  stillMs: number
  longestPauseMs: number
}>

const MOVING_MM_S = 15
const MAX_GAP_MS = 500
const STEADY_CV = 0.15
const MIN_PHASE_MS = 150

type Rep = { peak: number; concentricMs: number; eccentricMs: number; startedAt: number; endedAt: number }

const mean = (values: readonly number[]) => values.reduce((sum, value) => sum + value, 0) / values.length
const round = (value: number, step: number) => Number((Math.round(value / step) * step).toFixed(2))

export class RepTracker {
  private key = ''
  private reps: Rep[] = []
  private current: Rep = { peak: 0, concentricMs: 0, eccentricMs: 0, startedAt: 0, endedAt: 0 }
  private count: number | null = null
  private last: TelemetrySample | null = null
  private movedAt = 0
  private lastRepAt = 0
  private longestPause = 0
  private readonly finished = new Map<string, SetTelemetry>()

  /** Start (or keep) tracking the given set; a new key closes the previous set's metrics. */
  begin(key: string, nowMs: number, reps: number | null): void {
    if (key === this.key) return
    // A finished set is measured up to its last rep: the walk to the rest screen is not a pause.
    if (this.key) this.finished.set(this.key, this.snapshot(this.reps.length ? this.lastRepAt : nowMs))
    while (this.finished.size > 64) this.finished.delete(this.finished.keys().next().value!)
    this.key = key
    this.reps = []
    this.current = { peak: 0, concentricMs: 0, eccentricMs: 0, startedAt: nowMs, endedAt: nowMs }
    this.count = reps
    this.last = null
    this.movedAt = nowMs
    this.longestPause = 0
  }

  sample(sample: TelemetrySample | null | undefined): void {
    if (!sample || !this.key || !Number.isFinite(sample.velocityMmPerSec) || !Number.isFinite(sample.atMs)) return
    const previous = this.last
    this.last = sample
    if (!previous || sample.atMs <= previous.atMs) return
    const dt = Math.min(MAX_GAP_MS, sample.atMs - previous.atMs)
    const speed = Math.abs(sample.velocityMmPerSec)
    if (speed < MOVING_MM_S) {
      if (this.reps.length) this.longestPause = Math.max(this.longestPause, sample.atMs - this.movedAt)
      return
    }
    this.movedAt = sample.atMs
    const up = sample.velocityMmPerSec > 0
    const concentric = sample.loadDirection === 'down' ? up : !up
    // Fatigue shows in the effort (concentric) phase; a dropped descent must not mask it.
    if (concentric) { this.current.concentricMs += dt; this.current.peak = Math.max(this.current.peak, speed) }
    else this.current.eccentricMs += dt
  }

  /** The confirmed rep counter (interpreter baseline) changed: close the current rep window. */
  rep(reps: number | null, nowMs: number): void {
    if (reps === null || this.count === null || reps <= this.count) { this.count = reps ?? this.count; return }
    for (let index = this.count; index < reps; index++) {
      this.reps.push({ ...this.current, endedAt: nowMs })
      this.current = { peak: 0, concentricMs: 0, eccentricMs: 0, startedAt: nowMs, endedAt: nowMs }
    }
    this.count = reps
    this.movedAt = Math.max(this.movedAt, nowMs)
    this.lastRepAt = nowMs
  }

  snapshot(nowMs: number): SetTelemetry {
    const reps = this.reps.filter(rep => rep.peak > 0)
    let velocityDropPct: number | null = null
    let steady: boolean | null = null
    if (reps.length >= 4) {
      const best = Math.max(...reps.slice(0, 3).map(rep => rep.peak))
      const recent = mean(reps.slice(-2).map(rep => rep.peak))
      velocityDropPct = best > 0 ? Math.max(0, Math.round((best - recent) / best * 100)) : null
      const durations = reps.map(rep => rep.endedAt - rep.startedAt).filter(value => value > 0)
      if (durations.length >= 4) {
        const average = mean(durations)
        const cv = Math.sqrt(mean(durations.map(value => (value - average) ** 2))) / average
        steady = cv < STEADY_CV
      }
    }
    const phases = reps.filter(rep => rep.concentricMs >= MIN_PHASE_MS && rep.eccentricMs >= MIN_PHASE_MS)
    const still = this.reps.length ? Math.max(0, nowMs - this.movedAt) : 0
    return Object.freeze({
      reps: this.reps.length, velocityDropPct,
      avgConcentricS: phases.length >= 2 ? round(mean(phases.map(rep => rep.concentricMs)) / 1000, 0.1) : null,
      avgEccentricS: phases.length >= 2 ? round(mean(phases.map(rep => rep.eccentricMs)) / 1000, 0.1) : null,
      steady, stillMs: still, longestPauseMs: Math.max(this.longestPause, still),
    })
  }

  /** Metrics of a set that has already ended (looked up when its result is saved). */
  finishedSet(key: string, nowMs: number): SetTelemetry | null {
    if (key === this.key) return this.snapshot(this.reps.length ? Math.min(nowMs, this.lastRepAt) : nowMs)
    return this.finished.get(key) ?? null
  }

  clear(): void { this.key = ''; this.finished.clear(); this.reps = []; this.count = null; this.last = null }
}

/** Bounded wire form for the coach: rounded, relative numbers only. */
export function telemetryContext(metrics: SetTelemetry | null): Record<string, number | boolean> {
  if (!metrics || metrics.reps < 1) return {}
  const out: Record<string, number | boolean> = { reps: metrics.reps, longestPauseS: round(metrics.longestPauseMs / 1000, 0.5) }
  if (metrics.velocityDropPct !== null) out.velocityDropPct = Math.min(100, metrics.velocityDropPct)
  if (metrics.avgConcentricS !== null) out.concentricS = metrics.avgConcentricS
  if (metrics.avgEccentricS !== null) out.eccentricS = metrics.avgEccentricS
  if (metrics.steady !== null) out.steady = metrics.steady
  return out
}
