import type { Meta, StoryObj } from '@storybook/react-vite'
import { machineScenarios } from '@/mocks/data'
import { EmergencyStopButton, FormaShell, TopNavigationMenu, TopSystemBar } from '@/shared/ui/layout/forma-shell'

const meta = {
  title: 'Shared/Forma Shell',
  parameters: {
    layout: 'fullscreen',
  },
  tags: ['autodocs'],
} satisfies Meta

export default meta

type Story = StoryObj<typeof meta>

export const Components: Story = {
  render: () => (
    <div className="grid gap-6">
      <TopNavigationMenu userName="Алексей" />
      <div className="space-y-6">
        <TopSystemBar onStop={() => undefined} />
        <EmergencyStopButton onClick={() => undefined} />
      </div>
    </div>
  ),
}

export const FullShell: Story = {
  render: () => (
    <FormaShell userName="Алексей" machine={machineScenarios.ready} onStop={() => undefined}>
      <section className="glass-panel rounded-[32px] p-8 text-white/75">Верхняя навигация, меню профиля и постоянная аварийная остановка.</section>
    </FormaShell>
  ),
}