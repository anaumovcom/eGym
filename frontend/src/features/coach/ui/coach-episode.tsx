import { Award, Clapperboard } from 'lucide-react'
import { useEffect, useState } from 'react'
import './coach-scenario.css'

/** V11: the workout's story recap — title, highlights from facts, the finale and computed achievements. */
export type CoachEpisode = Readonly<{
  title: string; highlights: readonly string[]; finale: string
  achievements: readonly Readonly<{ id: string; label: string }>[]; source: 'generated' | 'local'
}>

const POLL_MS = 4_000
const POLL_LIMIT = 15
const text = (value: unknown, max: number) => typeof value === 'string' && value.length <= max ? value : null

export function parseEpisode(value: unknown): CoachEpisode | null {
  if (!value || typeof value !== 'object') return null
  const raw = value as Record<string, unknown>
  const title = text(raw.title, 80), finale = text(raw.finale, 240)
  const highlights = Array.isArray(raw.highlights) ? raw.highlights.flatMap(item => { const t = text(item, 200); return t ? [t] : [] }).slice(0, 5) : []
  const achievements = Array.isArray(raw.achievements) ? raw.achievements.flatMap(item => {
    const entry = item && typeof item === 'object' ? item as Record<string, unknown> : {}
    const id = text(entry.id, 16), label = text(entry.label, 60)
    return id && label ? [{ id, label }] : []
  }).slice(0, 7) : []
  if (!title || !finale || !highlights.length) return null
  return { title, finale, highlights, achievements, source: raw.source === 'generated' ? 'generated' : 'local' }
}

export function CoachEpisodeCard({ workoutId, userId }: { workoutId: number | undefined; userId: string | null }) {
  const [episode, setEpisode] = useState<CoachEpisode | null>(null)
  useEffect(() => {
    if (import.meta.env.VITE_COACH_ENABLED !== 'true' || !workoutId || !userId || !/^[a-zA-Z0-9_-]{1,120}$/.test(userId)) return
    const controller = new AbortController()
    let polls = 0
    let timer: ReturnType<typeof setTimeout> | null = null
    const load = () => {
      polls++
      fetch(`/api/coach/workouts/${workoutId}/episode?userId=${encodeURIComponent(userId)}`, { credentials: 'include',
        signal: controller.signal, headers: { Accept: 'application/json' } })
        .then(response => response.ok ? response.json() : null)
        .then(value => {
          const parsed = parseEpisode(value)
          if (parsed) setEpisode(parsed)
          // The coach writes the story right after the summary line; until then the facts template shows.
          if (parsed?.source !== 'generated' && polls < POLL_LIMIT) timer = setTimeout(load, POLL_MS)
        }, () => undefined)
    }
    load()
    return () => { controller.abort(); if (timer) clearTimeout(timer) }
  }, [workoutId, userId])
  if (!episode) return null
  return <section className="coach-episode" aria-label="Эпизод тренировки">
    <header><Clapperboard aria-hidden="true" /><h2>{episode.title}</h2></header>
    <ul>{episode.highlights.map(item => <li key={item}>{item}</li>)}</ul>
    <p className="coach-episode-finale">{episode.finale}</p>
    {episode.achievements.length > 0 && <div className="coach-episode-achievements" role="list" aria-label="Достижения">
      {episode.achievements.map(item => <span key={item.id} role="listitem" data-achievement={item.id}><Award aria-hidden="true" />{item.label}</span>)}
    </div>}
  </section>
}
