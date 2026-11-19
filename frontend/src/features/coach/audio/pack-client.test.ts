import { webcrypto } from 'node:crypto'
import { describe, expect, it, vi } from 'vitest'
import { FakeClock, FakeContext } from './audio-test-fakes'
import { LocalCoachAudioManager } from './local-coach-audio-manager'
import { playCue } from '../live/local-cue-player'
import type { CoachScope } from '../model/contracts'
import { isVerifiedLocalBuffer } from './local-buffers'
import { DEFAULT_COACH_PREFERENCES } from '../model/preferences'
import { cachedClipUrl, CoachPackClient, coachPackSlot, isPackSlot, clipUrl, manifestUrl, parsePackManifest, type PackDependencies } from './pack-client'

it('keys prepared phrases by model and character voice without OpenAI substitution', () => {
  expect(coachPackSlot(DEFAULT_COACH_PREFERENCES)).toBe('ru-base')
  const prefs = { ...DEFAULT_COACH_PREFERENCES, standardPack: false }
  expect(coachPackSlot(null)).toBeNull()
  expect(coachPackSlot(prefs)).toBe('fish-streamer')
  expect(coachPackSlot({ ...prefs, persona: 'classic' })).toBe('fish-classic')
  expect(coachPackSlot({ ...prefs, fishVoiceId: 'a'.repeat(32) })).toBe(`fish-${'a'.repeat(32)}`)
  expect(coachPackSlot({ ...prefs, fishVoiceId: 'invalid' })).toBeNull()
  expect(coachPackSlot({ ...prefs, voiceModel: 'openai-realtime' })).toBe('ash')
  expect(coachPackSlot({ ...prefs, voiceModel: 'openai-tts' })).toBe('tts-ash')
  for (const slot of ['tts-ash', 'fish-streamer', 'fish-classic', `fish-${'a'.repeat(32)}`]) expect(isPackSlot(slot)).toBe(true)
  for (const slot of ['tts-invalid', 'fish-../x', '../ash', 'fish-unknown']) expect(isPackSlot(slot)).toBe(false)
})

const RATE = 8000
function wav(samples: number, amplitude = 0.2): Uint8Array<ArrayBuffer> {
  const out = new Uint8Array(44 + samples * 2), view = new DataView(out.buffer)
  const text = (offset: number, value: string) => [...value].forEach((char, i) => { out[offset + i] = char.charCodeAt(0) })
  text(0, 'RIFF'); view.setUint32(4, 36 + samples * 2, true); text(8, 'WAVE'); text(12, 'fmt ')
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true); view.setUint32(24, RATE, true)
  view.setUint32(28, RATE * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true); text(36, 'data'); view.setUint32(40, samples * 2, true)
  for (let i = 0; i < samples; i++) view.setInt16(44 + i * 2, Math.round(32767 * amplitude * Math.sin(i / 3)), true)
  return out
}
async function sha(bytes: Uint8Array): Promise<string> { return Buffer.from(await webcrypto.subtle.digest('SHA-256', Buffer.from(bytes))).toString('hex') }

class MemoryCache {
  readonly store = new Map<string, Uint8Array>()
  quota = false
  async match(url: string) { const bytes = this.store.get(url); return bytes ? new Response(bytes.slice()) : undefined }
  async put(url: string, response: Response) {
    if (this.quota) throw new DOMException('full', 'QuotaExceededError')
    this.store.set(url, new Uint8Array(await response.arrayBuffer()))
  }
  async delete(url: string | Request) { return this.store.delete(typeof url === 'string' ? url : new URL(url.url).pathname) }
  async keys() { return [...this.store.keys()].map(path => new Request(`http://localhost${path}`)) }
}

