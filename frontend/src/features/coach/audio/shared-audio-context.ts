let sharedContext: AudioContext | null = null

/** Existing context only; never constructs one (safe from timers/subscriptions). */
export function peekSharedAudioContext(): AudioContext | null {
  return sharedContext?.state === 'closed' ? null : sharedContext
}

/** Lazy, browser-only, shared ownership. No caller may close this context. */
export function getSharedAudioContext(): AudioContext | null {
  if (sharedContext?.state === 'closed') return null
  if (sharedContext) return sharedContext
  if (typeof globalThis.AudioContext !== 'function') return null
  try {
    sharedContext = new globalThis.AudioContext()
  } catch {
    return null
  }
  return sharedContext
}

/** Call directly from a trusted click/key handler, not from an effect/timer.
 * No synthetic event, silent-buffer autoplay workaround, or retry fallback.
 */
export async function unlockSharedAudioContext(): Promise<boolean> {
  if (typeof navigator !== 'undefined' && navigator.userActivation && !navigator.userActivation.isActive) return false
  const context = getSharedAudioContext()
  if (!context) return false
  try {
    if (context.state !== 'running') await context.resume()
    return context.state === 'running'
  } catch {
    return false
  }
}