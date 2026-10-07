import { vi } from 'vitest'
import type { AudioTimerClock } from './local-coach-audio-manager'

export class FakeParam {
  value = 1
  events: { kind: string; value?: number; time: number }[] = []
  cancelAndHoldAtTime: ((time: number) => void) | undefined
  constructor(nativeHold = true) {
    if (nativeHold) this.cancelAndHoldAtTime = time => { this.events.push({ kind: 'hold', time }) }
  }
  setValueAtTime(value: number, time: number) { this.value = value; this.events.push({ kind: 'set', value, time }); return this }
  cancelScheduledValues(time: number) { this.events.push({ kind: 'cancel', time }); return this }
  linearRampToValueAtTime(value: number, time: number) { this.value = value; this.events.push({ kind: 'ramp', value, time }); return this }
}
class FakeNode {
  connect = vi.fn()
  disconnect = vi.fn()
}
export class FakeGain extends FakeNode {
  gain: FakeParam
  constructor(nativeHold: boolean) { super(); this.gain = new FakeParam(nativeHold) }
}
export class FakeSource extends FakeNode {
  buffer: AudioBuffer | null = null
  onended: (() => void) | null = null
  start = vi.fn()
  stop = vi.fn()
  end() { this.onended?.() }
}
export class FakeBuffer {
  readonly duration: number
  readonly numberOfChannels: number
  readonly length: number
  readonly sampleRate: number
  private readonly channels: Float32Array[]
  constructor(numberOfChannels: number, length: number, sampleRate: number) {
    this.numberOfChannels = numberOfChannels; this.length = length; this.sampleRate = sampleRate
    this.duration = length / sampleRate
    this.channels = Array.from({ length: numberOfChannels }, () => new Float32Array(length))
  }
  getChannelData(channel: number) { return this.channels[channel] }
}
export class FakeContext extends EventTarget {
  state: AudioContextState = 'running'
  sampleRate = 8000
  currentTime = 0
  destination = new FakeNode()
  sources: FakeSource[] = []
  gains: FakeGain[] = []
  compressors: FakeNode[] = []
  close = vi.fn()
  resume = vi.fn(async () => { this.state = 'running' })
  suspend = vi.fn()
  nativeHold = true
  createBuffer(channels: number, length: number, rate: number): AudioBuffer { return new FakeBuffer(channels, length, rate) as unknown as AudioBuffer }
  createGain(): GainNode { const node = new FakeGain(this.nativeHold); this.gains.push(node); return node as unknown as GainNode }
  createBufferSource(): AudioBufferSourceNode { const node = new FakeSource(); this.sources.push(node); return node as unknown as AudioBufferSourceNode }
  createDynamicsCompressor(): DynamicsCompressorNode {
    const node = Object.assign(new FakeNode(), { threshold: new FakeParam(), knee: new FakeParam(), ratio: new FakeParam(), attack: new FakeParam(), release: new FakeParam() })
    this.compressors.push(node); return node as unknown as DynamicsCompressorNode
  }
  decodeAudioData = vi.fn(async (bytes: ArrayBuffer): Promise<AudioBuffer> => {
    const view = new DataView(bytes)
    const frames = view.getUint32(40, true) / 2
    const result = this.createBuffer(1, frames, this.sampleRate)
    for (let i = 0; i < frames; i++) result.getChannelData(0)[i] = view.getInt16(44 + i * 2, true) / 32768
    return result
  })
  asAudioContext(): AudioContext { return this as unknown as AudioContext }
  setState(state: AudioContextState) { this.state = state; this.dispatchEvent(new Event('statechange')) }
}

/** Wall time and audio time are independent; tests can freeze/suspend audio explicitly. */
export class FakeClock implements AudioTimerClock {
  time = 0
  private next = 0
  private jobs = new Map<number, { at: number; callback: () => void }>()
  now = () => this.time
  setTimeout(callback: () => void, delayMs: number): unknown {
    const id = ++this.next; this.jobs.set(id, { at: this.time + delayMs, callback }); return id
  }
  clearTimeout(handle: unknown) { this.jobs.delete(handle as number) }
  get pendingTimers() { return this.jobs.size }
  advance(ms: number, context?: FakeContext, advanceAudio = true) {
    const end = this.time + ms
    while (true) {
      const next = [...this.jobs.entries()].filter(([, job]) => job.at <= end).sort((a, b) => a[1].at - b[1].at)[0]
      if (!next) break
      this.move(next[1].at, context, advanceAudio)
      this.jobs.delete(next[0]); next[1].callback()
    }
    this.move(end, context, advanceAudio)
  }
  private move(time: number, context?: FakeContext, advanceAudio = true) {
    if (context && advanceAudio && context.state === 'running') context.currentTime += (time - this.time) / 1000
    this.time = time
  }
}