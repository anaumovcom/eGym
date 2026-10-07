import { LocalCoachAudioManager, type AudioTimerClock, type LocalAudioSnapshot } from '../src/features/coach/audio/local-coach-audio-manager'
import { verifyLocalBuffer } from '../src/features/coach/audio/local-buffers'

/** Offline rendering cannot run JS timers on its audio thread. Suspend at exact
 * render quanta, flush an audio-time clock, then resume. Offline suspensions are
 * instrumentation, NOT autoplay locks: adapt only state to keep the production
 * manager running. Nodes, AudioParams, samples and currentTime remain native.
 */
export async function renderOffline(count: 1 | 2 | 3) {
  const sampleRate = 48_000, quantum = 128, step = quantum * 4 / sampleRate
  // Channel 0 is the unmodified production mix. Extra discrete channels are
  // passive taps AFTER each native utterance GainNode, before master/compressor.
  // They let acceptance measure automation in actual PCM, not only snapshots.
  const offline = new OfflineAudioContext(4, sampleRate * 1.5, sampleRate)
  const destination = offline.destination
  const merger = offline.createChannelMerger(4)
  merger.connect(destination)
  const mixDestination = offline.createGain()
  mixDestination.connect(merger, 0, 0)
  Object.defineProperty(offline, 'destination', { get: () => mixDestination })
  const createGain = offline.createGain.bind(offline)
  let gainIndex = 0
  offline.createGain = () => {
    const gain = createGain()
    // First manager-created gain is master, subsequent gains are utterances.
    if (++gainIndex > 1) gain.connect(merger, 0, gainIndex - 1)
    return gain
  }
  const nativeState = () => Object.getOwnPropertyDescriptor(BaseAudioContext.prototype, 'state')!.get!.call(offline) as string
  Object.defineProperty(offline, 'state', { get: () => nativeState() === 'closed' ? 'closed' : 'running' })
  let next = 0
  const timers = new Map<number, { due: number; callback: () => void }>()
  const clock: AudioTimerClock = {
    now: () => offline.currentTime * 1000,
    setTimeout: (callback, delayMs) => { const id = ++next; timers.set(id, { due: clock.now() + delayMs, callback }); return id },
    clearTimeout: id => { timers.delete(id as number) },
  }
  // Native offline statechange/onended dispatch is asynchronous relative to
  // rendering. Route observation to the SAME deterministic paused clock, not
  // the racing main-thread task queue. Sources still end natively in the PCM.
  const addEventListener = offline.addEventListener.bind(offline)
  const removeEventListener = offline.removeEventListener.bind(offline)
  offline.addEventListener = ((type: string, listener: EventListener, options?: boolean | AddEventListenerOptions) => {
    if (type !== 'statechange') addEventListener(type, listener, options)
  }) as typeof offline.addEventListener
  offline.removeEventListener = ((type: string, listener: EventListener, options?: boolean | EventListenerOptions) => {
    if (type !== 'statechange') removeEventListener(type, listener, options)
  }) as typeof offline.removeEventListener
  const createSource = offline.createBufferSource.bind(offline)
  offline.createBufferSource = () => {
    const source = createSource()
    let ended: ((this: AudioScheduledSourceNode, event: Event) => unknown) | null = null
    Object.defineProperty(source, 'onended', { get: () => ended, set: callback => { ended = callback } })
    const start = source.start.bind(source)
    source.start = (when = 0, offset = 0, duration = source.buffer!.duration - offset) => {
      start(when, offset, duration)
      clock.setTimeout(() => ended?.call(source, new Event('ended')), (when + duration - offline.currentTime) * 1000)
    }
    return source
  }
  const scope = { schemaVersion: 1 as const, userId: 'e05-offline', runId: 'render', exerciseId: 'test', setOrdinal: null, scopeEpoch: 0 }
  const manager = new LocalCoachAudioManager({ context: offline as unknown as AudioContext, clock, scope })
  const snapshots: { time: number; audio: LocalAudioSnapshot }[] = []
  const events: { time: number; audio: LocalAudioSnapshot }[] = []
  manager.subscribe(() => events.push({ time: offline.currentTime, audio: manager.snapshot() }))
  const admissions: boolean[] = []
  for (let index = 0; index < count; index++) {
    const duration = [1.2, 0.8, 0.4][index]
    const buffer = offline.createBuffer(1, Math.round(duration * sampleRate), sampleRate)
    // Identical phase/frequency is deliberately correlated, stressing sum peak.
    const samples = buffer.getChannelData(0)
    for (let i = 0; i < samples.length; i++) samples[i] = 0.9 * Math.sin(2 * Math.PI * 375 * i / sampleRate)
    admissions.push(manager.playLocal({ id: `tone-${index + 1}`, scope, source: 'local',
      buffer: verifyLocalBuffer(offline, buffer), baseGain: 1, delayMs: index * 160,
      startDeadlineMs: 2000, revalidate: () => true }))
  }
  // Register every suspend before rendering; unique quantum-aligned times.
  const pauses = Array.from({ length: 139 }, (_, i) => offline.suspend((i + 1) * step))
  const rendering = offline.startRendering()
  for (const pause of pauses) {
    await pause
    const due = [...timers].filter(([, timer]) => timer.due <= clock.now() + 1e-6)
    for (const [id, timer] of due) if (timers.delete(id)) {
      // Bracket every observer operation, including the single-voice case,
      // rather than relying on duplicate diagnostic notifications existing.
      events.push({ time: offline.currentTime, audio: manager.snapshot() })
      timer.callback()
      events.push({ time: offline.currentTime, audio: manager.snapshot() })
    }
    snapshots.push({ time: offline.currentTime, audio: manager.snapshot() })
    await offline.resume()
  }
  const rendered = await rendering
  const pcm = rendered.getChannelData(0)
  const probes: { id: string; time: number; gain: number }[] = []
  for (const snapshot of snapshots) for (const voice of snapshot.audio.utterances) {
    if (voice.state !== 'started') continue
    const index = Number(voice.id.split('-')[1])
    const channel = rendered.getChannelData(index)
    for (let frame = Math.ceil(snapshot.time * sampleRate); frame < Math.min(channel.length, Math.ceil(snapshot.time * sampleRate) + 128); frame++) {
      const time = frame / sampleRate
      const sourceFrame = frame - Math.round(voice.scheduledStartTime! * sampleRate)
      if (sourceFrame >= [1.2, 0.8, 0.4][index - 1] * sampleRate) break
      const normalizedTone = 0.25 * Math.sin(2 * Math.PI * 375 * sourceFrame / sampleRate)
      if (Math.abs(normalizedTone) < 0.20) continue
      probes.push({ id: voice.id, time, gain: channel[frame] / normalizedTone })
      break
    }
  }
  let samplePeak = 0, maxAdjacentDelta = 0, finite = true, energy = 0
  for (let i = 0; i < pcm.length; i++) {
    finite &&= Number.isFinite(pcm[i]); samplePeak = Math.max(samplePeak, Math.abs(pcm[i])); energy += pcm[i] ** 2
    if (i) maxAdjacentDelta = Math.max(maxAdjacentDelta, Math.abs(pcm[i] - pcm[i - 1]))
  }
  manager.dispose()
  return { count, sampleRate, sampleCount: pcm.length, admissions, finite, samplePeak,
    maxAdjacentDelta, rms: Math.sqrt(energy / pcm.length), snapshots, events, probes }
}