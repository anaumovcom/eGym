/** E02 wire contracts. Runtime kinds, control modes and progress units are separate. */
export const COACH_SCHEMA_VERSION = 1 as const
export const COACH_EVENT_KINDS = [
  'workout_started', 'exercise_ready', 'set_activated', 'rep_completed', 'rep_milestone',
  'last_rep_pending', 'set_paused', 'set_resumed', 'set_stopped', 'set_persisted',
  'rest_entered', 'rest_long_opportunity', 'rest_ending', 'exercise_finalized', 'workout_finalized',
  'pain_reported', 'safety_changed',
] as const
export const COACH_REASONS = [
  'disabled', 'no_consent', 'mute', 'audio_locked', 'hidden', 'safety', 'stale_source',
  'mock_source', 'owner_mismatch', 'scope_changed', 'no_window', 'cooldown', 'density_cap',
  'topic_repeat', 'pipeline_busy', 'budget', 'provider_circuit', 'validation_failed',
  'missing_clip', 'decode_failed', 'expired', 'duplicate', 'cancelled', 'queue_full',
] as const
export type CoachReason = typeof COACH_REASONS[number]
export type CoachEventKind = typeof COACH_EVENT_KINDS[number]
export type CoachPhase = 'disabled' | 'setup' | 'waiting-start' | 'active-set' | 'paused-set' |
  'finalizing-set' | 'rest' | 'exercise-summary' | 'workout-summary' | 'suspended'
export type CoachSource = 'hardware' | 'runtime_ack' | 'user_input' | 'synthetic' | 'recorded'
export type CoachOutcome = 'completed' | 'partial' | 'skipped' | 'aborted'
export type CoachScope = Readonly<{
  schemaVersion: 1; userId: string; runId: string; exerciseId: string | null
  setOrdinal: number | null; scopeEpoch: number
}>
export type CoachFact = Readonly<{
  schemaVersion: 1; id: string; value: boolean | number | string | null
  unit: 'reps' | 'seconds' | 'kg' | 'mm' | 'percent' | 'text' | 'boolean'
  source: CoachSource; confidence: 'confirmed' | 'derived-validated' | 'unknown'
  observedAtMs: number; validUntilMs: number; scopeEpoch: number
}>
export type CoachEvent = Readonly<{
  schemaVersion: 1; id: string; scope: CoachScope; kind: CoachEventKind; phase: CoachPhase
  source: CoachSource; exerciseKind: 'machine' | 'bodyweight' | 'timed' | 'stretch' | 'group' | null
  controlMode: string | null; progressUnit: 'reps' | 'seconds' | null; ordinal: number
  planRevision: number; contextVersion: number; createdAtMs: number; startDeadlineMs: number
  facts: readonly CoachFact[]; factDependencies: readonly string[]
}>
export type CoachSettings = Readonly<{
  schemaVersion: 1; enabled: boolean; consentVersion: number | null
  mode: 'local' | 'hybrid' | 'text-only'; density: 'quiet' | 'companion' | 'talkative'
  count: 'every' | 'last-three' | 'milestones' | 'off'; voiceProfile: string | null
  historyConsent: boolean; revision: number; budgetUsd: string
}>
export const DEFAULT_COACH_SETTINGS: CoachSettings = Object.freeze({
  schemaVersion: 1, enabled: false, consentVersion: null, mode: 'local', density: 'companion',
  count: 'off', voiceProfile: null, historyConsent: false, revision: 0, budgetUsd: '2.00',
})
export type CoachRun = Readonly<{
  schemaVersion: 1; scope: CoachScope; workoutSessionId: number | null
  mode: 'live' | 'test'; state: 'idle' | 'active' | 'closed'; pricingVersion: string | null
}>
export type CoachDecision = Readonly<{
  schemaVersion: 1; action: 'speak' | 'silence'; text: string
  intent: 'motivation' | 'humor' | 'factual-feedback' | 'general-tip' | 'summary'
  usedFactIds: readonly string[]; topicKey: string; delivery: 'neutral' | 'energetic' | 'calm'
}>
export type CoachAudio = Readonly<{
  schemaVersion: 1; utteranceId: string; generationId: string; scope: CoachScope; sequence: number
  source: 'local' | 'cache' | 'realtime' | 'tts' | 'fake'; codec: 'pcm_s16le' | 'wav'
  sampleRate: number; channels: 1 | 2; byteLength: number; durationMs: number; final: boolean
}>
export type CoachUsage = Readonly<{
  schemaVersion: 1; attemptId: string; ledger: 'workout' | 'test' | 'pack'; stage: 'text' | 'voice'
  status: 'reserved' | 'sent' | 'settled' | 'unsettled' | 'cancelled'
  completeness: 'complete' | 'partial' | 'unavailable'; inputTokens: number | null
  cachedInputTokens: number | null; outputTokens: number | null; reasoningTokens: number | null
  audioInputTokens: number | null; audioOutputTokens: number | null
  costUsd: string | null; pricingVersion: string | null
}>
export type CoachRuntimeNotice = Readonly<{
  schemaVersion: 1; kind: 'set_persisted' | 'exercise_finalized' | 'workout_finalized'
  userId: string; workoutSessionId: number | null; exerciseSessionId: number | null
  setId: number | null; setOrdinal: number | null; actualValue: number | null; outcome: CoachOutcome | null
}>
export type CoachCapabilities = Readonly<{
  schemaVersion: 1; enabled: boolean; implementation: 'control-plane'; paidDispatch: false
  lifecycleObservation: boolean; replay: 'test-only'
}>

/** Backend IDs are aliases, never a replacement for this identity. */
export function canonicalCoachKey(event: Pick<CoachEvent, 'scope' | 'kind' | 'ordinal'>): string {
  const { userId, runId, exerciseId, setOrdinal } = event.scope
  const workout = event.kind === 'workout_finalized' || event.kind === 'workout_started'
  const exercise = event.kind === 'exercise_finalized' || event.kind === 'exercise_ready'
  return JSON.stringify([userId, runId, workout ? null : exerciseId, workout || exercise ? null : setOrdinal, event.kind, event.ordinal])
}