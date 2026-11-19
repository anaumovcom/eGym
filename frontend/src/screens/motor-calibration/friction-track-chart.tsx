import { useState } from 'react'
import type { CalibrationStage, FrictionCoverage, FrictionTrack, Side } from '@/features/motor/api/motor-api'
import { FrictionHeightPlot } from './friction-height-plot'
import { binWidth, format, level, pairedEffort, railColor, railName, rails, signed, threshold, tightZones, zoneLabel } from './friction-track-model'
import './friction-track.css'

const passLabels = ['Ожидает прохода', 'Только подъём', 'Только спуск', 'Оба прохода']

export function LiveFrictionCoverage({ coverage }: { coverage: FrictionCoverage }) {
  if (!coverage.heightsMm.length) return null
  return <section className="bs-coverage" aria-label="Проходы S10 по высоте">
    <h3>Какие высоты измерены</h3>
    {rails.map(side => {
      const marks = coverage.sides[side], count = marks.filter(m => m === 3).length
      return <div className="bs-coverage-side" key={side}>
        <strong style={{color: railColor[side]}}>{railName[side]} ШВП</strong>
        <div className="bs-coverage-strip" role="img" aria-label={railName[side] + ' · оба прохода на ' + count + ' из ' + marks.length + ' участков'}>
          {marks.map((m, i) => <i key={coverage.heightsMm[i]} data-pass={m} title={format(coverage.heightsMm[i]) + ' мм · ' + passLabels[m]} />)}
        </div><small>{count} из {marks.length} с парой</small>
      </div>
    })}
    <div className="bs-coverage-axis"><span>{format(coverage.heightsMm[0])} мм</span><span>Высота от нижних упоров</span><span>{format(coverage.heightsMm.at(-1)!)} мм</span></div>
    <div className="bs-legend">{passLabels.map((label, i) => <span key={label}><i data-pass={i} />{label}</span>)}</div>
    <p>Участок засчитывается после трёх кадров на рабочей скорости. Итоговая карта сравнит усилия после встречного прохода.</p>
  </section>
}

export function hasWeightDeviation(stage: CalibrationStage) {
  const track = stage.result?.track as FrictionTrack | undefined
  return rails.some(side => track?.summary?.[side]?.weightWithinTolerance === false)
}

function HeightReadings({ track, before, i }: { track: FrictionTrack; before?: FrictionTrack; i: number }) {
  const previousIndex = before?.heightsMm.indexOf(track.heightsMm[i]) ?? -1
  const row = (name: string, get: (side: Side) => number | null | undefined, withSign = false, change = false) =>
    <tr key={name}><th scope="row">{name}</th>{rails.map(s => {
      const v = get(s)
      return <td key={s} data-change={change && v != null ? Math.sign(v) : undefined}>{v == null ? <span aria-label="Нет измерения">—</span> : (withSign ? signed(v) : format(v)) + ' Н'}</td>
    })}</tr>
  return <table className="bs-readings"><caption className="sr-only">Усилие на выбранной высоте</caption>
    <thead><tr><th scope="col">Усилие</th>{rails.map(s => <th key={s} scope="col" style={{ color: railColor[s] }}>{railName[s]}</th>)}</tr></thead>
    <tbody>
      {row('Сверх обычного', s => track.sides[s][i], true)}
      {track.directionalN && <>
        {row('При подъёме', s => track.directionalN?.[s]?.up[i])}
        {row('При спуске', s => track.directionalN?.[s]?.down[i])}
        {row('Среднее двух проходов', s => pairedEffort(track, s, i))}
      </>}
      {before && row('Среднее в прошлом замере', s => pairedEffort(before, s, previousIndex))}
      {before && row('Изменение среднего', s => {
        const a = pairedEffort(track, s, i), b = pairedEffort(before, s, previousIndex)
        return a == null || b == null ? null : Math.round((a - b) * 10) / 10
      }, true, true)}
    </tbody>
  </table>
}

