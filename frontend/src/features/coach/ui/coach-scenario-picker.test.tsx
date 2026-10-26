import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import * as Dialog from '@radix-ui/react-dialog'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { coachNetworkClient } from '../live/coach-live-runtime'
import type { NetworkSnapshot, ScenarioView } from '../live/coach-network-client'
import { CoachScenarioChip, CoachScenarioPicker } from './coach-scenario-picker'

const base: ScenarioView = { phase: 'choosing', cards: [
  { archetype: 'race', title: 'Гонка героев', tagline: 'Заезд за заездом', tone: 'дерзко' },
  { archetype: 'rpg', title: 'Боссфайт', tagline: 'Победи босса', tone: 'эпично' },
  { archetype: 'space', title: 'Орбита', tagline: 'Старт к звёздам', tone: 'торжественно' }],
  proposalsLeft: 2, title: null, tagline: null, archetype: null, acts: [], counters: [], coHost: null, error: null }

function mock(scenario: ScenarioView, patch: Partial<NetworkSnapshot> = {}) {
  const snapshot = { ...coachNetworkClient.getSnapshot(), scenario, ...patch } as NetworkSnapshot
  return vi.spyOn(coachNetworkClient, 'getSnapshot').mockReturnValue(snapshot)
}
afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('CoachScenarioPicker', () => {
  it('positions preparation below the actual compact safety dock', () => {
    mock({ ...base, phase: 'building' })
    const dock = document.createElement('header')
    dock.className = 'forma-system-dock'
    dock.getBoundingClientRect = () => ({ bottom: 180 } as DOMRect)
    document.body.append(dock)
    try {
      render(<CoachScenarioPicker />)
      expect(screen.getByRole('dialog')).toHaveStyle({ top: '196px' })
    } finally { dock.remove() }
  })
  it.each(['waiting', 'proposing', 'building'] as const)('shows a clear loading panel during %s without a fake percentage or ETA', phase => {
    mock({ ...base, phase, title: phase === 'building' ? 'Орбита' : null })
    render(<CoachScenarioPicker />)
    expect(screen.getByRole('dialog', { name: 'Готовим тренировку' })).toBeInTheDocument()
    expect(screen.getByText('Варианты сюжета')).toBeInTheDocument()
    expect(screen.getByText('Сценарий тренировки')).toBeInTheDocument()
    expect(screen.getByText('Озвучка упражнения')).toBeInTheDocument()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
    expect(screen.getByRole('dialog').textContent).not.toMatch(/%|осталось.*сек/i)
    if (phase === 'building') expect(screen.getByText('Орбита')).toBeInTheDocument()
  })

  it('does not close when the story is ready but voice preloading is still running; only explicit continue skips', () => {
    const scenario = { ...base, phase: 'ready' as const, title: 'Орбита' }
    const preparation = { state: 'preparing' as const, exerciseId: 'e1', completed: 3, total: 8, ready: 2 }
    const spy = mock(scenario, { preparation })
    const skip = vi.spyOn(coachNetworkClient, 'skipScenario').mockImplementation(() => undefined)
    const { rerender } = render(<CoachScenarioPicker />)
    expect(screen.getByRole('dialog')).not.toHaveAttribute('aria-modal', 'true')
    expect(screen.getByText('Обработано реплик: 3 из 8')).toBeInTheDocument()
    expect(screen.getByText('Готово к воспроизведению: 2')).toBeInTheDocument()
    expect(screen.getByText('Орбита')).toBeInTheDocument()
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    fireEvent.pointerDown(document.body)
    expect(skip).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Продолжить без ожидания' }))
    expect(skip).toHaveBeenCalledOnce()
    spy.mockReturnValue({ ...coachNetworkClient.getSnapshot(), preparation: { ...preparation, state: 'ready', completed: 8, ready: 8 } })
    rerender(<CoachScenarioPicker />)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows zero-total preparation without inventing a percentage', () => {
    mock({ ...base, phase: 'ready' }, { preparation: { state: 'preparing', exerciseId: null, completed: 0, total: 0, ready: 0 } })
    render(<CoachScenarioPicker />)
    expect(screen.getByText('Составляем список голосовых реплик')).toBeInTheDocument()
    expect(screen.getByText('Готово к воспроизведению: 0')).toBeInTheDocument()
  })

  it('yields to safety dialogs without skipping, then resumes preparation', () => {
    mock({ ...base, phase: 'ready' }, { preparation: { state: 'preparing', exerciseId: 'e1', completed: 1, total: 5, ready: 1 } })
    const skip = vi.spyOn(coachNetworkClient, 'skipScenario').mockImplementation(() => undefined)
    function View({ safety }: { safety: boolean }) {
      return <><CoachScenarioPicker /><Dialog.Root open={safety}><Dialog.Portal><SafetyDialogContent>
        <Dialog.Title>Безопасность</Dialog.Title><Dialog.Description>Управление остановкой</Dialog.Description>
      </SafetyDialogContent></Dialog.Portal></Dialog.Root></>
    }
    const { rerender } = render(<View safety={false} />)
    expect(screen.getByRole('dialog', { name: 'Готовим тренировку' })).toBeInTheDocument()
    rerender(<View safety />)
    expect(screen.queryByRole('dialog', { name: 'Готовим тренировку' })).not.toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: 'Безопасность' })).toBeInTheDocument()
    expect(skip).not.toHaveBeenCalled()
    rerender(<View safety={false} />)
    expect(screen.getByRole('dialog', { name: 'Готовим тренировку' })).toBeInTheDocument()
  })

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
