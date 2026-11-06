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
    const { container } = render(<AchievementAudioButton tier={{ ...tier, earned: false, title: '' }} autoPlay />)
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
    fireEvent.click(screen.getByRole('button', { name: 'Прослушать фразу «Большая награда»' }))
    await screen.findByRole('button', { name: 'Остановить фразу «Большая награда»' })
    fireEvent.click(screen.getByRole('button', { name: 'Прослушать фразу «Ещё награда»' }))
    await screen.findByRole('button', { name: 'Остановить фразу «Ещё награда»' })
    expect(screen.getByRole('button', { name: 'Прослушать фразу «Большая награда»' })).toBeInTheDocument()
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(2)
  })

  it('stops on STOP and prevents restarting while emergency is active', async () => {
    const { rerender } = render(<AchievementAudioButton tier={tier} />)
    fireEvent.click(screen.getByRole('button'))
    await screen.findByRole('button', { name: 'Остановить фразу «Большая награда»' })
    act(() => { useAppStore.setState({ emergencyStopActive: true }) })
    rerender(<AchievementAudioButton tier={tier} />)
    await waitFor(() => expect(screen.getByRole('button')).toBeDisabled())
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'false')
  })

  it('stops when the selected profile changes', async () => {
    const { rerender } = render(<AchievementAudioButton tier={tier} />)
    fireEvent.click(screen.getByRole('button'))
    await screen.findByRole('button', { name: 'Остановить фразу «Большая награда»' })
    act(() => { useAppStore.setState({ selectedUserId: 'elena' }) })
    rerender(<AchievementAudioButton tier={tier} />)
    await waitFor(() => expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'false'))
  })

  it('autoplays once and reports only successful playback', async () => {
    const onPlaybackStart = vi.fn()
    const { rerender } = render(<AchievementAudioButton tier={tier} autoPlay onPlaybackStart={onPlaybackStart} />)
    await waitFor(() => expect(onPlaybackStart).toHaveBeenCalledTimes(1))
    rerender(<AchievementAudioButton tier={tier} autoPlay onPlaybackStart={onPlaybackStart} />)
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalledTimes(1)
  })

  it('does not report blocked autoplay and leaves a working manual button', async () => {
    const onPlaybackStart = vi.fn()
    vi.spyOn(HTMLMediaElement.prototype, 'play').mockRejectedValueOnce(new DOMException('Blocked', 'NotAllowedError'))
    render(<AchievementAudioButton tier={tier} autoPlay onPlaybackStart={onPlaybackStart} />)
    await screen.findByText('Автовоспроизведение недоступно. Нажмите «Прослушать».')
    expect(onPlaybackStart).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Прослушать фразу «Большая награда»' }))
    await waitFor(() => expect(onPlaybackStart).toHaveBeenCalledTimes(1))
  })
})