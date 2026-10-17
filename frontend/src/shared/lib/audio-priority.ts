/** Dependency-free priority bus: importing this module never creates an AudioContext.
 * Each mixer owns only its own contribution; idle/disposed owners retain no state. */
const owners = new Map<symbol, number>()
const listeners = new Set<() => void>()

export function getCoachAudibleCount(): number {
  return [...owners.values()].reduce((sum, count) => sum + count, 0)
}

export function setCoachAudible(owner: symbol, count: number): void {
  const previous = getCoachAudibleCount()
  if (Number.isFinite(count) && count > 0) owners.set(owner, Math.floor(count))
  else owners.delete(owner)
  if (getCoachAudibleCount() === previous) return
  for (const listener of listeners) {
    try { listener() } catch { /* An effect must never interrupt voice playback. */ }
  }
}

export function removeCoachAudioOwner(owner: symbol): void { setCoachAudible(owner, 0) }

export function subscribeAudioPriority(listener: () => void): () => void {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}