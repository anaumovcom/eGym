import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeClock, FakeContext } from './audio-test-fakes'

beforeEach(() => vi.resetModules())
afterEach(() => vi.unstubAllGlobals())

describe('lazy shared context gesture ownership', () => {
  it('does not create at import; creates once and resumes only on explicit unlock', async () => {
    const context = new FakeContext(); context.state = 'suspended'
    const constructor = vi.fn(function () { return context })
    vi.stubGlobal('AudioContext', constructor)
    const { getSharedAudioContext, unlockSharedAudioContext } = await import('./shared-audio-context')
    expect(constructor).not.toHaveBeenCalled()
    expect(getSharedAudioContext()).toBe(context)
    expect(getSharedAudioContext()).toBe(context)
    expect(constructor).toHaveBeenCalledOnce()
    expect(context.resume).not.toHaveBeenCalled()
    expect(await unlockSharedAudioContext()).toBe(true)
    expect(context.resume).toHaveBeenCalledOnce()
    expect(await unlockSharedAudioContext()).toBe(true)
    expect(context.resume).toHaveBeenCalledOnce()
  })

  it('is graceful when unavailable/constructor throws, with no fallback', async () => {
    vi.stubGlobal('AudioContext', undefined)
    const { getSharedAudioContext, unlockSharedAudioContext } = await import('./shared-audio-context')
    expect(getSharedAudioContext()).toBeNull()
    expect(await unlockSharedAudioContext()).toBe(false)
    vi.stubGlobal('AudioContext', vi.fn(function () { throw new Error('not supported') }))
    expect(getSharedAudioContext()).toBeNull()
    expect(await unlockSharedAudioContext()).toBe(false)
  })

  it('checks resulting resume state/rejection, not just resolved promise, and never replaces a closed shared context', async () => {
    const context = new FakeContext(); context.state = 'suspended'
    vi.stubGlobal('AudioContext', vi.fn(function () { return context }))
    const { getSharedAudioContext, unlockSharedAudioContext } = await import('./shared-audio-context')
    context.resume.mockImplementationOnce(async () => {})
    expect(await unlockSharedAudioContext()).toBe(false)
    context.resume.mockRejectedValueOnce(new Error('gesture required'))
    expect(await unlockSharedAudioContext()).toBe(false)
    context.state = 'closed'
    expect(getSharedAudioContext()).toBeNull()
    expect(await unlockSharedAudioContext()).toBe(false)
  })

  it('refuses inactive browser user activation before constructing/resuming', async () => {
    vi.stubGlobal('navigator', { userActivation: { isActive: false } })
    const constructor = vi.fn(function () { return new FakeContext() })
    vi.stubGlobal('AudioContext', constructor)
    const { unlockSharedAudioContext } = await import('./shared-audio-context')
    expect(await unlockSharedAudioContext()).toBe(false)
    expect(constructor).not.toHaveBeenCalled()
  })

  it('two managers share the singleton while disposal leaves the other manager and shared context alive', async () => {
    const context = new FakeContext()
    vi.stubGlobal('AudioContext', vi.fn(function () { return context }))
    const { LocalCoachAudioManager } = await import('./local-coach-audio-manager')
    const { createTestClipBuffer } = await import('./test-clips')
    const { getSharedAudioContext } = await import('./shared-audio-context')
    const clock = new FakeClock()
    const a = new LocalCoachAudioManager({ clock }); const b = new LocalCoachAudioManager({ clock })
    const buffer = createTestClipBuffer(context.asAudioContext())
    const scope = { schemaVersion: 1 as const, userId: 'u', runId: 'r', exerciseId: 'e', setOrdinal: 1, scopeEpoch: 1 }
    for (const [manager, id] of [[a, 'a'], [b, 'b']] as const) {
      expect(manager.playLocal({ id, scope, source: 'local', buffer, baseGain: 1, startDeadlineMs: 1000, revalidate: () => true })).toBe(true)
    }
    clock.advance(100, context)
    a.dispose()
    expect(b.snapshot().active).toBe(1)
    expect(context.sources[1].stop).not.toHaveBeenCalled()
    expect(context.close).not.toHaveBeenCalled()
    expect(getSharedAudioContext()).toBe(context)
    b.dispose(); expect(clock.pendingTimers).toBe(0)
  })
})