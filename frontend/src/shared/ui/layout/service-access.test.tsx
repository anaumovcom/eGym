import { act, cleanup, render, screen } from '@testing-library/react'
import { useEffect } from 'react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SettingsLayout } from '@/shared/ui/layout/service-access'
import { useAppStore } from '@/stores/app-store'

const originalAppState = useAppStore.getState()

afterEach(() => {
  cleanup()
  useAppStore.setState(originalAppState, true)
})

describe('SettingsLayout', () => {
  it('opens nested service routes immediately and remounts on user changes', () => {
    const mount = vi.fn()
    const unmount = vi.fn()
    function ServiceScreen() {
      useEffect(() => {
        mount()
        return () => { unmount() }
      }, [])
      return <h2>Технические настройки</h2>
    }

    useAppStore.setState({ selectedUserId: 'alexey' })
    render(
      <MemoryRouter initialEntries={['/settings/service']}>
        <Routes>
          <Route path="/settings" element={<SettingsLayout />}>
            <Route path="service" element={<ServiceScreen />} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: 'Технические настройки' })).toBeVisible()
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(mount).toHaveBeenCalledTimes(1)

    act(() => { useAppStore.setState({ selectedUserId: 'elena' }) })
    expect(screen.getByRole('heading', { name: 'Технические настройки' })).toBeVisible()
    expect(unmount).toHaveBeenCalledTimes(1)
    expect(mount).toHaveBeenCalledTimes(2)
  })
})