import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CoachEpisodeCard, parseEpisode } from './coach-episode'

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.unstubAllEnvs() })

describe('CoachEpisodeCard', () => {
  it('parses only bounded fields', () => {
    expect(parseEpisode({ title: 'Финал', highlights: ['Раз', 7], finale: 'Конец', achievements: [{ id: 'plan', label: 'Весь план' }, {}],
      source: 'generated' })).toEqual({ title: 'Финал', highlights: ['Раз'], finale: 'Конец', achievements: [{ id: 'plan', label: 'Весь план' }],
      source: 'generated' })
    expect(parseEpisode({ title: 'x', highlights: [], finale: 'y' })).toBeNull()
  })
  it('shows the recap with achievements for the finished workout', async () => {
    vi.stubEnv('VITE_COACH_ENABLED', 'true')
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ title: 'Финал сезона', highlights: ['Десять повторений в копилку'],
      finale: 'Занавес, овации.', achievements: [{ id: 'record', label: 'Новый личный рекорд' }], source: 'generated' })))
    vi.stubGlobal('fetch', fetchMock)
    render(<CoachEpisodeCard workoutId={42} userId="alexey" />)
    expect(await screen.findByRole('heading', { name: 'Финал сезона' })).toBeInTheDocument()
    expect(screen.getByText('Десять повторений в копилку')).toBeInTheDocument()
    expect(screen.getByText('Новый личный рекорд')).toBeInTheDocument()
    expect((fetchMock.mock.calls[0] as unknown as [string])[0]).toBe('/api/coach/workouts/42/episode?userId=alexey')
  })
  it('stays hidden without the coach feature or a saved workout', () => {
    vi.stubGlobal('fetch', vi.fn())
    const { container } = render(<CoachEpisodeCard workoutId={undefined} userId="alexey" />)
    expect(container).toBeEmptyDOMElement()
  })
})
