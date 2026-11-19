import { COACH_VOICES, type CoachVoice } from '../model/contracts'
import type { CoachPreferences } from '../model/preferences'
import { verifyLocalBuffer, localBufferBytes } from './local-buffers'
import { MAX_DECODED_CACHE_BYTES } from './fixture-pack-storage'
import { getSharedAudioContext } from './shared-audio-context'
import { reviewedTipMetadata } from '../interpreter/reviewed-machine-tips'
import { workoutTipMetadata } from '../interpreter/workout-guidance'

/** E09 prepared voice pack: verified download → CacheStorage → decode → pinned in-memory clips.
 * Never generates audio, never substitutes another voice, never fetches during a cue. */
/** Legacy OpenAI Realtime slots plus model-qualified TTS and Fish character/library slots. */
export type PackSlot = 'ru-base' | CoachVoice | `tts-${CoachVoice}` | `fish-${string}`
export const PACK_SLOTS: readonly PackSlot[] = COACH_VOICES
export function isPackSlot(value: unknown): value is PackSlot {
  return typeof value === 'string' && (value === 'ru-base' || COACH_VOICES.includes(value as CoachVoice) ||
    (value.startsWith('tts-') && COACH_VOICES.includes(value.slice(4) as CoachVoice)) ||
    /^fish-(?:[a-f0-9]{32}|streamer|classic)$/.test(value))
}
/** Model and effective character voice, shared by preparation and workout playback. */
export function coachPackSlot(prefs: CoachPreferences | null): PackSlot | null {
  if (!prefs) return null
  if (prefs.standardPack) return 'ru-base'
  if (prefs.voiceModel === 'fish-drama-3') {
    const slot = `fish-${prefs.fishVoiceId || prefs.persona}`
    return isPackSlot(slot) ? slot : null
  }
  return prefs.voiceModel === 'openai-tts' ? `tts-${prefs.voiceProfile}` : prefs.voiceProfile
}
export type PackState = 'not_prepared' | 'downloading' | 'decoding' | 'ready' | 'partial' | 'failed' | 'offline'
export type PackReason = 'no_pack' | 'unavailable' | 'invalid_manifest' | 'checksum' | 'decode' | 'quota' | 'no_storage' | 'no_audio' | 'cancelled' | null
export type PackSnapshot = Readonly<{
  slot: PackSlot | null; state: PackState; reason: PackReason; packVersion: string | null
  prepared: number; required: number; optional: number; unapproved: number; encodedBytes: number; decodedBytes: number
}>
export type PackClipEntry = Readonly<{
  fingerprint: string; sha256: string; bytes: number; durationMs: number; sampleRate: number; required: boolean; approved: boolean
  text: string; group: string
  tip?: NonNullable<ReturnType<typeof reviewedTipMetadata | typeof workoutTipMetadata>>
}>
export type PackManifest = Readonly<{ slot: PackSlot; packVersion: string; complete: true; missingClips: number; clips: Readonly<Record<string, PackClipEntry>> }>
export type ClipLookup = Readonly<{ get: (clipId: string) => AudioBuffer | null; has: (clipId: string) => boolean }>

export const PACK_CACHE_NAME = 'coach-pack-v1'
const HEX64 = /^[a-f0-9]{64}$/
const VERSION = /^[a-f0-9]{16}$/
const CLIP_ID = /^[a-z0-9-]{1,40}$/
const MAX_CLIPS = 256
const MAX_CLIP_BYTES = 2_880_000
const DURATION_TOLERANCE_S = 0.02

export type PackDependencies = Readonly<{
  fetch: (url: string, init: RequestInit) => Promise<Response>
  openCache: () => Promise<Cache | null>
  deleteCache: () => Promise<void>
  context: () => BaseAudioContext | null
  digest: (bytes: ArrayBuffer) => Promise<ArrayBuffer>
  decodedLimit: number
}>

