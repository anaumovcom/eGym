import type { BarStartPoint } from '@/features/hardware/model/types'
import { Button } from '@/shared/ui/button'

const options: { value: BarStartPoint; label: string }[] = [
  { value: 'lower', label: 'У нижней точки' },
  { value: 'upper', label: 'У верхней точки' },
]

export function BarStartPointSelector({ value, disabled = false, hint, onChange }: {
  value: BarStartPoint; disabled?: boolean; hint?: string; onChange: (value: BarStartPoint) => void
}) {
  return (
    <div className="rt-start-point">
      <span className="rt-start-point-label">Начальное положение грифа</span>
      <div className="rt-start-point-options" role="group" aria-label="Начальное положение грифа">
        {options.map((option) => (
          <Button key={option.value} variant={value === option.value ? 'primary' : 'secondary'} aria-pressed={value === option.value}
            disabled={disabled} onClick={() => { if (option.value !== value) onChange(option.value) }}>
            {option.label}
          </Button>
        ))}
      </div>
      {hint ? <small className="rt-start-point-hint">{hint}</small> : null}
    </div>
  )
}
