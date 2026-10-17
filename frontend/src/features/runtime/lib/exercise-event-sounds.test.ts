import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useStage4Store } from '@/stores/stage4-store'
import { getCoachAudibleCount } from '@/shared/lib/audio-priority'
import { FakeClock, FakeContext } from '@/features/coach/audio/audio-test-fakes'
import { LocalCoachAudioManager } from '@/features/coach/audio/local-coach-audio-manager'
import { createTestClipBuffer } from '@/features/coach/audio/test-clips'
import type { CoachAudio, CoachScope } from '@/features/coach/model/contracts'
import { playExerciseEventSound, useExerciseEventSounds } from './exercise-event-sounds'

const play = vi.fn().mockResolvedValue(undefined)
class FakeAudio extends EventTarget {
  volume = 1
  play = play
  pause = vi.fn()
  addEventListener = vi.fn(super.addEventListener.bind(this))
  removeEventListener = vi.fn(super.removeEventListener.bind(this))
}
const instances: FakeAudio[] = []
const audio = vi.fn(function (_src: string) {
  const instance = new FakeAudio()
  instances.push(instance)
  return instance
})
const savedSettings = useStage4Store.getState().settingsSaved
const managers: LocalCoachAudioManager[] = []
const scope: CoachScope = { schemaVersion: 1, userId: 'u', runId: 'r', exerciseId: 'e', setOrdinal: 1, scopeEpoch: 1 }
function coach() {
  const context = new FakeContext()
  const clock = new FakeClock()
  const manager = new LocalCoachAudioManager({ context: context.asAudioContext(), clock, scope })
  managers.push(manager)
  const start = (source: 'local' | 'cache' = 'local', baseGain = 1, delayMs = 0) => manager.playLocal({
    id: `voice-${context.sources.length}-${clock.now()}`, scope, source, baseGain, delayMs,
    buffer: createTestClipBuffer(context.asAudioContext()), startDeadlineMs: 10_000, revalidate: () => true,
  })
  return { manager, context, clock, start, advance: (ms = 20) => clock.advance(ms, context) }
}

