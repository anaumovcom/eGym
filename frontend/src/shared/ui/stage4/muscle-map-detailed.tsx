import { memo, useLayoutEffect, useMemo, useState, type CSSProperties } from 'react'
import type { FatigueMuscle } from '@/entities/stage4/model/types'
import { fatigueColors, fatigueLabels, muscleHeatOpacity } from './fatigue-appearance'
import { fatigueRegionOwners, muscleIsVisibleOnView, resolveSvgIdsForMuscle, svgIdsByView, type BodyMapView } from './fatigue-muscle-map'
import { useBodyFigure, type FigureGender } from './use-body-figure'
import { useMuscleHover } from './use-muscle-hover'

type MapProps = {
  muscles: FatigueMuscle[]
  selectedId: string
  onSelect: (id: string) => void
  figureGender?: FigureGender
  userId?: string | null
}

export function MuscleMapDetailed({ muscles, selectedId, onSelect, figureGender = 'male', userId }: MapProps) {
  const owners = useMemo(() => ({
    front: fatigueRegionOwners(muscles, 'front'),
    back: fatigueRegionOwners(muscles, 'back'),
  }), [muscles])
  const selected = muscles.find(({ id }) => id === selectedId)
  const preferred = selected?.group ?? 'front'
  const otherSide = preferred === 'front' ? 'back' : 'front'
  const labelView = muscleIsVisibleOnView(selectedId, preferred) ? preferred : otherSide

  return (
    <div className="atlas-figures">
      {(['front', 'back'] as const).map((view) => (
        <MuscleFigure key={view} view={view} owners={owners[view]} selected={selected}
          showCallout={labelView === view} onSelect={onSelect} figureGender={figureGender} userId={userId} />
      ))}
    </div>
  )
}

// Keep the inline DOM and keyboard focus intact when a tooltip moves.
const FigureArtwork = memo(function FigureArtwork({ markup }: { markup: string }) {
  return <div className="atlas-svg" dangerouslySetInnerHTML={{ __html: markup }} />
})

type Hint = { muscle: FatigueMuscle; left: number; top: number }
type Callout = { name: string; x: number; y: number; leftward: boolean }

