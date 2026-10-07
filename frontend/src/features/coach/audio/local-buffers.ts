export const MAX_LOCAL_DURATION_SECONDS = 60
export const MAX_LOCAL_BUFFER_BYTES = 2_880_000
const verified = new WeakSet<AudioBuffer>()

export function localBufferBytes(buffer: AudioBuffer): number {
  return buffer.length * buffer.numberOfChannels * Float32Array.BYTES_PER_ELEMENT
}

/** Always copy: callers cannot change samples that the mixer owns. Attenuate only. */
export function copyNormalizedLocalBuffer(context: BaseAudioContext, buffer: AudioBuffer): AudioBuffer {
  if (!Number.isInteger(buffer.length) || buffer.length < 1 ||
      ![1, 2].includes(buffer.numberOfChannels) ||
      !Number.isFinite(buffer.sampleRate) || buffer.sampleRate < 8000 || buffer.sampleRate > 96000 ||
      !Number.isFinite(buffer.duration) || buffer.duration <= 0 || buffer.duration > MAX_LOCAL_DURATION_SECONDS ||
      Math.abs(buffer.duration - buffer.length / buffer.sampleRate) > 1 / buffer.sampleRate ||
      localBufferBytes(buffer) > MAX_LOCAL_BUFFER_BYTES) throw new Error('invalid_local_buffer')
  let peak = 0
  for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
    const samples = buffer.getChannelData(channel)
    if (samples.length !== buffer.length) throw new Error('invalid_local_buffer')
    for (const sample of samples) {
      if (!Number.isFinite(sample)) throw new Error('nonfinite_local_buffer')
      peak = Math.max(peak, Math.abs(sample))
    }
  }
  const result = context.createBuffer(buffer.numberOfChannels, buffer.length, buffer.sampleRate)
  const scale = peak > 0.25 ? 0.25 / peak : 1
  for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
    const source = buffer.getChannelData(channel)
    const target = result.getChannelData(channel)
    for (let index = 0; index < source.length; index++) target[index] = source[index] * scale
  }
  return result
}

/** Internal provenance boundary: only checksum-decoded fixtures and TEST generators call this. */
export function verifyLocalBuffer(context: BaseAudioContext, buffer: AudioBuffer): AudioBuffer {
  const copy = copyNormalizedLocalBuffer(context, buffer)
  verified.add(copy)
  return copy
}

export function isVerifiedLocalBuffer(buffer: AudioBuffer): boolean {
  return verified.has(buffer)
}