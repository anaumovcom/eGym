import { act, cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAppStore } from '@/stores/app-store'
import { SelectedUserSync } from './providers'

vi.mock('@/features/hardware/lib/hardware-realtime-provider', () => ({ HardwareRealtimeProvider: () => null }))
vi.mock('@/features/scales/scale-realtime-provider', () => ({ ScaleRealtimeProvider: () => null }))

let fetchMock: ReturnType<typeof vi.fn>
beforeEach(() => {
  fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
  vi.stubGlobal('fetch', fetchMock)
  useAppStore.setState({ selectedUserId: null })
})
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('SelectedUserSync', () => {
  it('syncs real and guest users globally, but never clears selection for null', async () => {
    render(<SelectedUserSync />)
    expect(fetchMock).not.toHaveBeenCalled()
    for (const userId of ['alexey', 'guest', 'elena']) {
      act(() => useAppStore.setState({ selectedUserId: userId }))
      await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith('/api/users/select', expect.objectContaining({ method: 'POST', body: JSON.stringify({ userId }) })))
    }
    act(() => useAppStore.setState({ selectedUserId: null }))
    expect(fetchMock).toHaveBeenCalledTimes(3)
  })

  it('ignores backend selection errors for guests too', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('offline'))
    useAppStore.setState({ selectedUserId: 'guest' })
    render(<SelectedUserSync />)
    await act(async () => {})
    expect(fetchMock).toHaveBeenCalledWith('/api/users/select', expect.objectContaining({ body: JSON.stringify({ userId: 'guest' }) }))
  })
})