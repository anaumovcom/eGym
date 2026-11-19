import { useCallback, useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  motorApi,
  motorKeys,
  type CalibrationSessionPayload,
  type CalibrationSpec,
  type CalibrationState,
  type CalibrationWorkingZone,
  type StartOptions,
} from '@/features/motor/api/motor-api'
import { ApiError, resolveApiAssetUrl } from '@/shared/api/client'
import {
  OBSERVATION_MS,
  beatNow,
  startBeatLoop,
  type BeatEnd,
  type BeatLoop,
  type BeatNotice,
} from './heartbeat.worker'

const KEEPALIVE_PATH = '/api/motor/calibration/keepalive'

type RunIdentity = { code: string; workingZone?: CalibrationWorkingZone }
type OwnedRun = RunIdentity & { id: string }
type PendingStart = RunIdentity & { cancelled: boolean }
type Heartbeat = { observe: (deadline: number) => void; stop: () => void }

export type CalibrationRunOptions = RunIdentity & {
  spec: CalibrationSpec | null
  enabled: boolean
}

function errorText(error: unknown): string {
  return error instanceof ApiError || error instanceof Error ? error.message : 'Ошибка запроса'
}

function sameIdentity(a: RunIdentity, b: RunIdentity): boolean {
  return a.code === b.code && a.workingZone === b.workingZone
}

/** A start requires a complete, successful precondition payload, not merely a previously cached one. */
function preconditionsPass(payload: CalibrationState | undefined, workingZone?: CalibrationWorkingZone): boolean {
  if (!payload?.preconditions.length || payload.preconditions.some((item) => !item.ok)) return false
  if (workingZone !== 'middle') return true
  const zone = payload.workingZone
  return payload.preconditions.some((item) => item.id === 'middleZone' && item.ok)
    && zone != null
    && Number.isFinite(zone.lowMm)
    && Number.isFinite(zone.highMm)
    && zone.lowMm < zone.highMm
}

/** Both worker and fallback use the same session-scoped, observation-bounded loop. */
function startHeartbeat(sessionId: string, onEnded: (reason: BeatEnd) => void): Heartbeat {
  let deadline = beatNow() + OBSERVATION_MS
  let worker: Worker | null = null
  let fallback: BeatLoop | null = null
  let stopped = false

  const stop = () => {
    stopped = true
    worker?.terminate()
    worker = null
    fallback?.stop()
    fallback = null
  }
  const ended = (reason: BeatEnd) => {
    if (stopped) return
    stop()
    onEnded(reason)
  }
  const startFallback = () => {
    if (stopped || fallback) return
    fallback = startBeatLoop(deadline, (intervalMs) => motorApi.keepalive(sessionId, intervalMs), ended)
  }
  const observe = (nextDeadline: number) => {
    if (stopped) return
    deadline = nextDeadline
    if (worker) {
      worker.postMessage({ type: 'observe', sessionId, deadline })
    } else {
      fallback?.observe(nextDeadline)
    }
  }

  if (typeof Worker === 'undefined') {
    startFallback()
  } else {
    try {
      worker = new Worker(new URL('./heartbeat.worker.ts', import.meta.url), { type: 'module' })
      worker.onmessage = ({ data }: MessageEvent<BeatNotice>) => {
        if (data.sessionId === sessionId) ended(data.reason)
      }
      worker.onerror = () => {
        worker?.terminate()
        worker = null
        startFallback()
      }
      const url = new URL(resolveApiAssetUrl(KEEPALIVE_PATH) ?? KEEPALIVE_PATH, window.location.href).href
      worker.postMessage({ type: 'start', url, sessionId, deadline })
    } catch {
      worker = null
      startFallback()
    }
  }
  return { observe, stop }
}

