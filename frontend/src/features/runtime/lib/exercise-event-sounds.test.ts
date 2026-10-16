import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useStage4Store } from '@/stores/stage4-store'
import { playExerciseEventSound, useExerciseEventSounds } from './exercise-event-sounds'

const play = vi.fn().mockResolvedValue(undefined)
const audio = vi.fn(function (this: { volume: number; play: typeof play }, _src: string) {
  this.volume = 1
  this.play = play
})
const savedSettings = useStage4Store.getState().settingsSaved

describe('exercise event sounds', () => {
  beforeEach(() => {
    audio.mockClear()
    play.mockClear().mockResolvedValue(undefined)
    vi.stubGlobal('Audio', audio)
    useStage4Store.setState({ settingsSaved: { ...savedSettings, soundEnabled: true, signalVolume: '70%' } })
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    useStage4Store.setState({ settingsSaved: savedSettings })
  })

  it('plays the requested files at the saved signal volume', () => {
    playExerciseEventSound('upper')
    playExerciseEventSound('lower')
    playExerciseEventSound('error')
    playExerciseEventSound('success')
    expect(audio.mock.calls.map(([src]) => src)).toEqual(['/audio/pop-up.mp3', '/audio/pop-down.mp3', '/audio/error-notification.mp3', '/audio/success.mp3'])
    expect(audio.mock.instances[0].volume).toBe(0.7)
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