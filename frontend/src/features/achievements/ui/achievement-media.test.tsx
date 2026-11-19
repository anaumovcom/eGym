import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AchievementTier } from '@/entities/achievement/model/types'
import { useAppStore } from '@/stores/app-store'
import { useStage4Store } from '@/stores/stage4-store'
import { AchievementAudioButton } from './achievement-media'

const tier: AchievementTier = {
  id: 'practice.workouts:t6', tier: 6, tierName: 'Большой путь', threshold: 400,
  title: 'Большая награда', phrase: 'Практика сохранена', rarity: 'rare', imageUrl: null,
  thumbnailUrl: null, audioUrl: '/media/achievements/v2/audio/test.wav', imageState: 'missing',
  audioState: 'ready', earned: true, earnedAt: null, awardedAt: null, status: 'earned',
}

beforeEach(() => {
  useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
  const saved = useStage4Store.getState().settingsSaved
  useStage4Store.setState({ settingsSaved: { ...saved, soundEnabled: true, voiceHintsEnabled: true } })
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event('pause'))
  })
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('achievement audio safety', () => {
  it('renders no control and no audio source for a tier that is not earned', () => {
    const { container } = render(<AchievementAudioButton tier={{ ...tier, earned: false, title: '' }} />)
    expect(container).toBeEmptyDOMElement()
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled()
  })

  it('does not autoplay and preloads no audio', () => {
    const { container } = render(<AchievementAudioButton tier={tier} />)
    expect(container.querySelector('audio')).toHaveAttribute('preload', 'none')
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled()
  })

  it('stops the other clip before starting another', async () => {
    render(<><AchievementAudioButton tier={tier} /><AchievementAudioButton tier={{ ...tier, id: 'practice.workouts:t5', title: 'Ещё награда' }} /></>)
    fireEvent.click(screen.getByRole('button', { name: 'Послушать историю «Большая награда»' }))
    await screen.findByRole('button', { name: 'Остановить озвучку «Большая награда»' })
    fireEvent.click(screen.getByRole('button', { name: 'Послушать историю «Ещё награда»' }))
    await screen.findByRole('button', { name: 'Остановить озвучку «Ещё награда»' })
    expect(screen.getByRole('button', { name: 'Послушать историю «Большая награда»' })).toBeInTheDocument()
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2)
  })

  it('stops on STOP and prevents restarting while emergency is active', async () => {
    const { rerender } = render(<AchievementAudioButton tier={tier} />)
    fireEvent.click(screen.getByRole('button'))
    await screen.findByRole('button', { name: 'Остановить озвучку «Большая награда»' })
    act(() => { useAppStore.setState({ emergencyStopActive: true }) })
    rerender(<AchievementAudioButton tier={tier} />)
    await waitFor(() => expect(screen.getByRole('button')).toBeDisabled())
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'false')
  })

  it('stops when the selected profile changes', async () => {
    const { rerender } = render(<AchievementAudioButton tier={tier} />)
    fireEvent.click(screen.getByRole('button'))
    await screen.findByRole('button', { name: 'Остановить озвучку «Большая награда»' })
    act(() => { useAppStore.setState({ selectedUserId: 'elena' }) })
    rerender(<AchievementAudioButton tier={tier} />)
    await waitFor(() => expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'false'))
  })

  it('stops the current recording when its award leaves the screen', async () => {
    const { unmount } = render(<AchievementAudioButton tier={tier} />)
    fireEvent.click(screen.getByRole('button', { name: 'Послушать историю «Большая награда»' }))
    await screen.findByRole('button', { name: 'Остановить озвучку «Большая награда»' })
    vi.mocked(HTMLMediaElement.prototype.pause).mockClear()
    unmount()
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalledTimes(1)
  })

  it('reports only a requested playback, even after rerender', async () => {
    const onPlaybackStart = vi.fn()
    const { rerender } = render(<AchievementAudioButton tier={tier} onPlaybackStart={onPlaybackStart} />)
    expect(onPlaybackStart).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button'))
    await waitFor(() => expect(onPlaybackStart).toHaveBeenCalledTimes(1))
    rerender(<AchievementAudioButton tier={tier} onPlaybackStart={onPlaybackStart} />)
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1)
  })

  it('reports a failed manual playback and allows a retry', async () => {
    const onPlaybackStart = vi.fn()
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockRejectedValueOnce(new DOMException('Blocked', 'NotAllowedError'))
    render(<AchievementAudioButton tier={tier} onPlaybackStart={onPlaybackStart} />)
    fireEvent.click(screen.getByRole('button'))
    await screen.findByText('Не удалось воспроизвести запись. Попробуйте ещё раз.')
    expect(onPlaybackStart).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Послушать историю «Большая награда»' }))
    await waitFor(() => expect(onPlaybackStart).toHaveBeenCalledTimes(1))
  })
})
