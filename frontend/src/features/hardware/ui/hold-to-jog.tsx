import { ArrowDown, ArrowUp } from 'lucide-react'
import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react'
import { runHardwareCommand } from '@/features/hardware/api/hardware-api'
import { Button } from '@/shared/ui/button'
import { useHardwareStore } from '@/stores/hardware-store'

type Hold = { id: string; userId: string; exerciseSlug: string; started: boolean; released: boolean; timer?: number; sending: boolean }

type HoldToJogOptions = {
  userId: string | null; exerciseSlug: string; disabled?: boolean; onMoved?: () => void; onHoldingChange?: (holding: boolean) => void
}

export const jogLabels = { up: '↑ Вверх · удерживать', down: '↓ Вниз · удерживать' } as const

/**
 * Press-and-hold bar movement. One hook owns a single hold, so its up and down
 * buttons may live in different places of the screen and still never move the bar twice.
 */
export function useHoldToJog({ userId, exerciseSlug, disabled = false, onMoved, onHoldingChange }: HoldToJogOptions) {
  const runCommand = useHardwareStore((state) => state.runCommand)
  const setError = useHardwareStore((state) => state.setErrorMessage)
  const hold = useRef<Hold | null>(null)
  const [busy, setBusy] = useState(false)
  const latest = useRef({ userId, exerciseSlug, runCommand, setError, onMoved, onHoldingChange })
  latest.current = { userId, exerciseSlug, runCommand, setError, onMoved, onHoldingChange }
  const releaseRef = useRef<() => void>(() => undefined)
  const windowRelease = useRef(() => releaseRef.current()).current

  function release() {
    const current = hold.current
    if (!current || current.released) return
    current.released = true
    window.removeEventListener('pointerup', windowRelease)
    window.removeEventListener('pointercancel', windowRelease)
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
    window.addEventListener('pointerup', windowRelease)
    window.addEventListener('pointercancel', windowRelease)
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
        window.removeEventListener('pointerup', windowRelease)
        window.removeEventListener('pointercancel', windowRelease)
        if (hold.current === current) { hold.current = null; setBusy(false); latest.current.onHoldingChange?.(false) }
      })
  }

  useEffect(() => {
    releaseRef.current = release
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

  /** Props for a hold button moving the bar in `direction`; spread them onto any button. */
  function buttonProps(direction: 'up' | 'down') {
    return {
      disabled: (!hold.current && (disabled || busy)) || !userId,
      'aria-label': jogLabels[direction],
      onPointerDown: (event: PointerEvent<HTMLButtonElement>) => {
        if (event.pointerType === 'mouse' && event.button !== 0) return
        event.currentTarget.setPointerCapture?.(event.pointerId)
        press(direction)
      },
      onPointerUp: release,
      onPointerCancel: release,
      onLostPointerCapture: release,
      onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => {
        if ((event.key === ' ' || event.key === 'Enter') && !event.repeat) { event.preventDefault(); press(direction) }
      },
      onKeyUp: (event: KeyboardEvent<HTMLButtonElement>) => { if (event.key === ' ' || event.key === 'Enter') { event.preventDefault(); release() } },
    }
  }

  return { buttonProps, holding: busy }
}

export function HoldToJog(options: HoldToJogOptions) {
  const jog = useHoldToJog(options)
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label="Перемещение грифа при настройке">
      {(['up', 'down'] as const).map((direction) => (
        <Button key={direction} variant="secondary" {...jog.buttonProps(direction)}
          iconLeft={direction === 'up' ? <ArrowUp aria-hidden="true" /> : <ArrowDown aria-hidden="true" />}
        >{direction === 'up' ? 'Вверх · удерживать' : 'Вниз · удерживать'}</Button>
      ))}
    </div>
  )
}
