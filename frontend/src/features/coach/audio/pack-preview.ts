import type { CoachPackClient, PackSlot } from './pack-client'
import { peekSharedAudioContext, unlockSharedAudioContext } from './shared-audio-context'

/** Trusted settings gesture only. No URL, provider, fallback voice or workout mixer. */
export async function previewPackClip(client: CoachPackClient, slot: PackSlot, id: string, volume: number, signal: AbortSignal): Promise<boolean> {
  if (!(volume > 0) || signal.aborted || !await unlockSharedAudioContext() || signal.aborted) return false
  const context = peekSharedAudioContext(), buffer = await client.audition(slot, id, signal)
  if (!context || context.state !== 'running' || !buffer || signal.aborted) return false
  const source = context.createBufferSource(), gain = context.createGain()
  source.buffer = buffer; gain.gain.value = Math.min(1, volume)
  source.connect(gain); gain.connect(context.destination)
  return new Promise(resolve => {
    const finish = () => {
      signal.removeEventListener('abort', cancel); source.onended = null
      source.disconnect(); gain.disconnect(); resolve(!signal.aborted)
    }
    const cancel = () => { try { source.stop() } finally { finish() } }
    source.onended = finish
    signal.addEventListener('abort', cancel, { once: true })
    try { source.start() } catch { signal.removeEventListener('abort', cancel); source.onended = null; source.disconnect(); gain.disconnect(); resolve(false) }
  })
}