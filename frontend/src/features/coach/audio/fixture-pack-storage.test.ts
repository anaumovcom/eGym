import { webcrypto } from 'node:crypto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeContext } from './audio-test-fakes'
import { FixturePackStorage, LOCAL_FIXTURE_CATALOG, LocalClipPreparer, MAX_DECODED_CACHE_BYTES } from './fixture-pack-storage'
import { copyNormalizedLocalBuffer, isVerifiedLocalBuffer, verifyLocalBuffer } from './local-buffers'
import { createTestClipWav } from './test-clips'

// jsdom and Node have separate ArrayBuffer realms. Keep real SHA256, converting
// only at the test crypto boundary to Node's Buffer (never alter production).
const testCrypto = { subtle: { digest: (algorithm: string, data: ArrayBuffer) => webcrypto.subtle.digest(algorithm, Buffer.from(new Uint8Array(data))) } }
beforeEach(() => vi.stubGlobal('crypto', testCrypto))
afterEach(() => vi.unstubAllGlobals())

describe('whitelisted synthetic local pack', () => {
  it('verifies fixed encoded SHA256 and decodes bounded immutable TEST metadata, with no network', async () => {
    const fetch = vi.fn(() => { throw new Error('network forbidden') }); vi.stubGlobal('fetch', fetch)
    const context = new FakeContext()
    const preparer = new LocalClipPreparer(context.asAudioContext())
    for (const id of ['test-sine', 'test-chime'] as const) {
      const metadata = LOCAL_FIXTURE_CATALOG[id]
      expect(Object.isFrozen(metadata)).toBe(true)
      expect(metadata.label).toContain('TEST')
      const bytes = createTestClipWav(id)
      const digest = await crypto.subtle.digest('SHA-256', bytes.buffer)
      expect(Buffer.from(digest).toString('hex')).toBe(metadata.sha256)
      const buffer = await preparer.prepare(id)
      expect(buffer.duration).toBe(0.25); expect(buffer.sampleRate).toBe(8000)
      expect(isVerifiedLocalBuffer(buffer)).toBe(true)
    }
    expect(fetch).not.toHaveBeenCalled()
    expect(preparer.snapshot()).toMatchObject({ entries: 2, bytes: 16000, inFlight: 0 })
  })

  it('rejects nonwhitelisted IDs, size/checksum corruption before decoding', async () => {
    const context = new FakeContext()
    const storage = new FixturePackStorage()
    const read = vi.spyOn(storage, 'read')
    const preparer = new LocalClipPreparer(context.asAudioContext(), storage)
    // Runtime input need not obey the TS union.
    await expect(preparer.prepare('__proto__' as 'test-sine')).rejects.toThrow('missing_clip')
    expect(read).not.toHaveBeenCalled()
    read.mockResolvedValueOnce(new Uint8Array(1))
    await expect(preparer.prepare('test-sine')).rejects.toThrow('invalid_encoded_size')
    const corrupted = createTestClipWav('test-sine'); corrupted[100] ^= 1
    read.mockResolvedValueOnce(corrupted)
    await expect(preparer.prepare('test-sine')).rejects.toThrow('checksum_mismatch')
    expect(context.decodeAudioData).not.toHaveBeenCalled()
    expect(preparer.snapshot().entries).toBe(0)
  })

  it('rejects absent checksum support, decode failure, wrong duration/rate/channels and nonfinite samples', async () => {
    const context = new FakeContext()
    const preparer = new LocalClipPreparer(context.asAudioContext())
    vi.stubGlobal('crypto', {})
    await expect(preparer.prepare('test-sine')).rejects.toThrow('checksum_unavailable')
    vi.stubGlobal('crypto', testCrypto)
    context.decodeAudioData.mockRejectedValueOnce(new Error('decode_failed'))
    await expect(preparer.prepare('test-sine')).rejects.toThrow('decode_failed')
    for (const buffer of [context.createBuffer(1, 3000, 8000), context.createBuffer(1, 4000, 16000), context.createBuffer(2, 2000, 8000)]) {
      context.decodeAudioData.mockResolvedValueOnce(buffer)
      await expect(preparer.prepare('test-sine')).rejects.toThrow('decoded_metadata_mismatch')
    }
    const nonfinite = context.createBuffer(1, 2000, 8000); nonfinite.getChannelData(0)[4] = Infinity
    context.decodeAudioData.mockResolvedValueOnce(nonfinite)
    await expect(preparer.prepare('test-sine')).rejects.toThrow('nonfinite_local_buffer')
    expect(preparer.snapshot()).toMatchObject({ bytes: 0, inFlight: 0 })
  })

  it('allows Web Audio resampling, checking decoded rate against the context', async () => {
    const context = new FakeContext(); context.sampleRate = 48000
    context.decodeAudioData.mockResolvedValueOnce(context.createBuffer(1, 12000, 48000))
    const preparer = new LocalClipPreparer(context.asAudioContext())
    expect((await preparer.prepare('test-sine')).sampleRate).toBe(48000)
  })

  it('isolates mutable caller buffers, coalesces concurrent decoding and uses an LRU byte cap', async () => {
    const context = new FakeContext()
    const preparer = new LocalClipPreparer(context.asAudioContext(), new FixturePackStorage(), 8000)
    const [a, b] = await Promise.all([preparer.prepare('test-sine'), preparer.prepare('test-sine')])
    expect(context.decodeAudioData).toHaveBeenCalledTimes(1)
    expect(a).not.toBe(b)
    const original = b.getChannelData(0)[1]
    a.getChannelData(0).fill(1)
    expect((await preparer.prepare('test-sine')).getChannelData(0)[1]).toBe(original)
    await preparer.prepare('test-chime')
    expect(preparer.snapshot()).toMatchObject({ entries: 1, bytes: 8000 })
    await preparer.prepare('test-sine')
    expect(context.decodeAudioData).toHaveBeenCalledTimes(3)
    preparer.clear(); expect(preparer.snapshot().bytes).toBe(0)
    expect(() => new LocalClipPreparer(context.asAudioContext(), undefined, MAX_DECODED_CACHE_BYTES + 1)).toThrow('invalid_cache_limit')
  })

  it('clear prevents an in-flight decode from repopulating the cache', async () => {
    const context = new FakeContext()
    let release!: (buffer: AudioBuffer) => void
    context.decodeAudioData.mockImplementationOnce(() => new Promise(resolve => { release = resolve }))
    const preparer = new LocalClipPreparer(context.asAudioContext())
    const pending = preparer.prepare('test-sine')
    const rejected = expect(pending).rejects.toThrow('decode_cancelled')
    await vi.waitFor(() => expect(context.decodeAudioData).toHaveBeenCalledOnce())
    preparer.clear()
    release(context.createBuffer(1, 2000, 8000)); await rejected
    expect(preparer.snapshot()).toMatchObject({ entries: 0, bytes: 0, inFlight: 0 })
  })

  it('does not coalesce a new epoch with a cleared decode or let old cleanup erase a new task', async () => {
    const context = new FakeContext()
    const releases: ((buffer: AudioBuffer) => void)[] = []
    context.decodeAudioData.mockImplementation(() => new Promise(resolve => { releases.push(resolve) }))
    const preparer = new LocalClipPreparer(context.asAudioContext())
    const old = preparer.prepare('test-sine')
    const rejected = expect(old).rejects.toThrow('decode_cancelled')
    await vi.waitFor(() => expect(releases).toHaveLength(1))
    preparer.clear()
    const current = preparer.prepare('test-sine')
    await vi.waitFor(() => expect(releases).toHaveLength(2))
    releases[0](context.createBuffer(1, 2000, 8000)); await rejected
    expect(preparer.snapshot().inFlight).toBe(1)
    releases[1](context.createBuffer(1, 2000, 8000)); await current
    expect(preparer.snapshot()).toMatchObject({ entries: 1, bytes: 8000, inFlight: 0 })
  })

  it('bounds outstanding reads/decodes across repeated clear, not just the current epoch', async () => {
    const context = new FakeContext(), releases: ((bytes: Uint8Array<ArrayBuffer>) => void)[] = []
    const preparer = new LocalClipPreparer(context.asAudioContext(), {
      read: () => new Promise(resolve => { releases.push(resolve) }),
    })
    const pending: Promise<unknown>[] = []
    for (let index = 0; index < 4; index++) {
      pending.push(preparer.prepare('test-sine').catch(error => error.message))
      preparer.clear()
    }
    await expect(preparer.prepare('test-sine')).rejects.toThrow('decode_busy')
    expect(releases).toHaveLength(4)
    for (const release of releases) release(createTestClipWav('test-sine'))
    expect(await Promise.all(pending)).toEqual(Array(4).fill('decode_cancelled'))
    expect(preparer.snapshot().inFlight).toBe(0)
  })
})

