import { useEffect, useMemo, useRef, useState } from 'react'
import type { TuningEvent } from '@/features/hardware/model/tuning-types'
import { cn } from '@/shared/lib/cn'

export type ChartChannel = {
  field: string
  label: string
  color: string
  axis: 'left' | 'right'
}

export const DEFAULT_CHANNELS: ChartChannel[] = [
  { field: 'posL', label: 'Позиция Л, мм', color: '#f2cf87', axis: 'left' },
  { field: 'posR', label: 'Позиция П, мм', color: '#d6b05f', axis: 'left' },
  { field: 'vel', label: 'Скорость, мм/с', color: '#7fc8ff', axis: 'right' },
  { field: 'acc', label: 'Ускорение, мм/с²', color: '#4f86c6', axis: 'right' },
  { field: 'forceL', label: 'Сила привода Л, кг', color: '#9be29b', axis: 'right' },
  { field: 'forceR', label: 'Сила привода П, кг', color: '#4fb04f', axis: 'right' },
  { field: 'userForce', label: 'Усилие пользователя, кг', color: '#ff9f6e', axis: 'right' },
  { field: 'loadTarget', label: 'Заданная нагрузка, кг', color: '#c9a5ff', axis: 'right' },
  { field: 'loadEffective', label: 'Фактическая нагрузка, кг', color: '#9b6bff', axis: 'right' },
  { field: 'syncDelta', label: 'Рассинхрон, мм', color: '#ff6b6b', axis: 'right' },
  { field: 'currentL', label: 'Ток Л, А', color: '#ffd166', axis: 'right' },
  { field: 'currentR', label: 'Ток П, А', color: '#e0b13f', axis: 'right' },
  { field: 'tempL', label: 'Температура Л, °C', color: '#ff8fa3', axis: 'right' },
  { field: 'tempR', label: 'Температура П, °C', color: '#d9647c', axis: 'right' },
  { field: 'cmdL', label: 'Команда Л, кг', color: '#8de3d7', axis: 'right' },
  { field: 'cmdR', label: 'Команда П, кг', color: '#3fb9a8', axis: 'right' },
]

const EVENT_COLORS: Record<string, string> = {
  rep: '#9be29b',
  partial_rep: '#6fae6f',
  reversal: '#7fc8ff',
  spotter: '#ff9f6e',
  failure: '#ff6b6b',
  desync: '#ff6b6b',
  fault: '#ff3b3b',
  grip: '#f2cf87',
  release: '#c9a5ff',
  param: '#ffffff',
  capture: '#f2cf87',
  mode: '#8a8a8a',
  obstacle: '#ff6b6b',
  target: '#9be29b',
}

type Props = {
  fields: string[]
  samples: (number | string)[][]
  events?: TuningEvent[]
  channels: ChartChannel[]
  enabled: Set<string>
  windowSeconds: number
  height?: number
  overlay?: { fields: string[]; samples: (number | string)[][]; label: string } | null
  className?: string
}

