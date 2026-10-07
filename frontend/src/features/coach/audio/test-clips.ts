import { verifyLocalBuffer } from './local-buffers'

export type TestClipId = 'test-sine' | 'test-chime'
const SINE = Object.freeze([0, 12539, 23170, 30273, 32767, 30273, 23170, 12539, 0, -12539, -23170, -30273, -32767, -30273, -23170, -12539])

/** Explicit TEST tones, NOT a selected coach voice or a real voice pack. No I/O. */
export function createTestClipWav(id: TestClipId): Uint8Array<ArrayBuffer> {
  if (id !== 'test-sine' && id !== 'test-chime') throw new Error('missing_clip')
  const bytes = new Uint8Array(4044)
  const view = new DataView(bytes.buffer)
  const ascii = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) bytes[offset + i] = value.charCodeAt(i)
  }
  ascii(0, 'RIFF'); view.setUint32(4, 4036, true); ascii(8, 'WAVE')
  ascii(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true)
  view.setUint16(22, 1, true); view.setUint32(24, 8000, true); view.setUint32(28, 16000, true)
  view.setUint16(32, 2, true); view.setUint16(34, 16, true)
  ascii(36, 'data'); view.setUint32(40, 4000, true)
  for (let i = 0; i < 2000; i++) {
    const envelope = id === 'test-chime' ? (2000 - i) / 2000 : 1
    view.setInt16(44 + i * 2, Math.trunc(SINE[i % 16] * envelope / 4), true)
  }
  return bytes
}

export function createTestClipBuffer(context: BaseAudioContext, id: TestClipId = 'test-sine'): AudioBuffer {
  const wav = createTestClipWav(id)
  const view = new DataView(wav.buffer)
  const buffer = context.createBuffer(1, 2000, 8000)
  for (let i = 0; i < 2000; i++) buffer.getChannelData(0)[i] = view.getInt16(44 + i * 2, true) / 32768
  return verifyLocalBuffer(context, buffer)
}