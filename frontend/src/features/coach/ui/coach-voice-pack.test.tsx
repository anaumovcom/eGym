import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CoachPackClient, type PackSnapshot, type PackClipEntry } from '../audio/pack-client'
import { CoachVoicePackSection } from './coach-voice-pack'
import { generateCoachPack, recordStarterClip } from '../audio/pack-generation'
import { previewPackClip } from '../audio/pack-preview'

vi.mock('../audio/pack-generation', () => ({ generateCoachPack: vi.fn(), recordStarterClip: vi.fn(), approveCoachClip: vi.fn() }))
vi.mock('../audio/pack-preview', () => ({ previewPackClip: vi.fn() }))

afterEach(() => { cleanup(); vi.clearAllMocks() })

function fakeClient(initial: Partial<PackSnapshot> = {}) {
  const client = new CoachPackClient({ fetch: vi.fn(), openCache: async () => null, deleteCache: vi.fn(async () => {}), context: () => null })
  let value: PackSnapshot = { ...client.snapshot(), ...initial }
  const version = '0000000000000001'
  const entry = (text: string): PackClipEntry => ({ text, group: 'count', sha256: 'a'.repeat(64), fingerprint: 'a'.repeat(64), durationMs: 300, bytes: 12000, required: true, approved: true, sampleRate: 8000 })
  vi.spyOn(client, 'installed').mockImplementation(slot => slot && slot === value.slot && value.state === 'ready' ? { slot: value.slot!, packVersion: version,
    complete: true, missingClips: 0, clips: { 'count-1': entry('Раз.'), 'count-2': entry('Два.') } } : null)
  const listeners = new Set<() => void>()
  const set = (next: Partial<PackSnapshot>) => { value = { ...value, ...next }; listeners.forEach(listener => listener()) }
  Object.defineProperty(client, 'snapshot', { value: () => value })
  Object.defineProperty(client, 'subscribe', { value: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener) } })
  const prepare = vi.spyOn(client, 'prepare').mockImplementation(async slot => { set({ slot, state: 'ready', prepared: 54, required: 54, optional: 0, encodedBytes: 3 * 1024 * 1024, unapproved: 2 }); return value })
  const remove = vi.spyOn(client, 'deleteLocal').mockImplementation(async () => { set({ state: 'not_prepared', prepared: 0, required: 0, encodedBytes: 0 }) })
  const restore = vi.spyOn(client, 'restore').mockImplementation(async () => value)
  return { client, prepare, remove, restore, set }
}

