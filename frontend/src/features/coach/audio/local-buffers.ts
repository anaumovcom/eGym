export const MAX_LOCAL_BUFFER_BYTES = 2_880_000
const verified = new WeakSet<AudioBuffer>()

export function localBufferBytes(buffer: AudioBuffer): number {
  return buffer.length * buffer.numberOfChannels * Float32Array.BYTES_PER_ELEMENT
}

/** Always copy: preserve provider samples without changing their amplitude. */
export function copyNormalizedLocalBuffer(context: BaseAudioContext, buffer: AudioBuffer): AudioBuffer {
  if (!Number.isInteger(buffer.length) || buffer.length < 1 ||
      ![1, 2].includes(buffer.numberOfChannels) ||
      !Number.isFinite(buffer.sampleRate) || buffer.sampleRate < 8000 || buffer.sampleRate > 96000 ||
      !Number.isFinite(buffer.duration) || buffer.duration <= 0 ||
      Math.abs(buffer.duration - buffer.length / buffer.sampleRate) > 1 / buffer.sampleRate ||
      localBufferBytes(buffer) > MAX_LOCAL_BUFFER_BYTES) throw new Error('invalid_local_buffer')
  for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
    const samples = buffer.getChannelData(channel)
    if (samples.length !== buffer.length) throw new Error('invalid_local_buffer')
    for (const sample of samples) {
      if (!Number.isFinite(sample)) throw new Error('nonfinite_local_buffer')
    }
  }
  const result = context.createBuffer(buffer.numberOfChannels, buffer.length, buffer.sampleRate)
  for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
    const source = buffer.getChannelData(channel)
    const target = result.getChannelData(channel)
    target.set(source)
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