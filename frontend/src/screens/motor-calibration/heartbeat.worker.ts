/// <reference lib="webworker" />
// Heartbeat of the calibration screen off the main thread: rendering, charts and the realtime feed
// cannot delay it. intervalMs (the real gap since the previous beat) lets the backend tell a late
// browser from a lost request.

type Message = { type: 'start'; url: string; periodMs: number } | { type: 'stop' }

let timer: ReturnType<typeof setInterval> | null = null
let last = 0

self.onmessage = (event: MessageEvent<Message>) => {
  if (timer !== null) { clearInterval(timer); timer = null }
  if (event.data.type !== 'start') return
  const { url, periodMs } = event.data
  last = 0
  const beat = () => {
    const now = performance.now()
    const intervalMs = last ? Math.round(now - last) : 0
    last = now
    fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ intervalMs }) })
      .then((response) => (response.ok ? response.json() : null))
      .then((result: { running?: boolean } | null) => { if (result && result.running === false) self.postMessage('stopped') })
      .catch(() => undefined) // not fatal: the backend aborts by itself after 1.5 s without a heartbeat
  }
  beat()
  timer = setInterval(beat, periodMs)
}
