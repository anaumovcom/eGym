import type { RuntimeSetResult } from '@/entities/runtime/model/types'
import { formatTimedSeconds } from '@/features/runtime/lib/timed-set'
import { getSetTypeLabel } from '@/features/strength/lib/strength-plan'
import './set-results-table.css'

function formatPlan(result: RuntimeSetResult, timed: boolean) {
  if (result.setType === 'failure') return 'До отказа'
  if (timed) return formatTimedSeconds(result.plannedValue)
  if (result.targetMinReps && result.targetMaxReps && result.targetMinReps !== result.targetMaxReps) {
    return `${result.targetMinReps}–${result.targetMaxReps}`
  }
  return result.targetMaxReps ?? result.plannedValue
}

export function SetResultsTable({ results, timed }: { results: RuntimeSetResult[]; timed: boolean }) {
  const showWeight = results.some(result => result.weightKg || result.volumeKg)
  return (
    <table className="rt-set-results-table" aria-label="Результаты подходов">
      <thead>
        <tr>
          <th scope="col">Подход</th>
          <th scope="col">Тип</th>
          <th scope="col">План</th>
          <th scope="col">Факт</th>
          {showWeight && <th scope="col">Вес / объём</th>}
          <th scope="col">Качество</th>
        </tr>
      </thead>
      <tbody>
        {results.map(result => {
          const actual = timed ? formatTimedSeconds(result.actualValue) : result.reps ?? result.actualValue
          const quality = [
            result.tempoLabel,
            result.amplitudePercent != null && `${result.amplitudePercent}%`,
            result.pain && 'боль',
            result.techniqueBreakdown && 'техника',
          ].filter(Boolean).join(' · ')
          return (
            <tr key={result.setNumber}>
              <th scope="row">
                {result.side ? `Подход ${result.roundNumber ?? result.setNumber} · ${result.side === 'left' ? 'Левая сторона' : 'Правая сторона'}` : result.setNumber}
              </th>
              <td>{getSetTypeLabel(result.setType)}</td>
              <td>{formatPlan(result, timed)}</td>
              <td>
                <strong>{result.completionStatus === 'skipped' ? 'Пропущен' : actual}</strong>
                {typeof result.rir === 'number' && ` · RIR ${result.rir}`}
              </td>
              {showWeight && (
                <td>{result.weightKg ? `${result.weightKg} кг` : '—'}{result.volumeKg ? ` · ${Math.round(result.volumeKg)} кг` : ''}</td>
              )}
              <td>{quality || '—'}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}
