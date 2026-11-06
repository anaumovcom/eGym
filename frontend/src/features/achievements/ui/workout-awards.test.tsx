import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { AchievementAward } from '@/entities/achievement/model/types'
import { WorkoutAwards } from './workout-awards'

const api = vi.hoisted(() => ({ workoutAwards: vi.fn(), recordReceipt: vi.fn() }))

vi.mock('@/features/achievements/lib/achievements-api', () => ({ achievementsApi: api }))
vi.mock('@/features/achievements/ui/achievement-media', () => ({
  AchievementImage: () => <span>icon</span>,
  RarityBadge: () => <span>rarity</span>,
  AchievementAudioButton: ({ onPlaybackStart }: { onPlaybackStart?: () => void }) =>
    <button type="button" onClick={onPlaybackStart}>play</button>,
}))

const award: AchievementAward = {
  grantId: 7, definitionId: 'start.first_set', group: 'start', sourceWorkoutId: 42,
  status: 'earned', isNew: true, earnedAt: null, awardedAt: '2026-11-05T12:00:00Z',
  unit: 'подход', description: 'condition',
  tier: {
    id: 'start.first_set:t1', tier: 1, tierName: 'Начало', threshold: 1,
    title: 'Полученная награда', phrase: 'Фраза', rarity: 'common', imageUrl: null,
    thumbnailUrl: null, audioUrl: '/audio.wav', imageState: 'missing', audioState: 'ready',
    earned: true, earnedAt: null, awardedAt: null, status: 'earned',
  },
}

describe('WorkoutAwards receipts', () => {
  it('shows the new badge and records only actual playback', async () => {
    api.workoutAwards.mockResolvedValue({ workoutId: 42, awards: [award], isRebuilding: false })
    api.recordReceipt.mockResolvedValue({ isNew: false })
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter><WorkoutAwards userId="alexey" workoutId={42} /></MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('Новая')).toBeInTheDocument()
    expect(api.recordReceipt).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'play' }))
    await waitFor(() => expect(api.recordReceipt).toHaveBeenCalledWith('alexey', 'start.first_set', 'audio', 1))
  })
})
