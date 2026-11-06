import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { AchievementLine } from '@/entities/achievement/model/types'
import { AchievementCard } from './achievement-card'

vi.mock('./achievement-media', () => ({
  AchievementImage: ({ tier }: { tier: { title: string; earned: boolean } }) => <span>{tier.earned ? `image:${tier.title}` : 'image:?'}</span>,
  RarityBadge: () => <span>Редкость</span>,
}))

const line: AchievementLine = {
  id: 'practice.workouts', group: 'practice', groupName: 'Практика', metric: 'qualified_workouts',
  unit: 'тренировка', description: 'Подтверждённая практика в разные дни',
  thresholds: [5, 20, 50, 100, 200, 400], applicability: 'available', currentValue: 400,
  highestTier: 6, state: 'available', nextTierId: null, progressPercent: 100,
  tiers: [5, 20, 50, 100, 200, 400].map((threshold, index) => ({
    id: `practice.workouts:t${index + 1}`, tier: index + 1, tierName: `Ступень ${index + 1}`,
    threshold, title: `Награда ${index + 1}`, phrase: 'Практика сохранена', rarity: 'rare',
    imageUrl: null, thumbnailUrl: null, audioUrl: null, imageState: 'missing', audioState: 'missing',
    earned: true, earnedAt: null, awardedAt: null, status: 'earned',
  })),
}

describe('achievement card', () => {
  it('shows an icon with its title for every earned tier and the final threshold', () => {
    render(<MemoryRouter><AchievementCard line={line} /></MemoryRouter>)
    const tiers = within(screen.getByLabelText('Получено ступеней: 6 из 6')).getAllByRole('listitem')
    expect(tiers).toHaveLength(6)
    tiers.forEach((tier, index) => {
      expect(within(tier).getByText(`image:Награда ${index + 1}`)).toBeInTheDocument()
      expect(within(tier).getByText(`Награда ${index + 1}`)).toBeInTheDocument()
    })
    expect(screen.getByText(/400 \/ 400/)).toBeInTheDocument()
    expect(screen.getByText('Все ступени получены')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Открыть достижение «Награда 6»' })).toBeInTheDocument()
  })

  it('shows only earned tiers while progressing and never names the next reward', () => {
    const progressing = {
      ...line, highestTier: 4, currentValue: 140, nextTierId: line.tiers[4].id,
      tiers: line.tiers.map((tier, index) => ({ ...tier, earned: index < 4, title: index < 4 ? tier.title : '' })),
    }
    render(<MemoryRouter><AchievementCard line={progressing} /></MemoryRouter>)
    expect(within(screen.getByLabelText('Получено ступеней: 4 из 6')).getAllByRole('listitem')).toHaveLength(4)
    expect(screen.getByText(/140 \/ 200/)).toBeInTheDocument()
    expect(screen.queryByText('Награда 5')).not.toBeInTheDocument()
    expect(screen.queryByText('image:?')).not.toBeInTheDocument()
  })

  it('shows the independent evidence-day requirement for a started line', () => {
    const progressing = {
      ...line, highestTier: 1, currentValue: 20, evidenceDays: 1, nextTierId: line.tiers[1].id, progressPercent: 6.3,
      tiers: line.tiers.map((tier, index) => ({ ...tier, earned: index === 0, minimumEvidenceDays: 16 })),
    }
    render(<MemoryRouter><AchievementCard line={progressing} /></MemoryRouter>)
    expect(screen.getByText('Подтверждённая практика: 1 / 16 разных дней')).toBeInTheDocument()
    expect(screen.queryByText('Все ступени получены')).not.toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '6')
  })

  it('marks the latest earned line as new', () => {
    render(<MemoryRouter><AchievementCard line={{ ...line, isNew: true }} /></MemoryRouter>)
    expect(screen.getByText('Новая')).toBeInTheDocument()
  })

  it('renders an unknown line as a closed question mark with no description, link or titles', () => {
    const unknown = {
      ...line, highestTier: 0, currentValue: 0, description: '', nextTierId: line.tiers[0].id,
      tiers: line.tiers.map((tier) => ({ ...tier, earned: false, title: '', phrase: '' })),
    }
    render(<MemoryRouter><AchievementCard line={unknown} /></MemoryRouter>)
    expect(screen.getByText('image:?')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Неизвестное достижение' })).toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.queryByText('Подтверждённая практика в разные дни')).not.toBeInTheDocument()
    expect(screen.queryByText(/Награда/)).not.toBeInTheDocument()
  })
})
