import { ChevronsDown, ChevronsUp, Feather, Pin } from 'lucide-react'
import { useHoldToJog } from '@/features/hardware/ui/hold-to-jog'
import { Button } from '@/shared/ui/button'

type Jog = ReturnType<typeof useHoldToJog>

function formatCentimeters(value?: number | null) {
  return value == null ? '—' : `${(value / 10).toFixed(1).replace('.0', '').replace('.', ',')} см`
}

/** One bar point: its value, the hold-to-move button towards it and "remember here". */
function PointCard({ label, valueMm, status, directions, jog, captureLabel, captureDisabled, onCapture }: {
  label: string
  valueMm: number | null
  status: string
  directions: ('up' | 'down')[]
  jog: Jog
  captureLabel: string
  captureDisabled: boolean
  onCapture: () => void
}) {
  return (
    <div className="rt-bar-point" role="group" aria-label={label} data-set={valueMm != null}>
      <span className="rt-field-label">{label}</span>
      <div className="rt-field rt-bar-point-row">
        <span className="rt-bar-point-value">
          <strong>{formatCentimeters(valueMm)}</strong>
          {valueMm == null ? <small>{status}</small> : null}
        </span>
        {directions.map((direction) => (
          <Button key={direction} variant="secondary" className="rt-icon-button" title={direction === 'up' ? 'Удерживайте — гриф поедет вверх' : 'Удерживайте — гриф поедет вниз'}
            {...jog.buttonProps(direction)}>
            {direction === 'up' ? <ChevronsUp aria-hidden="true" /> : <ChevronsDown aria-hidden="true" />}
          </Button>
        ))}
        <Button variant="secondary" className="rt-icon-button" data-capture title={`${captureLabel} — запомнить текущее положение`} aria-label={captureLabel}
          disabled={captureDisabled} onClick={onCapture}>
          <Pin aria-hidden="true" />
        </Button>
      </div>
    </div>
  )
}

/**
 * Bar setup grouped by point: the top point above the bottom one, each with the
 * button that moves the bar towards it and the one that remembers it.
 */
export function BarPointControls({ setupType, userId, exerciseSlug, livePositionMm, lowerPointMm, upperPointMm, fixedPositionMm, barMoving, barStill, weightlessActive, onToggleWeightless, onCapture, onHoldingChange }: {
  setupType: 'bar_range' | 'fixed_position'
  userId: string | null
  exerciseSlug: string
  livePositionMm: number | null
  lowerPointMm: number | null
  upperPointMm: number | null
  fixedPositionMm: number | null
  barMoving: boolean
  barStill: boolean
  weightlessActive: boolean
  onToggleWeightless: () => void
  onCapture: (point: 'lower' | 'upper' | 'fixed') => void
  onHoldingChange: (holding: boolean) => void
}) {
  const jog = useHoldToJog({ userId, exerciseSlug, disabled: (barMoving && !weightlessActive) || livePositionMm == null, onHoldingChange })
  const captureDisabled = barMoving || (weightlessActive && !barStill)

  return (
    <>
      <div className="rt-bar-live">
        <span className="rt-field-label">Гриф сейчас</span>
        <div className="rt-field rt-bar-point-row">
          <span className="rt-bar-point-value"><strong>{formatCentimeters(livePositionMm)}</strong></span>
          <Button variant="secondary" iconLeft={<Feather aria-hidden="true" />} aria-pressed={weightlessActive} disabled={barMoving} onClick={onToggleWeightless}>
            {weightlessActive ? 'Невесомый гриф: вкл' : 'Невесомый гриф'}
          </Button>
        </div>
      </div>
      <div className="rt-bar-points" data-mode={setupType}>
        {setupType === 'bar_range' ? (
          <>
            <PointCard label="Верхняя точка" valueMm={upperPointMm} status="Поднимите гриф и запомните точку"
              directions={['up']} jog={jog} captureLabel="Зафиксировать верхнюю точку" captureDisabled={captureDisabled} onCapture={() => onCapture('upper')} />
            <PointCard label="Нижняя точка" valueMm={lowerPointMm} status="Опустите гриф и запомните точку"
              directions={['down']} jog={jog} captureLabel="Зафиксировать нижнюю точку" captureDisabled={captureDisabled} onCapture={() => onCapture('lower')} />
          </>
        ) : (
          <PointCard label="Фиксированная высота" valueMm={fixedPositionMm} status="Выставьте высоту и запомните её"
            directions={['up', 'down']} jog={jog} captureLabel="Зафиксировать высоту грифа" captureDisabled={captureDisabled} onCapture={() => onCapture('fixed')} />
        )}
      </div>
      <p className="rt-bar-legend" aria-hidden="true">
        <span><ChevronsUp /><ChevronsDown /> удерживайте — гриф едет</span>
        <span><Pin /> запомнить положение</span>
      </p>
    </>
  )
}
