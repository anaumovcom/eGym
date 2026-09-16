import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getExerciseCatalog } from '@/mocks/stage2-data'
import { UserProfileScreen } from '@/screens/profile/user-profile-screen'
import { apiDelete, apiGet, apiPost, apiPut } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'

vi.mock('@/shared/api/client', async () => ({ ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'), apiGet: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn(), apiDelete: vi.fn() }))
vi.mock('@/shared/ui/photo/photo-capture-dialog', () => ({ PhotoCaptureDialog: ({ open }: { open: boolean }) => open ? <div role="dialog" aria-label="Фотофиксация">Камера открыта</div> : null }))
let client: QueryClient
const user = {
  id: 'alexey', name: 'Алексей', readinessPercent: 78,
  profile: { birthDate: '1991-06-12', heightCm: 182, weightKg: 84.2, photoUrl: null, notes: 'Без боли' },
  goals: [{ id: 1, goalType: 'strength', label: 'Жим 100 кг', targetValue: 100, targetUnit: 'кг', isPrimary: true }],
}
const measurements = { measurements: [
  { id: 2, measuredAt: '2026-09-10T10:00:00Z', weightKg: 84.2, bodyFatPercent: 17, chestCm: 108, waistCm: 91, hipsCm: 101 },
  { id: 1, measuredAt: '2026-08-10T10:00:00Z', weightKg: 86, bodyFatPercent: 18, chestCm: 107, waistCm: 94, hipsCm: 102 },
] }
const photos = { photos: [{ id: 5, view: 'front', takenAt: '2026-09-12T10:00:00Z', imageUrl: '/media/front.jpg', thumbnailUrl: '/media/front-thumb.jpg', width: 1200, height: 1600 }] }

function renderProfile(path = '/profile') { return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><UserProfileScreen /></MemoryRouter></QueryClientProvider>) }

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false, blacklistedExerciseSlugs: ['smith-machine-bench-press'] })
  vi.mocked(apiGet).mockReset().mockImplementation(async <T,>(path: string): Promise<T> => {
    if (path === '/api/users/current') return structuredClone(user) as T
    if (path.startsWith('/api/body-measurements?')) return structuredClone(measurements) as T
    if (path.startsWith('/api/photo-progress?')) return structuredClone(photos) as T
    if (path.startsWith('/api/exercises?')) return getExerciseCatalog() as T
    throw new Error(`Unexpected ${path}`)
  })
  vi.mocked(apiPut).mockReset().mockResolvedValue(user)
  vi.mocked(apiPost).mockReset().mockResolvedValue(measurements)
  vi.mocked(apiDelete).mockReset().mockResolvedValue(undefined)
})
afterEach(() => { cleanup(); client.clear(); vi.restoreAllMocks() })

describe('UserProfileScreen stage 6', () => {
  it('renders a compact identity, goal and exactly four tabs without duplicate summary', async () => {
    renderProfile()
    expect(await screen.findByRole('heading', { level: 1, name: 'Алексей' })).toBeVisible()
    expect(screen.getByText(/35 лет|34 лет/)).toBeVisible()
    expect(screen.getByText(/182 см/)).toBeVisible()
    expect(screen.getAllByText(/84\.2 кг/).length).toBeGreaterThan(0)
    expect(screen.getByText('Жим 100 кг')).toBeVisible()
    expect(screen.getByText('Ближайший ориентир: 100 кг')).toBeVisible()
    const nav = screen.getByRole('navigation', { name: 'Разделы профиля' })
    expect(within(nav).getAllByRole('button').map((button) => button.textContent)).toEqual(['Обзор', 'Измерения', 'Фото', 'Ограничения'])
    expect(screen.queryByText('Основная информация')).not.toBeInTheDocument()
    expect(screen.queryByText('Краткая сводка')).not.toBeInTheDocument()
  })

  it('persists edited profile data through the backend', async () => {
    const actor = userEvent.setup()
    renderProfile()
    await actor.click(await screen.findByRole('button', { name: 'Редактировать' }))
    const dialog = screen.getByRole('dialog', { name: 'Редактировать профиль' })
    await actor.clear(within(dialog).getByLabelText('Вес, кг'))
    await actor.type(within(dialog).getByLabelText('Вес, кг'), '83.4')
    await actor.clear(within(dialog).getByLabelText('Основная цель'))
    await actor.type(within(dialog).getByLabelText('Основная цель'), 'Присед 140 кг')
    await actor.click(within(dialog).getByRole('button', { name: 'Сохранить', exact: true }))
    expect(apiPut).toHaveBeenCalledWith('/api/users/alexey/profile', expect.objectContaining({ name: 'Алексей', weightKg: 83.4, goalLabel: 'Присед 140 кг', targetValue: 100 }))
  })

  it('adds measurements through the real endpoint', async () => {
    const actor = userEvent.setup()
    renderProfile('/profile?tab=measurements')
    await actor.click(await screen.findByRole('button', { name: 'Добавить измерение' }))
    const dialog = screen.getByRole('dialog', { name: 'Новое измерение' })
    await actor.type(within(dialog).getByLabelText('Вес, кг'), '83')
    await actor.type(within(dialog).getByLabelText('Талия, см'), '90')
    await actor.click(within(dialog).getByRole('button', { name: 'Сохранить измерение' }))
    expect(apiPost).toHaveBeenCalledWith('/api/body-measurements', expect.objectContaining({ userId: 'alexey', weightKg: 83, waistCm: 90 }))
  })

  it('shows Russian exercise cards instead of blacklist slugs', async () => {
    renderProfile('/profile?tab=restrictions')
    const heading = await screen.findByRole('heading', { name: 'Исключённые упражнения' })
    const panel = heading.closest('section')!
    expect(within(panel).getByText('Жим лёжа в тренажёре Смита')).toBeVisible()
    expect(within(panel).queryByText('smith-machine-bench-press')).not.toBeInTheDocument()
    expect(within(panel).getByRole('button', { name: /Жим лёжа в тренажёре Смита/ })).toHaveAttribute('aria-pressed', 'true')
  })

  it('opens photo capture as a modal without changing route', async () => {
    const actor = userEvent.setup()
    renderProfile('/profile?tab=photo')
    await actor.click(await screen.findByRole('button', { name: 'Фотофиксация' }))
    expect(screen.getByRole('dialog', { name: 'Фотофиксация' })).toBeVisible()
  })
})
