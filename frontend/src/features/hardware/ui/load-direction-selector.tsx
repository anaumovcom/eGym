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
            aria-pressed={value === option.value} disabled={disabled}
            onClick={() => { if (value !== option.value) onChange(option.value) }}>{option.label}</Button>
        ))}
      </div>
      <small className="rt-start-point-hint">
        {value === 'up' ? 'Тяга вверх: удобнее начинать у верхней точки. Начальное положение выбирается отдельно.' : 'Нагрузка направлена вниз (обычный режим).'}
        {nextSet ? ' Изменение применится только со следующего подхода.' : ''}
      </small>
    </div>
  )
}