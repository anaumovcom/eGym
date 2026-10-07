import type { CoachAudio, CoachDecision, CoachEvent, CoachScope } from '../model/contracts'

export interface CoachClock { nowMs(): number }
export interface CoachTextProvider {
  generate(event: CoachEvent, signal: AbortSignal): Promise<CoachDecision>
}
export interface CoachVoiceAdapter {
  stream(text: string, scope: CoachScope, generationId: string, signal: AbortSignal): AsyncIterable<{
    metadata: CoachAudio; data: Uint8Array
  }>
}
export interface CoachPackStorage {
  getVerified(packVersion: string, clipId: string): Promise<ArrayBuffer | null>
}
export interface CoachAudioManager {
  enqueue(metadata: CoachAudio, data: Uint8Array): void
  cancelScope(scope: CoachScope): void
}