describe('exercise event sounds', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    instances.length = 0
    audio.mockClear()
    play.mockClear().mockResolvedValue(undefined)
    vi.stubGlobal('Audio', audio)
    useStage4Store.setState({ settingsSaved: { ...savedSettings, soundEnabled: true, signalVolume: '70%' } })
  })
  afterEach(() => {
    for (const manager of managers.splice(0)) manager.dispose()
    for (const instance of instances) instance.dispatchEvent(new Event('ended'))
    expect(getCoachAudibleCount()).toBe(0)
    expect(vi.getTimerCount()).toBe(0)
    vi.useRealTimers()
    vi.unstubAllGlobals()
    useStage4Store.setState({ settingsSaved: savedSettings })
  })

  it('plays all requested files at the calibrated saved signal volume without initializing Web Audio', () => {
    const contextConstructor = vi.fn()
    vi.stubGlobal('AudioContext', contextConstructor)
    playExerciseEventSound('upper')
    playExerciseEventSound('lower')
    playExerciseEventSound('error')
    playExerciseEventSound('success')
    expect(audio.mock.calls.map(([src]) => src)).toEqual(['/audio/pop-up.mp3', '/audio/pop-down.mp3', '/audio/error-notification.mp3', '/audio/success.mp3'])
    for (const instance of instances.slice(0, 2)) expect(instance.volume).toBeCloseTo(0.7 * 0.12 * 0.3)
    for (const instance of instances.slice(2)) expect(instance.volume).toBeCloseTo(0.7 * 0.12)
    expect(contextConstructor).not.toHaveBeenCalled()
    expect(play).toHaveBeenCalledTimes(4)
  })

  it('respects mute and tolerates playback rejection', async () => {
    useStage4Store.setState({ settingsSaved: { ...savedSettings, soundEnabled: false } })
    playExerciseEventSound('upper')
    expect(audio).not.toHaveBeenCalled()
    useStage4Store.setState({ settingsSaved: { ...savedSettings, soundEnabled: true, signalVolume: '0%' } })
    playExerciseEventSound('error')
    expect(audio).not.toHaveBeenCalled()
    useStage4Store.setState({ settingsSaved: { ...savedSettings, soundEnabled: true, signalVolume: '70%' } })
    play.mockRejectedValueOnce(new Error('Autoplay blocked'))
    expect(() => playExerciseEventSound('lower')).not.toThrow()
    await Promise.resolve()
    expect(instances[0].removeEventListener).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each(['local', 'cache'] as const)('ducks current and future effects only after actual %s start and restores on finish', source => {
    const voice = coach()
    playExerciseEventSound('upper')
    voice.start(source)
    expect(instances[0].volume).toBeCloseTo(0.0252) // Scheduled, not started.
    voice.advance()
    expect(getCoachAudibleCount()).toBe(1)
    expect(instances[0].volume).toBeCloseTo(0.00252)
    playExerciseEventSound('lower')
    expect(instances[1].volume).toBeCloseTo(0.00252)
    voice.context.sources[0].end()
    for (const instance of instances) expect(instance.volume).toBeCloseTo(0.0252)
  })

  it.each(['cancel', 'mute', 'zero', 'dispose', 'suspend'] as const)('releases priority on %s', action => {
    const voice = coach()
    voice.start(); voice.advance()
    playExerciseEventSound('error')
    expect(instances[0].volume).toBeCloseTo(0.0084)
    if (action === 'cancel') voice.manager.cancelAll()
    if (action === 'mute') voice.manager.setVolume(1, true)
    if (action === 'zero') voice.manager.setVolume(0)
    if (action === 'dispose') voice.manager.dispose()
    if (action === 'suspend') voice.context.setState('suspended')
    expect(instances[0].volume).toBeCloseTo(0.084)
  })

  it('does not duck for delayed, buffering, zero-gain or elapsed sources, even without ended callbacks', () => {
    const voice = coach()
    playExerciseEventSound('success')
    voice.start('local', 0)
    voice.advance(20)
    voice.start('local', 1, 1000)
    voice.advance(500)
    expect(instances[0].volume).toBeCloseTo(0.084)
    voice.advance(600)
    expect(instances[0].volume).toBeCloseTo(0.0084)
    voice.advance(500)
    expect(instances[0].volume).toBeCloseTo(0.084)
  })

  it('releases stream underrun immediately at PCM end, not at the mixer gap grace; resumes only at PCM start', () => {
    const voice = coach()
    playExerciseEventSound('error')
    voice.manager.beginStream({ id: 'stream', generationId: 'g', scope, source: 'realtime', sampleRate: 8000,
      startDeadlineMs: 10_000, baseGain: 1, revalidate: () => true })
    const push = (sequence: number, seconds: number, final = false) => {
      const pcm = new Uint8Array(seconds * 8000 * 2)
      const metadata: CoachAudio = { schemaVersion: 1, utteranceId: 'stream', generationId: 'g', scope, sequence,
        source: 'realtime', codec: 'pcm_s16le', sampleRate: 8000, channels: 1, byteLength: pcm.length,
        durationMs: seconds * 1000, final }
      voice.manager.pushStream(metadata, pcm)
    }
    push(0, 0.05)
    voice.advance(50)
    expect(instances[0].volume).toBeCloseTo(0.084)
    push(1, 0.1)
    expect(instances[0].volume).toBeCloseTo(0.084)
    voice.advance(30)
    expect(instances[0].volume).toBeCloseTo(0.0084)
    voice.advance(150)
    expect(voice.manager.snapshot().utterances[0].stream?.inGap).toBe(false)
    expect(instances[0].volume).toBeCloseTo(0.084)
    voice.advance(300)
    push(2, 0.2, true)
    expect(instances[0].volume).toBeCloseTo(0.084)
    voice.advance(30)
    expect(instances[0].volume).toBeCloseTo(0.0084)
    for (const source of voice.context.sources) source.end()
    expect(instances[0].volume).toBeCloseTo(0.084)
  })

  it('retains ducking until every manager owner releases playback', () => {
    const first = coach(), second = coach()
    first.start(); second.start(); first.advance(); second.advance()
    expect(getCoachAudibleCount()).toBe(2)
    playExerciseEventSound('upper')
    first.manager.dispose()
    expect(instances[0].volume).toBeCloseTo(0.00252)
    second.manager.cancelAll()
    expect(instances[0].volume).toBeCloseTo(0.0252)
  })

  it('updates playing effects with user volume and mute, preserving zero across priority changes', () => {
    const voice = coach()
    playExerciseEventSound('upper')
    useStage4Store.setState({ settingsSaved: { ...savedSettings, soundEnabled: true, signalVolume: '100%' } })
    expect(instances[0].volume).toBeCloseTo(0.036)
    voice.start(); voice.advance()
    expect(instances[0].volume).toBeCloseTo(0.0036)
    useStage4Store.setState({ settingsSaved: { ...savedSettings, soundEnabled: true, signalVolume: '0%' } })
    voice.manager.cancelAll()
    expect(instances[0].volume).toBe(0)
    useStage4Store.setState({ settingsSaved: { ...savedSettings, soundEnabled: false, signalVolume: '100%' } })
    expect(instances[0].volume).toBe(0)
  })

  it.each(['ended', 'error'] as const)('removes listeners, timer and subscriptions on %s', event => {
    playExerciseEventSound('upper')
    const instance = instances[0]
    instance.dispatchEvent(new Event(event))
    expect(instance.removeEventListener).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(0)
    const voice = coach()
    voice.start(); voice.advance()
    expect(instance.volume).toBeCloseTo(0.0252) // No retained priority listener.
    useStage4Store.setState({ settingsSaved: { ...savedSettings, soundEnabled: false } })
    expect(instance.volume).toBeCloseTo(0.0252) // No retained store listener.
  })

  it('bounds pending play promises and simultaneous effects; late resolution cannot restart expired audio', async () => {
    let resolve!: () => void
    play.mockImplementation(() => new Promise<void>(done => { resolve = done }))
    playExerciseEventSound('upper')
    const first = instances[0]
    const resolveFirst = resolve
    for (let i = 0; i < 16; i++) playExerciseEventSound('lower')
    expect(first.pause).toHaveBeenCalledOnce()
    expect(first.removeEventListener).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(16)
    vi.advanceTimersByTime(15_000)
    expect(vi.getTimerCount()).toBe(0)
    resolveFirst(); await Promise.resolve()
    expect(first.pause).toHaveBeenCalledTimes(2)
    for (const instance of instances) expect(instance.removeEventListener).toHaveBeenCalledTimes(2)
  })

  it('tolerates a synchronous play exception without leaking subscriptions or timers', () => {
    play.mockImplementationOnce(() => { throw new Error('unavailable') })
    expect(() => playExerciseEventSound('upper')).not.toThrow()
    expect(instances[0].removeEventListener).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(0)
  })

  type Inputs = { scope: string; position: 'upper' | 'lower' | 'neutral' | null; problems: string[]; partialReps: number }
  const initial: Inputs = { scope: 'set-1', position: 'lower', problems: [], partialReps: 0 }
  const useSounds = (props: Inputs) => useExerciseEventSounds(props.scope, props.position, props.problems, props.partialReps)

  it('plays once on endpoint arrival, not on mounting, repeated telemetry or a new set', () => {
    const { rerender } = renderHook(useSounds, { initialProps: initial })
    expect(audio).not.toHaveBeenCalled()
    rerender({ ...initial, position: 'neutral' })
    rerender({ ...initial, position: 'upper' })
    rerender({ ...initial, position: 'upper' })
    rerender({ ...initial, position: 'neutral' })
    rerender(initial)
    expect(audio.mock.calls.map(([src]) => src)).toEqual(['/audio/pop-up.mp3', '/audio/pop-down.mp3'])
    rerender({ ...initial, scope: 'set-2', position: 'upper' })
    expect(audio).toHaveBeenCalledTimes(2)
  })

  it('prioritizes new problems and partial reps, without repeating unchanged warnings', () => {
    const { rerender } = renderHook(useSounds, { initialProps: initial })
    rerender({ ...initial, position: 'upper', problems: ['fault'] })
    expect(audio).toHaveBeenLastCalledWith('/audio/error-notification.mp3')
    rerender({ ...initial, position: 'upper', problems: ['fault'] })
    expect(audio).toHaveBeenCalledTimes(1)
    rerender({ ...initial, problems: ['fault', 'network'] })
    expect(audio).toHaveBeenCalledTimes(2)
    rerender(initial)
    rerender({ ...initial, problems: ['fault'] })
    rerender({ ...initial, problems: ['fault'], partialReps: 1 })
    expect(audio).toHaveBeenCalledTimes(4)
    expect(audio.mock.calls.every(([src]) => src === '/audio/error-notification.mp3')).toBe(true)
  })
})