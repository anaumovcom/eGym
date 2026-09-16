import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getWorkoutCalendarData } from '@/mocks/stage2-data'
import { formatDayTitle, shiftMonth, WorkoutCalendarScreen } from '@/screens/calendar/workout-calendar-screen'
import { apiGet } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'

vi.mock('@/shared/api/client', async () => ({
  ...await vi.importActual<typeof import('@/shared/api/client')>('@/shared/api/client'),
  apiGet: vi.fn(),
}))

const fetchMock = vi.fn().mockRejectedValue(new Error('Real network is forbidden in calendar tests'))
let client: QueryClient

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function renderCalendar(entry = '/calendar') {
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes><Route path="/calendar" element={<><WorkoutCalendarScreen /><LocationProbe /></>} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.stubGlobal('fetch', fetchMock)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
  vi.mocked(apiGet).mockReset().mockImplementation(async <T,>(path: string): Promise<T> => {
    const url = new URL(path, 'http://localhost')
    if (url.pathname === '/api/calendar') return getWorkoutCalendarData(url.searchParams.get('month') ?? undefined) as T
    throw new Error(`Unexpected request ${path}`)
  })
})

afterEach(() => {
  cleanup()
  client.clear()
  vi.unstubAllGlobals()
  expect(fetchMock).not.toHaveBeenCalled()
})

describe('shiftMonth / formatDayTitle', () => {
  it('moves across year boundaries and formats Russian dates', () => {
    expect(shiftMonth('2026-01', -1)).toBe('2025-12')
    expect(shiftMonth('2026-12', 1)).toBe('2027-01')
    expect(formatDayTitle('2026-05-14')).toMatch(/^Четверг, 14 мая 2026 г\./)
  })
})

describe('WorkoutCalendarScreen', () => {
  it('renders the full month grid with weekdays, today and completed marks only', async () => {
    renderCalendar()
    const grid = await screen.findByRole('grid', { name: 'Выполненные тренировки: Май 2026' })
    expect(screen.getByRole('heading', { level: 1, name: 'Май 2026' })).toBeVisible()
    expect(within(grid).getAllByRole('row')).toHaveLength(6)
    const cells = within(grid).getAllByRole('gridcell')
    expect(cells).toHaveLength(42)
    expect(cells[0]).toHaveAttribute('aria-label', expect.stringMatching(/27 апреля 2026/))
    expect(cells[0]).toHaveAttribute('data-in-month', 'false')
    const today = cells.find((cell) => cell.dataset.today === 'true')!
    expect(today).toHaveTextContent(/14сегодня/)
    expect(within(today).getByRole('button', { name: /14 мая 2026 г\., 2 тренировки/ })).toBeVisible()
    expect(within(today).getByText('×2')).toBeVisible()
    const empty = cells.find((cell) => cell.getAttribute('aria-label')?.startsWith('Пятница, 15 мая'))!
    expect(within(empty).queryByRole('button')).not.toBeInTheDocument()
    expect(empty).toHaveTextContent('15')
    expect(vi.mocked(apiGet)).toHaveBeenCalledWith('/api/calendar?userId=alexey')
    expect(screen.queryByText(/Запланировано|Пропущено|Отдых|Неделя|Быстрые действия|Баланс/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Начать|Добавить|Изменить план|Убрать|Назначить/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Сегодня', exact: true })).toBeDisabled()
    expect(screen.getByText('6 тренировок за месяц')).toBeVisible()
  })

  it('opens a read-only day dialog with every workout, restores focus and never touches runtime', async () => {
    const user = userEvent.setup()
    const runtimeBefore = useRuntimeStore.getState()
    renderCalendar()
    const trigger = await screen.findByRole('button', { name: /14 мая 2026 г\., 2 тренировки/ })
    await user.click(trigger)
    const dialog = screen.getByRole('dialog', { name: /Четверг, 14 мая 2026 г\./ })
    expect(dialog).toBeVisible()
    expect(within(dialog).getByText(/2 тренировки · только просмотр/)).toBeVisible()
    const records = within(dialog).getAllByRole('article')
    expect(records.map((record) => record.getAttribute('aria-label'))).toEqual(['Фуллбоди', 'Ноги + кор'])
    expect(within(records[0]).getByText('07:10–07:40')).toBeVisible()
    expect(within(records[0]).getByText('Выполнена')).toBeVisible()
    expect(within(records[1]).getByText('1 850 кг')).toBeVisible()
    expect(within(records[1]).getByText('3 подх. · 30 повт. · до 50 кг')).toBeVisible()
    expect(within(dialog).getByRole('button', { name: 'Аварийная остановка', exact: true })).toBeVisible()
    expect(within(dialog).queryByRole('button', { name: /Начать|Изменить|Убрать|Удалить|Повторить/ })).not.toBeInTheDocument()
    expect(within(dialog).queryByRole('link')).not.toBeInTheDocument()
    await user.click(within(dialog).getByRole('button', { name: 'Закрыть', exact: true }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(trigger).toHaveFocus()
    expect(useRuntimeStore.getState()).toBe(runtimeBefore)
    expect(screen.getByTestId('location')).toHaveTextContent('/calendar')
  })

  it('navigates months through the URL and returns to the current month', async () => {
    const user = userEvent.setup()
    renderCalendar('/calendar?month=2026-07')
    expect(await screen.findByRole('heading', { level: 1, name: 'Июль 2026' })).toBeVisible()
    expect(vi.mocked(apiGet)).toHaveBeenCalledWith('/api/calendar?userId=alexey&month=2026-07')
    expect(screen.getByText('В этом месяце нет завершённых тренировок')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Сегодня', exact: true })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: 'Предыдущий месяц' }))
    expect(screen.getByTestId('location')).toHaveTextContent('/calendar?month=2026-06')
    expect(await screen.findByRole('heading', { level: 1, name: 'Июнь 2026' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Следующий месяц' }))
    await user.click(screen.getByRole('button', { name: 'Следующий месяц' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Август 2026' })).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Сегодня', exact: true }))
    expect(screen.getByTestId('location')).toHaveTextContent(/^\/calendar$/)
    expect(await screen.findByRole('heading', { level: 1, name: 'Май 2026' })).toBeVisible()
  })

  it('ignores legacy week/day parameters and malformed months', async () => {
    renderCalendar('/calendar?mode=week&selectedDayId=2026-05-14&month=2026-13')
    expect(await screen.findByRole('heading', { level: 1, name: 'Май 2026' })).toBeVisible()
    expect(vi.mocked(apiGet)).toHaveBeenCalledWith('/api/calendar?userId=alexey')
  })

  it('shows an error state with retry', async () => {
    const user = userEvent.setup()
    vi.mocked(apiGet).mockRejectedValueOnce(new Error('offline'))
    renderCalendar()
    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось загрузить календарь тренировок.')
    await user.click(screen.getByRole('button', { name: 'Повторить' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Май 2026' })).toBeVisible()
  })
})
