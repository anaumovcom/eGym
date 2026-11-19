import { Flag, Shield, SlidersHorizontal } from 'lucide-react'
import { createContext, useContext } from 'react'
import type { CalibrationPriority, CalibrationSpec } from '@/features/motor/api/motor-api'

export const CalibrationCatalogContext = createContext<ReadonlyMap<string, CalibrationSpec>>(new Map())

const LEVELS = {
  critical: { label: 'Критично', icon: Shield, meaning: 'Влияет на контроль усилия, удержание грифа или его остановку в пределах хода.' },
  important: { label: 'Важно', icon: Flag, meaning: 'Определяет точность рабочего веса, ровность хода или достоверность проверки.' },
  refinement: { label: 'Тонкая настройка', icon: SlidersHorizontal, meaning: 'Уточняет отклик в отдельных условиях, например после паузы или при малом усилии.' },
} satisfies Record<CalibrationPriority, { label: string; icon: typeof Shield; meaning: string }>

export function priorityLabel(level: CalibrationPriority) {
  return LEVELS[level]?.label ?? ''
}

export function PriorityTag({ level, reason }: { level: CalibrationPriority; reason?: string }) {
  const { icon: Icon, label } = LEVELS[level]
  return <span className="cal-priority-tag" data-priority={level} title={reason}>
    <Icon size={13} strokeWidth={2} aria-hidden="true" /><span className="sr-only">Важность — </span>{label}
  </span>
}

export function PriorityMark({ code, explain = false }: { code: string; explain?: boolean }) {
  const spec = useContext(CalibrationCatalogContext).get(code)
  if (!spec?.priority || !LEVELS[spec.priority]) return null
  const tag = <PriorityTag level={spec.priority} reason={explain ? undefined : spec.priorityReason} />
  return explain ? <div className="cal-priority-note">{tag}<p>{spec.priorityReason}</p></div> : tag
}

export function PriorityLegend() {
  return <details className="cal-priority-legend">
    <summary>Что означают метки важности</summary>
    <dl>{(Object.keys(LEVELS) as CalibrationPriority[]).map(level =>
      <div key={level}><dt><PriorityTag level={level} /></dt><dd>{LEVELS[level].meaning}</dd></div>,
    )}</dl>
    <p>Важность серии определяется самым важным из её замеров.</p>
  </details>
}
