import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { FrictionSource } from '@/features/motor/api/motor-api'
import { fmt, type Direction } from './measurement-model'

export function PlotFrame({ title, description, tools, inspector, children }: {
  title: string; description: string; tools?: ReactNode; inspector: ReactNode; children: ReactNode
}) {
  return <div className="mp-workspace">
    <section className="mp-figure" aria-label={title}>
      <header className="mp-chart-head"><div><h3>{title}</h3><p>{description}</p></div>{tools}</header>
      {children}
    </section>
    <aside className="mp-inspector" aria-label="Подробности замера">{inspector}</aside>
  </div>
}

export function DirectionChoice({ dir, onChange }: { dir: Direction; onChange: (v: Direction) => void }) {
  return <div className="mp-switch" role="group" aria-label="Направление движения">
    <button type="button" aria-pressed={dir === 'up'} onClick={() => onChange('up')}>↑ Подъём</button>
    <button type="button" aria-pressed={dir === 'down'} onClick={() => onChange('down')}>↓ Спуск</button>
  </div>
}

export function KeyMark({ color, shape = 'line', children }: { color: string; shape?: 'line' | 'circle' | 'diamond' | 'dash'; children: ReactNode }) {
  return <span className="mp-key"><i aria-hidden="true" data-shape={shape} style={{ color }} />{children}</span>
}

export function Metric({ label, children }: { label: string; children: ReactNode }) {
  return <div><dt>{label}</dt><dd>{children}</dd></div>
}

export function NoPoints({ children }: { children?: ReactNode }) {
  return <p className="mp-no-data" role="status">{children ?? 'Для графика в этой записи нет числовых измерений.'}</p>
}

export function HeightMapLink({ source, height }: { source: FrictionSource; height: number }) {
  return <Link className="mp-map-link" to={'?tab=friction&source=' + source + '&height=' + height + '&from=calibration'}>
    Последняя карта ШВП · {fmt(height)} мм <span aria-hidden="true">→</span></Link>
}