describe('CoachVoicePackSection', () => {
  it('restores the selected cached pack after reload without paid generation or manual preparation', async () => {
    const f = fakeClient()
    f.restore.mockImplementationOnce(async slot => {
      f.set({ slot, state: 'ready', prepared: 56, required: 56 })
      return f.client.snapshot()
    })
    render(<CoachVoicePackSection slot="fish-streamer" client={f.client} />)
    await waitFor(() => expect(screen.getByTestId('coach-pack-status')).toHaveTextContent('Готово к воспроизведению: 56/56'))
    expect(f.restore).toHaveBeenCalledWith('fish-streamer', { signal: expect.any(AbortSignal) })
    expect(f.prepare).not.toHaveBeenCalled()
  })

  it('offers explicit capped generation for a missing pack and then downloads it', async () => {
    const f = fakeClient()
    f.prepare.mockImplementationOnce(async slot => ({ ...f.client.snapshot(), slot, reason: 'no_pack' }))
    vi.mocked(generateCoachPack).mockImplementationOnce(async (_slot, _user, _cap, _signal, progress) => { progress(4, 56) })
    render(<CoachVoicePackSection slot="fish-streamer" userId="alexey" budgetUsd="0.50" client={f.client} />)
    expect(generateCoachPack).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Скачать голосовой пакет' }))
    const create = await screen.findByRole('button', { name: 'Создать недостающие фразы (до 0.50 $)' })
    expect(generateCoachPack).not.toHaveBeenCalled()
    fireEvent.click(create)
    await waitFor(() => expect(generateCoachPack).toHaveBeenCalledWith('fish-streamer', 'alexey', '0.50', expect.any(AbortSignal), expect.any(Function), undefined))
    await waitFor(() => expect(f.prepare).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole('button', { name: /Создать недостающие/ })).not.toBeInTheDocument()
  })

  it('shows actionable generation errors instead of an unhandled rejection', async () => {
    const f = fakeClient()
    f.prepare.mockImplementationOnce(async slot => ({ ...f.client.snapshot(), slot, reason: 'no_pack' }))
    vi.mocked(generateCoachPack).mockRejectedValueOnce(new Error('Войдите в доступ оператора'))
    render(<CoachVoicePackSection slot="fish-streamer" userId="alexey" client={f.client} />)
    fireEvent.click(screen.getByRole('button', { name: 'Скачать голосовой пакет' }))
    fireEvent.click(await screen.findByRole('button', { name: /Создать недостающие/ }))
    expect(await screen.findByText('Войдите в доступ оператора')).toBeInTheDocument()
  })

  it('aborts paid preparation when the selected voice changes', async () => {
    const f = fakeClient()
    f.prepare.mockImplementationOnce(async slot => ({ ...f.client.snapshot(), slot, reason: 'no_pack' }))
    let signal: AbortSignal | undefined
    vi.mocked(generateCoachPack).mockImplementationOnce(async (_slot, _user, _cap, abort) => {
      signal = abort
      await new Promise<void>(resolve => abort.addEventListener('abort', () => resolve(), { once: true }))
    })
    const view = render(<CoachVoicePackSection slot="fish-streamer" userId="alexey" client={f.client} />)
    fireEvent.click(screen.getByRole('button', { name: 'Скачать голосовой пакет' }))
    fireEvent.click(await screen.findByRole('button', { name: /Создать недостающие/ }))
    await waitFor(() => expect(signal).toBeDefined())
    view.rerender(<CoachVoicePackSection slot="tts-ash" userId="alexey" client={f.client} />)
    expect(signal?.aborted).toBe(true)
    expect(screen.queryByRole('button', { name: /Создать недостающие/ })).not.toBeInTheDocument()
  })

  it('needs a selected voice and never prepares on mount', () => {
    const f = fakeClient()
    render(<CoachVoicePackSection slot={null} client={f.client} />)
    expect(screen.getByText(/Выберите и сохраните голос/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Скачать голосовой пакет' })).not.toBeInTheDocument()
    expect(f.prepare).not.toHaveBeenCalled()
  })

  it('prepares only on click and shows progress, size and pending safety approval', async () => {
    const f = fakeClient()
    render(<CoachVoicePackSection slot="ash" client={f.client} />)
    expect(screen.getByTestId('coach-pack-status')).toHaveTextContent('Не скачан')
    fireEvent.click(screen.getByRole('button', { name: 'Скачать голосовой пакет' }))
    await waitFor(() => expect(screen.getByTestId('coach-pack-status')).toHaveTextContent('Готово к воспроизведению: 54/54 · 3.0 МБ'))
    expect(screen.getByTestId('coach-pack-status')).toHaveTextContent('На проверке: 2')
    expect(f.prepare).toHaveBeenCalledWith('ash', expect.any(AbortSignal))
    fireEvent.click(screen.getByRole('button', { name: 'Удалить с устройства' }))
    await waitFor(() => expect(f.remove).toHaveBeenCalledOnce())
    expect(screen.getByTestId('coach-pack-status')).toHaveTextContent('Не скачан')
  })

  it('does not show another voice pack as prepared', () => {
    const f = fakeClient({ slot: 'ash', state: 'ready', prepared: 54, required: 54 })
    render(<CoachVoicePackSection slot="cedar" client={f.client} />)
    expect(screen.getByTestId('coach-pack-status')).toHaveTextContent('Не скачан')
    expect(screen.getByTestId('coach-pack-status')).not.toHaveTextContent('54')
    act(() => f.set({ slot: 'cedar', state: 'failed', reason: 'no_audio', prepared: 0, required: 0 }))
    expect(screen.getByTestId('coach-pack-status')).toHaveTextContent('Не удалось установить пакет · звук в браузере недоступен')
  })

  it.each(['ru-base', 'ash'] as const)('auditions the actual selected clip locally; replaces only that clip after confirmation (%s)', async slot => {
    const f = fakeClient({ slot, state: 'ready' })
    vi.mocked(previewPackClip).mockResolvedValue(true)
    render(<CoachVoicePackSection slot={slot} client={f.client} budgetUsd="1.00" userId="u" />)
    fireEvent.change(screen.getByLabelText(/Фраза пакета/), { target: { value: 'count-2' } })
    fireEvent.click(screen.getByRole('button', { name: 'Прослушать' }))
    await waitFor(() => expect(previewPackClip).toHaveBeenCalledWith(f.client, slot, 'count-2', 1, expect.any(AbortSignal)))
    expect(f.prepare).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Перегенерировать фразу' }))
    expect(screen.getByRole('group', { name: 'Подтверждение замены' })).toHaveTextContent('«Два.»')
    expect(generateCoachPack).not.toHaveBeenCalled(); expect(recordStarterClip).not.toHaveBeenCalled()
    if (slot === 'ru-base') fireEvent.change(screen.getByLabelText(/Темп новой записи/), { target: { value: 'slow' } })
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить замену' }))
    const target = { clipId: 'count-2', expectedPackVersion: '0000000000000001' }
    if (slot === 'ru-base') {
      expect(recordStarterClip).toHaveBeenCalledWith(target, 'slow', expect.any(AbortSignal)); expect(generateCoachPack).not.toHaveBeenCalled()
    } else expect(generateCoachPack).toHaveBeenCalledWith(slot, 'u', '1.00', expect.any(AbortSignal), expect.any(Function), target)
    await waitFor(() => expect(f.prepare).toHaveBeenCalledOnce())
  })
})
