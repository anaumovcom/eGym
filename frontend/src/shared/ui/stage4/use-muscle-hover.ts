import { useEffect, useRef } from 'react'
import { fatigueColors } from './fatigue-appearance'

export function useMuscleHover<T extends HTMLElement>() {
  const ref = useRef<T>(null)

  useEffect(() => {
    const host = ref.current
    if (!host) return

    // Paint above the heat mask so a resting muscle can also show an outline.
    const overlay = document.createElementNS('http://www.w3.org/2000/svg', 'g')
    overlay.setAttribute('class', 'muscle-hover-outline')
    overlay.setAttribute('aria-hidden', 'true')
    overlay.setAttribute('pointer-events', 'none')
    let hovered: SVGElement | null = null
    let focused: SVGElement | null = null
    let painted: SVGElement | null = null

    const regionAt = (target: EventTarget | null) => {
      if (!(target instanceof Element) || !host.contains(target)) return null
      const region = target.closest<SVGElement>('g[data-map-tone]')
      return region && Object.hasOwn(fatigueColors, region.dataset.mapTone ?? '') ? region : null
    }

    function paint() {
      const region = hovered ?? focused
      if (painted === region) return
      painted = region
      if (!region?.ownerSVGElement) {
        overlay.remove()
        return
      }
      const contours = Array.from(region.querySelectorAll('path:not([fill="none"]), ellipse'), shape => {
        const copy = shape.cloneNode(false) as SVGElement
        copy.removeAttribute('id')
        copy.removeAttribute('fill')
        return copy
      })
      overlay.replaceChildren(...contours)
      region.ownerSVGElement.append(overlay)
    }

    const events = new AbortController()
    const options = { signal: events.signal }
    function pointer(event: PointerEvent) {
      if (event.pointerType === 'touch') return
      hovered = regionAt(event.type === 'pointerout' ? event.relatedTarget : event.target)
      paint()
    }
    host.addEventListener('pointerover', pointer, options)
    host.addEventListener('pointermove', pointer, options)
    host.addEventListener('pointerout', pointer, options)
    host.addEventListener('pointercancel', () => { hovered = null; paint() }, options)
    host.addEventListener('focusin', (event) => {
      const region = regionAt(event.target)
      focused = region?.matches(':focus-visible') ? region : null
      paint()
    }, options)
    host.addEventListener('focusout', () => { focused = null; paint() }, options)
    return () => { events.abort(); overlay.remove() }
  }, [])

  return ref
}
