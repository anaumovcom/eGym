import { useSyncExternalStore } from 'react'
import { useAppStore } from '@/stores/app-store'

let scope = { userId: useAppStore.getState().selectedUserId, epoch: 0 }
const listeners = new Set<() => void>()
export function isCurrentCoachScope(epoch: number) { return scope.epoch === epoch }
useAppStore.subscribe((current, previous) => {
  if (current.selectedUserId === previous.selectedUserId) return
  scope = { userId: current.selectedUserId, epoch: scope.epoch + 1 }
  listeners.forEach(listener => listener())
})
export function useCoachSettingsScope() {
  return useSyncExternalStore(listener => { listeners.add(listener); return () => { listeners.delete(listener) } }, () => scope)
}