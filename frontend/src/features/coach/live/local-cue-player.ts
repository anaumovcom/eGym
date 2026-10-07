import type { AudioReason, LocalCoachAudioManager } from '../audio/local-coach-audio-manager'
import type { LocalCue } from '../interpreter/coach-interpreter'

/** Verified, decoded clips by semantic ID (E09 prepared pack). Never fetches. */
export type ClipSource = Readonly<{ get: (clipId: string) => AudioBuffer | null }>
export const NO_CLIPS: ClipSource = Object.freeze({ get: () => null })
export type CueManager = Pick<LocalCoachAudioManager, 'playLocal' | 'cancelAll' | 'snapshot'>
export type CueOutcome = Readonly<{ cue: LocalCue; admitted: boolean; reason: AudioReason | 'admitted' }>

/** Maps interpreter cues to the local mixer. Safety cancels ordinary speech first.
 * Missing clips are an explicit `missing_clip`, never a substitute voice or beep here.
 */
export function playCue(manager: CueManager, clips: ClipSource, cue: LocalCue, nowMs: number, allowed: () => boolean): CueOutcome {
  if (cue.priority === 'safety') manager.cancelAll('safety')
  if (nowMs > cue.deadlineMs) return Object.freeze({ cue, admitted: false, reason: 'expired' })
  const buffer = cue.clipId ? clips.get(cue.clipId) : null
  if (!buffer) return Object.freeze({ cue, admitted: false, reason: 'missing_clip' })
  const admitted = manager.playLocal({ id: cue.id, scope: cue.scope, source: 'local', buffer, startDeadlineMs: cue.deadlineMs,
    baseGain: 1, revalidate: allowed })
  return Object.freeze({ cue, admitted, reason: admitted ? 'admitted' : manager.snapshot().reason })
}

/** Rep beep arbitration: an admitted voice count replaces the legacy beep for that
 * rep; a missing/rejected clip leaves the beep as the single fallback signal. */
export class RepBeepArbiter {
  private readonly voiced = new Map<number, number>()
  private readonly now: () => number
  constructor(now: () => number = () => performance.now()) { this.now = now }

  noteVoiceCount(count: number): void {
    this.prune()
    if (Number.isInteger(count) && count > 0 && this.voiced.size < 64) this.voiced.set(count, this.now())
  }

  shouldPlayLegacyBeep(count: number): boolean {
    this.prune()
    return !this.voiced.has(count)
  }

  clear(): void { this.voiced.clear() }

  private prune(): void {
    const now = this.now()
    for (const [count, at] of this.voiced) if (now - at > 2000 || now < at) this.voiced.delete(count)
  }
}

export const coachRepBeep = new RepBeepArbiter()
