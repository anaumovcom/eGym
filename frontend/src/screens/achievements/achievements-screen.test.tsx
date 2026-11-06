import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AchievementLine } from '@/entities/achievement/model/types'
import { useAppStore } from '@/stores/app-store'
import { AchievementsScreen } from './achievements-screen'

const api = vi.hoisted(() => ({ catalog: vi.fn(), overview: vi.fn() }))

vi.mock('@/features/achievements/lib/achievements-api', () => ({ achievementsApi: api }))
vi.mock('@/features/achievements/ui/achievement-media', () => ({
  AchievementImage: ({ tier }: { tier: { earned: boolean } }) => <span>{tier.earned ? 'image:earned' : 'image:?'}</span>,
  RarityBadge: () => <span>Редкость</span>,
}))
vi.mock('@/shared/ui/layout/forma-shell', () => ({ FormaShell: ({ children }: { children: React.ReactNode }) => <>{children}</> }))
vi.mock('@/shared/ui/overlays/surface-components', () => ({ EmergencyStopOverlay: () => null }))

function make(id: string, group: string, groupName: string, earned: boolean, isNew = false): AchievementLine {
  return {
    id, group, groupName, metric: 'm', unit: 'подход', description: earned ? 'Открытое условие' : '',
    thresholds: [1, 5], applicability: 'available', currentValue: earned ? 1 : 0, highestTier: earned ? 1 : 0,
    state: 'available', nextTierId: `${id}:t2`, progressPercent: 10, isNew,
    tiers: [1, 2].map((tier) => ({
      id: `${id}:t${tier}`, tier, tierName: `Ступень ${tier}`, threshold: tier === 1 ? 1 : 5,
      title: earned && tier === 1 ? `Награда ${id}` : '', phrase: '', rarity: 'rare' as const, imageUrl: null,
      thumbnailUrl: null, audioUrl: null, imageState: 'x', audioState: 'x', earned: earned && tier === 1,
      earnedAt: null, awardedAt: null, status: earned && tier === 1 ? 'earned' : 'not_started',
    })),
  }
}

const lines = [make('start.one', 'start', 'Начало пути', true, true), make('start.two', 'start', 'Начало пути', false), make('practice.x', 'practice', 'Практика', false)]

function renderScreen() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}><MemoryRouter><AchievementsScreen /></MemoryRouter></QueryClientProvider>)
}

beforeEach(() => {
  useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
  api.overview.mockResolvedValue({ earnedTiers: 1, totalTiers: 6, completedLines: 0, totalLines: 3, activeDays: 12, recent: [], upcoming: [], computedThrough: null, isRebuilding: false, media: { lines: 3, tiers: 6, images: 1, audio: 1 } })
  api.catalog.mockResolvedValue({ lines, total: 3, nextCursor: null, computedThrough: null, isRebuilding: false, groups: [{ id: 'start', name: 'Начало пути' }, { id: 'practice', name: 'Практика' }], media: { lines: 3, tiers: 6, images: 1, audio: 1 } })
})
afterEach(() => { cleanup(); vi.clearAllMocks() })

describe('achievements collection screen', () => {
  it('requests the whole collection once and keeps unknown lines closed', async () => {
    renderScreen()
    expect(await screen.findByText('Награда start.one')).toBeInTheDocument()
    expect(api.catalog).toHaveBeenCalledTimes(1)
    expect(api.catalog).toHaveBeenCalledWith('alexey', { limit: 200 })
    expect(screen.getAllByRole('heading', { name: 'Неизвестное достижение' })).toHaveLength(2)
    expect(screen.getByRole('status')).toHaveTextContent('Найдено: 3')
    const tabs = screen.getByRole('group', { name: 'Подборка достижений' })
    expect(within(tabs).getByRole('button', { name: /Неизвестные/ })).toHaveTextContent('2')
    expect(within(tabs).getByRole('button', { name: /Новые/ })).toHaveTextContent('1')
  })

  it('filters by tab, section and hidden text without leaking unknown lines', async () => {
    renderScreen()
    await screen.findByText('Награда start.one')
    fireEvent.click(screen.getByRole('button', { name: /Полученные/ }))
    expect(screen.queryByRole('heading', { name: 'Неизвестное достижение' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /^Все/ }))
    fireEvent.change(screen.getByRole('searchbox', { name: 'Поиск достижений' }), { target: { value: 'открытое' } })
    expect(screen.getByRole('status')).toHaveTextContent('Найдено: 1')
    fireEvent.change(screen.getByRole('searchbox', { name: 'Поиск достижений' }), { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: /^Практика/ }))
    expect(screen.getByRole('status')).toHaveTextContent('Найдено: 1')
    expect(screen.queryByText('Награда start.one')).not.toBeInTheDocument()
  })
})
