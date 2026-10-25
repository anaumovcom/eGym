import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { coachNetworkClient } from '../live/coach-live-runtime'
import type { NetworkSnapshot, ScenarioView } from '../live/coach-network-client'
import { CoachScenarioChip, CoachScenarioPicker } from './coach-scenario-picker'

const base: ScenarioView = { phase: 'choosing', cards: [
  { archetype: 'race', title: 'Гонка героев', tagline: 'Заезд за заездом', tone: 'дерзко' },
  { archetype: 'rpg', title: 'Боссфайт', tagline: 'Победи босса', tone: 'эпично' },
  { archetype: 'space', title: 'Орбита', tagline: 'Старт к звёздам', tone: 'торжественно' }],
  proposalsLeft: 2, title: null, tagline: null, archetype: null, acts: [], counters: [], coHost: null, error: null }

function mock(scenario: ScenarioView) {
  const snapshot = { ...coachNetworkClient.getSnapshot(), scenario } as NetworkSnapshot
  return vi.spyOn(coachNetworkClient, 'getSnapshot').mockReturnValue(snapshot)
}
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('CoachScenarioPicker', () => {
  it('shows three cards, picks one, offers new variants and a no-story exit', () => {
    mock(base)
    const select = vi.spyOn(coachNetworkClient, 'selectScenario').mockImplementation(() => undefined)
    const propose = vi.spyOn(coachNetworkClient, 'proposeScenarios').mockImplementation(() => undefined)
    const skip = vi.spyOn(coachNetworkClient, 'skipScenario').mockImplementation(() => undefined)
    render(<CoachScenarioPicker />)
    expect(screen.getByRole('dialog', { name: 'Выберите сюжет тренировки' })).toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    fireEvent.click(screen.getByRole('button', { name: /Боссфайт/ }))
    expect(select).toHaveBeenCalledWith(1)
    fireEvent.click(screen.getByRole('button', { name: 'Другие варианты (2)' }))
    expect(propose).toHaveBeenCalled()
    act(() => { fireEvent.click(screen.getByRole('button', { name: 'Без сценария' })) })
    expect(skip).toHaveBeenCalled()
  })
  it('stays closed when no choice is pending and explains failures', () => {
    const spy = mock({ ...base, phase: 'ready' })
    const { rerender } = render(<CoachScenarioPicker />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    spy.mockReturnValue({ ...coachNetworkClient.getSnapshot(), scenario: { ...base, phase: 'failed', error: 'budget', proposalsLeft: 0 } } as NetworkSnapshot)
    rerender(<CoachScenarioPicker key="failed" />)
    expect(screen.getByText('Не хватает бюджета тренировки на сценарий.')).toBeInTheDocument()
  })
})

describe('CoachScenarioChip', () => {
  it('names the story, the act of this exercise and counter values', () => {
    mock({ ...base, phase: 'ready', title: 'Боссфайт', archetype: 'rpg', acts: [{ act: 1, title: 'Подземелье', exerciseIds: ['e1'] },
      { act: 2, title: 'Босс', exerciseIds: ['e2'] }], counters: [{ id: 'c1', label: 'урон боссу', value: 120 }] })
    render(<CoachScenarioChip exerciseId="e2" />)
    expect(screen.getByText('Боссфайт · Акт 2/2: Босс')).toBeInTheDocument()
    expect(screen.getByText('урон боссу: 120')).toBeInTheDocument()
  })
})