export function BallScrewMap({ track, before, atHeight, heightFrom }: { track: FrictionTrack; before?: FrictionTrack; atHeight?: number; heightFrom?: 'calibration' | 'exercise' }) {
  const zones = { left: tightZones(track, 'left'), right: tightZones(track, 'right') }
  const strongest = [...zones.left, ...zones.right].sort((a, b) => b.peakN - a.peakN)[0]
  const [picked, setPicked] = useState<number | null>(null)
  const heights = track.heightsMm
  if (!heights.length) return null
  const width = binWidth(track)
  const requested = atHeight == null ? -1 : heights.findIndex(h => h - width / 2 <= atHeight && atHeight < h + width / 2)
  const index = Math.min(picked ?? (requested >= 0 ? requested : strongest?.peakIndex ?? Math.floor(heights.length / 2)), heights.length - 1)
  const height = heights[index]
  const weightWarnings = rails.filter(s => track.summary?.[s]?.weightWithinTolerance === false)
  const incomplete = rails.filter(s => track.coverageOk?.[s] === false)
  const formerZones = before ? rails.flatMap(s => tightZones(before, s)) : []
  return <div className="bs-map">
    <figure className="bs-profile" aria-label="Карта трения направляющих">
      <figcaption><h3>Карта трения по высоте</h3><p>Чем дальше линия от нуля наружу, тем больше усилие сверх обычного для этой стороны.</p></figcaption>
      <FrictionHeightPlot track={track} previous={before} index={index} select={setPicked} />
      <div className="bs-legend" aria-label="Обозначения карты">
        <span><i data-level="usual" />Обычный ход</span><span><i data-level="raised" />Повышено</span>
        <span><i data-level="high" />Выражено</span><span><i data-level="missing" />Нет пары</span>
        {before && <span><i className="bs-dash" />Прошлый замер</span>}
      </div>
      <p className="bs-hint">Высота от нижних упоров. Коснитесь карты или выберите участок из списка.</p>
    </figure>
    <div className="bs-details">
      <section className="bs-inspection" aria-label="Участки для осмотра">
        <h3>Участки для осмотра</h3>
        {rails.map(s => {
          const summary = track.summary?.[s], covered = track.sides[s].filter(v => v != null).length
          return <div className="bs-side" key={s}>
            <div className="bs-side-title"><strong><i style={{ background: railColor[s] }} />{railName[s]} ШВП</strong>
              <small>Измерено участков {covered} из {heights.length}</small></div>
            {zones[s].length ? <div className="bs-zones">{zones[s].map(z =>
              <button type="button" key={z.low} data-level={level(z.peakN, threshold(track, s))}
                aria-label={railName[s] + ' ШВП, ' + zoneLabel(z.low, z.high) + ', пик ' + signed(z.peakN) + ' Н'}
                aria-pressed={height >= z.low && height < z.high} onClick={() => setPicked(z.peakIndex)}>
                <span className="bs-zone-mark" aria-hidden="true" /><span>{zoneLabel(z.low, z.high)}</span>
                <small>{level(z.peakN, threshold(track, s)) === 'high' ? 'Выражено' : 'Повышено'}</small><b>Пик {signed(z.peakN)} Н</b>
              </button>)}</div> : <p>{covered ? 'На измеренных высотах порог не превышен.' : 'Нет высот с обоими проходами.'}</p>}
            {summary?.peakMm != null && summary.peakN != null && <p>Пик на {format(summary.peakMm)} мм · {signed(summary.peakN)} Н</p>}
            {summary?.typicalN != null && summary.thresholdN != null && <p>Обычный ход {format(summary.typicalN)} Н · подсветка свыше {signed(summary.thresholdN)} Н</p>}
          </div>
        })}
      </section>
      <section className="bs-inspector" aria-label="Выбранная высота">
        <div className="bs-selected-height"><div><span>Выбранная высота</span><h3>{format(height)} <small>мм</small></h3></div>
          <div><button type="button" aria-label="На участок ниже" disabled={index === 0} onClick={() => setPicked(index - 1)}>↓</button>
            <button type="button" aria-label="На участок выше" disabled={index === heights.length - 1} onClick={() => setPicked(index + 1)}>↑</button></div>
        </div>
        {atHeight != null && <p>{heightFrom === 'calibration' ? 'Высота из графика калибровки' : 'Высота перекоса в упражнении'} · {format(atHeight)} мм{requested < 0 ? ' · вне диапазона этого замера' : ''}.</p>}
        <HeightReadings track={track} before={before} i={index} />
        {before && <p>Пунктир показывает прибавку к обычному ходу прошлого замера. Отрицательное изменение среднего означает, что на этой высоте ход стал легче.</p>}
        {rails.some(s => track.sides[s][index] == null) && <p>Для участка {zoneLabel(height - width / 2, height + width / 2)} есть пропуск. Штриховка отмечает высоты без встречного измерения.</p>}
        {before && formerZones.length > 0 && <details className="bs-former"><summary>Найти прежние тугие участки</summary>
          <div>{formerZones.map(z => {
            const oldHeight = before.heightsMm[z.peakIndex], i = heights.indexOf(oldHeight)
            return <button type="button" key={z.side + z.low} disabled={i === -1} onClick={() => setPicked(i)}>
              {railName[z.side]} · {format(oldHeight)} мм · было {signed(z.peakN)} Н{i === -1 && ' · вне текущего диапазона'}
            </button>
          })}</div>
        </details>}
        <p className="bs-mechanics-note">Усилие относится к каретке в сборе. На отмеченной высоте проверьте положение ШВП и направляющей.</p>
      </section>
    </div>
    <div className="bs-notes">
      {track.heightBasis === 'bar' && <p>Карта из сохранённого профиля. В этом замере усилие сторон записано по общей высоте грифа. Доступен диапазон сохранённых точек.</p>}
      {incomplete.length > 0 && <p className="bs-balance">Неполная карта · {incomplete.map(s => railName[s].toLowerCase()).join(', ')}. Для оценки участков со штриховкой нужен повторный проход S10.</p>}
      {weightWarnings.length > 0 && <p className="bs-balance">Проверьте баланс S7. Остаток веса меняется по высоте · {weightWarnings.map(s => railName[s].toLowerCase() + ' до ' + format(track.summary![s]!.weightResidualN) + ' Н').join(', ')}.</p>}
      <details><summary>Как читать измерение</summary>
        {track.heightBasis !== 'bar' && <p>На каждом участке длиной {format(width)} мм S10 берёт медиану усилия привода при установившемся движении. Зоны разгона и торможения у концов хода исключены. Прибавка считается от медианы парных замеров этой стороны по высоте. Оба прохода помогают отделить сопротивление движению от веса грифа.</p>}
        {track.directionalN ? <p>Для подъёма показано усилие привода сверх расчётного веса, для спуска — вес за вычетом усилия привода. Порог подсветки учитывает разброс по ходу{rails.map(s => track.summary?.[s]?.thresholdN != null ? ' · ' + railName[s].toLowerCase() + ' ' + signed(threshold(track, s)) + ' Н' : '').join('')}. Выраженный участок превышает двойной порог.</p>
          : <p>В архивной карте сохранена прибавка по высоте. Для подсветки принят порог +4 Н, для выраженного участка — свыше +8 Н. Раздельные силы подъёма и спуска доступны в новых замерах.</p>}
        <p>Пики локализуют сопротивление всей каретки, включая винт и направляющие. Направление смещения винта определяют при механическом осмотре. После регулировки повторите S10 и сравните усилие на той же высоте.</p>
      </details>
    </div>
  </div>
}

export function FrictionTrackChart({ stage }: { stage: CalibrationStage }) {
  const track = stage.result?.track as FrictionTrack | undefined
  if (!track?.heightsMm?.length || !track.sides?.left || !track.sides?.right) return null
  return <BallScrewMap track={track} />
}
