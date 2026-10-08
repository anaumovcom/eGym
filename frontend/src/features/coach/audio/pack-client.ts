import { COACH_VOICES, type CoachVoice } from '../model/contracts'
import { verifyLocalBuffer, localBufferBytes } from './local-buffers'
import { MAX_DECODED_CACHE_BYTES } from './fixture-pack-storage'
import { getSharedAudioContext } from './shared-audio-context'

/** E09 prepared voice pack: verified download → CacheStorage → decode → pinned in-memory clips.
 * Never generates audio, never substitutes another voice, never fetches during a cue. */
/** One pack per provider voice: the slot IS the voice ID (same timbre as live speech). */
export type PackSlot = CoachVoice
export const PACK_SLOTS: readonly PackSlot[] = COACH_VOICES
export type PackState = 'not_prepared' | 'downloading' | 'decoding' | 'ready' | 'partial' | 'failed' | 'offline'
export type PackReason = 'no_pack' | 'unavailable' | 'invalid_manifest' | 'checksum' | 'decode' | 'quota' | 'no_audio' | 'cancelled' | null
export type PackSnapshot = Readonly<{
  slot: PackSlot | null; state: PackState; reason: PackReason; packVersion: string | null
  prepared: number; required: number; optional: number; unapproved: number; encodedBytes: number; decodedBytes: number
}>
export type PackClipEntry = Readonly<{
  fingerprint: string; sha256: string; bytes: number; durationMs: number; sampleRate: number; required: boolean; approved: boolean
}>
export type PackManifest = Readonly<{ slot: PackSlot; packVersion: string; complete: true; clips: Readonly<Record<string, PackClipEntry>> }>
export type ClipLookup = Readonly<{ get: (clipId: string) => AudioBuffer | null }>

export const PACK_CACHE_NAME = 'coach-pack-v1'
const HEX64 = /^[a-f0-9]{64}$/
const VERSION = /^[a-f0-9]{16}$/
const CLIP_ID = /^[a-z0-9-]{1,40}$/
const MAX_CLIPS = 256
const MAX_CLIP_BYTES = 600_000
const DURATION_TOLERANCE_S = 0.02

export type PackDependencies = Readonly<{
  fetch: (url: string, init: RequestInit) => Promise<Response>
  openCache: () => Promise<Cache | null>
  deleteCache: () => Promise<void>
  context: () => BaseAudioContext | null
  digest: (bytes: ArrayBuffer) => Promise<ArrayBuffer>
  decodedLimit: number
}>

const defaults: PackDependencies = {
  fetch: (url, init) => globalThis.fetch(url, init),
  openCache: async () => typeof caches === 'undefined' ? null : caches.open(PACK_CACHE_NAME),
  deleteCache: async () => { if (typeof caches !== 'undefined') await caches.delete(PACK_CACHE_NAME) },
  context: getSharedAudioContext,
  digest: bytes => globalThis.crypto.subtle.digest('SHA-256', bytes),
  decodedLimit: MAX_DECODED_CACHE_BYTES,
}

export function manifestUrl(slot: PackSlot): string { return `/api/coach/packs/${slot}/manifest` }
export function clipUrl(slot: PackSlot, version: string, clipId: string): string { return `/api/coach/packs/${slot}/${version}/clips/${clipId}` }

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
        typeof c.durationMs !== 'number' || !(c.durationMs > 0 && c.durationMs <= 6000) ||
        !Number.isInteger(c.sampleRate) || (c.sampleRate as number) < 8000 || (c.sampleRate as number) > 48000 ||
        typeof c.required !== 'boolean' || typeof c.approved !== 'boolean') fail()
    // Pick known fields only.
    clips[id] = Object.freeze({ fingerprint: c.fingerprint as string, sha256: c.sha256 as string, bytes: c.bytes as number,
      durationMs: c.durationMs as number, sampleRate: c.sampleRate as number, required: c.required as boolean, approved: c.approved as boolean })
  }
  return Object.freeze({ slot, packVersion: m.packVersion as string, complete: true, clips: Object.freeze(clips) })
}

function hex(buffer: ArrayBuffer): string { return Array.from(new Uint8Array(buffer), byte => byte.toString(16).padStart(2, '0')).join('') }
function isQuota(error: unknown): boolean { return error instanceof DOMException && error.name === 'QuotaExceededError' }

