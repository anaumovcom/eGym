import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { StrictMode, type PropsWithChildren } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppProviders } from '@/app/providers'
import { getExerciseCatalog } from '@/mocks/stage2-data'
import { apiGet } from '@/shared/api/client'
import { ExercisePickerModal } from '@/shared/ui/training/exercise-picker-modal'
import { useAppStore } from '@/stores/app-store'
import { exerciseCatalogOptions, filterExerciseCatalog, useExerciseCatalog } from './catalog'

vi.mock('@/features/hardware/lib/hardware-realtime-provider', () => ({ HardwareRealtimeProvider: () => null }))
vi.mock('@/shared/api/client', async () => ({
  ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'),
  apiGet: vi.fn(), apiPost: vi.fn().mockResolvedValue({}),
}))

const originalState = useAppStore.getState()
let client: QueryClient
const catalog = getExerciseCatalog()
const wrapper = ({ children }: PropsWithChildren) => <QueryClientProvider client={client}>{children}</QueryClientProvider>

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  useAppStore.setState({ selectedUserId: 'alexey', favoriteExerciseSlugs: [], blacklistedExerciseSlugs: [] })
  vi.mocked(apiGet).mockReset().mockResolvedValue(catalog)
})
afterEach(() => { cleanup(); client.clear(); useAppStore.setState(originalState) })

