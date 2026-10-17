import { Outlet } from 'react-router-dom'
import { useAppStore } from '@/stores/app-store'

/** Remount settings on identity changes without an intermediate access screen. */
export function SettingsLayout() {
  const selectedUserId = useAppStore((state) => state.selectedUserId)

  return <Outlet key={selectedUserId === null ? 'no-user' : `user:${selectedUserId}`} />
}