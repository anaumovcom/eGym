import { describe, expect, it } from 'vitest'
import type { CoachAudio, CoachScope } from '../model/contracts'
import { FakeContext } from './audio-test-fakes'
import { CoachFrameReader, decodeCoachFrame, encodeCoachFrame, MAX_FRAME_PCM_BYTES, pcmS16ToAudioBuffer, STREAM_SCALE } from './coach-frames'

// Produced by backend voice.encode_frame (test_coach_e08_voice.GOLDEN): cross-language wire compatibility.
const GOLDEN = 'RUNBMUABAAB7InNjaGVtYVZlcnNpb24iOjEsInV0dGVyYW5jZUlkIjoidS0xIiwiZ2VuZXJhdGlvbklk' +
  'IjoiZy0xIiwic2NvcGUiOnsic2NoZW1hVmVyc2lvbiI6MSwidXNlcklkIjoiYWxleGV5IiwicnVuSWQi' +
  'OiJydW4tMSIsImV4ZXJjaXNlSWQiOiJjaGVzdC1wcmVzcyIsInNldE9yZGluYWwiOjIsInNjb3BlRXBv' +
  'Y2giOjN9LCJzZXF1ZW5jZSI6MCwic291cmNlIjoidHRzIiwiY29kZWMiOiJwY21fczE2bGUiLCJzYW1w' +
  'bGVSYXRlIjoyNDAwMCwiY2hhbm5lbHMiOjEsImJ5dGVMZW5ndGgiOjgsImR1cmF0aW9uTXMiOjAuMTY2' +
  'NjY2NjY2NjY2NjY2NjYsImZpbmFsIjp0cnVlfQAAAEAAwP9/'
const bytes = (b64: string) => Uint8Array.from(atob(b64), c => c.charCodeAt(0))
const scope: CoachScope = { schemaVersion: 1, userId: 'alexey', runId: 'run-1', exerciseId: 'chest-press', setOrdinal: 2, scopeEpoch: 3 }
function meta(length: number, extra: Partial<CoachAudio> = {}): CoachAudio {
  return { schemaVersion: 1, utteranceId: 'u-1', generationId: 'g-1', scope, sequence: 0, source: 'tts', codec: 'pcm_s16le',
    sampleRate: 24000, channels: 1, byteLength: length, durationMs: length / 2 / 24000 * 1000, final: false, ...extra }
}

describe('tagged PCM frames', () => {
  it('decodes the backend golden frame exactly', () => {
    const frame = decodeCoachFrame(bytes(GOLDEN))
    expect(frame.metadata).toMatchObject({ utteranceId: 'u-1', generationId: 'g-1', scope, sequence: 0, source: 'tts',
      sampleRate: 24000, byteLength: 8, final: true })
    expect([...frame.pcm]).toEqual([0, 0, 0, 0x40, 0, 0xc0, 0xff, 0x7f])
    expect(encodeCoachFrame(frame.metadata, frame.pcm)).toHaveLength(bytes(GOLDEN).length)
  })

  it('rejects magic/header/length/duration/codec violations', () => {
    const good = encodeCoachFrame(meta(4), new Uint8Array(4))
    const cases: [Uint8Array, string][] = [
      [Uint8Array.from([0x58, ...good.subarray(1)]), 'frame_magic'],
      [good.subarray(0, 5), 'frame_magic'],
      [good.subarray(0, good.length - 1), 'frame_length'],
      [Uint8Array.from([...good, 0, 0]), 'frame_length'],
    ]
    for (const [input, reason] of cases) expect(() => decodeCoachFrame(input)).toThrow(reason)
    expect(() => encodeCoachFrame(meta(4, { durationMs: 50 }), new Uint8Array(4))).toThrow('frame_duration')
    expect(() => encodeCoachFrame(meta(4, { codec: 'wav' as 'pcm_s16le' }), new Uint8Array(4))).toThrow('frame_codec')
    expect(() => encodeCoachFrame(meta(3), new Uint8Array(3))).toThrow('frame_length')
    expect(() => encodeCoachFrame(meta(4, { generationId: '' }), new Uint8Array(4))).toThrow('frame_header')
    expect(() => encodeCoachFrame(meta(4, { scope: { ...scope, exerciseId: null } }), new Uint8Array(4))).toThrow('frame_header')
    const tooBig = MAX_FRAME_PCM_BYTES + 2
    expect(() => encodeCoachFrame(meta(tooBig), new Uint8Array(tooBig))).toThrow('frame_length')
  })

  it('reassembles frames split at arbitrary network boundaries and detects truncation', () => {
    const stream = Uint8Array.from([...encodeCoachFrame(meta(6), Uint8Array.from([1, 0, 2, 0, 3, 0])),
      ...encodeCoachFrame(meta(2, { sequence: 1, final: true }), Uint8Array.from([4, 0]))])
    for (const size of [1, 3, 7, 64, stream.length]) {
      const reader = new CoachFrameReader()
      const out = []
      for (let i = 0; i < stream.length; i += size) out.push(...reader.push(stream.subarray(i, i + size)))
      reader.finish()
      expect(out.map(f => [f.metadata.sequence, [...f.pcm]])).toEqual([[0, [1, 0, 2, 0, 3, 0]], [1, [4, 0]]])
    }
    const partial = new CoachFrameReader()
    partial.push(stream.subarray(0, 20))
    expect(() => partial.finish()).toThrow('truncated')
    expect(() => new CoachFrameReader().push(Uint8Array.from([1, 2, 3, 4, 5, 6, 7, 8]))).toThrow('frame_magic')
  })

  it('converts s16le to float with fixed headroom', () => {
    const context = new FakeContext()
    const buffer = pcmS16ToAudioBuffer(context.asAudioContext(), Uint8Array.from([0, 0x40, 0, 0xc0, 0xff, 0x7f]), 24000)
    expect(buffer.sampleRate).toBe(24000)
    expect([...buffer.getChannelData(0)].map(v => v / STREAM_SCALE)).toEqual([0.5, -0.5, 32767 / 32768])
    expect(() => pcmS16ToAudioBuffer(context.asAudioContext(), new Uint8Array(3), 24000)).toThrow('frame_length')
  })
})
