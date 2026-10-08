import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { machineScenarios } from '@/mocks/data'
import { FormaShell, TopNavigationMenu, TopSystemBar } from '@/shared/ui/layout/forma-shell'
import { Button } from '@/shared/ui/button'
import { useHardwareStore } from '@/stores/hardware-store'
import { getSafetyLabel } from '@/shared/lib/machine-status'

afterEach(() => useHardwareStore.setState({ snapshot: null, connectionStatus: 'idle' }))

describe('TV system status', () => {
  it('keeps healthy status visible and discloses details without an action', async () => {
    const user = userEvent.setup()
    const stop = vi.fn()
    render(<TopSystemBar machine={machineScenarios.ready} onStop={stop} />)
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