export function TelemetryChart({ fields, samples, events = [], channels, enabled, windowSeconds, height = 320, overlay, className }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [cursor, setCursor] = useState<number | null>(null)
  const [hover, setHover] = useState<{ t: number; values: { label: string; value: string; color: string }[] } | null>(null)

  const tIndex = fields.indexOf('t')
  const active = useMemo(() => channels.filter((channel) => enabled.has(channel.field) && fields.includes(channel.field)), [channels, enabled, fields])

  const visible = useMemo(() => {
    if (samples.length === 0 || tIndex < 0) return []
    const last = Number(samples[samples.length - 1][tIndex])
    const from = last - windowSeconds
    let start = 0
    for (let i = samples.length - 1; i >= 0; i -= 1) {
      if (Number(samples[i][tIndex]) < from) {
        start = i
        break
      }
    }
    return samples.slice(start)
  }, [samples, tIndex, windowSeconds])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    const width = canvas.clientWidth
    canvas.width = width * dpr
    canvas.height = height * dpr
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.scale(dpr, dpr)
    ctx.clearRect(0, 0, width, height)
    ctx.fillStyle = 'rgba(255,255,255,0.02)'
    ctx.fillRect(0, 0, width, height)

    const padL = 52
    const padR = 52
    const padT = 12
    const padB = 22
    const plotW = width - padL - padR
    const plotH = height - padT - padB

    if (visible.length < 2 || tIndex < 0) {
      ctx.fillStyle = 'rgba(255,255,255,0.35)'
      ctx.font = '12px sans-serif'
      ctx.fillText('Нет данных телеметрии', padL, height / 2)
      return
    }

    const t0 = Number(visible[0][tIndex])
    const t1 = Number(visible[visible.length - 1][tIndex])
    const span = Math.max(0.001, t1 - t0)
    const xOf = (t: number) => padL + ((t - t0) / span) * plotW

    const ranges: Record<'left' | 'right', { min: number; max: number }> = {
      left: { min: Infinity, max: -Infinity },
      right: { min: Infinity, max: -Infinity },
    }
    for (const channel of active) {
      const index = fields.indexOf(channel.field)
      for (const row of visible) {
        const value = Number(row[index])
        if (!Number.isFinite(value)) continue
        const range = ranges[channel.axis]
        range.min = Math.min(range.min, value)
        range.max = Math.max(range.max, value)
      }
    }
    for (const axis of ['left', 'right'] as const) {
      const range = ranges[axis]
      if (!Number.isFinite(range.min)) {
        range.min = 0
        range.max = 1
      }
      if (range.max - range.min < 1e-6) {
        range.min -= 1
        range.max += 1
      }
      const pad = (range.max - range.min) * 0.08
      range.min -= pad
      range.max += pad
    }
    const yOf = (value: number, axis: 'left' | 'right') => {
      const range = ranges[axis]
      return padT + plotH - ((value - range.min) / (range.max - range.min)) * plotH
    }

    // grid
    ctx.strokeStyle = 'rgba(255,255,255,0.08)'
    ctx.lineWidth = 1
    ctx.font = '10px sans-serif'
    for (let i = 0; i <= 4; i += 1) {
      const y = padT + (plotH / 4) * i
      ctx.beginPath()
      ctx.moveTo(padL, y)
      ctx.lineTo(padL + plotW, y)
      ctx.stroke()
      const leftValue = ranges.left.max - ((ranges.left.max - ranges.left.min) / 4) * i
      const rightValue = ranges.right.max - ((ranges.right.max - ranges.right.min) / 4) * i
      ctx.fillStyle = 'rgba(242,207,135,0.7)'
      ctx.textAlign = 'right'
      ctx.fillText(leftValue.toFixed(0), padL - 6, y + 3)
      ctx.fillStyle = 'rgba(127,200,255,0.8)'
      ctx.textAlign = 'left'
      ctx.fillText(rightValue.toFixed(1), padL + plotW + 6, y + 3)
    }
    ctx.fillStyle = 'rgba(255,255,255,0.4)'
    ctx.textAlign = 'center'
    for (let i = 0; i <= 5; i += 1) {
      const t = t0 + (span / 5) * i
      ctx.fillText(`${t.toFixed(1)} с`, xOf(t), height - 6)
    }

    // events
    for (const event of events) {
      if (event.time < t0 || event.time > t1) continue
      const x = xOf(event.time)
      ctx.strokeStyle = EVENT_COLORS[event.kind] ?? 'rgba(255,255,255,0.3)'
      ctx.globalAlpha = 0.6
      ctx.setLineDash([3, 3])
      ctx.beginPath()
      ctx.moveTo(x, padT)
      ctx.lineTo(x, padT + plotH)
      ctx.stroke()
      ctx.setLineDash([])
      ctx.globalAlpha = 1
      ctx.fillStyle = EVENT_COLORS[event.kind] ?? 'rgba(255,255,255,0.5)'
      ctx.beginPath()
      ctx.arc(x, padT + 4, 3, 0, Math.PI * 2)
      ctx.fill()
    }

    const drawSeries = (rows: (number | string)[][], rowFields: string[], dashed: boolean) => {
      const rowT = rowFields.indexOf('t')
      if (rowT < 0 || rows.length < 2) return
      const rowT0 = Number(rows[0][rowT])
      for (const channel of active) {
        const index = rowFields.indexOf(channel.field)
        if (index < 0) continue
        ctx.strokeStyle = channel.color
        ctx.lineWidth = dashed ? 1 : 1.5
        ctx.setLineDash(dashed ? [4, 4] : [])
        ctx.beginPath()
        let started = false
        for (const row of rows) {
          const t = dashed ? t0 + (Number(row[rowT]) - rowT0) : Number(row[rowT])
          if (t > t1) break
          const value = Number(row[index])
          if (!Number.isFinite(value)) continue
          const x = xOf(t)
          const y = yOf(value, channel.axis)
          if (!started) {
            ctx.moveTo(x, y)
            started = true
          } else {
            ctx.lineTo(x, y)
          }
        }
        ctx.stroke()
      }
      ctx.setLineDash([])
    }
    drawSeries(visible, fields, false)
    if (overlay) drawSeries(overlay.samples, overlay.fields, true)

    if (cursor !== null) {
      const x = Math.min(padL + plotW, Math.max(padL, cursor))
      ctx.strokeStyle = 'rgba(255,255,255,0.6)'
      ctx.beginPath()
      ctx.moveTo(x, padT)
      ctx.lineTo(x, padT + plotH)
      ctx.stroke()
    }
  }, [visible, active, fields, events, height, tIndex, cursor, overlay])

  const onMove = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current
    if (!canvas || visible.length < 2 || tIndex < 0) return
    const rect = canvas.getBoundingClientRect()
    const x = event.clientX - rect.left
    setCursor(x)
    const padL = 52
    const plotW = rect.width - 104
    const t0 = Number(visible[0][tIndex])
    const t1 = Number(visible[visible.length - 1][tIndex])
    const t = t0 + ((x - padL) / plotW) * (t1 - t0)
    let nearest = visible[0]
    for (const row of visible) {
      if (Math.abs(Number(row[tIndex]) - t) < Math.abs(Number(nearest[tIndex]) - t)) nearest = row
    }
    setHover({
      t: Number(nearest[tIndex]),
      values: active.map((channel) => ({ label: channel.label, color: channel.color, value: String(nearest[fields.indexOf(channel.field)]) })),
    })
  }

  return (
    <div className={cn('relative', className)}>
      <canvas
        ref={canvasRef}
        style={{ height }}
        className="w-full rounded-2xl border border-white/10"
        onMouseMove={onMove}
        onMouseLeave={() => {
          setCursor(null)
          setHover(null)
        }}
      />
      {hover && (
        <div className="pointer-events-none absolute right-16 top-3 rounded-xl border border-white/10 bg-[#0d0b07]/90 px-3 py-2 text-[11px] text-white/80">
          <div className="text-white/50">t = {hover.t.toFixed(2)} с</div>
          {hover.values.map((item) => (
            <div key={item.label} className="flex items-center gap-2">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: item.color }} />
              <span className="text-white/60">{item.label}:</span>
              <span className="font-mono">{item.value}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
