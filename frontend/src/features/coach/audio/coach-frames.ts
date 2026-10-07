import type { CoachAudio, CoachScope } from '../model/contracts'

/** E08 tagged PCM wire format: "ECA1" | u32 LE header length | JSON CoachAudio | PCM s16le mono. */
export const FRAME_MAGIC = [0x45, 0x43, 0x41, 0x31] as const
export const MAX_FRAME_HEADER_BYTES = 4096
export const MAX_FRAME_PCM_BYTES = 96_000
export const MAX_STREAM_PCM_BYTES = 2_880_000
export type CoachFrame = Readonly<{ metadata: CoachAudio; pcm: Uint8Array }>
export class CoachFrameError extends Error {}

const SOURCES = new Set(['local', 'cache', 'realtime', 'tts', 'fake'])
const isId = (value: unknown) => typeof value === 'string' && value.length > 0 && value.length <= 120
const isCount = (value: unknown) => Number.isInteger(value) && (value as number) >= 0

function parseScope(value: unknown): CoachScope {
  const scope = value as Record<string, unknown> | null
  if (!scope || typeof scope !== 'object' || scope.schemaVersion !== 1 || !isId(scope.userId) || !isId(scope.runId) ||
      !(scope.exerciseId === null || (typeof scope.exerciseId === 'string' && scope.exerciseId.length > 0 && scope.exerciseId.length <= 160)) ||
      !(scope.setOrdinal === null || (Number.isInteger(scope.setOrdinal) && (scope.setOrdinal as number) >= 1)) ||
      !isCount(scope.scopeEpoch) || (scope.setOrdinal !== null && scope.exerciseId === null)) throw new CoachFrameError('frame_header')
  return Object.freeze({ schemaVersion: 1, userId: scope.userId as string, runId: scope.runId as string,
    exerciseId: scope.exerciseId as string | null, setOrdinal: scope.setOrdinal as number | null, scopeEpoch: scope.scopeEpoch as number })
}

export function pcmDurationMs(byteLength: number, sampleRate: number): number { return byteLength / 2 / sampleRate * 1000 }

function parseMetadata(value: unknown, payloadLength: number): CoachAudio {
  const meta = value as Record<string, unknown> | null
  if (!meta || typeof meta !== 'object' || meta.schemaVersion !== 1 || !isId(meta.utteranceId) || !isId(meta.generationId) ||
      !isCount(meta.sequence) || !SOURCES.has(meta.source as string) || typeof meta.final !== 'boolean' ||
      !Number.isInteger(meta.sampleRate) || (meta.sampleRate as number) < 8000 || (meta.sampleRate as number) > 96000 ||
      !isCount(meta.byteLength) || typeof meta.durationMs !== 'number' || !Number.isFinite(meta.durationMs)) throw new CoachFrameError('frame_header')
  if (meta.codec !== 'pcm_s16le' || meta.channels !== 1) throw new CoachFrameError('frame_codec')
  if (meta.byteLength !== payloadLength || payloadLength % 2 || payloadLength > MAX_FRAME_PCM_BYTES) throw new CoachFrameError('frame_length')
  if (Math.abs((meta.durationMs as number) - pcmDurationMs(payloadLength, meta.sampleRate as number)) > 1) throw new CoachFrameError('frame_duration')
  return Object.freeze({ schemaVersion: 1, utteranceId: meta.utteranceId as string, generationId: meta.generationId as string,
    scope: parseScope(meta.scope), sequence: meta.sequence as number, source: meta.source as CoachAudio['source'],
    codec: 'pcm_s16le', sampleRate: meta.sampleRate as number, channels: 1, byteLength: payloadLength,
    durationMs: meta.durationMs as number, final: meta.final as boolean })
}

