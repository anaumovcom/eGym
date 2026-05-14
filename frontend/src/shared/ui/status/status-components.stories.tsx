import type { Meta, StoryObj } from '@storybook/react-vite'
import { BlockingAlert, DriveStatusBadge, MachineStatusBadge, PrimaryActionBar, ReadinessIndicator, SafetyStatusBadge, WarningBanner } from '@/shared/ui/status/status-components'

const meta = {
  title: 'Shared/Status Components',
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
} satisfies Meta

export default meta

type Story = StoryObj<typeof meta>

export const Overview: Story = {
  render: () => (
    <div className="grid gap-6">
      <div className="flex flex-wrap gap-3">
        <MachineStatusBadge label="Тренажёр готов" tone="success" />
        <DriveStatusBadge label="Правый привод: требует проверки" tone="warning" />
        <SafetyStatusBadge label="Аварийная остановка: активна" tone="danger" />
      </div>
      <div className="flex gap-6">
        <ReadinessIndicator value={78} />
        <ReadinessIndicator value={84} accent="green" />
      </div>
      <WarningBanner title="Нужно внимание" description="Перед стартом требуется подтвердить готовность оборудования." />
      <BlockingAlert title="Старт заблокирован" description="Ошибка правого привода не позволяет начать тренировку." />
      <PrimaryActionBar>
        <div className="text-sm text-white/70">PrimaryActionBar используется как контейнер для закреплённого блока действий и краткой аналитики.</div>
      </PrimaryActionBar>
    </div>
  ),
}