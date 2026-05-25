import { useEffect } from 'react'
import { buildWebSocketUrl } from '@/shared/api/client'
import { useHardwareStore } from '@/stores/hardware-store'
import { useAppStore } from '@/stores/app-store'
import type { HardwareSnapshot } from '@/features/hardware/model/types'

const HARDWARE_SNAPSHOT_POLL_INTERVAL_MS = 500

export function HardwareRealtimeProvider() {
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const loadSnapshot = useHardwareStore((state) => state.loadSnapshot)
  const setSnapshot = useHardwareStore((state) => state.setSnapshot)
  const setConnectionStatus = useHardwareStore((state) => state.setConnectionStatus)
  const setErrorMessage = useHardwareStore((state) => state.setErrorMessage)
  const runCommand = useHardwareStore((state) => state.runCommand)
  const snapshot = useHardwareStore((state) => state.snapshot)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)

  useEffect(() => {
    let socket: WebSocket | null = null
    let reconnectTimer: number | null = null
    let snapshotPollTimer: number | null = null
    let isDisposed = false
    const search = selectedUserId ? `?userId=${encodeURIComponent(selectedUserId)}` : ''

    function stopSnapshotPolling() {
      if (snapshotPollTimer !== null) {
        window.clearInterval(snapshotPollTimer)
        snapshotPollTimer = null
      }
    }

    function refreshSnapshot() {
      return loadSnapshot(selectedUserId).catch(() => {
        setConnectionStatus('error')
      })
    }

    function startSnapshotPolling() {
      if (snapshotPollTimer !== null) {
        return
      }

      snapshotPollTimer = window.setInterval(() => {
        void refreshSnapshot()
      }, HARDWARE_SNAPSHOT_POLL_INTERVAL_MS)
    }

    void refreshSnapshot()

    function connect() {
      if (isDisposed) {
        return
      }

      setConnectionStatus('connecting')
      startSnapshotPolling()
      socket = new WebSocket(buildWebSocketUrl(`/api/hardware/realtime${search}`))

      socket.addEventListener('open', () => {
        setConnectionStatus('connected')
        setErrorMessage(null)
        stopSnapshotPolling()
      })

      socket.addEventListener('message', (event) => {
        try {
          const payload = JSON.parse(event.data) as HardwareSnapshot
          setSnapshot(payload)
        } catch {
          setConnectionStatus('error')
          setErrorMessage('Не удалось разобрать realtime сообщение hardware.')
        }
      })

      socket.addEventListener('error', () => {
        setConnectionStatus('error')
        setErrorMessage('Поток realtime hardware недоступен.')
        startSnapshotPolling()
      })

      socket.addEventListener('close', () => {
        if (isDisposed) {
          return
        }

        setConnectionStatus('disconnected')
        startSnapshotPolling()
        reconnectTimer = window.setTimeout(connect, 1000)
      })
    }

    connect()

    return () => {
      isDisposed = true
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer)
      }
      stopSnapshotPolling()
      socket?.close()
    }
  }, [loadSnapshot, selectedUserId, setConnectionStatus, setErrorMessage, setSnapshot])

  useEffect(() => {
    if (!emergencyStopActive) {
      return
    }

    if (snapshot?.safety.state === 'emergency_stop') {
      return
    }

    void runCommand({ action: 'trigger_emergency_stop', userId: selectedUserId }).catch(() => {
      setConnectionStatus('error')
    })
  }, [emergencyStopActive, runCommand, selectedUserId, setConnectionStatus, snapshot?.safety.state])

  return null
}