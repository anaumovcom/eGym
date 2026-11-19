import { useEffect, useState } from 'react'

/** Only for passive reads (status or port list), never for hardware commands. */
export function useModbusRead(load: () => Promise<void>, intervalMs?: number) {
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState({ loading: true, failed: false })
  useEffect(() => {
    let current = true
    let timer: ReturnType<typeof setTimeout>
    setState({ loading: true, failed: false })
    async function refresh() {
      try {
        await load()
        if (current) setState({ loading: false, failed: false })
      } catch {
        if (current) setState({ loading: false, failed: true })
      }
      if (current && intervalMs) timer = setTimeout(refresh, intervalMs)
    }
    void refresh()
    return () => { current = false; clearTimeout(timer) }
  }, [attempt, load, intervalMs])
  return { ...state, refresh: () => setAttempt((n) => n + 1) }
}