type Pinned = Readonly<{ slot: PackSlot; version: string; clips: ReadonlyMap<string, AudioBuffer> }>

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

  /** Clips only from the pinned pack of `slot`; another slot gets nothing (no voice substitution). */
  clipsFor(slot: string | null | undefined): ClipLookup {
    const pinned = this.pinned, context = this.context
    if (!pinned || !context || pinned.slot !== slot) return NO_PACK_CLIPS
    return Object.freeze({ get: (clipId: string) => {
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

  async deleteLocal(): Promise<void> {
    this.epoch++
    this.pinned = null
    const slot = this.value.slot
    await this.deps.deleteCache()
    this.publish(CoachPackClient.empty(slot))
  }

  async prepare(slot: PackSlot): Promise<PackSnapshot> {
    if (!PACK_SLOTS.includes(slot)) throw new Error('invalid_slot')
    const epoch = ++this.epoch
    const live = () => epoch === this.epoch
    const base = CoachPackClient.empty(slot)
    this.publish({ ...base, state: 'downloading' })
    const context = this.deps.context()
    if (!context) { this.publish(CoachPackClient.empty(slot, 'failed', 'no_audio')); return this.value }
    let cache: Cache | null = null
    try { cache = await this.deps.openCache() } catch { cache = null }
    let offline = false
    let manifest: PackManifest
    try {
      const response = await this.deps.fetch(manifestUrl(slot), { credentials: 'include', cache: 'no-store', headers: { Accept: 'application/json' } })
      if (response.status === 404) { if (live()) this.publish(CoachPackClient.empty(slot, 'not_prepared', 'no_pack')); return this.value }
      if (!response.ok) throw new Error('unavailable')
      manifest = parsePackManifest(await response.json(), slot)
      await cache?.put(manifestUrl(slot), new Response(JSON.stringify({ schemaVersion: 1, ...manifest }), { headers: { 'Content-Type': 'application/json' } }))
    } catch (error) {
      if (isQuota(error)) { if (live()) this.publish(CoachPackClient.empty(slot, 'failed', 'quota')); return this.value }
      if (error instanceof Error && error.message === 'invalid_manifest') { if (live()) this.publish(CoachPackClient.empty(slot, 'failed', 'invalid_manifest')); return this.value }
      // Offline: fall back to the last cached manifest; its clips must also be cached.
      const cached = await cache?.match(manifestUrl(slot)).catch(() => undefined)
      try { manifest = parsePackManifest(cached ? await cached.json() : null, slot) } catch {
        if (live()) this.publish(CoachPackClient.empty(slot, 'offline', 'unavailable')); return this.value
      }
      offline = true
    }
    if (!live()) return this.value
    const ids = Object.keys(manifest.clips).filter(id => manifest.clips[id].approved)
      .sort((a, b) => Number(manifest.clips[b].required) - Number(manifest.clips[a].required))
    const required = ids.filter(id => manifest.clips[id].required).length
    const unapproved = Object.keys(manifest.clips).length - ids.length
    const clips = new Map<string, AudioBuffer>()
    let encodedBytes = 0, decodedBytes = 0, reason: PackReason = null
    const progress = (state: PackState) => ({ slot, state, reason, packVersion: manifest.packVersion, prepared: clips.size,
      required, optional: ids.length - required, unapproved, encodedBytes, decodedBytes })
    for (const id of ids) {
      if (!live()) return this.value
      const entry = manifest.clips[id]
      const url = clipUrl(slot, manifest.packVersion, id)
      let bytes: ArrayBuffer | null = null
      try {
        const hit = await cache?.match(url)
        if (hit) {
          const data = await hit.arrayBuffer()
          if (data.byteLength === entry.bytes && hex(await this.deps.digest(data)) === entry.sha256) bytes = data
          else await cache?.delete(url)
        }
        if (!bytes && !offline) {
          this.publish(progress('downloading'))
          const response = await this.deps.fetch(url, { credentials: 'include', headers: { Accept: 'audio/wav' } })
          if (!response.ok) throw new Error('unavailable')
          const data = await response.arrayBuffer()
          if (data.byteLength !== entry.bytes || hex(await this.deps.digest(data)) !== entry.sha256) throw new Error('checksum')
          bytes = data
          await cache?.put(url, new Response(data.slice(0), { headers: { 'Content-Type': 'audio/wav' } }))
        }
      } catch (error) {
        reason = isQuota(error) ? 'quota' : error instanceof Error && error.message === 'checksum' ? 'checksum' : 'unavailable'
        if (reason === 'quota') break
        continue
      }
      if (!bytes || !live()) continue
      this.publish(progress('decoding'))
      try {
        const decoded = await context.decodeAudioData(bytes.slice(0))
        if (!live()) return this.value
        if (decoded.numberOfChannels !== 1 || Math.abs(decoded.duration - entry.durationMs / 1000) > DURATION_TOLERANCE_S) throw new Error('decode')
        const normalized = verifyLocalBuffer(context, decoded)
        const size = localBufferBytes(normalized)
        // Required clips first; optional ones only while they fit (never evict a required clip).
        if (decodedBytes + size > this.deps.decodedLimit) { if (entry.required) reason = 'quota'; continue }
        clips.set(id, normalized); decodedBytes += size; encodedBytes += entry.bytes
      } catch { reason = 'decode' }
    }
    if (!live()) return this.value
    // Atomic swap: cues never see a mix of two pack versions.
    this.context = context
    this.pinned = { slot, version: manifest.packVersion, clips }
    const requiredReady = ids.filter(id => manifest.clips[id].required && clips.has(id)).length
    const state: PackState = reason === 'quota' ? 'failed' : requiredReady === required ? (offline ? 'offline' : 'ready') : clips.size ? 'partial' : offline ? 'offline' : 'failed'
    this.publish(progress(state))
    return this.value
  }
}

export const NO_PACK_CLIPS: ClipLookup = Object.freeze({ get: () => null })
export const coachPackClient = new CoachPackClient()
