import { AlertTriangle, Inbox, LoaderCircle, ShieldAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/cn'

export type FormaStateTone = 'loading' | 'error' | 'empty' | 'blocked'

const icons = {
  loading: LoaderCircle,
  error: AlertTriangle,
  empty: Inbox,
  blocked: ShieldAlert,
} as const

/** One large, centred state (loading / error / empty / blocked) with a single clear next action. */
export function FormaState({ tone, title, description, action, className }: { tone: FormaStateTone; title: string; description?: string; action?: { label: string; onClick: () => void } | ReactNode; className?: string }) {
  const Icon = icons[tone]
  const isActionConfig = Boolean(action) && typeof action === 'object' && action !== null && 'label' in (action as object)

  return (
    <div className={cn('forma-state', className)} data-tone={tone} role={tone === 'loading' ? 'status' : tone === 'empty' ? undefined : 'alert'} aria-live={tone === 'loading' ? 'polite' : undefined}>
      <div className="forma-state-icon" aria-hidden="true"><Icon /></div>
      <h2>{title}</h2>
      {description ? <p>{description}</p> : null}
      {isActionConfig
        ? <Button onClick={(action as { label: string; onClick: () => void }).onClick}>{(action as { label: string }).label}</Button>
        : (action as ReactNode) ?? null}
    </div>
  )
}
