import { ArrowDown, ArrowUp } from 'lucide-react'
import type { LoadDirection } from '@/features/hardware/model/types'
import { Button } from '@/shared/ui/button'

export function LoadDirectionSelector({ value = 'down', disabled = false, nextSet = false, onChange }: {
  value?: LoadDirection; disabled?: boolean; nextSet?: boolean; onChange: (value: LoadDirection) => void
}) {
  return (
    <div className="rt-start-point">
      <span className="rt-start-point-label">Направление нагрузки</span>
      <div className="rt-start-point-options" role="group" aria-label="Направление нагрузки">
        {([{ value: 'down', label: 'Нагрузка вниз' }, { value: 'up', label: 'Тяга вверх' }] as const).map((option) => (
          <Button key={option.value} variant={value === option.value ? 'primary' : 'secondary'}
            iconLeft={option.value === 'down' ? <ArrowDown aria-hidden="true" /> : <ArrowUp aria-hidden="true" />}
            aria-pressed={value === option.value} disabled={disabled}
            onClick={() => { if (value !== option.value) onChange(option.value) }}><span>{option.label}</span></Button>
        ))}
      </div>
      {/* The usual "down" needs no explanation; only the unusual choice and deferred changes do. */}
      {value === 'up' || nextSet ? (
        <small className="rt-start-point-hint">
          {value === 'up' ? 'Тяга вверх: удобнее начинать у верхней точки. Начальное положение выбирается отдельно.' : ''}
          {nextSet ? ' Изменение применится только со следующего подхода.' : ''}
        </small>
      ) : null}
    </div>
  )
}