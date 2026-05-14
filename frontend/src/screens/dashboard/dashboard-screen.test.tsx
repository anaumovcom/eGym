import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { dashboardStoryScenarios } from '@/mocks/data'
import { DashboardView } from '@/screens/dashboard/dashboard-screen'

describe('DashboardView', () => {
  it('renders no-workout state', () => {
    render(
      <MemoryRouter>
        <DashboardView
          data={dashboardStoryScenarios['no-workout']}
          userName="Алексей"
          emergencyStopActive={false}
          onStop={vi.fn()}
          onEmergencyStopChange={vi.fn()}
        />
      </MemoryRouter>,
    )

    expect(screen.getByText('Сегодня нет сохранённой тренировки')).toBeInTheDocument()
  })

  it('renders blocking alert for drive-error state', () => {
    render(
      <MemoryRouter>
        <DashboardView
          data={dashboardStoryScenarios['drive-error']}
          userName="Алексей"
          emergencyStopActive={false}
          onStop={vi.fn()}
          onEmergencyStopChange={vi.fn()}
        />
      </MemoryRouter>,
    )

    expect(screen.getByText('Ошибка правого привода')).toBeInTheDocument()
  })
})