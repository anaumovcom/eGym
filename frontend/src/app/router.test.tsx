import { render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AppRoutes } from '@/app/router'
import { useAppStore } from '@/stores/app-store'

vi.mock('@/screens/dashboard/dashboard-screen', () => ({ DashboardScreen: () => <div>Dashboard destination</div> }))
vi.mock('@/screens/builder/workout-builder-screen', () => ({ WorkoutBuilderScreen: () => <div>Builder destination</div> }))
vi.mock('@/screens/catalog/exercise-catalog-screen', () => ({ ExerciseCatalogScreen: () => <div>Catalog destination</div> }))
vi.mock('@/screens/progress/progress-screen', () => ({ ProgressScreen: () => <div>Progress destination</div> }))
vi.mock('@/screens/fatigue/fatigue-screen', () => ({ FatigueScreen: () => <div>Fatigue destination</div> }))
vi.mock('@/screens/profile/user-profile-screen', () => ({ UserProfileScreen: () => <div>Profile destination</div> }))
vi.mock('@/screens/modbus-debug/modbus-debug-screen', () => ({ ModbusDebugScreen: () => <div>Modbus controls</div> }))
vi.mock('@/screens/user-selection/user-selection-screen', () => ({ UserSelectionScreen: () => <div>Select a user</div> }))

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function renderAt(path: string) {
  render(<MemoryRouter initialEntries={[path]}><AppRoutes /><LocationProbe /></MemoryRouter>)
}

describe('Stage 1 routes', () => {
  beforeEach(() => {
    useAppStore.setState({ selectedUserId: 'alexey', selectedProgramId: 'my-workout', emergencyStopActive: false })
  })

  it.each([
    ['/programs?selected=old-template', '/builder', 'Builder destination'],
    ['/quick-start?selected=old-exercise', '/catalog', 'Catalog destination'],
    ['/today?scenario=planned', '/dashboard', 'Dashboard destination'],
    ['/photo-progress?source=profile&photo=manual', '/profile?tab=photo', 'Profile destination'],
    ['/photo-progress?source=progress&photo=manual', '/progress?tab=photo', 'Progress destination'],
  ])('redirects %s without modifying the selected user workout', (oldPath, destination, text) => {
    renderAt(oldPath)
    expect(screen.getByText(text)).toBeInTheDocument()
    expect(screen.getByTestId('location').textContent).toBe(destination)
    expect(useAppStore.getState().selectedProgramId).toBe('my-workout')
  })

  it('opens the standalone fatigue page without changing the selected workout', () => {
    renderAt('/fatigue?mode=7d&muscle=chest')
    expect(screen.getByText('Fatigue destination')).toBeInTheDocument()
    expect(screen.getByTestId('location').textContent).toBe('/fatigue?mode=7d&muscle=chest')
    expect(useAppStore.getState().selectedProgramId).toBe('my-workout')
  })

  it.each(['/modbus-debug', '/settings/service/modbus'])('redirects legacy debug URLs to the standalone Modbus page at %s', (path) => {
    renderAt(path)
    expect(screen.getByTestId('location').textContent).toBe('/modbus')
    expect(screen.getByText('Modbus controls')).toBeInTheDocument()
  })

  it.each(['/today', '/quick-start', '/programs', '/fatigue', '/modbus-debug', '/settings/service/modbus', '/modbus'])('requires a user for %s', (path) => {
    useAppStore.setState({ selectedUserId: null })
    renderAt(path)
    expect(screen.getByText('Select a user')).toBeInTheDocument()
    expect(screen.getByTestId('location').textContent).toBe('/')
  })
})