import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AchievementLine } from '@/entities/achievement/model/types'
import { useAppStore } from '@/stores/app-store'
import { AchievementDetailScreen } from './achievement-detail-screen'

const api = vi.hoisted(() => ({ detail: vi.fn(), recordReceipt: vi.fn() }))
const media = vi.hoisted(() => ({ audio: [] as Array<{ autoPlay?: boolean; onPlaybackStart?: () => void }> }))

vi.mock('@/features/achievements/lib/achievements-api', () => ({ achievementsApi: api }))
vi.mock('@/features/achievements/ui/achievement-media', () => ({
  AchievementImage: ({ tier }: { tier: { earned: boolean } }) => <span>{tier.earned ? 'image:earned' : 'image:?'}</span>,
  RarityBadge: () => <span>Редкость</span>,
  AchievementAudioButton: (props: { tier: { earned: boolean }; autoPlay?: boolean; onPlaybackStart?: () => void }) => {
    media.audio.push(props)
    return props.tier.earned ? <button type="button" onClick={props.onPlaybackStart}>audio</button> : null
  },
}))
vi.mock('@/shared/ui/layout/forma-shell', () => ({ FormaShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/shared/ui/overlays/surface-components', () => ({ EmergencyStopOverlay: () => null }))

const line: AchievementLine = {
  id: 'start.first_set', group: 'start', groupName: 'Начало пути', metric: 'qualified_sets', unit: 'подход',
  description: 'Нужны сохранённые подходы и доказательные дни', thresholds: [1, 5], applicability: 'available',
  currentValue: 5, evidenceDays: 24, highestTier: 1, state: 'available', nextTierId: 'start.first_set:t2',
  progressPercent: 50, isNew: true,
  tiers: [
    {
      id: 'start.first_set:t1', tier: 1, tierName: 'Начало', threshold: 1, minimumEvidenceDays: 12,
      title: 'Рычаг старта', phrase: 'Первая ступень получена', rarity: 'common', imageUrl: '/t1.webp',
      thumbnailUrl: '/t1.webp', audioUrl: '/t1.wav', imageState: 'ready', audioState: 'ready', earned: true,
      earnedAt: '2026-01-02T00:00:00Z', awardedAt: '2026-01-02T00:00:00Z', status: 'earned',
    },
    {
      id: 'start.first_set:t2', tier: 2, tierName: 'Практика', threshold: 5, minimumEvidenceDays: 24,
      title: '', phrase: '', rarity: 'common', imageUrl: null, thumbnailUrl: null, audioUrl: '/t2.wav',
      imageState: 'missing', audioState: 'ready', earned: false, earnedAt: null, awardedAt: null, status: 'not_started',
    },
  ],
}

beforeEach(() => {
  useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
  api.detail.mockResolvedValue(line)
  api.recordReceipt.mockResolvedValue({ isNew: false })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  media.audio.length = 0
})

describe('achievement detail receipts and privacy', () => {
  it('opens the highest earned tier, records real actions and hides locked editorial', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/achievements/start.first_set']}>
          <Routes><Route path="/achievements/:definitionId" element={<AchievementDetailScreen />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(await screen.findByRole('heading', { name: 'Рычаг старта', level: 1 })).toBeInTheDocument()
    expect(screen.getByText('Скрытая награда')).toBeInTheDocument()
    // Hero + the earned tier only: the locked tier has no audio control even if a stray URL arrived.
    expect(screen.getAllByText('audio')).toHaveLength(2)
    expect(screen.getByText('Новая')).toBeInTheDocument()
    expect(screen.queryByText('Практика сохранена')).not.toBeInTheDocument()
    await waitFor(() => expect(api.recordReceipt).toHaveBeenCalledWith('alexey', 'start.first_set', 'detail', undefined))
    expect(media.audio.some((props) => props.autoPlay)).toBe(true)

    fireEvent.click(screen.getAllByText('audio')[0])
    await waitFor(() => expect(api.recordReceipt).toHaveBeenCalledWith('alexey', 'start.first_set', 'audio', 1))
  })
})
