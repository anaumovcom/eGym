import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { runHardwareCommand } from '@/features/hardware/api/hardware-api'
import { HoldToJog } from '@/features/hardware/ui/hold-to-jog'
import { useHardwareStore } from '@/stores/hardware-store'

vi.mock('@/features/hardware/api/hardware-api', () => ({ runHardwareCommand: vi.fn() }))

describe('HoldToJog', () => {
  const send = vi.fn().mockResolvedValue({})

  beforeEach(() => {
    vi.useFakeTimers()
    send.mockClear()
    vi.mocked(runHardwareCommand).mockReset().mockResolvedValue({} as never)
    useHardwareStore.setState({ runCommand: send, setErrorMessage: vi.fn() })
  })

  afterEach(() => vi.useRealTimers())

  it('sends heartbeat while pressed and stops on release', async () => {
    render(<HoldToJog userId="alexey" exerciseSlug="barbell-floor-press" />)
    const up = screen.getByRole('button', { name: '↑ Вверх · удерживать' })
    fireEvent.pointerDown(up, { pointerType: 'mouse', button: 0, pointerId: 1 })
    await act(async () => { await Promise.resolve() })
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ action: 'jog_start', direction: 'up' }))
    await act(async () => { vi.advanceTimersByTime(410); await Promise.resolve() })
    expect(runHardwareCommand).toHaveBeenCalledWith(expect.objectContaining({ action: 'jog_keepalive', jogId: expect.any(String) }))
    fireEvent.pointerUp(up, { pointerType: 'mouse', pointerId: 1 })
    await act(async () => { await Promise.resolve() })
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ action: 'jog_stop', jogId: send.mock.calls[0][0].jogId }))
    const count = vi.mocked(runHardwareCommand).mock.calls.length
    await act(async () => { vi.advanceTimersByTime(1000) })
    expect(runHardwareCommand).toHaveBeenCalledTimes(count)
  })

  it('stops even if released before the start response arrives', async () => {
    let resolveStart!: (value: object) => void
    send.mockImplementationOnce(() => new Promise((resolve) => { resolveStart = resolve }))
    render(<HoldToJog userId="alexey" exerciseSlug="barbell-floor-press" />)
    const down = screen.getByRole('button', { name: '↓ Вниз · удерживать' })
    fireEvent.pointerDown(down, { pointerType: 'mouse', button: 0, pointerId: 1 })
    fireEvent.pointerUp(down, { pointerType: 'mouse', pointerId: 1 })
    expect(send).toHaveBeenCalledTimes(1)
    await act(async () => { resolveStart({}); await Promise.resolve() })
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ action: 'jog_stop' }))
  })

  it('stops on window blur', async () => {
    render(<HoldToJog userId="alexey" exerciseSlug="barbell-floor-press" />)
    fireEvent.pointerDown(screen.getByRole('button', { name: '↑ Вверх · удерживать' }), { pointerType: 'mouse', button: 0, pointerId: 1 })
    await act(async () => { await Promise.resolve() })
    fireEvent(window, new Event('blur'))
    await act(async () => { await Promise.resolve() })
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ action: 'jog_stop' }))
  })
})