function MuscleFigure({ view, owners, selected, showCallout, onSelect, figureGender, userId }: {
  view: BodyMapView
  owners: Map<string, FatigueMuscle>
  selected?: FatigueMuscle
  showCallout: boolean
  onSelect: MapProps['onSelect']
  figureGender: FigureGender
  userId?: string | null
}) {
  const host = useMuscleHover<HTMLElement>()
  const { markup, prefix, loadError } = useBodyFigure(view, figureGender, userId)
  const [hint, setHint] = useState<Hint | null>(null)
  const [callout, setCallout] = useState<Callout | null>(null)
  const title = view === 'front' ? 'Вид спереди' : 'Вид сзади'

  useLayoutEffect(() => {
    const figure = host.current
    const svg = figure?.querySelector('svg')
    setCallout(null)
    setHint(null)
    if (!figure || !svg || !markup) return

    svg.setAttribute('role', 'group')
    svg.setAttribute('aria-label', title)
    const listeners = new AbortController()
    const options = { signal: listeners.signal }
    const selectedRegions = selected ? resolveSvgIdsForMuscle(selected.id) : []
    let labelled: { region: SVGGraphicsElement; name: string } | undefined

    for (const id of svgIdsByView[view]) {
      const region = svg.querySelector<SVGGraphicsElement>(`[id="${prefix}${id}"]`)
      if (!region) continue
      const muscle = owners.get(id)
      if (!muscle) {
        region.style.color = '#40505e'
        region.removeAttribute('tabindex')
        region.removeAttribute('role')
        region.removeAttribute('aria-label')
        region.removeAttribute('aria-pressed')
        region.removeAttribute('data-map-tone')
        continue
      }
      region.style.color = fatigueColors[muscle.status]
      region.style.setProperty('--heat-opacity', String(muscleHeatOpacity(muscle.status, muscle.score)))
      region.setAttribute('role', 'button')
      region.setAttribute('tabindex', '0')
      region.setAttribute('aria-pressed', String(selected?.id === muscle.id))
      region.setAttribute('aria-label', `${muscle.name}: ${fatigueLabels[muscle.status]}${muscle.status === 'no_data' ? '' : `, ${muscle.score} из 100`}`)
      region.dataset.mapTone = muscle.status
      if (showCallout && selected && selectedRegions.includes(id) && !labelled) labelled = { region, name: selected.shortName }

      const showHint = (clientX: number, clientY: number) => {
        const rect = figure.getBoundingClientRect()
        const zone = region.getBoundingClientRect()
        const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16
        const width = Math.min(14 * rem, rect.width - 12)
        const height = 6.6 * rem
        const left = Math.max(6, Math.min(clientX - rect.left + 12, rect.width - width - 6))
        let top = Math.max(6, Math.min(clientY - rect.top + 14, rect.height - height - 6))
        if (rect.left + left < zone.right && rect.left + left + width > zone.left) {
          const below = zone.bottom - rect.top + 8
          const above = zone.top - rect.top - height - 8
          if (below + height <= rect.height - 6) top = below
          else if (above >= 6) top = above
        }
        setHint({ muscle, left, top })
      }
      const pointerHint = (event: PointerEvent) => {
        if (event.pointerType !== 'touch') showHint(event.clientX ?? 0, event.clientY ?? 0)
      }
      const select = () => { setHint(null); onSelect(muscle.id) }
      region.addEventListener('pointerenter', pointerHint, options)
      region.addEventListener('pointermove', pointerHint, options)
      region.addEventListener('pointerleave', () => setHint(null), options)
      region.addEventListener('focus', () => {
        if (!region.matches(':focus-visible')) return
        const rect = region.getBoundingClientRect()
        showHint(rect.right, rect.top)
      }, options)
      region.addEventListener('blur', () => setHint(null), options)
      region.addEventListener('click', select, options)
      region.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') setHint(null)
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          select()
        }
      }, options)
    }

    const positionLabel = () => {
      if (!labelled || !svg.createSVGPoint) return
      const { region, name } = labelled
      const matrix = region.getScreenCTM()
      if (!matrix) return
      const point = svg.createSVGPoint()
      if (region.dataset.anchor) {
        const [x, y] = region.dataset.anchor.split(' ').map(Number)
        point.x = x
        point.y = y
      } else {
        const box = (region.querySelector<SVGGraphicsElement>('path') ?? region).getBBox()
        point.x = box.x + box.width / 2
        point.y = box.y + box.height / 2
      }
      const screenPoint = point.matrixTransform(matrix)
      const bounds = figure.getBoundingClientRect()
      const x = screenPoint.x - bounds.left
      const y = screenPoint.y - bounds.top
      setCallout({ name, x, y, leftward: x > bounds.width * .69 })
    }
    positionLabel()
    const observer = typeof ResizeObserver !== 'undefined' && labelled ? new ResizeObserver(positionLabel) : null
    observer?.observe(figure)
    return () => { listeners.abort(); observer?.disconnect() }
  }, [markup, owners, selected, onSelect, view, title, showCallout, prefix])

  return (
    <figure ref={host} className="atlas-figure" onPointerLeave={() => setHint(null)}>
      <figcaption className="atlas-view-label">{title}</figcaption>
      <div className="atlas-stage">
        {markup ? <FigureArtwork markup={markup} /> : <p className="atlas-figure-state" role="status">{loadError ? 'Изображение недоступно' : 'Загрузка карты…'}</p>}
      </div>
      {callout && !hint && (
        <div aria-hidden="true" className="atlas-callout" data-leftward={callout.leftward || undefined} style={{ left: callout.x, top: callout.y }}>
          <span>{callout.name}</span>
        </div>
      )}
      {hint && (
        <div className="atlas-hint" role="tooltip" style={{ left: hint.left, top: hint.top, '--tone': fatigueColors[hint.muscle.status] } as CSSProperties}>
          <strong>{hint.muscle.name}</strong>
          <span>{fatigueLabels[hint.muscle.status]}</span>
          <small>{hint.muscle.status === 'no_data' ? 'Нет сохранённых данных о нагрузке' : `${hint.muscle.score} балл. усталости`}</small>
        </div>
      )}
    </figure>
  )
}
