import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { userSelectionScenarios } from '@/mocks/data'
import { UserSelectionView } from '@/screens/user-selection/user-selection-screen'

describe('UserSelectionView', () => {
  it('selects a user profile', async () => {
    const user = userEvent.setup()
    const onSelectUser = vi.fn()

    render(
      <UserSelectionView
        {...userSelectionScenarios.ready}
        emergencyStopActive={false}
        onSelectUser={onSelectUser}
        onGuest={vi.fn()}
        onEmergencyStopChange={vi.fn()}
        onStop={vi.fn()}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Выбрать профиль Алексей' }))

    expect(onSelectUser).toHaveBeenCalledWith('alexey')
  })

  it('shows guest mode and disabled add-user action', () => {
    render(
      <UserSelectionView
        {...userSelectionScenarios.ready}
        emergencyStopActive={false}
        onSelectUser={vi.fn()}
        onGuest={vi.fn()}
        onEmergencyStopChange={vi.fn()}
        onStop={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'Гость' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Добавить пользователя' })).toBeDisabled()
  })
})