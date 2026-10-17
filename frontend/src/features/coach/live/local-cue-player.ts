import type { AudioReason, LocalCoachAudioManager, LocalPlayback } from '../audio/local-coach-audio-manager'
import type { LocalCue } from '../interpreter/coach-interpreter'
import { COMPLETION_IDEAS } from './local-completion'

/** Verified, decoded clips by semantic ID (E09 prepared pack). Never fetches. */
export type ClipSource = Readonly<{ get: (clipId: string) => AudioBuffer | null }>
export const NO_CLIPS: ClipSource = Object.freeze({ get: () => null })
// Keep count clearly below live speech, including a later count that ducks
// the live voice to .65: .4 / .65 leaves ~4 dB of voice/count separation.
export const OFFLINE_COUNT_GAIN = 0.4
export type CueManager = Pick<LocalCoachAudioManager, 'playLocal' | 'cancelAll' | 'snapshot'>
export type CueOutcome = Readonly<{ cue: LocalCue; admitted: boolean; reason: AudioReason | 'admitted' }>

function playback(cue: LocalCue): LocalPlayback {
  if (cue.kind === 'count' || cue.kind === 'countdown') return { kind: 'count', action: 'count' }
  const action = cue.priority === 'safety' ? 'safety'
    : cue.kind.startsWith('workout-') || cue.kind.startsWith('exercise-') ? 'summary'
      : cue.kind.startsWith('set-') || cue.kind === 'target' ? 'result'
        : ['start', 'hold-start', 'resume', 'last-set-next', 'rest-ready'].includes(cue.kind) ? 'orient' : 'support'
  return { kind: 'cue', action }
}

/** Maps interpreter cues to the local mixer. Safety cancels ordinary speech first.
 * Missing clips are an explicit `missing_clip`, never a substitute voice or beep here.
 */
export function playCue(manager: CueManager, clips: ClipSource, cue: LocalCue, nowMs: number, allowed: () => boolean): CueOutcome {
  if (cue.priority === 'safety') manager.cancelAll('safety')
  if (nowMs > cue.deadlineMs) return Object.freeze({ cue, admitted: false, reason: 'expired' })
  const buffer = cue.clipId ? clips.get(cue.clipId) : null
  if (!buffer) return Object.freeze({ cue, admitted: false, reason: 'missing_clip' })
  const localPlayback = playback(cue)
  const admitted = manager.playLocal({ id: cue.id, scope: cue.scope, source: 'local', buffer, startDeadlineMs: cue.deadlineMs,
    baseGain: localPlayback.kind === 'count' ? OFFLINE_COUNT_GAIN : 1, revalidate: allowed,
    completion: !!cue.clipId && cue.clipId in COMPLETION_IDEAS, localPlayback })
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
