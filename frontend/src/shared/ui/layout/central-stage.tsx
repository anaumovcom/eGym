import { useId, useState, type ReactNode } from 'react'
import { Button } from '@/shared/ui/button'

/** Secondary content is opt-in; the primary scenario owns the centred stage. */
export function CentralStage({ children, secondary, secondaryLabel }: { children: ReactNode; secondary: ReactNode; secondaryLabel: string }) {
  const [expanded, setExpanded] = useState(false)
  const panelId = useId()

  return (
    <section className="space-y-4">
      <div className="flex justify-end">
        <Button variant="secondary" aria-expanded={expanded} aria-controls={panelId} onClick={() => setExpanded((value) => !value)}>
          {secondaryLabel}
        </Button>
      </div>
      <div className="forma-stage-grid" data-expanded={expanded}>
        <div>{children}</div>
        <aside id={panelId} aria-label={secondaryLabel} hidden={!expanded}>{expanded ? secondary : null}</aside>
      </div>
    </section>
  )
}