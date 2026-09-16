import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useEffect } from 'react'
import { Link, MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ServiceAccessGate, SettingsLayout } from '@/shared/ui/layout/service-access'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'

const originalAppState = useAppStore.getState()
const originalHardwareState = useHardwareStore.getState()
const mountProtected = vi.fn()
const unmountProtected = vi.fn()
const runCommand = vi.fn().mockResolvedValue({})
let queryClient: QueryClient

function ProtectedScreen() {
  useEffect(() => {
    mountProtected()
    return () => { unmountProtected() }
  }, [])
  return <h2>Закрытые технические настройки</h2>
}

function LocationProbe() {
  const location = useLocation()
  const navigate = useNavigate()
  return (
    <>
      <output data-testid="location">{location.pathname}{location.search}</output>
      <Link to="/dashboard">Выйти из настроек</Link>
      <Link to="/settings/service/modbus">Вернуться в сервис</Link>
      <button onClick={() => navigate(-1)}>Назад по истории</button>
    </>
  )
}

function renderGate(initialEntry = '/settings/service/modbus') {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <LocationProbe />
        <Routes>
          <Route path="/settings" element={<SettingsLayout />}>
            <Route index element={<h2>Обзор настроек</h2>} />
            <Route path="service/modbus" element={<ServiceAccessGate><ProtectedScreen /></ServiceAccessGate>} />
          </Route>
          <Route path="/dashboard" element={<h2>Главная страница</h2>} />
          <Route path="/without-layout" element={<ServiceAccessGate><ProtectedScreen /></ServiceAccessGate>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function confirmAccess(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('checkbox', { name: 'Понимаю риски изменения технических настроек' }))
  await user.click(screen.getByRole('button', { name: 'Открыть сервисный раздел' }))
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  useAppStore.setState({ selectedUserId: 'alexey', emergencyStopActive: false })
  useHardwareStore.setState({ snapshot: null, settings: null, errorMessage: null, runCommand })
  mountProtected.mockClear()
  unmountProtected.mockClear()
  runCommand.mockClear()
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})

afterEach(() => {
  cleanup()
  queryClient.clear()
  useAppStore.setState(originalAppState, true)
  useHardwareStore.setState(originalHardwareState, true)
  vi.restoreAllMocks()
})

describe('ServiceAccessGate and SettingsLayout', () => {
  it('does not mount children at a direct URL until both acknowledgement and explicit confirmation', async () => {
    const user = userEvent.setup()
    renderGate('/settings/service/modbus?tab=control&unlocked=true&serviceMode=true&pin=1234')

    expect(screen.getByRole('heading', { name: 'Сервисный раздел' })).toBeVisible()
    expect(screen.getByText(/а не авторизация backend или проверка PIN/)).toBeVisible()
    expect(screen.queryByText('Закрытые технические настройки')).not.toBeInTheDocument()
    expect(mountProtected).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Открыть сервисный раздел' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Открыть сервисный раздел' }))
    expect(mountProtected).not.toHaveBeenCalled()

    await user.click(screen.getByRole('checkbox'))
    expect(mountProtected).not.toHaveBeenCalled()
    expect(runCommand).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Открыть сервисный раздел' }))

    expect(screen.getByText('Закрытые технические настройки')).toBeVisible()
    expect(mountProtected).toHaveBeenCalledTimes(1)
    expect(runCommand).not.toHaveBeenCalled()
    expect(screen.getByTestId('location')).toHaveTextContent('/settings/service/modbus?tab=control&unlocked=true&serviceMode=true&pin=1234')
  })

  it('cancels to overview without mounting children or issuing hardware commands', async () => {
    const user = userEvent.setup()
    renderGate()
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('link', { name: 'Отмена — к настройкам' }))

    expect(screen.getByTestId('location')).toHaveTextContent('/settings?tab=overview')
    expect(screen.getByText('Обзор настроек')).toBeVisible()
    expect(mountProtected).not.toHaveBeenCalled()
    expect(runCommand).not.toHaveBeenCalled()

    await user.click(screen.getByRole('link', { name: 'Вернуться в сервис' }))
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'Открыть сервисный раздел' })).toBeDisabled()
  })

  it('fails closed without SettingsLayout even after checking the warning', async () => {
    const user = userEvent.setup()
    renderGate('/without-layout')
    await user.click(screen.getByRole('checkbox'))
    expect(screen.getByRole('button', { name: 'Открыть сервисный раздел' })).toBeDisabled()
    expect(mountProtected).not.toHaveBeenCalled()
    expect(runCommand).not.toHaveBeenCalled()
  })

  it('clears access on leaving settings and browser-history return', async () => {
    const user = userEvent.setup()
    renderGate()
    await confirmAccess(user)
    await user.click(screen.getByRole('link', { name: 'Выйти из настроек' }))
    expect(screen.getByText('Главная страница')).toBeVisible()
    expect(unmountProtected).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('button', { name: 'Назад по истории' }))
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(screen.queryByText('Закрытые технические настройки')).not.toBeInTheDocument()
    expect(mountProtected).toHaveBeenCalledTimes(1)
    expect(runCommand).not.toHaveBeenCalled()
  })

  it.each(['elena', 'guest', null])('clears access on change to %s and does not restore it for the previous user', async (nextUserId) => {
    const user = userEvent.setup()
    renderGate()
    await confirmAccess(user)

    act(() => { useAppStore.setState({ selectedUserId: nextUserId }) })
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(screen.queryByText('Закрытые технические настройки')).not.toBeInTheDocument()
    expect(unmountProtected).toHaveBeenCalledTimes(1)

    await confirmAccess(user)
    act(() => { useAppStore.setState({ selectedUserId: 'alexey' }) })
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(screen.queryByText('Закрытые технические настройки')).not.toBeInTheDocument()
    expect(runCommand).not.toHaveBeenCalled()
  })

  it('clears an unconfirmed checkbox when the user changes', async () => {
    const user = userEvent.setup()
    renderGate()
    await user.click(screen.getByRole('checkbox'))
    act(() => { useAppStore.setState({ selectedUserId: 'elena' }) })
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(screen.getByRole('button', { name: 'Открыть сервисный раздел' })).toBeDisabled()
  })

  it('does not persist access and starts locked after a fresh layout mount', async () => {
    const user = userEvent.setup()
    const view = renderGate()
    const localWrite = vi.spyOn(Storage.prototype, 'setItem')
    await confirmAccess(user)
    expect(localWrite).not.toHaveBeenCalled()
    view.unmount()
    renderGate()

    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(screen.queryByText('Закрытые технические настройки')).not.toBeInTheDocument()
  })

  it('keeps one shell and an emergency-stop action and overlay available while locked', async () => {
    const user = userEvent.setup()
    renderGate()
    expect(screen.getAllByRole('main')).toHaveLength(1)
    expect(screen.getAllByRole('button', { name: 'Аварийная остановка', exact: true })).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Аварийная остановка', exact: true }))

    expect(runCommand).toHaveBeenCalledExactlyOnceWith({ action: 'trigger_emergency_stop', userId: 'alexey' })
    expect(screen.getByRole('dialog', { name: 'Аварийная остановка активна' })).toBeVisible()
    expect(mountProtected).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Закрыть оверлей' }))
    expect(screen.getByRole('link', { name: 'Отмена — к настройкам' })).toBeVisible()
    expect(runCommand).toHaveBeenCalledTimes(1)
  })
})