import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getExerciseCatalog, getExerciseDetails, getWorkoutCalendarData } from '@/mocks/stage2-data'
import { machineScenarios } from '@/mocks/data'
import { ExerciseCatalogScreen } from '@/screens/catalog/exercise-catalog-screen'
import { WorkoutCalendarScreen } from '@/screens/calendar/workout-calendar-screen'
import { apiGet } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'

vi.mock('@/shared/api/client', async () => ({
  ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'),
  apiGet: vi.fn(),
}))

let client: QueryClient
beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
  vi.mocked(apiGet).mockReset()
  vi.mocked(apiGet).mockImplementation(async <T,>(path: string): Promise<T> => {
    if (path.startsWith('/api/calendar?')) return getWorkoutCalendarData() as T
    if (path.startsWith('/api/exercises/')) return { ...getExerciseDetails('barbell-floor-press'), videos: [] } as T
    if (path.startsWith('/api/exercises?')) {
      const catalog = getExerciseCatalog()
      return { ...catalog, items: [], total: 0 } as T
    }
    if (path.startsWith('/api/machine/status')) return machineScenarios.ready as T
    throw new Error(`Unexpected request ${path}`)
  })
})

afterEach(() => { cleanup(); client.clear() })

describe('Stage 1 discovery transitions', () => {
  it('offers a back-to-top button only after the catalog is scrolled', () => {
    sessionStorage.removeItem('egym-catalog-position')
    render(<QueryClientProvider client={client}><MemoryRouter><ExerciseCatalogScreen /></MemoryRouter></QueryClientProvider>)
    const main = document.querySelector<HTMLElement>('.forma-main')!
    main.scrollTo = vi.fn(({ top }: ScrollToOptions) => {
      main.scrollTop = top ?? 0
      fireEvent.scroll(main)
    })

    expect(screen.queryByRole('button', { name: 'Наверх' })).not.toBeInTheDocument()
    main.scrollTop = 500
    fireEvent.scroll(main)
    fireEvent.click(screen.getByRole('button', { name: 'Наверх' }))

    expect(main.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' })
    expect(screen.queryByRole('button', { name: 'Наверх' })).not.toBeInTheDocument()
  })

  it('keeps the catalog and scroll position while updating favorites', async () => {
    const user = userEvent.setup()
    const catalog = getExerciseCatalog()
    useAppStore.setState({ favoriteExerciseSlugs: [] })
    vi.mocked(apiGet).mockImplementation(async <T,>(path: string): Promise<T> => {
      if (path.startsWith('/api/exercises?')) {
        if (!path.includes('favorites=&')) return new Promise<T>(() => {})
        return { ...catalog, items: catalog.items.slice(0, 48), total: 48 } as T
      }
      if (path.startsWith('/api/machine/status')) return machineScenarios.ready as T
      throw new Error(`Unexpected request ${path}`)
    })

    render(<QueryClientProvider client={client}><MemoryRouter><ExerciseCatalogScreen /></MemoryRouter></QueryClientProvider>)
    const card = await screen.findByRole('article', { name: catalog.items[0].name })
    const main = document.querySelector<HTMLElement>('.forma-main')!
    main.scrollTop = 600

    await user.click(within(card).getByRole('button', { name: `Добавить в избранное: ${catalog.items[0].name}` }))
    await vi.waitFor(() => expect(vi.mocked(apiGet).mock.calls.some(([path]) => path.includes(`favorites=${catalog.items[0].slug}`))).toBe(true))
    expect(main.scrollTop).toBe(600)
    expect(screen.getByRole('article', { name: catalog.items[0].name })).toBeInTheDocument()
  })

  it('starts a standalone exercise from its catalog card without quick-start or photos', async () => {
    const user = userEvent.setup()
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/catalog?selected=barbell-floor-press']}>
          <Routes>
            <Route path="/catalog" element={<ExerciseCatalogScreen />} />
            <Route path="/exercise-setup" element={<div>Настройка упражнения</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByRole('dialog')).toBeVisible()
    expect(screen.queryByRole('button', { name: 'Открыть быстрый старт' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Начать упражнение', exact: true }))
    expect(screen.getByText('Настройка упражнения')).toBeVisible()
  })

  it('has no workout launch, planning or legacy plan actions in the calendar', async () => {
    render(<QueryClientProvider client={client}><MemoryRouter><WorkoutCalendarScreen /></MemoryRouter></QueryClientProvider>)
    expect(await screen.findByRole('grid', { name: /Выполненные тренировки/ })).toBeVisible()
    expect(screen.queryByRole('button', { name: /Начать тренировку|Добавить тренировку|Открыть план|Перенести|Назначить|Неделя|Месяц/ })).not.toBeInTheDocument()
    expect(screen.queryByText('Быстрые действия')).not.toBeInTheDocument()
  })
})