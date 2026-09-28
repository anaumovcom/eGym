import { useEffect, useRef, useState } from 'react'
import { runHardwareCommand } from '@/features/hardware/api/hardware-api'
import { Button } from '@/shared/ui/button'
import { useHardwareStore } from '@/stores/hardware-store'

type Hold = { id: string; userId: string; exerciseSlug: string; started: boolean; released: boolean; timer?: number; sending: boolean }

export function HoldToJog({ userId, exerciseSlug, disabled = false, onMoved, onHoldingChange }: {
  userId: string | null; exerciseSlug: string; disabled?: boolean; onMoved?: () => void; onHoldingChange?: (holding: boolean) => void
}) {
  const runCommand = useHardwareStore((state) => state.runCommand)
  const setError = useHardwareStore((state) => state.setErrorMessage)
  const hold = useRef<Hold | null>(null)
  const [busy, setBusy] = useState(false)
  const latest = useRef({ userId, exerciseSlug, runCommand, setError, onMoved, onHoldingChange })
  latest.current = { userId, exerciseSlug, runCommand, setError, onMoved, onHoldingChange }

  function release() {
    const current = hold.current
    if (!current || current.released) return
    current.released = true
    if (current.timer !== undefined) window.clearInterval(current.timer)
    if (!current.started) return // The start request can still be in flight; stop after it finishes.
    const { runCommand: send, setError: showError, onMoved: moved } = latest.current
    void send({ action: 'jog_stop', jogId: current.id, userId: current.userId, exerciseSlug: current.exerciseSlug })
      .then(() => moved?.())
      .catch((error: unknown) => showError(error instanceof Error ? error.message : 'Не удалось остановить гриф. Проверьте состояние тренажёра.'))
      .finally(() => {
        if (hold.current === current) { hold.current = null; setBusy(false); latest.current.onHoldingChange?.(false) }
      })
  }

  function press(direction: 'up' | 'down') {
    const { userId: owner, exerciseSlug: slug, runCommand: send, setError: showError } = latest.current
    if (disabled || !owner || hold.current) return
    const current: Hold = { id: crypto.randomUUID?.() ?? `${Date.now()}-${Math.random()}`, userId: owner, exerciseSlug: slug, started: false, released: false, sending: false }
    hold.current = current
    setBusy(true)
    latest.current.onHoldingChange?.(true)
    showError(null)
    void send({ action: 'jog_start', jogId: current.id, userId: owner, exerciseSlug: slug, direction, mode: 'service' })
      .then(() => {
        current.started = true
        if (current.released) { current.released = false; release(); return }
        current.timer = window.setInterval(() => {
          if (current.released || current.sending) return
          current.sending = true
          void runHardwareCommand({ action: 'jog_keepalive', jogId: current.id, userId: owner, exerciseSlug: slug })
            .catch((error: unknown) => {
              showError(error instanceof Error ? error.message : 'Связь с тренажёром потеряна. Гриф остановлен.')
              release()
            })
            .finally(() => { current.sending = false })
        }, 200)
      })
      .catch((error: unknown) => {
        showError(error instanceof Error ? error.message : 'Не удалось переместить гриф.')
        if (hold.current === current) { hold.current = null; setBusy(false); latest.current.onHoldingChange?.(false) }
      })
  }

  useEffect(() => {
    const onBlur = () => release()
    const onVisibility = () => { if (document.hidden) release() }
    window.addEventListener('blur', onBlur)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('blur', onBlur)
      document.removeEventListener('visibilitychange', onVisibility)
      release()
    }
  }, [userId, exerciseSlug])

  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Перемещение грифа при настройке">
      {(['up', 'down'] as const).map((direction) => (
        <Button key={direction} variant="secondary" disabled={(!hold.current && (disabled || busy)) || !userId}
          onPointerDown={(event) => {
            if (event.pointerType === 'mouse' && event.button !== 0) return
            event.currentTarget.setPointerCapture?.(event.pointerId)
            press(direction)
          }}
          onPointerUp={release} onPointerCancel={release} onLostPointerCapture={release} onPointerLeave={release}
          onKeyDown={(event) => {
            if ((event.key === ' ' || event.key === 'Enter') && !event.repeat) { event.preventDefault(); press(direction) }
          }}
          onKeyUp={(event) => { if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); release() } }}
        >{direction === 'up' ? '↑ Вверх · удерживать' : '↓ Вниз · удерживать'}</Button>
      ))}
    </div>
  )
}