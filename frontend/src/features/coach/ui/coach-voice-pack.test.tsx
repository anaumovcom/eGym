import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CoachPackClient, type PackSnapshot } from '../audio/pack-client'
import { CoachVoicePackSection } from './coach-voice-pack'

afterEach(cleanup)

function fakeClient(initial: Partial<PackSnapshot> = {}) {
  const client = new CoachPackClient({ fetch: vi.fn(), openCache: async () => null, deleteCache: vi.fn(async () => {}), context: () => null })
  let value: PackSnapshot = { ...client.snapshot(), ...initial }
  const listeners = new Set<() => void>()
  const set = (next: Partial<PackSnapshot>) => { value = { ...value, ...next }; listeners.forEach(listener => listener()) }
  Object.defineProperty(client, 'snapshot', { value: () => value })
  Object.defineProperty(client, 'subscribe', { value: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener) } })
  const prepare = vi.spyOn(client, 'prepare').mockImplementation(async slot => { set({ slot, state: 'ready', prepared: 54, required: 54, optional: 0, encodedBytes: 3 * 1024 * 1024, unapproved: 2 }); return value })
  const remove = vi.spyOn(client, 'deleteLocal').mockImplementation(async () => { set({ state: 'not_prepared', prepared: 0, required: 0, encodedBytes: 0 }) })
  return { client, prepare, remove, set }
}

describe('CoachVoicePackSection', () => {
  it('needs a selected voice and never prepares on mount', () => {
    const f = fakeClient()
    render(<CoachVoicePackSection slot={null} client={f.client} />)
    expect(screen.getByText(/Выберите голос/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Подготовить частые фразы' })).toBeDisabled()
    expect(f.prepare).not.toHaveBeenCalled()
    expect(screen.getByText(/создаёт оператор отдельной платной задачей/)).toBeInTheDocument()
  })

  it('prepares only on click and shows progress, size and pending safety approval', async () => {
    const f = fakeClient()
    render(<CoachVoicePackSection slot="female" client={f.client} />)
    expect(screen.getByTestId('coach-pack-status')).toHaveTextContent('Не подготовлено')
    fireEvent.click(screen.getByRole('button', { name: 'Подготовить частые фразы' }))
    await waitFor(() => expect(screen.getByTestId('coach-pack-status')).toHaveTextContent('Готово · Подготовлено 54/54 · 3.0 MB'))
    expect(screen.getByTestId('coach-pack-status')).toHaveTextContent('фраз безопасности ждут прослушивания: 2')
    expect(f.prepare).toHaveBeenCalledWith('female')
    fireEvent.click(screen.getByRole('button', { name: 'Удалить локальные файлы' }))
    await waitFor(() => expect(f.remove).toHaveBeenCalledOnce())
    expect(screen.getByTestId('coach-pack-status')).toHaveTextContent('Не подготовлено')
  })

  it('does not show another voice pack as prepared', () => {
    const f = fakeClient({ slot: 'female', state: 'ready', prepared: 54, required: 54 })
    render(<CoachVoicePackSection slot="male" client={f.client} />)
    expect(screen.getByTestId('coach-pack-status')).toHaveTextContent('Не подготовлено')
    expect(screen.getByTestId('coach-pack-status')).not.toHaveTextContent('54')
    act(() => f.set({ slot: 'male', state: 'failed', reason: 'no_audio', prepared: 0, required: 0 }))
    expect(screen.getByTestId('coach-pack-status')).toHaveTextContent('Ошибка подготовки · звук браузера недоступен')
  })
})
