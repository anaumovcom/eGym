import { Minus, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { cn } from '@/shared/lib/cn'

export type ValueStepperProps = {
  label: string
  value: number | null
  unit?: string
  emptyLabel?: string
  onChange: (delta: number) => void
  onValueCommit?: (value: number | null) => void
  onReset?: () => void
  resetLabel?: string
  readOnly?: boolean
  /** Digits kept when a typed value is committed (weight: 1 for 47,5 kg). */
  decimals?: number
  className?: string
}

/** Large TV-friendly "− value +" control: big targets, centred value, explicit unit. */
export function ValueStepper({ label, value, unit, emptyLabel = '—', onChange, onValueCommit, onReset, resetLabel = 'Убрать', readOnly = false, decimals = 0, className }: ValueStepperProps) {
  const [draft, setDraft] = useState(value === null ? '' : String(value))
  const isEmpty = value === null

  useEffect(() => {
    setDraft(value === null ? '' : String(value))
  }, [value])

  function commitDraft() {
    if (!onValueCommit) {
      setDraft(value === null ? '' : String(value))
      return
    }
    const normalized = draft.trim()
    if (!normalized) {
      onValueCommit(null)
      return
    }
    const parsed = Number(normalized.replace(',', '.'))
    if (!Number.isFinite(parsed)) {
      setDraft(value === null ? '' : String(value))
      return
    }
    const factor = 10 ** decimals
    onValueCommit(Math.round(parsed * factor) / factor)
  }

  return (
    <div className={cn('value-stepper', className)} data-empty={isEmpty} role="group" aria-label={label}>
      <div className="value-stepper-heading">
        <span>{label}{unit ? <span className="value-stepper-heading-unit" aria-hidden="true">, {unit}</span> : null}</span>
        {onReset && !isEmpty ? <button type="button" className="value-stepper-reset" onClick={onReset}>{resetLabel}</button> : null}
      </div>
      <div className="value-stepper-row">
        <button type="button" disabled={readOnly} aria-label={`Уменьшить: ${label}`} onClick={() => onChange(-1)}><Minus aria-hidden="true" /></button>
        <label className="value-stepper-value">
          <input
            type="text"
            inputMode="numeric"
            aria-label={`${label}${unit ? `, ${unit}` : ''}`}
            value={draft}
            readOnly={readOnly}
            onChange={(event) => setDraft(event.target.value.replace(/[^\d.,-]/g, ''))}
            onBlur={commitDraft}
            onKeyDown={(event) => {
              if (event.key === 'Enter') { event.preventDefault(); commitDraft() }
              if (event.key === 'Escape') setDraft(value === null ? '' : String(value))
            }}
            placeholder={emptyLabel}
          />
          {unit ? <span className="value-stepper-unit">{unit}</span> : null}
        </label>
        <button type="button" disabled={readOnly} aria-label={`Увеличить: ${label}`} onClick={() => onChange(1)}><Plus aria-hidden="true" /></button>
      </div>
    </div>
  )
}