let decoder: BaseAudioContext | null = null
const defaults: PackDependencies = {
  fetch: (url, init) => globalThis.fetch(url, init),
  openCache: async () => typeof caches === 'undefined' ? null : caches.open(PACK_CACHE_NAME),
  deleteCache: async () => { if (typeof caches !== 'undefined') await caches.delete(PACK_CACHE_NAME) },
  // The output device can run at 96 kHz. Decode mono speech at a fixed rate rather than exhausting the pack budget.
  context: () => decoder ??= typeof OfflineAudioContext === 'function' ? new OfflineAudioContext(1, 1, 24000) : getSharedAudioContext(),
  digest: bytes => globalThis.crypto.subtle.digest('SHA-256', bytes),
  decodedLimit: MAX_DECODED_CACHE_BYTES,
}

export function manifestUrl(slot: PackSlot): string { return `/api/coach/packs/${slot}/manifest` }
export function clipUrl(slot: PackSlot, version: string, clipId: string): string { return `/api/coach/packs/${slot}/${version}/clips/${clipId}` }
// Private CacheStorage key, never fetched. An unchanged recording survives a pack version bump.
export function cachedClipUrl(slot: PackSlot, sha256: string): string { return `/__egym_voice/${slot}/${sha256}` }

export function parsePackManifest(value: unknown, slot: PackSlot): PackManifest {
  const fail = () => { throw new Error('invalid_manifest') }
  if (!value || typeof value !== 'object' || Array.isArray(value)) fail()
  const m = value as Record<string, unknown>
  if (m.schemaVersion !== 1 || m.slot !== slot || typeof m.packVersion !== 'string' || !VERSION.test(m.packVersion) || m.complete !== true ||
      !m.clips || typeof m.clips !== 'object' || Array.isArray(m.clips)) fail()
  const entries = Object.entries(m.clips as Record<string, unknown>)
  if (entries.length < 1 || entries.length > MAX_CLIPS) fail()
  const clips: Record<string, PackClipEntry> = {}
  for (const [id, raw] of entries) {
    const c = (raw ?? {}) as Record<string, unknown>
    if (!CLIP_ID.test(id) || typeof c.fingerprint !== 'string' || !HEX64.test(c.fingerprint) || typeof c.sha256 !== 'string' || !HEX64.test(c.sha256) ||
        !Number.isInteger(c.bytes) || (c.bytes as number) < 44 || (c.bytes as number) > MAX_CLIP_BYTES ||
        typeof c.durationMs !== 'number' || !Number.isFinite(c.durationMs) || c.durationMs <= 0 ||
        !Number.isInteger(c.sampleRate) || (c.sampleRate as number) < 8000 || (c.sampleRate as number) > 48000 ||
        typeof c.required !== 'boolean' || typeof c.approved !== 'boolean') fail()
    // Pick known fields only.
    const tip = reviewedTipMetadata(id, c.tip) ?? workoutTipMetadata(id, c.tip)
    clips[id] = Object.freeze({ fingerprint: c.fingerprint as string, sha256: c.sha256 as string, bytes: c.bytes as number,
      text: typeof c.text === 'string' && c.text.length <= 500 ? c.text : id,
      group: typeof c.group === 'string' && /^[a-z-]{1,24}$/.test(c.group) ? c.group : 'other',
      durationMs: c.durationMs as number, sampleRate: c.sampleRate as number, required: c.required as boolean, approved: c.approved as boolean,
      ...(tip ? { tip } : {}) })
  }
  return Object.freeze({ slot, packVersion: m.packVersion as string, complete: true, clips: Object.freeze(clips),
    missingClips: Number.isSafeInteger(m.missingClips) && Number(m.missingClips) > 0 ? Number(m.missingClips) : 0 })
}

function hex(buffer: ArrayBuffer): string { return Array.from(new Uint8Array(buffer), byte => byte.toString(16).padStart(2, '0')).join('') }
function isQuota(error: unknown): boolean { return error instanceof DOMException && error.name === 'QuotaExceededError' }

type Pinned = Readonly<{ slot: PackSlot; manifest: PackManifest; clips: ReadonlyMap<string, AudioBuffer>; snapshot: PackSnapshot }>

export class CoachPackClient {
  private readonly deps: PackDependencies
  private readonly listeners = new Set<() => void>()
  private epoch = 0
  private pinned: Pinned | null = null
  private context: BaseAudioContext | null = null
  private value: PackSnapshot = CoachPackClient.empty(null)

