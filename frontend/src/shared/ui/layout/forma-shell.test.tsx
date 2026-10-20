import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { machineScenarios } from '@/mocks/data'
import { FormaShell, ResetBlockButton, TopNavigationMenu, TopSystemBar } from '@/shared/ui/layout/forma-shell'
import { Button } from '@/shared/ui/button'
import { useHardwareStore } from '@/stores/hardware-store'
import { getSafetyLabel } from '@/shared/lib/machine-status'
import { useAppStore } from '@/stores/app-store'
import type { HardwareCommandResponse, HardwareSnapshot } from '@/features/hardware/model/types'

afterEach(() => {
  vi.restoreAllMocks()
  useHardwareStore.setState({ snapshot: null, connectionStatus: 'idle', errorMessage: null })
  useAppStore.setState({ emergencyStopActive: false })
})

describe('ResetBlockButton', () => {
  const stopped = { ...machineScenarios.ready, machineState: 'blocked' as const, safety: 'emergency_stop' as const }
  const snapshot = (stopped: boolean) => ({
    safety: { state: stopped ? 'emergency_stop' : 'enabled' },
    control: { mode: stopped ? 'estop' : 'idle' },
  }) as HardwareSnapshot

  it('clears an emergency through the guarded STOP command, not reset_fault', async () => {
    useAppStore.setState({ emergencyStopActive: true })
    useHardwareStore.setState({ snapshot: snapshot(true) })
    const run = vi.spyOn(useHardwareStore.getState(), 'runCommand').mockResolvedValue({ snapshot: snapshot(false) } as HardwareCommandResponse)
    render(<ResetBlockButton machine={stopped} />)
    await userEvent.click(screen.getByRole('button', { name: 'Сбросить ошибку' }))
    expect(run).toHaveBeenCalledExactlyOnceWith({ action: 'clear_emergency_stop' })
    await waitFor(() => expect(useAppStore.getState().emergencyStopActive).toBe(false))
  })

  it('waits for panel confirmation before dismissing the emergency overlay', async () => {
    useAppStore.setState({ emergencyStopActive: true })
    useHardwareStore.setState({ snapshot: snapshot(true) })
    const run = vi.spyOn(useHardwareStore.getState(), 'runCommand').mockResolvedValue({ status: 'pending', snapshot: snapshot(true) } as HardwareCommandResponse)
    render(<ResetBlockButton machine={stopped} />)
    await userEvent.click(screen.getByRole('button', { name: 'Сбросить ошибку' }))
    expect(run).toHaveBeenCalledExactlyOnceWith({ action: 'clear_emergency_stop' })
    expect(useAppStore.getState().emergencyStopActive).toBe(true)
    act(() => useHardwareStore.setState({ snapshot: snapshot(false) }))
    expect(useAppStore.getState().emergencyStopActive).toBe(false)
  })

  it('preserves the emergency and displays a refusal when the physical STOP is pressed', async () => {
    useAppStore.setState({ emergencyStopActive: true })
    useHardwareStore.setState({ snapshot: snapshot(true) })
    const run = vi.spyOn(useHardwareStore.getState(), 'runCommand').mockRejectedValue(new Error('Физическая кнопка STOP нажата'))
    render(<ResetBlockButton machine={stopped} />)
    await userEvent.click(screen.getByRole('button', { name: 'Сбросить ошибку' }))
    await waitFor(() => expect(useHardwareStore.getState().errorMessage).toBe('Физическая кнопка STOP нажата'))
    expect(useAppStore.getState().emergencyStopActive).toBe(true)
    expect(run).toHaveBeenCalledTimes(1)
  })

  it('still resets ordinary faults without sending clear_stop', async () => {
    const run = vi.spyOn(useHardwareStore.getState(), 'runCommand').mockResolvedValue({ snapshot: snapshot(false) } as HardwareCommandResponse)
    render(<ResetBlockButton machine={{ ...machineScenarios.ready, machineState: 'blocked' }} />)
    await userEvent.click(screen.getByRole('button', { name: 'Сбросить ошибку' }))
    expect(run).toHaveBeenCalledExactlyOnceWith({ action: 'reset_fault' })
  })
})

