import { act, render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { HardwareRealtimeProvider } from '@/features/hardware/lib/hardware-realtime-provider'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'
import type { HardwareSnapshot } from '@/features/hardware/model/types'

class MockWebSocket {
  static instances: MockWebSocket[] = []

  readonly url: string
  private listeners = new Map<string, Array<(event?: Event | MessageEvent) => void>>()

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  addEventListener(type: string, listener: (event?: Event | MessageEvent) => void) {
    const current = this.listeners.get(type) ?? []
    current.push(listener)
    this.listeners.set(type, current)
  }

  close() {
    this.emit('close', new Event('close'))
  }

  emit(type: string, event?: Event | MessageEvent) {
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event)
    }
  }
}

function createSnapshot(): HardwareSnapshot {
  return {
    motion: {
      moving: true,
      motionProfile: 'training',
      barPositionMm: 920,
      leftPositionMm: 919.6,
      rightPositionMm: 920,
      syncDeltaMm: 0.4,
      amplitudePercent: 52,
      tempoLabel: 'стабилен',
      repetitionCount: 3,
      currentSet: 1,
      targetSet: 1,
      targetReps: 10,
      direction: 'up',
      lowerBoundMm: 640,
      upperBoundMm: 1320,
    },
    safety: {
      state: 'enabled',
      label: 'Готово',
      message: 'ok',
      requiresService: false,
      activeEventId: null,
    },
  } as HardwareSnapshot
}

describe('HardwareRealtimeProvider', () => {
  const originalWebSocket = globalThis.WebSocket

  beforeEach(() => {
    vi.useFakeTimers()
    MockWebSocket.instances = []
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket

    useAppStore.setState({
      selectedUserId: 'alexey',
      emergencyStopActive: false,
    })

    useHardwareStore.setState({
      snapshot: null,
      errorMessage: null,
      loadSnapshot: vi.fn().mockResolvedValue(createSnapshot()),
      runCommand: vi.fn(),
    })
  })

  it('polls snapshots until realtime connection is opened', async () => {
    const loadSnapshotMock = useHardwareStore.getState().loadSnapshot as ReturnType<typeof vi.fn>

    render(<HardwareRealtimeProvider />)

    expect(loadSnapshotMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      vi.advanceTimersByTime(1200)
    })

    expect(loadSnapshotMock.mock.calls.length).toBeGreaterThanOrEqual(3)

    const callsBeforeOpen = loadSnapshotMock.mock.calls.length

    await act(async () => {
      MockWebSocket.instances[0]?.emit('open', new Event('open'))
      vi.advanceTimersByTime(1200)
    })

    expect(loadSnapshotMock).toHaveBeenCalledTimes(callsBeforeOpen)
  })
})