  constructor(dependencies: Partial<PackDependencies> = {}) {
    this.deps = { ...defaults, ...dependencies }
    if (!Number.isInteger(this.deps.decodedLimit) || this.deps.decodedLimit < 0 || this.deps.decodedLimit > MAX_DECODED_CACHE_BYTES) throw new Error('invalid_cache_limit')
  }

  private static empty(slot: PackSlot | null, state: PackState = 'not_prepared', reason: PackReason = null): PackSnapshot {
    return Object.freeze({ slot, state, reason, packVersion: null, prepared: 0, required: 0, optional: 0, unapproved: 0, encodedBytes: 0, decodedBytes: 0 })
  }

  readonly snapshot = (): PackSnapshot => this.value
  readonly subscribe = (listener: () => void): (() => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  private publish(value: PackSnapshot): void { this.value = Object.freeze(value); this.listeners.forEach(listener => listener()) }

  installed(slot: string | null): PackManifest | null { return this.pinned?.slot === slot ? this.pinned.manifest : null }

  /** Audition includes unpublished-for-playback safety takes, strictly from verified local bytes. */
  async audition(slot: PackSlot, id: string, signal: AbortSignal): Promise<AudioBuffer | null> {
    const pinned = this.pinned, context = this.context
    if (signal.aborted || !context || !pinned || pinned.slot !== slot || !Object.hasOwn(pinned.manifest.clips, id)) return null
    const playable = this.clipsFor(slot).get(id)
    if (playable) return playable
    const entry = pinned.manifest.clips[id], cache = await this.deps.openCache()
    const hit = await cache?.match(cachedClipUrl(slot, entry.sha256)) ?? await cache?.match(clipUrl(slot, pinned.manifest.packVersion, id))
    if (!hit || signal.aborted) return null
    const data = await hit.arrayBuffer()
    if (data.byteLength !== entry.bytes || hex(await this.deps.digest(data)) !== entry.sha256) return null
    const buffer = await context.decodeAudioData(data)
    return this.pinned === pinned && !signal.aborted && buffer.numberOfChannels === 1 &&
      Math.abs(buffer.duration - entry.durationMs / 1000) <= DURATION_TOLERANCE_S ? verifyLocalBuffer(context, buffer) : null
  }

  /** Clips only from the pinned pack of `slot`; another slot gets nothing (no voice substitution). */
  clipsFor(slot: string | null | undefined): ClipLookup {
    const pinned = this.pinned, context = this.context
    if (!pinned || !context || pinned.slot !== slot) return NO_PACK_CLIPS
    return Object.freeze({ has: (id: string) => this.pinned === pinned && pinned.clips.has(id), get: (clipId: string) => {
      const buffer = this.pinned === pinned ? pinned.clips.get(clipId) : undefined
      return buffer ? verifyLocalBuffer(context, buffer) : null
    } })
  }

  /** Switching voice clears decoded clips immediately; the next prepare loads the other pack. */
  select(slot: PackSlot | null): void {
    if (this.value.slot === slot) return
    this.epoch++
    this.pinned = null
    this.publish(CoachPackClient.empty(slot))
  }

  async deleteLocal(slot?: PackSlot): Promise<void> {
    const epoch = ++this.epoch
    if (slot) {
      const cache = await this.deps.openCache()
      for (const request of await cache?.keys() ?? []) {
        const path = new URL(request.url).pathname
        if (path.startsWith(`/__egym_voice/${slot}/`) || path.startsWith(`/api/coach/packs/${slot}/`)) await cache!.delete(request)
      }
    } else await this.deps.deleteCache()
    if (epoch !== this.epoch) return
    if (!slot || this.pinned?.slot === slot) this.pinned = null
    this.publish(CoachPackClient.empty(slot ?? this.value.slot))
  }

  /** Re-pin an installed pack before a workout. Never repair cache misses over the network. */
  async restore(slot: PackSlot, { signal }: { signal?: AbortSignal } = {}): Promise<PackSnapshot> {
    if (signal?.aborted || !isPackSlot(slot) || this.pinned?.slot === slot ||
      (this.value.slot === slot && ['downloading', 'decoding'].includes(this.value.state))) return this.value
    const epoch = this.epoch
    let cache: Cache | null = null
    try { cache = await this.deps.openCache() } catch { cache = null }
    const hit = await cache?.match(manifestUrl(slot)).catch(() => undefined)
    // A manual prepare/select/delete meanwhile wins.
    if (!hit || !cache || epoch !== this.epoch || signal?.aborted) return this.value
    let manifest: PackManifest
    try { manifest = parsePackManifest(await hit.json(), slot) } catch { return this.value }
    if (epoch !== this.epoch || signal?.aborted) return this.value
    const context = this.deps.context()
    if (!context) return this.value
    const token = ++this.epoch
    return this.pin(manifest, context, cache, () => token === this.epoch && !signal?.aborted, 'cache')
  }

  async prepare(slot: PackSlot, signal?: AbortSignal): Promise<PackSnapshot> {
    if (!isPackSlot(slot)) throw new Error('invalid_slot')
    if (signal?.aborted) return this.value
    const epoch = ++this.epoch
    const live = () => epoch === this.epoch && !signal?.aborted
    const base = CoachPackClient.empty(slot)
    const onAbort = () => { if (epoch === this.epoch) this.publish(this.pinned?.slot === slot ? this.pinned.snapshot : base) }
    signal?.addEventListener('abort', onAbort, { once: true })
    try { return await this.download(slot, base, live, signal) }
    finally { signal?.removeEventListener('abort', onAbort) }
  }

  private async download(slot: PackSlot, base: PackSnapshot, live: () => boolean, signal?: AbortSignal): Promise<PackSnapshot> {
    this.publish({ ...base, state: 'downloading' })
    const context = this.deps.context()
    if (!context) { this.publish(CoachPackClient.empty(slot, 'failed', 'no_audio')); return this.value }
    let cache: Cache | null = null
    try { cache = await this.deps.openCache() } catch { cache = null }
    if (!live()) return this.value
    if (!cache) { this.publish({ ...base, state: 'failed', reason: 'no_storage' }); return this.value }
    let offline = false
    let manifest: PackManifest
    try {
      const response = await this.deps.fetch(manifestUrl(slot), { credentials: 'include', cache: 'no-store', signal, headers: { Accept: 'application/json' } })
      if (response.status === 404) { if (live()) this.publish(CoachPackClient.empty(slot, 'not_prepared', 'no_pack')); return this.value }
      if (!response.ok) throw new Error('unavailable')
      manifest = parsePackManifest(await response.json(), slot)
    } catch (error) {
      if (!live()) return this.value
      if (error instanceof Error && error.message === 'invalid_manifest') { if (live()) this.publish(CoachPackClient.empty(slot, 'failed', 'invalid_manifest')); return this.value }
      // Offline: fall back to the last cached manifest; its clips must also be cached.
      const cached = await cache?.match(manifestUrl(slot)).catch(() => undefined)
      try { manifest = parsePackManifest(cached ? await cached.json() : null, slot) } catch {
        if (live()) this.publish(CoachPackClient.empty(slot, 'offline', 'unavailable')); return this.value
      }
      offline = true
    }
    return this.pin(manifest, context, cache, live, offline ? 'offline' : 'download', signal)
  }

  private async pin(manifest: PackManifest, context: BaseAudioContext, cache: Cache | null, live: () => boolean,
    source: 'cache' | 'offline' | 'download', signal?: AbortSignal): Promise<PackSnapshot> {
    const slot = manifest.slot
    if (!live()) return this.value
    let previous = this.installed(slot)
    if (source === 'download' && !previous) {
      try {
        const prior = await cache?.match(manifestUrl(slot))
        if (prior) previous = parsePackManifest(await prior.json(), slot)
      } catch { /* No usable earlier installation. */ }
    }
    const ids = Object.keys(manifest.clips)
      .sort((a, b) => Number(manifest.clips[b].required) - Number(manifest.clips[a].required))
    const allowed = ids.filter(id => manifest.clips[id].approved && (!id.startsWith('tip-') || manifest.clips[id].tip))
    const required = allowed.filter(id => manifest.clips[id].required).length
    const unapproved = ids.filter(id => !manifest.clips[id].approved).length
    const clips = new Map<string, AudioBuffer>()
    let encodedBytes = 0, decodedBytes = 0, reason: PackReason = null
    const progress = (state: PackState) => ({ slot, state, reason, packVersion: manifest.packVersion, prepared: clips.size,
      required, optional: allowed.length - required, unapproved, encodedBytes, decodedBytes })
    for (const id of ids) {
      if (!live()) return this.value
      const entry = manifest.clips[id]
      const url = clipUrl(slot, manifest.packVersion, id)
      const key = cachedClipUrl(slot, entry.sha256)
      let bytes: ArrayBuffer | null = null
      try {
        // Pre-upgrade browsers stored WAVs by versioned URL. Promote verified hits only on an explicit download.
        const oldUrl = previous && previous.clips[id]?.sha256 === entry.sha256 ? clipUrl(slot, previous.packVersion, id) : url
        const byHash = await cache?.match(key)
        const hit = byHash ?? await cache?.match(oldUrl)
        if (hit) {
          const data = await hit.arrayBuffer()
          if (data.byteLength === entry.bytes && hex(await this.deps.digest(data)) === entry.sha256) {
            bytes = data
            if (!byHash && source === 'download' && live()) await cache?.put(key, new Response(data.slice(0), { headers: { 'Content-Type': 'audio/wav' } }))
          } else await cache?.delete(byHash ? key : oldUrl)
        }
        if (!bytes && source === 'download') {
          this.publish(progress('downloading'))
          if (!live()) return this.value
          const response = await this.deps.fetch(url, { credentials: 'include', signal, headers: { Accept: 'audio/wav' } })
          if (!response.ok) throw new Error('unavailable')
          const data = await response.arrayBuffer()
          if (data.byteLength !== entry.bytes || hex(await this.deps.digest(data)) !== entry.sha256) throw new Error('checksum')
          bytes = data
          if (!live()) return this.value
          await cache?.put(key, new Response(data.slice(0), { headers: { 'Content-Type': 'audio/wav' } }))
        }
      } catch (error) {
        reason = isQuota(error) ? 'quota' : error instanceof Error && error.message === 'checksum' ? 'checksum' : 'unavailable'
        if (reason === 'quota') break
        continue
      }
      if (!live()) return this.value
      if (!bytes) { if (entry.approved) reason ??= 'unavailable'; continue }
      encodedBytes += entry.bytes
      if (!allowed.includes(id)) continue // Review copies can be auditioned, never played during a workout.
      // A cancelled preflight must not leave the settings snapshot stuck on decoding.
      if (source !== 'cache') this.publish(progress('decoding'))
      try {
        const decoded = await context.decodeAudioData(bytes.slice(0))
        if (!live()) return this.value
        if (decoded.numberOfChannels !== 1 || Math.abs(decoded.duration - entry.durationMs / 1000) > DURATION_TOLERANCE_S) throw new Error('decode')
        const normalized = verifyLocalBuffer(context, decoded)
        const size = localBufferBytes(normalized)
        // Never mark a partial installation ready or evict a previously installed working pack.
        if (decodedBytes + size > this.deps.decodedLimit) { reason = 'quota'; break }
        clips.set(id, normalized); decodedBytes += size
      } catch { reason = 'decode' }
    }
    if (!live()) return this.value
    // Commit the durable pointer LAST. A failed/cancelled update cannot displace a working pack,
    // including after a reload. Verified files already staged are reusable on retry.
    if (reason || allowed.some(id => manifest.clips[id].required && !clips.has(id))) {
      this.publish(progress(clips.size && reason !== 'quota' ? 'partial' : 'failed')); return this.value
    }
    if (source === 'download') {
      try { await cache!.put(manifestUrl(slot), new Response(JSON.stringify({ schemaVersion: 1, ...manifest }), { headers: { 'Content-Type': 'application/json' } })) }
      catch (error) { if (live()) this.publish({ ...progress('failed'), reason: isQuota(error) ? 'quota' : 'unavailable' }); return this.value }
    }
    if (!live()) return this.value
    this.context = context
    const ready = progress(source === 'offline' ? 'offline' : 'ready')
    this.pinned = { slot, manifest, clips, snapshot: ready }
    this.publish(ready)
    return this.value
  }
}

export const NO_PACK_CLIPS: ClipLookup = Object.freeze({ get: () => null, has: () => false })
export const coachPackClient = new CoachPackClient()