describe('local copied normalization', () => {
  it('attenuates stereo peaks to .25 without amplification, mutation or channel skew', () => {
    const context = new FakeContext(); const raw = context.createBuffer(2, 2000, 8000)
    raw.getChannelData(0).fill(1); raw.getChannelData(1).fill(-0.5)
    const copy = verifyLocalBuffer(context.asAudioContext(), raw)
    expect(copy.getChannelData(0)[0]).toBe(0.25)
    expect(copy.getChannelData(1)[0]).toBe(-0.125)
    expect(raw.getChannelData(0)[0]).toBe(1)
    raw.getChannelData(0).fill(0.1); raw.getChannelData(1).fill(0)
    expect(copyNormalizedLocalBuffer(context.asAudioContext(), raw).getChannelData(0)[0]).toBeCloseTo(0.1)
  })

  it('accepts exact limits and rejects 60s+, bytes+, nonfinite, invalid samples/rates/channels', () => {
    const context = new FakeContext()
    expect(verifyLocalBuffer(context.asAudioContext(), context.createBuffer(1, 480000, 8000)).duration).toBe(60)
    expect(verifyLocalBuffer(context.asAudioContext(), context.createBuffer(1, 720000, 12000)).length * 4).toBe(2880000)
    for (const raw of [context.createBuffer(1, 480001, 8000), context.createBuffer(1, 720001, 12001),
      context.createBuffer(3, 2000, 8000), context.createBuffer(1, 0, 8000), context.createBuffer(1, 2000, 1000)]) {
      expect(() => verifyLocalBuffer(context.asAudioContext(), raw)).toThrow('invalid_local_buffer')
    }
    const raw = context.createBuffer(1, 2000, 8000); raw.getChannelData(0)[0] = NaN
    expect(() => verifyLocalBuffer(context.asAudioContext(), raw)).toThrow('nonfinite_local_buffer')
  })
})