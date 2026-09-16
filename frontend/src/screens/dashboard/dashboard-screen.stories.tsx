import type { Meta, StoryObj } from '@storybook/react-vite'
import { dashboardStoryScenarios } from '@/mocks/data'
import { DashboardView } from '@/screens/dashboard/dashboard-screen'

const meta = {
  title: 'Screens/Dashboard',
  component: DashboardView,
  parameters: {
    layout: 'fullscreen',
  },
  tags: ['autodocs'],
} satisfies Meta<typeof DashboardView>

export default meta

type Story = StoryObj<typeof meta>

const baseArgs = {
  userName: 'Алексей',
  emergencyStopActive: false,
  onStop: () => undefined,
  onEmergencyStopChange: () => undefined,
}

export const Default: Story = {
  args: {
    ...baseArgs,
    data: {
      ...dashboardStoryScenarios.default,
      workouts: ['Спина и бицепс', 'Грудь и плечи', 'Ноги', 'Общая тренировка'].map((title, index) => ({
        id: `personal-${index}`, title, duration: '≈ 45 минут',
        exercises: [{ slug: 'machine-pulldown', name: 'Тяга сверху' }, { slug: 'barbell-curl', name: 'Сгибание рук со штангой' }],
      })),
    },
  },
}

export const NoWorkout: Story = {
  args: {
    ...baseArgs,
    data: dashboardStoryScenarios['no-workout'],
  },
}

export const HighFatigue: Story = {
  args: {
    ...baseArgs,
    data: dashboardStoryScenarios['high-fatigue'],
  },
}

export const MachineWarning: Story = {
  args: {
    ...baseArgs,
    data: dashboardStoryScenarios['machine-warning'],
  },
}

export const DriveError: Story = {
  args: {
    ...baseArgs,
    data: dashboardStoryScenarios['drive-error'],
  },
}

export const ThreeWorkouts: Story = {
  args: { ...baseArgs, data: { ...Default.args!.data!, workouts: Default.args!.data!.workouts!.slice(0, 3) } },
}