import type { Meta, StoryObj } from '@storybook/react-vite'
import { userSelectionScenarios } from '@/mocks/data'
import { UserSelectionView } from '@/screens/user-selection/user-selection-screen'

const meta = {
  title: 'Screens/User Selection',
  component: UserSelectionView,
  parameters: {
    layout: 'fullscreen',
  },
  tags: ['autodocs'],
} satisfies Meta<typeof UserSelectionView>

export default meta

type Story = StoryObj<typeof meta>

const baseArgs = {
  emergencyStopActive: false,
  onSelectUser: () => undefined,
  onGuest: () => undefined,
  onEmergencyStopChange: () => undefined,
  onStop: () => undefined,
}

export const Ready: Story = {
  args: {
    ...baseArgs,
    ...userSelectionScenarios.ready,
  },
}

export const Warning: Story = {
  args: {
    ...baseArgs,
    ...userSelectionScenarios.warning,
  },
}

export const Blocked: Story = {
  args: {
    ...baseArgs,
    ...userSelectionScenarios.blocked,
  },
}