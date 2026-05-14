import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'
import { Button } from '@/shared/ui/button'
import { ActionSheet, ConfirmDialog, EmergencyStopOverlay, Modal, PopoverCard, SidePanel, ToastNotification } from '@/shared/ui/overlays/surface-components'

const meta = {
  title: 'Shared/Surface Components',
  parameters: {
    layout: 'padded',
  },
  tags: ['autodocs'],
} satisfies Meta

export default meta

type Story = StoryObj<typeof meta>

export const Overview: Story = {
  render: () => {
    const [open, setOpen] = useState(false)

    return (
      <div className="grid gap-6 xl:grid-cols-2">
        <div className="space-y-4">
          <div className="flex flex-wrap gap-3">
            <Button onClick={() => setOpen(true)}>Открыть EmergencyStopOverlay</Button>
            <Modal title="Модалка" description="Базовая модальная поверхность." trigger={<Button variant="secondary">Открыть Modal</Button>} />
            <ConfirmDialog trigger={<Button variant="secondary">Открыть ConfirmDialog</Button>} />
            <PopoverCard trigger={<Button variant="ghost">Открыть Popover</Button>} content={<div>Содержимое popover.</div>} />
          </div>
          <SidePanel title="SidePanel">
            <div className="text-sm text-white/70">Контент боковой панели.</div>
          </SidePanel>
          <ActionSheet title="ActionSheet" items={['Диагностика', 'Настройки', 'Сервис']} />
        </div>
        <div className="space-y-4">
          <ToastNotification title="ToastNotification" description="Системное сообщение отображается поверх layout-компонентов." />
        </div>
        <EmergencyStopOverlay open={open} onOpenChange={setOpen} />
      </div>
    )
  },
}