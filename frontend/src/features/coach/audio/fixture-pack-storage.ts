import { localBufferBytes, verifyLocalBuffer } from './local-buffers'
import { createTestClipWav } from './test-clips'
import type { TestClipId } from './test-clips'

export const MAX_DECODED_CACHE_BYTES = 32 * 1024 * 1024
export const LOCAL_FIXTURE_CATALOG = Object.freeze({
  'test-sine': Object.freeze({ id: 'test-sine', label: 'TEST sine tone (not a voice)', encodedBytes: 4044, durationSeconds: 0.25, sampleRate: 8000, channels: 1,
    sha256: '86e58017da62fc2106b3a5b124b5b0d25df8f6c2d0b11ccb84e41f259a40452f' }),
  'test-chime': Object.freeze({ id: 'test-chime', label: 'TEST chime tone (not a voice)', encodedBytes: 4044, durationSeconds: 0.25, sampleRate: 8000, channels: 1,
    sha256: 'b62fb755ce673fd2185069881d78f0158ce8a29bda9b257664bfe82c076d9637' }),
})

export interface LocalFixtureStorage {
  read(id: TestClipId): Promise<Uint8Array<ArrayBuffer>>
}

/** Synthetic, in-memory local pack. No voice selection, network, or persistence. */
export class FixturePackStorage implements LocalFixtureStorage {
  async read(id: TestClipId): Promise<Uint8Array<ArrayBuffer>> { return createTestClipWav(id) }
}

export class LocalClipPreparer {
  private readonly cache = new Map<TestClipId, AudioBuffer>()
  private readonly inFlight = new Map<TestClipId, Promise<AudioBuffer>>()
  private bytes = 0
  private epoch = 0
  private outstanding = 0 // Includes obsolete tasks that Web Audio cannot abort.
  private readonly context: BaseAudioContext
  private readonly storage: LocalFixtureStorage
  private readonly cacheByteLimit: number

  constructor(
    context: BaseAudioContext,
    storage: LocalFixtureStorage = new FixturePackStorage(),
    cacheByteLimit = MAX_DECODED_CACHE_BYTES,
  ) {
    if (!Number.isInteger(cacheByteLimit) || cacheByteLimit < 0 || cacheByteLimit > MAX_DECODED_CACHE_BYTES) throw new Error('invalid_cache_limit')
    this.context = context; this.storage = storage; this.cacheByteLimit = cacheByteLimit
  }

  async prepare(id: TestClipId): Promise<AudioBuffer> {
    if (!Object.hasOwn(LOCAL_FIXTURE_CATALOG, id)) throw new Error('missing_clip')
    const cached = this.cache.get(id)
    if (cached) {
      this.cache.delete(id); this.cache.set(id, cached)
      return verifyLocalBuffer(this.context, cached)
    }
    let task = this.inFlight.get(id)
    if (!task) {
      if (this.outstanding >= 4) throw new Error('decode_busy')
      this.outstanding++
      task = this.decode(id, this.epoch).finally(() => { this.outstanding-- })
      this.inFlight.set(id, task)
    }
    const epoch = this.epoch
    try {
      // Canonical cached data never escapes, even to concurrent callers.
      const buffer = await task
      this.checkEpoch(epoch)
      return verifyLocalBuffer(this.context, buffer)
    } finally {
      if (this.inFlight.get(id) === task) this.inFlight.delete(id)
    }
  }

  clear(): void { this.epoch++; this.cache.clear(); this.inFlight.clear(); this.bytes = 0 }
  snapshot(): Readonly<{ entries: number; bytes: number; inFlight: number }> {
    return Object.freeze({ entries: this.cache.size, bytes: this.bytes, inFlight: this.outstanding })
  }

  private checkEpoch(epoch: number): void {
    if (epoch !== this.epoch) throw new Error('decode_cancelled')
  }

  private async decode(id: TestClipId, epoch: number): Promise<AudioBuffer> {
    const metadata = LOCAL_FIXTURE_CATALOG[id]
    const supplied = await this.storage.read(id)
    this.checkEpoch(epoch)
    if (supplied.byteLength !== metadata.encodedBytes) throw new Error('invalid_encoded_size')
    const bytes = new Uint8Array(supplied) // Defend against mutation during digest/decode.
    if (!globalThis.crypto?.subtle) throw new Error('checksum_unavailable')
    const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes.buffer)
    this.checkEpoch(epoch)
    const checksum = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
    if (checksum !== metadata.sha256) throw new Error('checksum_mismatch')
    const decoded = await this.context.decodeAudioData(bytes.buffer.slice(0))
    this.checkEpoch(epoch)
    // Web Audio resamples to the decoding context's rate, not the WAV's rate.
    if (decoded.sampleRate !== this.context.sampleRate || decoded.numberOfChannels !== metadata.channels ||
        Math.abs(decoded.duration - metadata.durationSeconds) > 1 / decoded.sampleRate ||
        Math.abs(decoded.length - metadata.durationSeconds * decoded.sampleRate) > 1) throw new Error('decoded_metadata_mismatch')
    const normalized = verifyLocalBuffer(this.context, decoded)
    const size = localBufferBytes(normalized)
    if (epoch === this.epoch && size <= this.cacheByteLimit) {
      while (this.bytes + size > this.cacheByteLimit && this.cache.size) {
        const oldest = this.cache.keys().next().value!
        this.bytes -= localBufferBytes(this.cache.get(oldest)!)
        this.cache.delete(oldest)
      }
      this.cache.set(id, normalized); this.bytes += size
    }
    return normalized
  }
}