import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { AchievementAward } from '@/entities/achievement/model/types'
import { WorkoutAwards } from './workout-awards'

const api = vi.hoisted(() => ({ workoutAwards: vi.fn(), recordReceipt: vi.fn() }))

vi.mock('@/features/achievements/lib/achievements-api', () => ({ achievementsApi: api }))
vi.mock('@/features/achievements/ui/achievement-media', () => ({
  AchievementImage: () => <span aria-hidden="true">icon</span>,
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

function renderAwards(awards: AchievementAward[], isRebuilding = false) {
  api.workoutAwards.mockResolvedValue({ workoutId: 42, awards, isRebuilding })
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter><WorkoutAwards userId="alexey" workoutId={42} /></MemoryRouter>
    </QueryClientProvider>,
  )
  return queryClient
}

describe('WorkoutAwards', () => {
  it('opens the selected tier on demand and records audio only after playback starts', async () => {
    api.recordReceipt.mockResolvedValue({ isNew: false })
    renderAwards([award])
    const open = await screen.findByRole('button', { name: award.tier.title })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.queryByText('Новая')).not.toBeInTheDocument()
    expect(screen.queryByText(award.description)).not.toBeInTheDocument()
    expect(api.recordReceipt).not.toHaveBeenCalled()
    fireEvent.click(open)
    const dialog = within(screen.getByRole('dialog', { name: 'Достижения тренировки' }))
    expect(dialog.getByText('Новая')).toBeInTheDocument()
    expect(dialog.getByText(award.description)).toBeInTheDocument()
    expect(dialog.getByText('«Фраза»')).toBeInTheDocument()
    expect(dialog.getByRole('link', { name: 'В коллекцию наград' })).toHaveAttribute('href', '/achievements/start.first_set?tier=1')
    await waitFor(() => expect(api.recordReceipt).toHaveBeenCalledWith('alexey', 'start.first_set', 'detail', 1))
    expect(api.recordReceipt).toHaveBeenCalledTimes(1)
    fireEvent.click(dialog.getByRole('button', { name: 'play' }))
    await waitFor(() => expect(api.recordReceipt).toHaveBeenCalledWith('alexey', 'start.first_set', 'audio', 1))
    fireEvent.click(dialog.getByRole('button', { name: 'Закрыть' }))
    await waitFor(() => expect(open).toHaveFocus())
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('releases the space used by the pending indicator when there are no awards', async () => {
    const queryClient = renderAwards([], true)
    expect(await screen.findByRole('status')).toBeInTheDocument()
    queryClient.setQueryData(['workout-awards', 'alexey', 42], { workoutId: 42, awards: [], isRebuilding: false })
    await waitFor(() => expect(screen.queryByRole('region')).not.toBeInTheDocument())
  })

  it('steps through earned scenes on demand and shows the movements behind the selected award', async () => {
    api.recordReceipt.mockClear()
    const second = { ...award, grantId: 8, definitionId: 'discovery.crossroads', unit: 'пар', valueAtAward: 3,
      movements: ['Присед', 'Тяга'], tier: { ...award.tier, id: 'discovery.crossroads:t2', tier: 2, title: 'Столик для новой компании' } }
    renderAwards([award, second])
    fireEvent.click(await screen.findByRole('button', { name: award.tier.title }))
    const dialog = within(screen.getByRole('dialog'))
    expect(dialog.getByRole('button', { name: 'Предыдущая награда' })).toBeDisabled()
    fireEvent.click(dialog.getByRole('button', { name: 'Следующая награда' }))
    expect(dialog.getByRole('heading', { name: second.tier.title })).toBeVisible()
    expect(dialog.getByText('Присед · Тяга')).toBeVisible()
    expect(dialog.getByText('3 пары')).toBeVisible()
    expect(dialog.getByRole('button', { name: 'Следующая награда' })).toBeDisabled()
    expect(api.recordReceipt.mock.calls.every(([, , surface]) => surface === 'detail')).toBe(true)
  })
})