describe('TV system status', () => {
  it('shows the service exit only while enabled and uses the guarded disable command', async () => {
    useAppStore.setState({ selectedUserId: 'alexey' })
    const snapshot = { serviceMode: true, safety: { state: 'enabled' } } as HardwareSnapshot
    useHardwareStore.setState({ snapshot })
    let finish!: (value: HardwareCommandResponse) => void
    const run = vi.spyOn(useHardwareStore.getState(), 'runCommand').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    render(<TopSystemBar machine={machineScenarios.ready} onStop={vi.fn()} />)
    const button = screen.getByRole('button', { name: 'Отключить сервисный режим' })
    await userEvent.click(button)
    expect(run).toHaveBeenCalledExactlyOnceWith({ action: 'toggle_service_mode', userId: 'alexey', serviceMode: false })
    expect(button).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Аварийная остановка' })).toBeEnabled()
    await act(async () => { finish({ snapshot } as HardwareCommandResponse) })
    expect(button).toBeEnabled() // Wait for actual telemetry, not an optimistic toggle.
    act(() => useHardwareStore.setState({ snapshot: { ...snapshot, serviceMode: false } }))
    expect(screen.queryByRole('button', { name: 'Отключить сервисный режим' })).not.toBeInTheDocument()
  })

  it('keeps service exit available after failure and reports the error', async () => {
    useHardwareStore.setState({ snapshot: { serviceMode: true, safety: { state: 'enabled' } } as HardwareSnapshot })
    vi.spyOn(useHardwareStore.getState(), 'runCommand').mockRejectedValue(new Error('Команда отклонена'))
    render(<TopSystemBar machine={machineScenarios.ready} onStop={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Отключить сервисный режим' }))
    await waitFor(() => expect(useHardwareStore.getState().errorMessage).toBe('Команда отклонена'))
    expect(screen.getByRole('button', { name: 'Отключить сервисный режим' })).toBeEnabled()
  })

  it('keeps healthy status visible and discloses details without an action', async () => {
    const user = userEvent.setup()
    const stop = vi.fn()
    render(<TopSystemBar machine={machineScenarios.ready} onStop={stop} />)
    expect(screen.queryByRole('button', { name: 'Отключить сервисный режим' })).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(machineScenarios.ready.machineLabel)
    await user.click(screen.getByRole('button', { name: /Состояние тренажёра:/ }))
    expect(screen.getByText(getSafetyLabel(machineScenarios.ready.safety))).toBeVisible()
    expect(stop).not.toHaveBeenCalled()
  })

  it('does not present a stale ready snapshot as connected', () => {
    useHardwareStore.setState({ connectionStatus: 'disconnected' })
    render(<TopSystemBar machine={machineScenarios.ready} onStop={vi.fn()} />)
    expect(screen.getByRole('status')).toHaveTextContent('Нет связи с тренажёром')
  })

  it('prioritizes an emergency over drive warnings and a lost connection', () => {
    useHardwareStore.setState({ connectionStatus: 'error' })
    render(<TopSystemBar machine={{ ...machineScenarios.ready, leftDrive: 'warning', safety: 'emergency_stop' }} onStop={vi.fn()} />)
    expect(screen.getByRole('status')).toHaveTextContent(getSafetyLabel('emergency_stop'))
  })
})

describe('Stage 1 navigation', () => {
  it('shows six primary destinations and marks nested catalog pages active', () => {
    render(<MemoryRouter initialEntries={['/catalog/barbell-floor-press']}><TopNavigationMenu userName="Алексей" /></MemoryRouter>)
    const nav = screen.getByRole('navigation', { name: 'Основная навигация' })
    expect(within(nav).getAllByRole('link').map((link) => [link.textContent, link.getAttribute('href')])).toEqual([
      ['Главная', '/dashboard'], ['Мои тренировки', '/builder'], ['Каталог', '/catalog'], ['Календарь', '/calendar'], ['Прогресс', '/progress'], ['Усталость мышц', '/fatigue'],
    ])
    expect(within(nav).getByRole('link', { name: 'Каталог' })).toHaveAttribute('aria-current', 'page')
    expect(screen.queryByRole('link', { name: 'Профиль' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Настройки' })).not.toBeInTheDocument()
  })

  it('opens the profile menu with keyboard, closes on Escape and on navigation', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><TopNavigationMenu userName="Алексей" /></MemoryRouter>)
    const avatar = screen.getByRole('button', { name: 'Меню профиля: Алексей' })
    avatar.focus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('link', { name: 'Профиль', exact: true })).toHaveAttribute('href', '/profile')
    expect(screen.getByRole('link', { name: 'Настройки', exact: true })).toHaveAttribute('href', '/settings')
    expect(screen.getByRole('link', { name: 'Modbus', exact: true })).toHaveAttribute('href', '/modbus')
    expect(screen.queryByRole('link', { name: 'Механика', exact: true })).not.toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('navigation', { name: 'Меню пользователя' })).not.toBeInTheDocument()
    expect(avatar).toHaveFocus()
    await user.click(avatar)
    await user.click(screen.getByRole('link', { name: 'Профиль', exact: true }))
    expect(screen.queryByRole('navigation', { name: 'Меню пользователя' })).not.toBeInTheDocument()
  })

  it('preserves hidden navigation and the emergency-stop handler', async () => {
    const user = userEvent.setup()
    const stop = vi.fn()
    render(<MemoryRouter><FormaShell userName="Алексей" machine={machineScenarios.ready} hideNavigation onStop={stop}>Упражнение</FormaShell></MemoryRouter>)
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
    expect(screen.getAllByRole('main')).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Аварийная остановка' }))
    expect(stop).toHaveBeenCalledOnce()
  })

  it.each([false, true])('renders a button as a single link with optional icon (%s)', (withIcon) => {
    render(<Button asChild iconLeft={withIcon ? <span data-testid="icon">→</span> : undefined}><a href="/settings">Настройки</a></Button>)
    expect(screen.getByRole('link', { name: /Настройки/ })).toHaveAttribute('href', '/settings')
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByTestId('icon') !== null).toBe(withIcon)
  })
})