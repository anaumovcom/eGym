import { useEffect, useId, useMemo, useState } from 'react'
import { useAppStore } from '@/stores/app-store'
import type { BodyMapView } from './fatigue-muscle-map'

export type FigureGender = 'male' | 'female'
const figures = new Map<string, Promise<string>>()

function loadFigure(path: string) {
  const cached = figures.get(path)
  if (cached) return cached

  const request = fetch(path)
    .then(async (response) => {
      if (!response.ok) throw new Error(path)
      const svg = await response.text()
      if (!svg.trimStart().startsWith('<svg')) throw new Error(path)
      return svg
    })
    .catch((error: unknown) => {
      figures.delete(path)
      throw error
    })
  figures.set(path, request)
  return request
}

// Inline each local illustration so its regions can be labelled, coloured and focused.
// Its gradients, masks and mirrored paths need unique references on every instance.
function scopeFigure(svg: string, prefix: string) {
  return svg
    .replace(/\sclass="([^"]*)"/g, (_, classes: string) => {
      const kept = classes.split(/\s+/).filter((name) => name !== 'bodymap' && !/^(?:text-mw-|active:text-mw-|lg:hover:text-mw-)/.test(name))
      return kept.length ? ` class="${kept.join(' ')}"` : ''
    })
    .replace(/\bid="([^"]+)"/g, `id="${prefix}$1"`)
    .replace(/url\(#([^)]+)\)/g, `url(#${prefix}$1)`)
    .replace(/href="#([^"]+)"/g, `href="#${prefix}$1"`)
}

export function useBodyFigure(view: BodyMapView, gender?: FigureGender, userId?: string | null) {
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const profile = userId === undefined ? selectedUserId : userId
  const figureGender = gender ?? (profile === 'elena' ? 'female' : 'male')
  const prefix = `figure-${useId().replace(/[^\w-]/g, '')}-`
  const path = profile === 'alexey' && figureGender === 'male'
    ? `/fatigue-atlas/alexey-${view}.svg?v=6`
    : `/${figureGender}-muscles-${view}.svg`
  const [loaded, setLoaded] = useState<{ path: string; svg: string | null }>()
  useEffect(() => {
    let active = true
    void loadFigure(path).then(
      (svg) => { if (active) setLoaded({ path, svg }) },
      () => { if (active) setLoaded({ path, svg: null }) },
    )
    return () => { active = false }
  }, [path])
  const svg = loaded?.path === path ? loaded.svg : undefined
  const markup = useMemo(() => svg ? scopeFigure(svg, prefix) : null, [svg, prefix])
  return { markup, prefix, loadError: svg === null }
}
