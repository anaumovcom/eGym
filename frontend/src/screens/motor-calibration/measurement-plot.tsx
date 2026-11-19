import { memo } from 'react'
import type { FrictionSource, PlotStage } from '@/features/motor/api/motor-api'
import { BrakeMeasurementPlot } from './brake-measurement-plot'
import { ForceMeasurementPlot } from './force-measurement-plot'
import { RepeatabilityPlot } from './repeatability-plot'
import { SyncMeasurementPlot } from './sync-measurement-plot'
import { brakeRuns, forcePoints, syncRuns, type Result } from './measurement-model'
import './measurement-plots.css'

type PlotProps = { code: PlotStage; result: Result; mapSource?: FrictionSource }
function Chart({ code, result, mapSource }: PlotProps) {
  if (code === 'G4') return <RepeatabilityPlot result={result} mapSource={mapSource} />
  if (code === 'X3') return <SyncMeasurementPlot result={result} />
  if (code === 'M5') return <BrakeMeasurementPlot result={result} />
  return <ForceMeasurementPlot code={code} result={result} mapSource={mapSource} />
}

function progressLabel(code: PlotStage, result: Result) {
  if (code === 'G4') return 'Получено проходов · ' + (Array.isArray(result.passes) ? result.passes.length : 0) + ' из 6'
  if (code === 'M5') {
    const runs = brakeRuns(result)
    return 'Завершено прогонов · ' + runs.length + '. Путь измерен в ' + runs.filter(r => r.total !== null).length
  }
  if (code === 'X3') return 'Проверено настроек выравнивания · ' + syncRuns(result).length
  const counts = (['left', 'right'] as const).map(side => forcePoints(code, result, side, 'up').length + (code === 'S7' ? 0 : forcePoints(code, result, side, 'down').length))
  return 'Получено точек · левая ' + counts[0] + ', правая ' + counts[1]
}

export const MeasurementPlot = memo(function MeasurementPlot({ code, result, mapSource, live = false }: PlotProps & { live?: boolean }) {
  return <div className="mp-panel">
    {(live || result.partial === true) && <p className="mp-progress" role="status"><strong>{live ? 'Идёт замер' : 'Неполный замер'}</strong>{progressLabel(code, result)}</p>}
    <Chart code={code} result={result} mapSource={mapSource} />
  </div>
})
