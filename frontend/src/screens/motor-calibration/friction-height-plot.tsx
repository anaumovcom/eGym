import { useId, type KeyboardEvent, type PointerEvent } from 'react'
import type { FrictionTrack, Side } from '@/features/motor/api/motor-api'
import { binWidth, format, level, railColor, railName, rails, signed, threshold } from './friction-track-model'

const top = 36, bottom = 383
const bands = { left: 277, right: 393 }
const tones = { usual: '#347477', raised: '#ffbe57', high: '#fb7961' }

function scaleStep(value: number) {
  const decade = 10 ** Math.floor(Math.log10(value))
  return ([1, 2, 5, 10].find(step => step * decade >= value) ?? 10) * decade
}

export function FrictionHeightPlot({ track, previous, index, select }: {
  track: FrictionTrack; previous?: FrictionTrack; index: number; select: (index: number) => void
}) {
  const id = useId().replace(/:/g, '')
  const heights = track.heightsMm, half = binWidth(track) / 2
  const low = heights[0] - half, high = heights[heights.length - 1] + half
  const previousIndex = new Map(previous?.heightsMm.map((h, i) => [h, i]))
  const older = (side: Side, i: number) => {
    const j = previousIndex.get(heights[i])
    return j === undefined || track.sides[side][i] == null ? null : previous?.sides[side][j] ?? null
  }
  const measured = rails.flatMap(s => heights.flatMap((_, i) => [track.sides[s][i], older(s, i)]))
    .filter((v): v is number => v != null)
  const limit = scaleStep(Math.max(4, ...measured) / 2) * 2
  const floor = -scaleStep(Math.max(limit / 4, ...measured.map(v => -v)))
  const x = (s: Side, v: number) => {
    const distance = (v - floor) / (limit - floor) * 222
    return s === 'left' ? 260 - distance : 440 + distance
  }
  const y = (h: number) => bottom - (h - low) / (high - low) * (bottom - top)
  const tick = scaleStep((high - low) / 7)
  const ticks = [low, high]
  for (let h = Math.ceil(low / tick) * tick; h < high; h += tick) {
    if (y(low) - y(h) > 20 && y(h) - y(high) > 20) ticks.push(h)
  }
  const trace = (s: Side, values: (number | null)[]) => {
    const segments: string[] = [], fills: string[] = []
    let points: string[] = [], first = 0
    heights.forEach((h, i) => {
      const v = values[i]
      if (v == null) return
      if (!points.length) first = i
      points.push(x(s, v) + ' ' + y(h))
      if (values[i + 1] == null || heights[i + 1] - h !== 2 * half) {
        segments.push('M' + points.join(' L'))
        fills.push('M' + x(s, 0) + ' ' + y(heights[first]) + ' L' + points.join(' L') + ' L' + x(s, 0) + ' ' + y(h) + ' Z')
        points = []
      }
    })
    return { line: segments.join(' '), fill: fills.join(' ') }
  }
  const choose = (e: PointerEvent<SVGSVGElement>) => {
    const svg = e.currentTarget, matrix = svg.getScreenCTM()
    if (!matrix) return
    const pos = new DOMPoint(e.clientX, e.clientY).matrixTransform(matrix.inverse())
    const h = low + (bottom - pos.y) / (bottom - top) * (high - low)
    select(heights.reduce((best, n, i) => Math.abs(n - h) < Math.abs(heights[best] - h) ? i : best, 0))
  }
  const keys = (e: KeyboardEvent<SVGSVGElement>) => {
    const next: Record<string, number> = { ArrowUp: index + 1, ArrowRight: index + 1, ArrowDown: index - 1,
      ArrowLeft: index - 1, Home: 0, End: heights.length - 1, PageUp: index + 5, PageDown: index - 5 }
    if (!(e.key in next)) return
    e.preventDefault()
    select(Math.max(0, Math.min(heights.length - 1, next[e.key])))
  }
  const selectedY = y(heights[index])
  return <svg className="bs-height-plot" viewBox="0 0 700 419" role="slider" tabIndex={0}
    aria-label="Высота на карте трения" aria-orientation="vertical" aria-valuemin={heights[0]} aria-valuemax={heights.at(-1)}
    aria-valuenow={heights[index]} aria-valuetext={format(heights[index]) + ' мм от нижних упоров'}
    onKeyDown={keys} onPointerDown={e => { if (e.button === 0) { e.currentTarget.setPointerCapture(e.pointerId); choose(e) } }}
    onPointerMove={e => { if (e.currentTarget.hasPointerCapture(e.pointerId)) choose(e) }}>
    <defs>
      <pattern id={id + '-gap'} width="6" height="6" patternUnits="userSpaceOnUse">
        <rect width="6" height="6" fill="#1d2c3b" /><line x1="-1" y1="6" x2="6" y2="-1" stroke="#8896a5" strokeWidth="1.6" />
      </pattern>
    </defs>
    {ticks.map(h => <g key={h}>
      <line x1="25" x2="675" y1={y(h)} y2={y(h)} stroke="#2e424e" strokeDasharray="3 4" />
      {Math.abs(y(h) - selectedY) > 18 && <text x="350" y={y(h) + 4} textAnchor="middle">{format(h)}</text>}
    </g>)}
    {rails.map(s => {
      const current = trace(s, track.sides[s])
      const before = previous && trace(s, heights.map((_, i) => older(s, i)))
      const values = track.sides[s], color = railColor[s]
      return <g key={s}>
        <text x={s === 'left' ? 149 : 551} y="18" textAnchor="middle" className="bs-axis-heading">{railName[s]} ШВП</text>
        {[floor, 0, limit].map(v => <g key={v}>
          <line x1={x(s, v)} x2={x(s, v)} y1={top} y2={bottom} stroke={v === 0 ? '#5a6c78' : '#273c48'} strokeDasharray={v === 0 ? undefined : '3 5'} />
          <text x={x(s, v)} y="406" textAnchor="middle">{signed(v)} Н</text>
        </g>)}
        <path d={current.line} fill="none" stroke={color} strokeWidth="2.4" strokeLinejoin="round" />
        <path d={current.fill} fill={color} fillOpacity=".16" />
        {before && <path d={before.line} fill="none" stroke="#dee3ec" strokeDasharray="5 4" strokeWidth="1.5" />}
        <rect x={bands[s]} y={top} width="30" height={bottom - top} fill={'url(#' + id + '-gap)'} />
        {heights.map((h, i) => {
          const band = level(values[i] ?? null, threshold(track, s))
          const isolated = values[i] != null && values[i - 1] == null && values[i + 1] == null
          return <g key={h}>
            {band !== 'missing' && <rect x={bands[s]} y={y(h + half)} width="30" height={y(h - half) - y(h + half)} fill={tones[band]} />}
            {isolated && <circle cx={x(s, values[i]!)} cy={y(h)} r="2.3" fill={color} />}
          </g>
        })}
        {[top - 3, bottom].map(cap => <rect key={cap} x={bands[s] - 3} y={cap} width="36" height="3" rx="1" fill="#83929f" />)}
      </g>
    })}
    <text x="350" y="18" textAnchor="middle">мм</text>
    <line x1="24" x2="676" y1={selectedY} y2={selectedY} stroke="#f6f9fc" strokeDasharray="4 5" opacity=".85" />
    <rect x="314" y={selectedY - 11} width="72" height="22" rx="5" fill="#e5f3f8" />
    <text className="bs-cursor-height" x="350" y={selectedY + 4.5} textAnchor="middle">{format(heights[index])}</text>
    {rails.map(s => track.sides[s][index] != null &&
      <circle key={s} cx={x(s, track.sides[s][index]!)} cy={selectedY} r="4" fill="#10212c" stroke={railColor[s]} strokeWidth="2.2" />)}
  </svg>
}
