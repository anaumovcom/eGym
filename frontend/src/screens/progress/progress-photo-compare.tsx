import { Camera, Columns2, SplitSquareHorizontal } from 'lucide-react'
import { useRef, useState, type PointerEvent } from 'react'
import { daysBetween, formatSigned, weightNear, type BodyMeasurement } from '@/features/body/body-metrics'
import { Button } from '@/shared/ui/button'
import { PhotoImage, photoViews, type ProgressPhoto } from './progress-photo-gallery'

const dateFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
const chipFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', year: '2-digit' })
const dayKey = (value: string) => new Date(value).toDateString()

/** One photo per view and day (the latest), oldest first — the unit of comparison. */
function shotsOf(photos: ProgressPhoto[], view: ProgressPhoto['view']) {
  const byDay = new Map<string, ProgressPhoto>()
  for (const photo of [...photos].filter((item) => item.view === view).sort((a, b) => Date.parse(a.takenAt) - Date.parse(b.takenAt))) byDay.set(dayKey(photo.takenAt), photo)
  return [...byDay.values()]
}

export function PhotoCompare({ photos, measurements, onPhoto }: { photos: ProgressPhoto[]; measurements: BodyMeasurement[]; onPhoto: () => void }) {
  const available = photoViews.filter((view) => shotsOf(photos, view.id).length > 0)
  const preferred = available.find((view) => shotsOf(photos, view.id).length > 1) ?? available[0]
  const [viewId, setViewId] = useState<ProgressPhoto['view']>(preferred?.id ?? 'front')
  const shots = shotsOf(photos, viewId)
  const [beforeId, setBeforeId] = useState<number | null>(null)
  const [afterId, setAfterId] = useState<number | null>(null)
  const [mode, setMode] = useState<'slider' | 'side'>('slider')
  const [position, setPosition] = useState(50)
  const stage = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)
  if (!preferred) return null

  const after = shots.find((shot) => shot.id === afterId) ?? shots.at(-1)!
  const before = shots.find((shot) => shot.id === beforeId && shot.id !== after.id) ?? (shots.length > 1 ? shots.find((shot) => shot.id !== after.id && Date.parse(shot.takenAt) <= Date.parse(after.takenAt)) ?? shots[0] : null)
  const label = photoViews.find((view) => view.id === viewId)!.label
  const beforeWeight = before ? weightNear(measurements, before.takenAt) : null
  const afterWeight = weightNear(measurements, after.takenAt)
  const gap = before ? Math.abs(daysBetween(before.takenAt, after.takenAt)) : 0

  function selectView(next: ProgressPhoto['view']) { setViewId(next); setBeforeId(null); setAfterId(null) }
  function slide(event: PointerEvent<HTMLDivElement>) {
    const box = stage.current?.getBoundingClientRect()
    if (!box) return
    setPosition(Math.min(100, Math.max(0, ((event.clientX - box.left) / box.width) * 100)))
  }

  return (
    <section className="photo-compare" aria-labelledby="photo-compare-title">
      <header className="photo-compare-head">
        <div><h3 id="photo-compare-title">Сравнение до и после</h3><p>{before ? `${gap} ${gap % 10 === 1 && gap % 100 !== 11 ? 'день' : [2, 3, 4].includes(gap % 10) && ![12, 13, 14].includes(gap % 100) ? 'дня' : 'дней'} между снимками` : 'Нужен ещё один снимок этого ракурса'}</p></div>
        <div className="photo-compare-controls">
          <div className="photo-compare-segment" role="group" aria-label="Ракурс сравнения">{photoViews.map((view) => <button key={view.id} type="button" aria-pressed={viewId === view.id} disabled={!available.some((item) => item.id === view.id)} onClick={() => selectView(view.id)}>{view.label}</button>)}</div>
          {before ? <div className="photo-compare-segment" role="group" aria-label="Режим сравнения"><button type="button" aria-pressed={mode === 'slider'} onClick={() => setMode('slider')}><SplitSquareHorizontal aria-hidden="true" />Шторка</button><button type="button" aria-pressed={mode === 'side'} onClick={() => setMode('side')}><Columns2 aria-hidden="true" />Рядом</button></div> : null}
        </div>
      </header>

      {before ? (
        <div className="photo-compare-body">
          {mode === 'slider' ? (
            <div
              ref={stage}
              className="photo-compare-stage"
              onPointerDown={(event) => { dragging.current = true; event.currentTarget.setPointerCapture?.(event.pointerId); slide(event) }}
              onPointerMove={(event) => { if (dragging.current) slide(event) }}
              onPointerUp={() => { dragging.current = false }}
              onPointerCancel={() => { dragging.current = false }}
            >
              <div className="photo-compare-layer"><PhotoImage key={`a-${after.id}`} photo={after} full alt={`После: ${label}`} /></div>
              <div className="photo-compare-layer photo-compare-before" style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }}><PhotoImage key={`b-${before.id}`} photo={before} full alt={`До: ${label}`} /></div>
              <span className="photo-compare-tag" data-side="before">До</span><span className="photo-compare-tag" data-side="after">После</span>
              <span className="photo-compare-handle" style={{ left: `${position}%` }} aria-hidden="true"><i /></span>
              <input className="photo-compare-range" type="range" min={0} max={100} value={Math.round(position)} aria-label="Положение шторки" onChange={(event) => setPosition(Number(event.target.value))} />
            </div>
          ) : (
            <div className="photo-compare-side">
              <figure><PhotoImage key={`b-${before.id}`} photo={before} full alt={`До: ${label}`} /><span className="photo-compare-tag" data-side="before">До</span></figure>
              <figure><PhotoImage key={`a-${after.id}`} photo={after} full alt={`После: ${label}`} /><span className="photo-compare-tag" data-side="after">После</span></figure>
            </div>
          )}
          <div className="photo-compare-facts">
            <ShotFacts title="До" shot={before} weight={beforeWeight?.value ?? null} shots={shots} selected={before.id} disabled={after.id} onSelect={setBeforeId} />
            <div className="photo-compare-summary">
              <strong>{gap}</strong><span>дней</span>
              {beforeWeight && afterWeight ? <b data-tone={afterWeight.value < beforeWeight.value ? 'down' : afterWeight.value > beforeWeight.value ? 'up' : undefined}>{formatSigned(Math.round((afterWeight.value - beforeWeight.value) * 10) / 10)} кг</b> : <small>вес не измерялся</small>}
            </div>
            <ShotFacts title="После" shot={after} weight={afterWeight?.value ?? null} shots={shots} selected={after.id} disabled={before.id} onSelect={setAfterId} />
          </div>
        </div>
      ) : (
        <div className="photo-compare-single">
          <figure><PhotoImage key={after.id} photo={after} full alt={`${label}, ${dateFormat.format(new Date(after.takenAt))}`} /></figure>
          <div><p>Это первый снимок ракурса «{label.toLowerCase()}» от {dateFormat.format(new Date(after.takenAt))}</p><p>Сделайте следующий через 2–4 недели в том же месте и при том же свете — здесь появится сравнение.</p><Button iconLeft={<Camera aria-hidden="true" />} onClick={onPhoto}>Сделать снимок</Button></div>
        </div>
      )}
    </section>
  )
}

function ShotFacts({ title, shot, weight, shots, selected, disabled, onSelect }: { title: string; shot: ProgressPhoto; weight: number | null; shots: ProgressPhoto[]; selected: number; disabled: number; onSelect: (id: number) => void }) {
  return (
    <div className="photo-compare-shot">
      <span>{title}</span>
      <strong>{dateFormat.format(new Date(shot.takenAt))}</strong>
      <small>{weight !== null ? `${weight.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} кг в эти дни` : 'без взвешивания'}</small>
      {shots.length > 2 ? (
        <div className="photo-compare-dates" role="group" aria-label={`Дата снимка «${title}»`}>
          {shots.map((item) => <button key={item.id} type="button" aria-pressed={item.id === selected} disabled={item.id === disabled} onClick={() => onSelect(item.id)}>{chipFormat.format(new Date(item.takenAt)).replace('.', '')}</button>)}
        </div>
      ) : null}
    </div>
  )
}
