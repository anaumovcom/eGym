/// <reference lib="webworker" />
export const BEAT_MS = 250
export const OBSERVATION_MS = 3_000
// Absolute monotonic times are comparable between the window and its worker (different time origins).
export const beatNow = () => performance.timeOrigin + performance.now()
export type BeatEnd = 'finished' | 'unobserved' | 'unreachable'
export type BeatLoop = { observe: (deadline: number) => void; stop: () => void }
export type BeatMessage = { sessionId: string; deadline: number } & ({ type: 'start'; url: string } | { type: 'observe' })
export type BeatNotice = { sessionId: string; reason: BeatEnd }

/** One loop for both transports. A successful keepalive is NOT an observation of motor state. */
export function startBeatLoop(deadline: number, send: (intervalMs: number) => Promise<{ running: boolean }>, ended: (reason: BeatEnd) => void): BeatLoop {
  let active = true
  let sending = false
  let last = 0
  const stop = () => { active = false; clearInterval(timer) }
  const end = (reason: BeatEnd) => { if (active) { stop(); ended(reason) } }
  const tick = async () => {
    if (!active) return
    const now = beatNow()
    if (now >= deadline) { end('unobserved'); return }
    if (sending) return
    const gap = last ? Math.round(now - last) : 0
    last = now
    sending = true
    try { if (!(await send(gap)).running) end('finished') }
    catch { end('unreachable') }
    finally { sending = false }
  }
  const timer = setInterval(() => { void tick() }, BEAT_MS)
  void tick()
  return { stop, observe: (next) => { if (beatNow() >= deadline) end('unobserved'); else deadline = next } }
}

// Also imported by the window for the fallback above; never install a window.onmessage handler.
if (typeof WorkerGlobalScope !== 'undefined' && self instanceof WorkerGlobalScope) {
  const scope = self as unknown as DedicatedWorkerGlobalScope
  let loop: BeatLoop | undefined
  let id: string | undefined
  scope.onmessage = ({ data }: MessageEvent<BeatMessage>) => {
    if (data.type === 'observe') { if (id === data.sessionId) loop?.observe(data.deadline); return }
    loop?.stop()
    const { sessionId, url, deadline } = data
    id = sessionId
    loop = startBeatLoop(deadline, async (intervalMs) => {
      const response = await fetch(url, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sessionId, intervalMs }),
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return response.json()
    }, (reason) => scope.postMessage({ sessionId, reason } satisfies BeatNotice))
  }
}
