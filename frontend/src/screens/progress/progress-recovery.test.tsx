import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { FatigueData, ProgressData } from '@/entities/stage4/model/types'
import { buildFatigueData, buildProgressData, defaultStage4DevFlags, getProfileSeed } from '@/mocks/stage4-data'
import { FatigueScreen } from '@/screens/fatigue/fatigue-screen'
import { ProgressScreen } from '@/screens/progress/progress-screen'
import { apiGet } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'

vi.mock('@/shared/api/client', async () => ({ ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'), apiGet: vi.fn() }))
let client: QueryClient
let progress: ProgressData
let fatigue: FatigueData

function Probe() { const location = useLocation(); return <output data-testid="location">{location.pathname}{location.search}</output> }
function renderScreen(path = '/progress') { return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Probe /><Routes><Route path="/progress" element={<ProgressScreen />} /><Route path="/fatigue" element={<FatigueScreen />} /><Route path="/dashboard" element={<div>Главная</div>} /><Route path="/profile" element={<div>Профиль</div>} /></Routes></MemoryRouter></QueryClientProvider>) }
function location() { return screen.getByTestId('location').textContent }

beforeEach(() => {
  useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  progress = buildProgressData({ user: getProfileSeed('alexey'), period: '30d', blacklistedSlugs: [], dev: defaultStage4DevFlags })
  fatigue = buildFatigueData({ dev: defaultStage4DevFlags })
  vi.mocked(apiGet).mockReset().mockImplementation(async <T,>(path: string): Promise<T> => {
    if (path.startsWith('/api/progress?')) return progress as T
    if (path.startsWith('/api/fatigue?')) return fatigue as T
    if (path.startsWith('/api/photo-progress?')) return { photos: [] } as T
    throw new Error(`Unexpected ${path}`)
  })
  vi.stubGlobal('fetch', vi.fn(async () => new Response('<svg xmlns="http://www.w3.org/2000/svg"><g id="chest"><path d="M0 0h10v10z" /></g></svg>', { status: 200 })))
})
afterEach(() => { cleanup(); client.clear(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

const tabNames = ['Обзор', 'Сила', 'Тело', 'Фото']

describe('Progress stage 6', () => {
  it('shows four tabs, one period switch and no more than four overview metrics', async () => {
    renderScreen('/progress?period=30d')
    expect(await screen.findByRole('heading', { name: 'Прогресс' })).toBeVisible()
    expect(await screen.findByText('Динамика объёма')).toBeVisible()
    for (const tab of tabNames) expect(screen.getByRole('button', { name: tab, exact: true })).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Восстановление' })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Усталость мышц' })).toHaveAttribute('href', '/fatigue')
    const periods = screen.getByRole('group', { name: 'Период прогресса' })
    expect(within(periods).getByRole('button', { name: '30 дней' })).toHaveAttribute('aria-pressed', 'true')
    expect(document.querySelectorAll('.progress-metrics article')).toHaveLength(4)
    for (const removed of ['Сводка', 'Упражнения', 'Сила и объём', 'Регулярность', 'Мышцы', 'Фото прогресса']) expect(screen.queryByRole('button', { name: removed, exact: true })).not.toBeInTheDocument()
  })

  it('keeps legacy analytics links useful by mapping them to strength', async () => {
    renderScreen('/progress?tab=exercise&period=3m&exercise=machine-pulldown')
    expect(await screen.findByRole('heading', { name: 'Тяга сверху', level: 2 })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Сила' })).toHaveAttribute('aria-current', 'page')
    expect(apiGet).toHaveBeenCalledWith('/api/progress?userId=alexey&period=3m')
  })

  it('changes period with one switch and preserves the current tab', async () => {
    const user = userEvent.setup()
    renderScreen('/progress?tab=strength&period=30d')
    await screen.findByRole('heading', { name: 'Тяга сверху', level: 2 })
    await user.click(screen.getByRole('button', { name: '7 дней' }))
    await waitFor(() => expect(apiGet).toHaveBeenCalledWith('/api/progress?userId=alexey&period=7d'))
    expect(location()).toContain('tab=strength')
    expect(location()).toContain('period=7d')
  })

  it('redirects old recovery links to the standalone page without requesting analytics', async () => {
    renderScreen('/progress?tab=recovery&mode=7d&muscle=chest')
    expect(await screen.findByRole('heading', { name: 'Карта мышечной усталости' })).toBeVisible()
    expect(location()).toBe('/fatigue?mode=7d&muscle=chest')
    expect(apiGet).toHaveBeenCalledWith('/api/fatigue?userId=alexey&mode=7d')
    expect(apiGet).not.toHaveBeenCalledWith(expect.stringMatching(/^\/api\/progress\?/))
    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: 'Аварийная остановка', exact: true })).toHaveLength(1)
    expect(document.querySelector('.fatigue-hero')).toContainElement(screen.getByRole('heading', { name: 'Карта мышечной усталости' }))
    expect(document.querySelector('.fatigue-details')).toContainElement(screen.getByText('Рекомендация Forma'))
  })

  it('opens progress from the separate muscle fatigue page', async () => {
    const user = userEvent.setup()
    renderScreen('/fatigue?mode=current')
    await screen.findByRole('heading', { name: 'Карта мышечной усталости' })
    await user.click(screen.getByRole('link', { name: 'Прогресс' }))
    expect(await screen.findByText('Динамика объёма')).toBeVisible()
    expect(location()).toBe('/progress')
  })

  it('shows muscle fatigue on hover and hides the hint when the pointer leaves', async () => {
    renderScreen('/fatigue')
    const chest = await screen.findByRole('button', { name: /Грудь: .* из 100/ })
    fireEvent.pointerEnter(chest, { pointerType: 'mouse', clientX: 100, clientY: 100 })
    expect(screen.getByRole('tooltip')).toHaveTextContent('Грудь')
    expect(screen.getByRole('tooltip')).toHaveTextContent('Высокая усталость')
    expect(screen.getByRole('tooltip')).toHaveTextContent('балл. усталости')
    expect(location()).toBe('/fatigue')
    expect(chest).toBeInTheDocument()
    fireEvent.pointerLeave(screen.getByText('Вид спереди').parentElement!)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()

  })

  it('shows missing fatigue data on hover', async () => {
    fatigue = { ...fatigue, muscles: fatigue.muscles.map((muscle) => muscle.id === 'chest' ? { ...muscle, status: 'no_data' } : muscle) }
    renderScreen('/fatigue')
    const chest = await screen.findByRole('button', { name: /Грудь: .* из 100/ })
    fireEvent.pointerEnter(chest, { pointerType: 'mouse', clientX: 100, clientY: 100 })
    expect(screen.getByRole('tooltip')).toHaveTextContent('Нет сохранённых данных о нагрузке')
    fireEvent.pointerLeave(screen.getByText('Вид спереди').parentElement!)
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()
  })

  it('summarises the period with comparisons, insights, records and muscle balance', async () => {
    renderScreen('/progress')
    const days = await screen.findByText('Тренировочных дней')
    const card = days.closest('article')!
    expect(within(card).getByText('+33%')).toBeVisible()
    expect(within(card).getByText('было 6')).toBeVisible()
    expect(screen.getByRole('link', { name: /Присед: \+20%/ })).toHaveAttribute('href', '/progress?tab=strength&exercise=barbell-heels-up-back-squat')
    expect(screen.getByText('Личные рекорды')).toBeVisible()
    expect(screen.getByText('Баланс нагрузки')).toBeVisible()
    expect(screen.getByRole('link', { name: /Карта усталости/ })).toHaveAttribute('href', '/fatigue')
    expect(screen.getByText('Регулярность')).toBeVisible()
  })

  it('switches exercises locally and shows the next-session target', async () => {
    const user = userEvent.setup()
    renderScreen('/progress?tab=strength')
    expect(await screen.findByRole('heading', { name: 'Тяга сверху', level: 2 })).toBeVisible()
    expect(screen.getByText('Цель на следующую тренировку')).toBeVisible()
    expect(screen.getByRole('table')).toBeVisible()
    const calls = vi.mocked(apiGet).mock.calls.length
    await user.click(screen.getByRole('button', { name: /Присед/ }))
    expect(await screen.findByRole('heading', { name: 'Присед', level: 2 })).toBeVisible()
    expect(location()).toContain('exercise=barbell-heels-up-back-squat')
    expect(vi.mocked(apiGet).mock.calls.length).toBe(calls)
    await user.click(screen.getByRole('button', { name: 'Вес' }))
    expect(screen.getByRole('button', { name: 'Вес' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('renders one actionable empty state instead of zero metric tiles', async () => {
    progress = buildProgressData({ user: getProfileSeed('guest'), period: '30d', blacklistedSlugs: [], dev: { ...defaultStage4DevFlags, noHistory: true, noPhotos: true } })
    renderScreen()
    expect(await screen.findByRole('heading', { name: /Недостаточно данных/ })).toBeVisible()
    expect(screen.getByRole('link', { name: 'Завершить тренировку' })).toHaveAttribute('href', '/dashboard')
    expect(document.querySelectorAll('.progress-metrics article')).toHaveLength(0)
  })

  it('shows the photo gallery with three views and retains profile management', async () => {
    const user = userEvent.setup()
    vi.mocked(apiGet).mockImplementation(async <T,>(path: string): Promise<T> => {
      if (path.startsWith('/api/progress?')) return progress as T
      if (path.startsWith('/api/photo-progress?')) return { photos: [{ id: 1, view: 'front', takenAt: '2026-09-15T08:00:00Z', thumbnailUrl: '/media/front.jpg' }] } as T
      throw new Error(`Unexpected ${path}`)
    })
    renderScreen('/progress?tab=photo')
    expect(await screen.findByText('Последняя съёмка')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Управление снимками' })).toHaveAttribute('href', '/profile?tab=photo')
    expect(document.querySelectorAll('.photo-gallery-card')).toHaveLength(3)
    expect(screen.queryByRole('group', { name: 'Период прогресса' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Фотофиксация' })).toBeVisible()
    expect(screen.queryByText('История фотофиксаций')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Фотофиксация' }))
    expect(screen.getByRole('dialog', { name: 'Фотофиксация' })).toBeVisible()
  })
})