export function useCalibrationRun({ code, spec, enabled, workingZone }: CalibrationRunOptions) {
  const queryClient = useQueryClient()
  const [starting, setStarting] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [owned, setOwned] = useState<OwnedRun | null>(null)

  const mountedRef = useRef(true)
  const identityRef = useRef<RunIdentity>({ code, workingZone })
  identityRef.current = { code, workingZone }
  const renderedIdentityRef = useRef(`${code}\0${workingZone ?? ''}`)
  const enabledRef = useRef(enabled)
  enabledRef.current = enabled
  const specRef = useRef(spec)
  specRef.current = spec
  const ownedRef = useRef<OwnedRun | null>(null)
  const startRef = useRef<PendingStart | null>(null)
  const heartbeatRef = useRef<Heartbeat | null>(null)
  const busyRef = useRef(false)
  const stoppingRef = useRef<string | null>(null)
  const sessionRef = useRef<CalibrationSessionPayload | null>(null)

  const queryKey = motorKeys.session(code, workingZone)
  const state = useQuery({
    queryKey,
    queryFn: () => motorApi.session(code, workingZone),
    refetchInterval: (query) => (
      ownedRef.current || startRef.current || query.state.data?.session?.status === 'running' ? 250 : 1500
    ),
  })
  const session = state.data?.session ?? null
  sessionRef.current = session
  const running = session?.status === 'running'

  const updateOwned = useCallback((next: OwnedRun | null) => {
    ownedRef.current = next
    if (mountedRef.current) setOwned(next)
  }, [])

  const stopHeartbeat = useCallback(() => {
    heartbeatRef.current?.stop()
    heartbeatRef.current = null
  }, [])

  const invalidateFinished = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: motorKeys.runs })
    void queryClient.invalidateQueries({ queryKey: motorKeys.catalog })
    void queryClient.invalidateQueries({ queryKey: motorKeys.parameters })
  }, [queryClient])

  const refetch = useCallback(async (identity: RunIdentity) => {
    await queryClient.refetchQueries({ queryKey: motorKeys.session(identity.code, identity.workingZone), exact: true })
  }, [queryClient])

  const putSession = useCallback((identity: RunIdentity, next: CalibrationSessionPayload | null) => {
    queryClient.setQueryData<CalibrationState>(motorKeys.session(identity.code, identity.workingZone), (old) => ({
      session: next,
      preconditions: old?.preconditions ?? [],
      profileVersion: old?.profileVersion ?? null,
      ...(identity.workingZone ? { workingZone: old?.workingZone ?? null } : {}),
    }))
  }, [queryClient])

  const heartbeatEnded = useCallback((sessionId: string, reason: BeatEnd) => {
    const current = ownedRef.current
    if (!current || current.id !== sessionId) return
    stopHeartbeat()
    if (reason !== 'finished' && mountedRef.current) {
      setError(reason === 'unobserved'
        ? 'Нет актуального состояния калибровки: heartbeat остановлен. Проверьте экран и связь; СТОП остаётся доступен.'
        : 'Потеряна связь с калибровкой: heartbeat остановлен. СТОП остаётся доступен.')
    }
    void refetch(current)
  }, [refetch, stopHeartbeat])

  /** Cancels a pending start and addresses cleanup only to the session captured by this hook. */
  const dispose = useCallback(() => {
    const pending = startRef.current
    if (pending) {
      pending.cancelled = true
      startRef.current = null
    }
    stopHeartbeat()
    const current = ownedRef.current
    ownedRef.current = null
    if (mountedRef.current) {
      setOwned(null)
      setStarting(false)
    }
    if (current) {
      void motorApi.abort(current.id)
        .then(() => queryClient.invalidateQueries({ queryKey: motorKeys.session(current.code, current.workingZone), exact: true }))
        .catch(() => undefined)
    }
  }, [queryClient, stopHeartbeat])

  useEffect(() => {
    const identity = `${code}\0${workingZone ?? ''}`
    if (renderedIdentityRef.current !== identity) {
      renderedIdentityRef.current = identity
      dispose()
      setError(null)
    }
  }, [code, workingZone, dispose])

  useEffect(() => {
    mountedRef.current = true
    const hidden = () => { if (document.hidden) dispose() }
    document.addEventListener('visibilitychange', hidden)
    window.addEventListener('pagehide', dispose)
    return () => {
      mountedRef.current = false
      document.removeEventListener('visibilitychange', hidden)
      window.removeEventListener('pagehide', dispose)
      dispose()
    }
  }, [dispose])

  useEffect(() => {
    const current = ownedRef.current
    if (!current || !sameIdentity(current, { code, workingZone })) return
    const observed = state.data?.session
    if (observed && observed.id !== current.id) {
      stopHeartbeat()
      updateOwned(null)
      return
    }
    if (observed?.id === current.id && observed.status !== 'running') {
      stopHeartbeat()
      updateOwned(null)
      invalidateFinished()
      return
    }
    if (observed?.id !== current.id || observed.status !== 'running') return
    if (!heartbeatRef.current) {
      heartbeatRef.current = startHeartbeat(current.id, (reason) => heartbeatEnded(current.id, reason))
    }
    // Only a fresh session payload extends the heartbeat; errors and a missing session do not.
    heartbeatRef.current.observe(beatNow() + OBSERVATION_MS)
  }, [code, workingZone, state.data, state.dataUpdatedAt, heartbeatEnded, invalidateFinished, stopHeartbeat, updateOwned])

  const start = useCallback(async (referenceKg?: number) => {
    const identity = identityRef.current
    if (
      startRef.current || ownedRef.current || busyRef.current || sessionRef.current
      || !enabledRef.current || !specRef.current?.runnable
    ) return

    const pending: PendingStart = { ...identity, cancelled: false }
    startRef.current = pending
    setStarting(true)
    setError(null)
    try {
      // The cached query only controls the button. The actual decision uses a fresh GET.
      const fresh = await motorApi.session(identity.code, identity.workingZone)
      if (pending.cancelled || !sameIdentity(identityRef.current, identity)) return
      queryClient.setQueryData(motorKeys.session(identity.code, identity.workingZone), fresh)
      if (fresh.session) {
        setError(fresh.session.status === 'running'
          ? 'Калибровка уже выполняется. Этот экран не будет управлять чужим запуском.'
          : 'Сначала сохраните или отклоните результат предыдущей калибровки.')
        return
      }
      if (!enabledRef.current || !specRef.current?.runnable || !preconditionsPass(fresh, identity.workingZone)) {
        setError('Условия запуска не выполнены или недоступны. Проверьте актуальный список условий.')
        return
      }

      const options: StartOptions = {}
      if (referenceKg !== undefined) options.referenceKg = referenceKg
      if (identity.workingZone) options.workingZone = identity.workingZone
      const next = await motorApi.start(identity.code, options)
      const started = next.session
      if (pending.cancelled || !sameIdentity(identityRef.current, identity)) {
        // start may have completed after close/hide/unmount; abort only that late session id.
        if (started) void motorApi.abort(started.id).catch(() => undefined)
        return
      }
      queryClient.setQueryData(motorKeys.session(identity.code, identity.workingZone), next)
      if (started?.status === 'running') {
        const nextOwned: OwnedRun = { ...identity, id: started.id }
        updateOwned(nextOwned)
        stopHeartbeat()
        heartbeatRef.current = startHeartbeat(started.id, (reason) => heartbeatEnded(started.id, reason))
      } else {
        if (!started) setError('Сервер не вернул сессию калибровки.')
        invalidateFinished()
      }
    } catch (cause) {
      if (!pending.cancelled && mountedRef.current && sameIdentity(identityRef.current, identity)) {
        setError(errorText(cause))
        await refetch(identity)
      }
    } finally {
      if (startRef.current === pending) startRef.current = null
      if (mountedRef.current && sameIdentity(identityRef.current, identity)) setStarting(false)
    }
  }, [heartbeatEnded, invalidateFinished, queryClient, refetch, stopHeartbeat, updateOwned])

  const stop = useCallback(async () => {
    const pending = startRef.current
    if (pending) {
      pending.cancelled = true
      startRef.current = null
      setStarting(false)
    }
    const current = ownedRef.current
    if (!current || stoppingRef.current === current.id) return
    stoppingRef.current = current.id
    stopHeartbeat()
    busyRef.current = true
    setBusy(true)
    setError(null)
    try {
      const result = await motorApi.abort(current.id)
      putSession(current, result.session)
      if (ownedRef.current?.id === current.id) updateOwned(null)
      await refetch(current)
      invalidateFinished()
    } catch (cause) {
      // Keep ownership and the last live view so STOP remains available for retry.
      if (mountedRef.current) setError(errorText(cause))
    } finally {
      if (stoppingRef.current === current.id) stoppingRef.current = null
      busyRef.current = false
      if (mountedRef.current) setBusy(false)
    }
  }, [invalidateFinished, putSession, refetch, stopHeartbeat, updateOwned])

  const reply = useCallback(async (promptText: string, value: number | null) => {
    const current = ownedRef.current
    const observed = sessionRef.current
    if (
      !current || busyRef.current || observed?.id !== current.id
      || observed.status !== 'running' || observed.prompt?.text !== promptText
    ) return
    busyRef.current = true
    setBusy(true)
    setError(null)
    try {
      const result = await motorApi.reply(current.id, promptText, value)
      putSession(current, result.session)
      await refetch(current)
    } catch (cause) {
      if (mountedRef.current) setError(errorText(cause))
    } finally {
      busyRef.current = false
      if (mountedRef.current) setBusy(false)
    }
  }, [putSession, refetch])

  const displayedSessionId = session?.id
  const finishAction = useCallback(async (action: 'accept' | 'discard', fitTravelLimit = false) => {
    const observed = sessionRef.current
    const identity = identityRef.current
    if (!observed || observed.id !== displayedSessionId || observed.status === 'running' || busyRef.current || startRef.current) return false
    busyRef.current = true
    setBusy(true)
    setError(null)
    try {
      if (action === 'accept') {
        const result = await motorApi.accept(observed.id, fitTravelLimit)
        putSession(identity, result.session)
      } else {
        await motorApi.discard(observed.id)
      }
      await refetch(identity)
      invalidateFinished()
      return true
    } catch (cause) {
      if (mountedRef.current) setError(errorText(cause))
      return false
    } finally {
      busyRef.current = false
      if (mountedRef.current) setBusy(false)
    }
  }, [displayedSessionId, invalidateFinished, putSession, refetch])

  const accept = useCallback((fitTravelLimit = false) => finishAction('accept', fitTravelLimit), [finishAction])
  const discard = useCallback(() => finishAction('discard'), [finishAction])
  const ownsRun = owned != null && sameIdentity(owned, { code, workingZone })
  const canStart = enabled && spec?.runnable === true && !starting && !busy && !ownsRun && !session
    && !state.isError && preconditionsPass(state.data, workingZone)

  return {
    state,
    session,
    running,
    starting,
    stopping: Boolean(session && busy && stoppingRef.current === session.id),
    busy,
    canStart,
    ownsRun,
    error,
    spec,
    start,
    stop,
    reply,
    accept,
    discard,
  }
}

export type CalibrationRun = ReturnType<typeof useCalibrationRun>