type Clip = { id: string; bytes: Uint8Array<ArrayBuffer>; required: boolean; approved: boolean }
async function fixture(overrides: Partial<PackDependencies> = {}) {
  const clips: Clip[] = [
    { id: 'count-1', bytes: wav(2400), required: true, approved: true },
    { id: 'set-start', bytes: wav(4000), required: true, approved: true },
    { id: 'count-31', bytes: wav(2400, 0.1), required: false, approved: true },
    { id: 'pain-stop', bytes: wav(4000, 0.1), required: true, approved: false },
  ]
  const manifest = { schemaVersion: 1, slot: 'ash', packVersion: '0123456789abcdef', complete: true, extra: 'ignored', clips: {} as Record<string, unknown> }
  for (const clip of clips) {
    manifest.clips[clip.id] = { fingerprint: 'a'.repeat(64), sha256: await sha(clip.bytes), bytes: clip.bytes.byteLength,
      durationMs: (clip.bytes.byteLength - 44) / 2 / RATE * 1000, sampleRate: RATE, required: clip.required, approved: clip.approved }
  }
  const context = new FakeContext()
  const cache = new MemoryCache()
  const routes = new Map<string, () => Response>([[manifestUrl('ash'), () => Response.json(manifest)]])
  for (const clip of clips) routes.set(clipUrl('ash', manifest.packVersion, clip.id), () => new Response(clip.bytes.slice()))
  const fetch = vi.fn(async (url: string, init: RequestInit) => {
    expect(init.credentials).toBe('include')
    const route = routes.get(url)
    return route ? route() : new Response(null, { status: 404 })
  })
  const deleteCache = vi.fn(async () => { cache.store.clear() })
  const client = new CoachPackClient({ fetch, openCache: async () => cache as unknown as Cache, deleteCache, context: () => context.asAudioContext(),
    digest: bytes => webcrypto.subtle.digest('SHA-256', Buffer.from(new Uint8Array(bytes))), ...overrides })
  return { client, fetch, cache, context, manifest, routes, clips, deleteCache }
}

