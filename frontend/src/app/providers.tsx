import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect, type PropsWithChildren } from 'react'
import { HardwareRealtimeProvider } from '@/features/hardware/lib/hardware-realtime-provider'
import { ApiError, apiPost } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status < 500) {
          return false
        }

        return failureCount < 1
      },
      refetchOnWindowFocus: false,
    },
  },
})

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <QueryClientProvider client={queryClient}>
      <HardwareRealtimeProvider />
      <SelectedUserSync />
      {children}
    </QueryClientProvider>
  )
}

function SelectedUserSync() {
  const selectedUserId = useAppStore((state) => state.selectedUserId)

  useEffect(() => {
    if (!selectedUserId || selectedUserId === 'guest') {
      return
    }

    void apiPost('/api/users/select', { userId: selectedUserId }).catch(() => {
      // Selection is also stored locally; ignore sync failures when backend is unavailable.
    })
  }, [selectedUserId])

  return null
}