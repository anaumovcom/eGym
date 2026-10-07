import type { CoachScope } from '../model/contracts'
import { CoachFrameError, CoachFrameReader } from './coach-frames'
import type { AudioReason, LocalCoachAudioManager } from './local-coach-audio-manager'

export type StreamMixer = Pick<LocalCoachAudioManager, 'beginStream' | 'pushStream' | 'cancelStream' | 'snapshot'>
export type PlayStreamOptions = Readonly<{
  scope: CoachScope; startDeadlineMs: number; baseGain: number; revalidate: () => boolean
  prebufferMs?: number; signal?: AbortSignal
}>
export type PlayStreamResult = Readonly<{ status: 'delivered' | 'cancelled' | 'failed'; reason: AudioReason | string; frames: number }>

/** Feeds a tagged-PCM byte stream into the shared mixer. Network chunking never defines frame boundaries.
 * 'delivered' means every frame reached the mixer, not that it was heard: start/end acks come from playback.
 */
export async function playCoachStream(mixer: StreamMixer, body: ReadableStream<Uint8Array>, options: PlayStreamOptions): Promise<PlayStreamResult> {
  const reader = body.getReader()
  const frames = new CoachFrameReader()
  let id: string | null = null
  let count = 0
  let final = false
  const stop = async (status: 'cancelled' | 'failed', reason: string): Promise<PlayStreamResult> => {
    if (id) mixer.cancelStream(id, status === 'cancelled' ? 'cancelled' : 'invalid')
    try { await reader.cancel() } catch { /* Already closed. */ }
    return Object.freeze({ status, reason, frames: count })
  }
  try {
    while (true) {
      if (options.signal?.aborted) return await stop('cancelled', 'cancelled')
      const { done, value } = await reader.read()
      if (options.signal?.aborted) return await stop('cancelled', 'cancelled')
      if (done) {
        frames.finish()
        // End is confirmed by the protocol (final frame), not inferred from silence or a closed socket.
        if (!final) return await stop('failed', 'truncated')
        break
      }
      for (const frame of frames.push(value)) {
        const meta = frame.metadata
        if (id === null) {
          if (meta.source === 'local' || meta.source === 'cache' || meta.sequence !== 0) return await stop('failed', 'invalid')
          id = meta.utteranceId
          if (!mixer.beginStream({ id, generationId: meta.generationId, scope: options.scope, source: meta.source,
            sampleRate: meta.sampleRate, startDeadlineMs: options.startDeadlineMs, baseGain: options.baseGain,
            revalidate: options.revalidate, prebufferMs: options.prebufferMs })) {
            const reason = mixer.snapshot().reason
            id = null
            return await stop('failed', reason)
          }
        }
        if (!mixer.pushStream(meta, frame.pcm)) return await stop('failed', mixer.snapshot().reason)
        count++
        final = meta.final
      }
    }
  } catch (error) {
    return await stop('failed', error instanceof CoachFrameError ? error.message : 'network')
  } finally {
    reader.releaseLock?.()
  }
  return Object.freeze({ status: 'delivered', reason: 'ready', frames: count })
}
