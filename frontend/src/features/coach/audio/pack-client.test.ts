import { webcrypto } from 'node:crypto'
import { describe, expect, it, vi } from 'vitest'
import { FakeContext } from './audio-test-fakes'
import { isVerifiedLocalBuffer } from './local-buffers'
import { CoachPackClient, clipUrl, manifestUrl, parsePackManifest, type PackDependencies } from './pack-client'

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
  async delete(url: string) { return this.store.delete(url) }
}

type Clip = { id: string; bytes: Uint8Array<ArrayBuffer>; required: boolean; approved: boolean }
async function fixture(overrides: Partial<PackDependencies> = {}) {
  const clips: Clip[] = [
    { id: 'count-1', bytes: wav(2400), required: true, approved: true },
    { id: 'set-start', bytes: wav(4000), required: true, approved: true },
    { id: 'count-31', bytes: wav(2400), required: false, approved: true },
    { id: 'pain-stop', bytes: wav(4000), required: true, approved: false },
  ]
  const manifest = { schemaVersion: 1, slot: 'female', packVersion: '0123456789abcdef', complete: true, extra: 'ignored', clips: {} as Record<string, unknown> }
  for (const clip of clips) {
    manifest.clips[clip.id] = { fingerprint: 'a'.repeat(64), sha256: await sha(clip.bytes), bytes: clip.bytes.byteLength,
      durationMs: (clip.bytes.byteLength - 44) / 2 / RATE * 1000, sampleRate: RATE, required: clip.required, approved: clip.approved }
  }
  const context = new FakeContext()
  const cache = new MemoryCache()
  const routes = new Map<string, () => Response>([[manifestUrl('female'), () => Response.json(manifest)]])
  for (const clip of clips) routes.set(clipUrl('female', manifest.packVersion, clip.id), () => new Response(clip.bytes.slice()))
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
  it('downloads, verifies, caches and pins approved clips of the selected voice only', async () => {
    const f = await fixture()
    const listener = vi.fn(); f.client.subscribe(listener)
    const snapshot = await f.client.prepare('female')
    expect(snapshot).toMatchObject({ slot: 'female', state: 'ready', packVersion: '0123456789abcdef', prepared: 3, required: 2, optional: 1, unapproved: 1 })
    expect(snapshot.encodedBytes).toBe(f.clips.slice(0, 3).reduce((sum, clip) => sum + clip.bytes.byteLength, 0))
    expect(listener).toHaveBeenCalled()
    expect(f.fetch.mock.calls.map(call => call[0])).not.toContain(clipUrl('female', '0123456789abcdef', 'pain-stop'))
    expect(f.fetch.mock.calls[0][1]).toMatchObject({ cache: 'no-store' })
    const clips = f.client.clipsFor('female')
    const buffer = clips.get('count-1')!
    expect(isVerifiedLocalBuffer(buffer)).toBe(true)
    expect(clips.get('count-1')).not.toBe(buffer) // Copies: callers never own canonical samples.
    expect(clips.get('pain-stop')).toBeNull()
    expect(clips.get('unknown')).toBeNull()
    expect(f.client.clipsFor('male').get('count-1')).toBeNull()
    expect(f.client.clipsFor(null).get('count-1')).toBeNull()
    expect(f.cache.store.size).toBe(4) // manifest + 3 clips
  })

  it('repeat preparation reuses verified cache without downloading clips', async () => {
    const f = await fixture()
    await f.client.prepare('female')
    f.fetch.mockClear()
    expect((await f.client.prepare('female')).state).toBe('ready')
    expect(f.fetch.mock.calls.map(call => call[0])).toEqual([manifestUrl('female')])
  })

  it('rejects checksum mismatch, never caches it and reports partial', async () => {
    const f = await fixture()
    const bad = f.clips[1].bytes.slice(); bad[60] ^= 1
    f.routes.set(clipUrl('female', '0123456789abcdef', 'set-start'), () => new Response(bad))
    const snapshot = await f.client.prepare('female')
    expect(snapshot).toMatchObject({ state: 'partial', reason: 'checksum', prepared: 2 })
    expect(f.cache.store.has(clipUrl('female', '0123456789abcdef', 'set-start'))).toBe(false)
    expect(f.client.clipsFor('female').get('set-start')).toBeNull()
  })

  it('replaces a corrupted cached clip and rejects wrong decoded duration', async () => {
    const f = await fixture()
    await f.client.prepare('female')
    const url = clipUrl('female', '0123456789abcdef', 'count-1')
    f.cache.store.set(url, new Uint8Array(10))
    f.context.decodeAudioData.mockImplementationOnce(async () => f.context.createBuffer(1, 10, RATE))
    const snapshot = await f.client.prepare('female')
    expect(snapshot).toMatchObject({ state: 'partial', reason: 'decode' })
    expect(f.cache.store.get(url)?.byteLength).toBe(f.clips[0].bytes.byteLength)
  })

  it('works offline from the cached manifest and clips; nothing cached means offline', async () => {
    const f = await fixture()
    await f.client.prepare('female')
    f.fetch.mockImplementation(async () => { throw new TypeError('offline') })
    expect(await f.client.prepare('female')).toMatchObject({ state: 'offline', prepared: 3 })
    expect(f.client.clipsFor('female').get('count-1')).not.toBeNull()
    await f.client.deleteLocal()
    expect(f.deleteCache).toHaveBeenCalled()
    expect(f.client.clipsFor('female').get('count-1')).toBeNull()
    expect(await f.client.prepare('female')).toMatchObject({ state: 'offline', reason: 'unavailable', prepared: 0 })
  })

  it('reports not prepared, invalid manifest, quota and missing audio context without generating', async () => {
    const f = await fixture()
    expect(await f.client.prepare('male')).toMatchObject({ state: 'not_prepared', reason: 'no_pack' })
    f.routes.set(manifestUrl('female'), () => Response.json({ ...f.manifest, clips: { '../x': Object.values(f.manifest.clips)[0] } }))
    expect(await f.client.prepare('female')).toMatchObject({ state: 'failed', reason: 'invalid_manifest' })
    f.routes.set(manifestUrl('female'), () => Response.json(f.manifest))
    f.cache.quota = true
    expect(await f.client.prepare('female')).toMatchObject({ state: 'failed', reason: 'quota' })
    const silent = await fixture({ context: () => null })
    expect(await silent.client.prepare('female')).toMatchObject({ state: 'failed', reason: 'no_audio' })
    expect(f.fetch.mock.calls.every(call => call[1].method === undefined)).toBe(true) // GET only.
  })

  it('selecting another voice clears decoded clips and cancels an in-flight prepare', async () => {
    const f = await fixture()
    await f.client.prepare('female')
    f.client.select('male')
    expect(f.client.snapshot()).toMatchObject({ slot: 'male', state: 'not_prepared' })
    expect(f.client.clipsFor('female').get('count-1')).toBeNull()
    const pending = f.client.prepare('female')
    f.client.select(null)
    await pending
    expect(f.client.snapshot()).toMatchObject({ slot: null, state: 'not_prepared' })
    expect(f.client.clipsFor('female').get('count-1')).toBeNull()
  })

  it('caps decoded memory, keeping required clips over optional ones', async () => {
    const f = await fixture({ decodedLimit: (2400 + 4000) * 4 })
    expect(await f.client.prepare('female')).toMatchObject({ state: 'ready', prepared: 2, decodedBytes: 6400 * 4 })
    expect(f.client.clipsFor('female').get('count-31')).toBeNull()
  })

  it('validates manifests strictly', () => {
    expect(() => parsePackManifest({ schemaVersion: 1, slot: 'male', packVersion: '0123456789abcdef', complete: true, clips: {} }, 'female')).toThrow('invalid_manifest')
    expect(() => parsePackManifest({ schemaVersion: 1, slot: 'female', packVersion: 'zz', complete: true, clips: {} }, 'female')).toThrow('invalid_manifest')
    expect(() => parsePackManifest({ schemaVersion: 1, slot: 'female', packVersion: '0123456789abcdef', complete: false, clips: {} }, 'female')).toThrow('invalid_manifest')
  })
})
