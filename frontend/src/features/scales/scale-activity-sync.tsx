import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useRuntimeStore } from '@/stores/runtime-store'
import { scalesApi, type ScaleActivityPhase } from './api'

const clientIdKey = 'egym-scales-client-id'
let fallbackClientId: string | undefined
let lastSequence = 0

function getClientId() {
  try {
    const stored = sessionStorage.getItem(clientIdKey)
    if (stored && stored.length <= 64) return stored
  } catch { /* Storage may be disabled; retain an in-memory identity instead. */ }
  if (!fallbackClientId) {
    fallbackClientId = typeof crypto.randomUUID === 'function' ? crypto.randomUUID() :
      '10000000-1000-4000-8000-100000000000'.replace(/[018]/g, digit =>
        (Number(digit) ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (Number(digit) / 4)))).toString(16))
  }
  try { sessionStorage.setItem(clientIdKey, fallbackClientId) } catch { /* Best effort. */ }
  return fallbackClientId
}

function sendActivity(phase: ScaleActivityPhase) {
  // Shared across effects/remounts: even StrictMode's idle cleanup must precede the next lease.
  lastSequence = Math.max(Date.now(), lastSequence + 1)
  void scalesApi.activity({ clientId: getClientId(), sequence: lastSequence, phase }).catch(() => {
    // Offline/older backends must not interfere with workouts. The next heartbeat retries.
  })
}

const workoutPhases: Record<string, ScaleActivityPhase> = {
  'exercise-setup': 'setup',
  'exercise-session': 'exercise',
  rest: 'rest',
}

/** Route-scoped leases only; never change persistent discovery settings or workout/hardware state. */
export function ScaleActivitySync() {
  const { pathname } = useLocation()
  const view = useRuntimeStore(state => state.session?.view)
  const route = pathname.replace(/\/+$/, '')
  const routePhase = workoutPhases[route.slice(1)]
  const phase: ScaleActivityPhase = ['/motor-calibration', '/modbus', '/modbus-debug', '/settings/service/modbus'].includes(route)
    ? 'setup'
    : routePhase ? (view && workoutPhases[view]) || routePhase : 'idle'

  useEffect(() => {
    // Do not serialize requests: a newer sequence supersedes any in-flight request on the server.
    sendActivity(phase)
    const timer = setInterval(() => sendActivity(phase), 5000)
    return () => clearInterval(timer)
  }, [phase])

  useEffect(() => () => sendActivity('idle'), [])
  return null
}