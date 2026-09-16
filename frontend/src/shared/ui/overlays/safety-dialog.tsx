import * as Dialog from '@radix-ui/react-dialog'
import { useCallback, useSyncExternalStore, type ComponentProps } from 'react'
import { cn } from '@/shared/lib/cn'

// The single safety dock belongs to the topmost modal focus scope. Merely raising
// its z-index outside a Radix dialog would leave it inert and hidden from AT.
const targets: HTMLElement[] = []
const listeners = new Set<() => void>()
const subscribe = (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener) } }
const snapshot = () => targets.at(-1) ?? null
const serverSnapshot = () => null

export function useSafetyDockTarget() {
  return useSyncExternalStore(subscribe, snapshot, serverSnapshot)
}

export function SafetyDialogContent({ className, children, onCloseAutoFocus, style, ...props }: ComponentProps<typeof Dialog.Content>) {
  const dockRef = useCallback((node: HTMLDivElement | null) => {
    if (!node) return
    targets.push(node)
    listeners.forEach((listener) => listener())
    return () => {
      const index = targets.indexOf(node)
      if (index >= 0) targets.splice(index, 1)
      listeners.forEach((listener) => listener())
    }
  }, [])

  return (
    <Dialog.Content
      {...props}
      style={{ ...style, pointerEvents: 'none' }}
      className="forma-dialog-root"
      onCloseAutoFocus={(event) => {
        onCloseAutoFocus?.(event)
        if (event.defaultPrevented) return
        const previousDock = snapshot()
        if (previousDock) {
          // A change of portal target replaces the dock DOM. Focus the surviving
          // dialog, not the detached STOP button that opened the inner dialog.
          event.preventDefault()
          requestAnimationFrame(() => {
            const previousDialog = previousDock.closest<HTMLElement>('[role="dialog"]')
            const stop = previousDock.querySelector<HTMLButtonElement>('.forma-stop')
            const nextFocus = stop ?? previousDialog
            nextFocus?.focus()
          })
        }
      }}
    >
      <div className={cn(className, 'forma-dialog-panel')} style={{ pointerEvents: 'auto' }}>{children}</div>
      <div ref={dockRef} className="forma-dialog-dock" />
    </Dialog.Content>
  )
}