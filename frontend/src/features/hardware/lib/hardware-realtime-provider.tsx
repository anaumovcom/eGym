import { useEffect } from 'react'
import { buildWebSocketUrl } from '@/shared/api/client'
import { useHardwareStore } from '@/stores/hardware-store'
import { useAppStore } from '@/stores/app-store'
import type { HardwareSnapshot } from '@/features/hardware/model/types'

export function HardwareRealtimeProvider() {
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const loadSnapshot = useHardwareStore((state) => state.loadSnapshot)
  const setSnapshot = useHardwareStore((state) => state.setSnapshot)
  const setConnectionStatus = useHardwareStore((state) => state.setConnectionStatus)
  const setErrorMessage = useHardwareStore((state) => state.setErrorMessage)

  useEffect(() => {
    let socket: WebSocket | null = null
    let reconnectTimer: number | null = null
    let isDisposed = false
    const search = selectedUserId ? `?userId=${encodeURIComponent(selectedUserId)}` : ''

    void loadSnapshot(selectedUserId).catch(() => {
      setConnectionStatus('error')
    })

    function connect() {
      if (isDisposed) {
        return
      }

      setConnectionStatus('connecting')
      socket = new WebSocket(buildWebSocketUrl(`/api/hardware/realtime${search}`))

      socket.addEventListener('open', () => {
        setConnectionStatus('connected')
        setErrorMessage(null)
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
      })

      socket.addEventListener('close', () => {
        if (isDisposed) {
          return
        }

        setConnectionStatus('disconnected')
        reconnectTimer = window.setTimeout(connect, 1000)
      })
    }

    connect()

    return () => {
      isDisposed = true
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer)
      }
      socket?.close()
    }
  }, [loadSnapshot, selectedUserId, setConnectionStatus, setErrorMessage, setSnapshot])

  return null
}