describe('shared exercise catalog', () => {
  it('loads on application startup, including StrictMode remounts', async () => {
    render(<StrictMode><AppProviders><div>Application</div></AppProviders></StrictMode>)
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(1))
    expect(apiGet).toHaveBeenCalledWith('/api/exercises?userId=alexey&favorites=&blacklist=')
  })

  it('reuses the startup fetch across consumers, searches, filters and reopening', async () => {
    await client.prefetchQuery(exerciseCatalogOptions('alexey'))
    const first = renderHook(({ search, muscles }) => useExerciseCatalog('alexey', { search, muscles }), {
      wrapper, initialProps: { search: '', muscles: [] as string[] },
    })
    renderHook(() => useExerciseCatalog('alexey'), { wrapper })
    first.rerender({ search: catalog.items[0].name.toUpperCase(), muscles: [] })
    expect(first.result.current.data?.items.map((item) => item.slug)).toContain(catalog.items[0].slug)
    first.rerender({ search: '', muscles: catalog.items[0].muscles })
    expect(first.result.current.data?.items.every((item) => item.muscles.some((muscle) => catalog.items[0].muscles.includes(muscle)))).toBe(true)
    first.unmount()
    renderHook(() => useExerciseCatalog('alexey'), { wrapper })
    expect(apiGet).toHaveBeenCalledTimes(1)
  })

  it('deduplicates concurrent requests and separates user catalogs', async () => {
    const first = renderHook(({ userId }) => useExerciseCatalog(userId), { wrapper, initialProps: { userId: 'alexey' } })
    renderHook(() => useExerciseCatalog('alexey'), { wrapper })
    await waitFor(() => expect(first.result.current.data).toBeDefined())
    expect(apiGet).toHaveBeenCalledTimes(1)
    first.rerender({ userId: 'elena' })
    await waitFor(() => expect(apiGet).toHaveBeenCalledTimes(2))
    expect(apiGet).toHaveBeenLastCalledWith('/api/exercises?userId=elena&favorites=&blacklist=')
    first.rerender({ userId: 'alexey' })
    expect(apiGet).toHaveBeenCalledTimes(2)
  })

  it('updates favorites and exclusions locally without mutating the cache', async () => {
    const { result } = renderHook(() => useExerciseCatalog('alexey'), { wrapper })
    await waitFor(() => expect(result.current.data).toBeDefined())
    const slug = catalog.items[0].slug
    act(() => useAppStore.getState().toggleFavoriteExercise(slug))
    expect(result.current.data?.items[0].favorite).toBe(true)
    act(() => useAppStore.getState().toggleBlacklistedExercise(slug))
    expect(result.current.data?.items[0]).toMatchObject({ favorite: false, blacklisted: true, compatibilityTone: 'blocked', recommended: false })
    act(() => useAppStore.getState().toggleBlacklistedExercise(slug))
    expect(result.current.data?.items[0].compatibilityTone).toBe(catalog.items[0].compatibilityTone)
    expect(client.getQueryData(exerciseCatalogOptions('alexey').queryKey)).toBe(catalog)
    expect(apiGet).toHaveBeenCalledTimes(1)
  })

  it('combines filters with OR within groups and AND between groups', () => {
    const item = catalog.items[0]
    const result = filterExerciseCatalog(catalog, {
      search: `  ${item.secondaryName.toUpperCase()}  `,
      muscles: ['missing-muscle', ...item.muscles], equipment: [item.equipment],
      difficulty: [item.difficulty], force: [item.force], mechanic: [item.mechanic], grips: [item.grips],
    })
    expect(result.items).toContain(item)
    expect(result.total).toBe(result.items.length)
    expect(result.availableFilters).toBe(catalog.availableFilters)
    expect(filterExerciseCatalog(catalog, { equipment: ['missing-equipment'] }).total).toBe(0)
  })

  it('shows all muscles and equipment in the picker and filters immediately from cache', async () => {
    const user = userEvent.setup()
    const muscles = Array.from({ length: 15 }, (_, index) => `Мышца ${index + 1}`)
    const equipment = Array.from({ length: 12 }, (_, index) => `Оборудование ${index + 1}`)
    const item = { ...catalog.items[0], muscles: [muscles[14]], equipment: equipment[11], previewVideoUrl: undefined }
    client.setQueryData(exerciseCatalogOptions('alexey').queryKey, {
      ...catalog, items: [item], availableFilters: { ...catalog.availableFilters, muscles, equipment },
    })
    render(<ExercisePickerModal open onOpenChange={vi.fn()} userId="alexey" mode="add" onSelect={vi.fn()} />, { wrapper })
    const filterButtons = screen.getAllByRole('button').filter((button) => button.classList.contains('discovery-option'))
    const filterLabels = filterButtons.map((button) => button.textContent)
    for (const name of [...muscles, ...equipment]) expect(filterLabels).toContain(name)
    expect(filterButtons[0].closest('details')?.querySelector('summary')).toHaveTextContent('Оборудование')
    expect(filterButtons[0].closest('.discovery-option-group')?.querySelector('h3')).toHaveTextContent('Тренажёры и инвентарь')
    await user.click(screen.getByRole('button', { name: muscles[14], exact: true }))
    expect(screen.getByRole('button', { name: muscles[14], exact: true })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: `Выбрать ${item.name}` })).toBeVisible()
    fireEvent.change(screen.getByPlaceholderText('Найти упражнение...'), { target: { value: 'нет такого упражнения' } })
    expect(screen.getByText('По текущему запросу упражнений не найдено.')).toBeVisible()
    expect(screen.getByRole('button', { name: muscles[0], exact: true })).toBeVisible()
    expect(apiGet).not.toHaveBeenCalled()
  })

  it('renders large picker catalogs incrementally without limiting search', async () => {
    const user = userEvent.setup()
    const items = Array.from({ length: 50 }, (_, index) => ({
      ...catalog.items[0], slug: `exercise-${index}`, name: `Упражнение ${index}`, previewVideoUrl: undefined,
    }))
    client.setQueryData(exerciseCatalogOptions('alexey').queryKey, { ...catalog, items, total: items.length })
    const view = render(<ExercisePickerModal open onOpenChange={vi.fn()} userId="alexey" mode="add" onSelect={vi.fn()} />, { wrapper })
    expect(view.baseElement.querySelectorAll('.picker-item')).toHaveLength(24)
    await user.click(screen.getByRole('button', { name: 'Показать ещё' }))
    expect(view.baseElement.querySelectorAll('.picker-item')).toHaveLength(48)
    fireEvent.change(screen.getByPlaceholderText('Найти упражнение...'), { target: { value: 'Упражнение 49' } })
    expect(screen.getByRole('button', { name: 'Выбрать Упражнение 49' })).toBeVisible()
    expect(view.baseElement.querySelectorAll('.picker-item')).toHaveLength(1)
    expect(apiGet).not.toHaveBeenCalled()
  })

  it('offers grouped filters immediately while the catalog is still loading', () => {
    vi.mocked(apiGet).mockImplementation(() => new Promise(() => {}))
    render(<ExercisePickerModal open onOpenChange={vi.fn()} userId="alexey" mode="add" onSelect={vi.fn()} />, { wrapper })
    expect(screen.getByRole('dialog')).toHaveClass('picker-fullscreen-root')
    expect(screen.getByRole('button', { name: 'Низ спины', exact: true })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Тазобедренные мышцы', exact: true })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Гантели', exact: true })).toBeVisible()
    expect(screen.getByRole('heading', { name: 'Свободные веса' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Избранное 0', exact: true })).toBeVisible()
  })

  it('filters favorites locally and updates the result when a star is toggled', async () => {
    const user = userEvent.setup()
    const items = catalog.items.slice(0, 2).map((item) => ({ ...item, previewVideoUrl: undefined }))
    client.setQueryData(exerciseCatalogOptions('alexey').queryKey, { ...catalog, items, total: 2 })
    useAppStore.setState({ favoriteExerciseSlugs: [items[0].slug] })
    render(<ExercisePickerModal open onOpenChange={vi.fn()} userId="alexey" mode="add" onSelect={vi.fn()} />, { wrapper })
    await user.click(screen.getByRole('button', { name: 'Избранное 1' }))
    expect(screen.getByRole('button', { name: `Выбрать ${items[0].name}` })).toBeVisible()
    expect(screen.queryByRole('button', { name: `Выбрать ${items[1].name}` })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: `Убрать из избранного: ${items[0].name}` }))
    expect(screen.getByText('В избранном пока пусто')).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Все упражнения', exact: true, pressed: false }))
    expect(screen.getByRole('button', { name: `Выбрать ${items[1].name}` })).toBeVisible()
    expect(apiGet).not.toHaveBeenCalled()
  })
})