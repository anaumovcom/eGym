import { useState } from 'react'
import { KeyMark, Metric, NoPoints, PlotFrame } from './measurement-frame'
import { axis, finite, fmt, syncRuns, withUnit, type Result } from './measurement-model'

const upColor = '#70dbc9', downColor = '#b9a7fa'
const signed = (v: number) => (v > 0 ? '+' : '') + fmt(v, 3)
function peakLabel(v: number | null) {
  if (v === null) return 'Знак не записан'
  if (v === 0) return '0 мм · вровень'
  return fmt(Math.abs(v), 3) + ' мм · ' + (v > 0 ? 'левая выше' : 'правая выше')
}

export function SyncMeasurementPlot({ result }: { result: Result }) {
  const [index, setIndex] = useState<number | null>(null)
  const [showLimit, setShowLimit] = useState(false)
  const runs = syncRuns(result), best = finite(result.selectedK), warning = finite(result.warningMm)
  if (!runs.length) return <NoPoints />
  const chosen = index ?? Math.max(0, runs.findIndex(r => r.k === best)), run = runs[chosen] ?? runs[0]
  const peaks = runs.flatMap(r => [r.up, r.down]).filter((v): v is number => v !== null)
  const range = Math.max(0.1, ...peaks.map(Math.abs), showLimit && warning !== null ? warning : 0)
  const scale = axis([-range, range], 6), left = 121, right = 793, y0 = 58, dy = 49
  const x = (v: number) => left + (v - scale.min) / (scale.max - scale.min) * (right - left)
  const bottom = y0 + dy * runs.length
  return <PlotFrame title="Перекос при разных настройках выравнивания"
    description="Для каждого коэффициента показан наибольший по модулю перекос при подъёме и спуске. Ноль означает, что каретки вровень."
    inspector={<>
      <h4>Проверенная настройка</h4>
      <label className="mp-select">Коэффициент выравнивания<select aria-label="Коэффициент выравнивания" value={chosen} onChange={e => setIndex(Number(e.target.value))}>
        {runs.map((r, i) => <option value={i} key={i}>{fmt(r.k, 3)} Н/мм{r.k === best ? ' · выбор X3' : ''}</option>)}</select></label>
      <div className="mp-large"><span>Наибольший перекос</span><strong>{fmt(run.max, 3)} <small>мм</small></strong></div>
      <dl className="mp-metrics"><Metric label="↑ Подъём">{peakLabel(run.up)}</Metric><Metric label="↓ Спуск">{peakLabel(run.down)}</Metric>
        <Metric label="Среднеквадратичный перекос">{withUnit(run.rms, 'мм', 3)}</Metric><Metric label="Смен знака вокруг среднего">{fmt(run.oscillation)}</Metric>
        <Metric label="Порог предупреждения"><span data-tone={warning !== null && run.max !== null && run.max >= warning ? 'warn' : undefined}>
          {warning === null ? 'Не записан' : '±' + fmt(warning) + ' мм' + (run.max !== null && run.max >= warning ? ' · достигнут' : '')}</span></Metric></dl>
      <p className="mp-note">{best !== null ? 'X3 выбрала коэффициент ' + fmt(best, 3) + ' Н/мм по перекосу и раскачке в обоих направлениях.'
        : result.partial ? 'Выбор коэффициента появится после оценки всех настроек.' : Object.hasOwn(result, 'selectedK') ? 'Ни одна настройка не прошла проверку X3. Проверьте ноль кареток B7 и тугие участки S8.' : 'В этой записи выбор коэффициента не указан.'}</p>
    </>}>
    {warning !== null && <div className="mp-switch" role="group" aria-label="Масштаб перекоса">
      <button type="button" aria-pressed={!showLimit} onClick={() => setShowLimit(false)}>По пикам</button>
      <button type="button" aria-pressed={showLimit} onClick={() => setShowLimit(true)}>С порогом ±{fmt(warning)} мм</button></div>}
    {peaks.length ? <svg className="mp-svg" viewBox={`0 0 826 ${bottom + 55}`} role="img" aria-label="Пики перекоса левой и правой сторон по коэффициентам">
      <text x="12" y="23" className="mp-axis-title">k, Н/мм</text>
      <text x={left} y="23" className="mp-axis-title">← Правая выше</text><text x={right} y="23" textAnchor="end" className="mp-axis-title">Левая выше →</text>
      <rect x="4" y={y0 + chosen * dy - 5} width="809" height={dy - 1} rx="7" fill="#203a47" opacity=".72" />
      {scale.ticks.map(t => <g key={t}><line className={t === 0 ? 'mp-zero' : 'mp-grid v'} x1={x(t)} x2={x(t)} y1="38" y2={bottom} />
        <text x={x(t)} y={bottom + 20} textAnchor="middle">{signed(t)}</text></g>)}
      {warning !== null && warning > 0 && warning <= scale.max && [-warning, warning].map(w => <line key={w} className="mp-limit" x1={x(w)} x2={x(w)} y1="38" y2={bottom} />)}
      {runs.map((r, i) => {
        const rowY = y0 + i * dy + 19
        return <g key={i} onClick={() => setIndex(i)} className="mp-hit"><rect x="0" y={rowY - 25} width="812" height={dy} fill="transparent" />
          <text x="14" y={rowY + 4} className="mp-axis-title">{fmt(r.k, 3)}{r.k === best ? ' ✓' : ''}</text>
          {([['up', upColor, -8], ['down', downColor, 8]] as const).map(([leg, color, offset]) => {
            const v = r[leg], py = rowY + offset
            return v !== null && <g key={leg}><line x1={x(0)} x2={x(v)} y1={py} y2={py} stroke={color} strokeWidth="3" />
              {leg === 'up' ? <circle cx={x(v)} cy={py} r="5" fill={color} /> : <path d={`M${x(v)} ${py - 6}l6 6 -6 6 -6 -6Z`} fill={color} />}</g>
          })}
        </g>
      })}
      <text className="mp-axis-title" x={(left + right) / 2} y={bottom + 46} textAnchor="middle">Высота левой минус высота правой, мм</text>
    </svg> : <NoPoints>В этой записи сохранилась величина перекоса без разбивки на подъём и спуск.</NoPoints>}
    <div className="mp-legend"><KeyMark color={upColor} shape="circle">Пик на подъёме</KeyMark><KeyMark color={downColor} shape="diamond">Пик на спуске</KeyMark>
      {warning !== null && warning <= scale.max && <KeyMark color="#fc8f83" shape="dash">Порог предупреждения</KeyMark>}</div>
  </PlotFrame>
}