function headerLength(bytes: Uint8Array): number {
  if (bytes.length < 8 || FRAME_MAGIC.some((value, index) => bytes[index] !== value)) throw new CoachFrameError('frame_magic')
  const size = new DataView(bytes.buffer, bytes.byteOffset, 8).getUint32(4, true)
  if (size < 2 || size > MAX_FRAME_HEADER_BYTES) throw new CoachFrameError('frame_header')
  return size
}

function parseHeader(bytes: Uint8Array): unknown {
  try { return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)) } catch { throw new CoachFrameError('frame_header') }
}

/** Decodes one complete frame; the PCM is copied so callers cannot alias the network buffer. */
export function decodeCoachFrame(bytes: Uint8Array): CoachFrame {
  const size = headerLength(bytes)
  if (bytes.length < 8 + size) throw new CoachFrameError('frame_header')
  const header = parseHeader(bytes.subarray(8, 8 + size))
  const pcm = bytes.slice(8 + size)
  return Object.freeze({ metadata: parseMetadata(header, pcm.length), pcm })
}

export function encodeCoachFrame(metadata: CoachAudio, pcm: Uint8Array): Uint8Array {
  parseMetadata(metadata, pcm.length)
  const header = new TextEncoder().encode(JSON.stringify(metadata))
  if (header.length > MAX_FRAME_HEADER_BYTES) throw new CoachFrameError('frame_header')
  const out = new Uint8Array(8 + header.length + pcm.length)
  out.set(FRAME_MAGIC, 0)
  new DataView(out.buffer).setUint32(4, header.length, true)
  out.set(header, 8); out.set(pcm, 8 + header.length)
  return out
}

/** Incremental reader for a byte stream of back-to-back frames.
 * Frame boundaries come from the header byteLength, not from network chunking.
 * The buffer never holds more than one maximal frame.
 */
export class CoachFrameReader {
  private buffer = new Uint8Array(0)
  private total = 0

  push(chunk: Uint8Array): CoachFrame[] {
    const merged = new Uint8Array(this.buffer.length + chunk.length)
    merged.set(this.buffer); merged.set(chunk, this.buffer.length)
    this.buffer = merged
    const frames: CoachFrame[] = []
    while (this.buffer.length >= 8) {
      const size = headerLength(this.buffer)
      if (this.buffer.length < 8 + size) break
      const header = parseHeader(this.buffer.subarray(8, 8 + size)) as Record<string, unknown>
      const length = header?.byteLength
      if (!isCount(length) || (length as number) > MAX_FRAME_PCM_BYTES) throw new CoachFrameError('frame_length')
      const end = 8 + size + (length as number)
      if (this.buffer.length < end) break
      const frame = decodeCoachFrame(this.buffer.subarray(0, end))
      this.total += frame.pcm.length
      if (this.total > MAX_STREAM_PCM_BYTES) throw new CoachFrameError('pcm_bound')
      frames.push(frame)
      this.buffer = this.buffer.slice(end)
    }
    if (this.buffer.length > 8 + MAX_FRAME_HEADER_BYTES + MAX_FRAME_PCM_BYTES) throw new CoachFrameError('frame_length')
    return frames
  }

  /** A clean stream ends exactly on a frame boundary; trailing bytes are a truncated frame. */
  finish(): void { if (this.buffer.length) throw new CoachFrameError('truncated') }
}

/** s16le mono → Float32 AudioBuffer with a fixed -12 dB headroom (same peak budget as local clips). */
export const STREAM_SCALE = 0.25
export function pcmS16ToAudioBuffer(context: BaseAudioContext, pcm: Uint8Array, sampleRate: number): AudioBuffer {
  if (!pcm.length || pcm.length % 2) throw new CoachFrameError('frame_length')
  const view = new DataView(pcm.buffer, pcm.byteOffset, pcm.byteLength)
  const buffer = context.createBuffer(1, pcm.length / 2, sampleRate)
  const samples = buffer.getChannelData(0)
  for (let index = 0; index < samples.length; index++) samples[index] = view.getInt16(index * 2, true) / 32768 * STREAM_SCALE
  return buffer
}
