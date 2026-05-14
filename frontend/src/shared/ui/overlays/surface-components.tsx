import * as Dialog from '@radix-ui/react-dialog'
import * as Popover from '@radix-ui/react-popover'
import { X } from 'lucide-react'
import type { PropsWithChildren, ReactNode } from 'react'
import { Button } from '@/shared/ui/button'

export function EmergencyStopOverlay({
  open,
  onOpenChange,
  actionLabel = 'Требуется сервисная проверка',
  onAction,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  actionLabel?: string
  onAction?: () => void
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-[#05080f]/78 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(520px,calc(100vw-24px))] -translate-x-1/2 -translate-y-1/2 rounded-[32px] border border-[#eb5345]/30 bg-[#12090a] p-8 text-white shadow-[0_32px_80px_rgba(0,0,0,0.5)]">
          <Dialog.Title className="font-display text-3xl font-bold text-[#ffb4a7]">Аварийная остановка активна</Dialog.Title>
          <Dialog.Description className="mt-3 text-base leading-7 text-white/75">
            Движение заблокировано. Для продолжения потребуется ручная проверка статуса безопасности и приводов.
          </Dialog.Description>
          <div className="mt-6 flex gap-3">
            <Button variant="secondary" onClick={() => onOpenChange(false)}>
              Закрыть оверлей
            </Button>
            <Button variant="danger" onClick={onAction}>
              {actionLabel}
            </Button>
          </div>
          <Dialog.Close className="absolute right-4 top-4 inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/10 bg-white/5 text-white/70">
            <X className="h-4 w-4" />
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export function Modal({ title, description, trigger }: { title: string; description: string; trigger: ReactNode }) {
  return (
    <Dialog.Root>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/60" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(560px,calc(100vw-24px))] -translate-x-1/2 -translate-y-1/2 rounded-[28px] border border-white/10 bg-[#09101a] p-6 text-white">
          <Dialog.Title className="font-display text-2xl font-bold">{title}</Dialog.Title>
          <Dialog.Description className="mt-2 text-sm text-white/70">{description}</Dialog.Description>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export function SidePanel({ title, children }: PropsWithChildren<{ title: string }>) {
  return (
    <aside className="glass-panel rounded-[28px] p-5">
      <div className="mb-4 font-display text-xl font-bold text-white">{title}</div>
      {children}
    </aside>
  )
}

export function PopoverCard({ trigger, content }: { trigger: ReactNode; content: ReactNode }) {
  return (
    <Popover.Root>
      <Popover.Trigger asChild>{trigger}</Popover.Trigger>
      <Popover.Portal>
        <Popover.Content sideOffset={12} className="z-50 max-w-xs rounded-2xl border border-white/10 bg-[#0b1220] p-4 text-sm text-white/75 shadow-2xl">
          {content}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}

export function ActionSheet({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="glass-panel rounded-[28px] p-4">
      <div className="mb-3 font-semibold text-white">{title}</div>
      <div className="space-y-2">
        {items.map((item) => (
          <button key={item} type="button" className="flex min-h-11 w-full items-center rounded-2xl border border-white/8 bg-white/4 px-4 text-left text-sm text-white/80">
            {item}
          </button>
        ))}
      </div>
    </div>
  )
}

export function ToastNotification({ title, description }: { title: string; description: string }) {
  return (
    <div className="fixed bottom-6 right-6 z-50 w-[320px] rounded-2xl border border-[#d6b05f]/25 bg-[#0c1420] p-4 text-white shadow-2xl">
      <div className="font-semibold text-[#f1d391]">{title}</div>
      <div className="mt-1 text-sm text-white/70">{description}</div>
    </div>
  )
}

export function ConfirmDialog({ trigger }: { trigger: ReactNode }) {
  return <Modal title="Подтвердить действие" description="Опасные действия в Forma всегда требуют дополнительного подтверждения." trigger={trigger} />
}