describe('E09 prepared pack client', () => {
  it('downloads and decodes phrases longer than the former six-second limit', async () => {
    const f = await fixture()
    const bytes = wav(RATE * 7)
    f.manifest.clips['count-1'] = { fingerprint: 'a'.repeat(64), sha256: await sha(bytes), bytes: bytes.byteLength,
      durationMs: 7000, sampleRate: RATE, required: true, approved: true }
    f.routes.set(clipUrl('ash', f.manifest.packVersion, 'count-1'), () => new Response(bytes.slice()))
    expect((await f.client.prepare('ash')).state).toBe('ready')
    expect(f.client.clipsFor('ash').get('count-1')?.duration).toBe(7)
  })

  it('downloads, verifies, caches and pins approved clips of the selected voice only', async () => {
    const f = await fixture()
    const listener = vi.fn(); f.client.subscribe(listener)
    const snapshot = await f.client.prepare('ash')
    expect(snapshot).toMatchObject({ slot: 'ash', state: 'ready', packVersion: '0123456789abcdef', prepared: 3, required: 2, optional: 1, unapproved: 1 })
    expect(snapshot.encodedBytes).toBe(f.clips.reduce((sum, clip) => sum + clip.bytes.byteLength, 0))
    expect(listener).toHaveBeenCalled()
    expect(f.fetch.mock.calls.map(call => call[0])).toContain(clipUrl('ash', '0123456789abcdef', 'pain-stop'))
    expect(f.fetch.mock.calls[0][1]).toMatchObject({ cache: 'no-store' })
    const clips = f.client.clipsFor('ash')
    const buffer = clips.get('count-1')!
    expect(isVerifiedLocalBuffer(buffer)).toBe(true)
    expect(clips.get('count-1')).not.toBe(buffer) // Copies: callers never own canonical samples.
    expect(clips.get('pain-stop')).toBeNull()
    expect(clips.get('unknown')).toBeNull()
    expect(f.client.clipsFor('cedar').get('count-1')).toBeNull()
    expect(f.client.clipsFor(null).get('count-1')).toBeNull()
    f.fetch.mockClear()
    expect(await f.client.audition('ash', 'pain-stop', new AbortController().signal)).not.toBeNull()
    expect(f.fetch).not.toHaveBeenCalled()
    expect(f.cache.store.size).toBe(5) // manifest + 3 playable clips + 1 review copy
  })

  it('repeat preparation reuses verified cache without downloading clips', async () => {
    const f = await fixture()
    await f.client.prepare('ash')
    f.fetch.mockClear()
    expect((await f.client.prepare('ash')).state).toBe('ready')
    expect(f.fetch.mock.calls.map(call => call[0])).toEqual([manifestUrl('ash')])
  })

  it('restore after a reload re-pins a pack prepared earlier but never starts a first download', async () => {
    const f = await fixture()
    expect((await f.client.restore('ash')).state).toBe('not_prepared')
    expect(f.fetch).not.toHaveBeenCalled()
    await f.client.prepare('ash')
    // A reloaded page: new client, same CacheStorage.
    const reloaded = (await fixture({ openCache: async () => f.cache as unknown as Cache })).client
    expect((await reloaded.restore('ash')).state).toBe('ready')
    expect(reloaded.clipsFor('ash').get('count-1')).not.toBeNull()
    expect((await reloaded.restore('cedar')).slot).toBe('ash') // nothing cached for another voice
  })

  it('loads an explicitly installed pack for workout counting and starts the mixer without a download', async () => {
    const install = await fixture(); await install.client.prepare('ash')
    const f = await fixture({ openCache: async () => install.cache as unknown as Cache })
    expect(f.client.clipsFor('ash').get('count-1')).toBeNull()
    expect(await f.client.restore('ash')).toMatchObject({ state: 'ready', prepared: 3 })
    expect(f.fetch).not.toHaveBeenCalled()
    const clock = new FakeClock()
    const scope: CoachScope = { schemaVersion: 1, userId: 'u', runId: 'r', exerciseId: 'e', setOrdinal: 1, scopeEpoch: 1 }
    const manager = new LocalCoachAudioManager({ context: f.context.asAudioContext(), clock, scope })
    try {
      const result = playCue(manager, f.client.clipsFor('ash'), {
        id: 'count-1', key: 'count-1', kind: 'count', clipId: 'count-1', triggerId: 'T14', scope,
        priority: 'ordinary', atMs: 0, deadlineMs: 900, value: 1,
      }, 0, () => true)
      expect(result.admitted).toBe(true)
      clock.advance(100, f.context)
      expect(manager.snapshot().counters.started).toBe(1)
      expect(manager.snapshot().audible).toBe(1)
      f.fetch.mockClear()
      await f.client.restore('ash')
      expect(f.fetch).not.toHaveBeenCalled() // Already pinned; never fetch per repetition.
    } finally { manager.dispose() }
  })

  it('never generates or substitutes another voice when the selected published pack is missing', async () => {
    const f = await fixture()
    expect(await f.client.restore('cedar')).toMatchObject({ state: 'not_prepared' })
    expect(f.fetch).not.toHaveBeenCalled()
    expect(f.client.clipsFor('cedar').get('count-1')).toBeNull()
  })

  it('does not start an automatic download after a concurrent select/delete', async () => {
    let release!: (cache: Cache | null) => void
    const f = await fixture({ openCache: () => new Promise(resolve => { release = resolve }) })
    const pending = f.client.restore('ash')
    f.client.select('cedar')
    release(null)
    await pending
    expect(f.fetch).not.toHaveBeenCalled()
    expect(f.client.snapshot()).toMatchObject({ slot: 'cedar', state: 'not_prepared' })
  })

  it('rejects checksum mismatch, never caches it and reports partial', async () => {
    const f = await fixture()
    const bad = f.clips[1].bytes.slice(); bad[60] ^= 1
    f.routes.set(clipUrl('ash', '0123456789abcdef', 'set-start'), () => new Response(bad))
    const snapshot = await f.client.prepare('ash')
    expect(snapshot).toMatchObject({ state: 'partial', reason: 'checksum', prepared: 2 })
    expect(f.cache.store.has(clipUrl('ash', '0123456789abcdef', 'set-start'))).toBe(false)
    expect(f.client.clipsFor('ash').get('set-start')).toBeNull()
  })

  it('replaces a corrupted cached clip and rejects wrong decoded duration', async () => {
    const f = await fixture()
    await f.client.prepare('ash')
    const url = cachedClipUrl('ash', await sha(f.clips[0].bytes))
    f.cache.store.set(url, new Uint8Array(10))
    f.context.decodeAudioData.mockImplementationOnce(async () => f.context.createBuffer(1, 10, RATE))
    const snapshot = await f.client.prepare('ash')
    expect(snapshot).toMatchObject({ state: 'partial', reason: 'decode' })
    expect(f.cache.store.get(url)?.byteLength).toBe(f.clips[0].bytes.byteLength)
  })

  it('works offline from the cached manifest and clips; nothing cached means offline', async () => {
    const f = await fixture()
    await f.client.prepare('ash')
    f.fetch.mockImplementation(async () => { throw new TypeError('offline') })
    expect(await f.client.prepare('ash')).toMatchObject({ state: 'offline', prepared: 3 })
    expect(f.client.clipsFor('ash').get('count-1')).not.toBeNull()
    await f.client.deleteLocal()
    expect(f.deleteCache).toHaveBeenCalled()
    expect(f.client.clipsFor('ash').get('count-1')).toBeNull()
    expect(await f.client.prepare('ash')).toMatchObject({ state: 'offline', reason: 'unavailable', prepared: 0 })
  })

  it('reports not prepared, invalid manifest, quota and missing audio context without generating', async () => {
    const f = await fixture()
    expect(await f.client.prepare('cedar')).toMatchObject({ state: 'not_prepared', reason: 'no_pack' })
    f.routes.set(manifestUrl('ash'), () => Response.json({ ...f.manifest, clips: { '../x': Object.values(f.manifest.clips)[0] } }))
    expect(await f.client.prepare('ash')).toMatchObject({ state: 'failed', reason: 'invalid_manifest' })
    f.routes.set(manifestUrl('ash'), () => Response.json(f.manifest))
    f.cache.quota = true
    expect(await f.client.prepare('ash')).toMatchObject({ state: 'failed', reason: 'quota' })
    const silent = await fixture({ context: () => null })
    expect(await silent.client.prepare('ash')).toMatchObject({ state: 'failed', reason: 'no_audio' })
    expect(f.fetch.mock.calls.every(call => call[1].method === undefined)).toBe(true) // GET only.
  })

  it('selecting another voice clears decoded clips and cancels an in-flight prepare', async () => {
    const f = await fixture()
    await f.client.prepare('ash')
    f.client.select('cedar')
    expect(f.client.snapshot()).toMatchObject({ slot: 'cedar', state: 'not_prepared' })
    expect(f.client.clipsFor('ash').get('count-1')).toBeNull()
    const pending = f.client.prepare('ash')
    f.client.select(null)
    await pending
    expect(f.client.snapshot()).toMatchObject({ slot: null, state: 'not_prepared' })
    expect(f.client.clipsFor('ash').get('count-1')).toBeNull()
  })

  it('never claims a pack is installed if it exceeded the decoded budget or browser storage is unavailable', async () => {
    const f = await fixture({ decodedLimit: (2400 + 4000) * 4 })
    expect(await f.client.prepare('ash')).toMatchObject({ state: 'failed', reason: 'quota', prepared: 2 })
    expect(f.client.clipsFor('ash').get('count-31')).toBeNull()
    expect(f.cache.store.has(manifestUrl('ash'))).toBe(false)
    const noCache = await fixture({ openCache: async () => null })
    expect(await noCache.client.prepare('ash')).toMatchObject({ state: 'failed', reason: 'no_storage' })
    expect(noCache.fetch).not.toHaveBeenCalled()
  })

  it('updates just one recording; interrupted or corrupt updates preserve the old pack even after a reload', async () => {
    const f = await fixture(); await f.client.prepare('ash'); f.fetch.mockClear()
    const old = f.manifest.packVersion
    // One recording still uses the cache layout from releases before per-clip replacement.
    const legacy = f.clips[1], hashKey = cachedClipUrl('ash', await sha(legacy.bytes))
    f.cache.store.set(clipUrl('ash', old, legacy.id), legacy.bytes); f.cache.store.delete(hashKey)
    f.manifest.packVersion = '1234567890abcdef'
    const next = clipUrl('ash', f.manifest.packVersion, 'count-1'), bytes = wav(2400, 0.4)
    Object.assign(f.manifest.clips['count-1'] as object, { text: 'Раз.', group: 'count', sha256: await sha(bytes) })
    f.routes.set(next, () => new Response(f.clips[0].bytes.slice()))
    expect((await f.client.prepare('ash')).reason).toBe('checksum')
    expect(f.client.installed('ash')?.packVersion).toBe(old)
    const reloaded = await fixture({ openCache: async () => f.cache as unknown as Cache })
    expect((await reloaded.client.restore('ash')).packVersion).toBe(old)
    expect(reloaded.fetch).not.toHaveBeenCalled()
    const abort = new AbortController(); f.routes.set(next, () => { abort.abort(); return new Response(bytes.slice()) })
    await f.client.prepare('ash', abort.signal)
    expect(f.client.installed('ash')?.packVersion).toBe(old)
    f.routes.set(next, () => new Response(bytes.slice())); f.fetch.mockClear()
    expect((await f.client.prepare('ash')).packVersion).toBe(f.manifest.packVersion)
    expect(f.fetch.mock.calls.map(([url]) => url)).toEqual([manifestUrl('ash'), next])
    expect(f.client.installed('ash')?.clips['count-1']).toMatchObject({ text: 'Раз.', group: 'count' })
    f.cache.store.set(manifestUrl('cedar'), new Uint8Array(3))
    await f.client.deleteLocal('ash')
    expect([...f.cache.store.keys()]).toEqual([manifestUrl('cedar')])
  })

  it('validates manifests strictly', () => {
    expect(() => parsePackManifest({ schemaVersion: 1, slot: 'cedar', packVersion: '0123456789abcdef', complete: true, clips: {} }, 'ash')).toThrow('invalid_manifest')
    expect(() => parsePackManifest({ schemaVersion: 1, slot: 'ash', packVersion: 'zz', complete: true, clips: {} }, 'ash')).toThrow('invalid_manifest')
    expect(() => parsePackManifest({ schemaVersion: 1, slot: 'ash', packVersion: '0123456789abcdef', complete: false, clips: {} }, 'ash')).toThrow('invalid_manifest')
  })
})
