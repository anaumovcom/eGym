/** E06 deterministic local cue vocabulary. Clip IDs are shared with the backend
 * editorial pack catalog (backend/app/services/coach/packs.py). Texts live there;
 * the browser only needs stable semantic IDs and admission metadata. */
export type CueKind =
  | 'count' | 'start' | 'hold-start' | 'pause' | 'resume' | 'half' | 'three-left' | 'target'
  | 'time-half' | 'ten-left' | 'countdown' | 'set-end' | 'set-partial' | 'set-skipped'
  | 'last-set-next' | 'rest-ten' | 'rest-five' | 'rest-ready'
  | 'exercise-done' | 'exercise-partial' | 'exercise-skipped' | 'workout-done' | 'workout-partial'
  | 'safety-stop' | 'pain-stop'

export type CueSpec = Readonly<{ triggerId: string; priority: 'safety' | 'ordinary'; deadlineMs: number; clip: string | null }>

export const MAX_COUNT_CLIP = 100
export const REQUIRED_COUNT_CLIPS = 30

export const CUE_SPECS: Readonly<Record<CueKind, CueSpec>> = Object.freeze({
  count: { triggerId: 'T14', priority: 'ordinary', deadlineMs: 900, clip: null },
  start: { triggerId: 'T13', priority: 'ordinary', deadlineMs: 1500, clip: 'set-start' },
  'hold-start': { triggerId: 'T27', priority: 'ordinary', deadlineMs: 1500, clip: 'hold-start' },
  pause: { triggerId: 'T24', priority: 'ordinary', deadlineMs: 1500, clip: 'set-pause' },
  resume: { triggerId: 'T25', priority: 'ordinary', deadlineMs: 1500, clip: 'set-resume' },
  half: { triggerId: 'T16', priority: 'ordinary', deadlineMs: 1500, clip: 'rep-half' },
  'three-left': { triggerId: 'T17', priority: 'ordinary', deadlineMs: 1200, clip: 'rep-three-left' },
  target: { triggerId: 'T26', priority: 'ordinary', deadlineMs: 1500, clip: 'rep-target' },
  'time-half': { triggerId: 'T28', priority: 'ordinary', deadlineMs: 1500, clip: 'time-half' },
  'ten-left': { triggerId: 'T29', priority: 'ordinary', deadlineMs: 1500, clip: 'time-ten-left' },
  countdown: { triggerId: 'T30', priority: 'ordinary', deadlineMs: 700, clip: null },
  'set-end': { triggerId: 'T35', priority: 'ordinary', deadlineMs: 2500, clip: 'set-end' },
  'set-partial': { triggerId: 'T35', priority: 'ordinary', deadlineMs: 2500, clip: 'set-partial' },
  'set-skipped': { triggerId: 'T38', priority: 'ordinary', deadlineMs: 2500, clip: 'set-skipped' },
  'last-set-next': { triggerId: 'T49', priority: 'ordinary', deadlineMs: 4000, clip: 'last-set-next' },
  'rest-ten': { triggerId: 'T50', priority: 'ordinary', deadlineMs: 1500, clip: 'rest-ten' },
  'rest-five': { triggerId: 'T50', priority: 'ordinary', deadlineMs: 1200, clip: 'rest-five' },
  'rest-ready': { triggerId: 'T51', priority: 'ordinary', deadlineMs: 2000, clip: 'rest-ready' },
  'exercise-done': { triggerId: 'T55', priority: 'ordinary', deadlineMs: 4000, clip: 'exercise-done' },
  'exercise-partial': { triggerId: 'T56', priority: 'ordinary', deadlineMs: 4000, clip: 'exercise-partial' },
  'exercise-skipped': { triggerId: 'T38', priority: 'ordinary', deadlineMs: 4000, clip: 'exercise-skipped' },
  'workout-done': { triggerId: 'T58', priority: 'ordinary', deadlineMs: 6000, clip: 'workout-done' },
  'workout-partial': { triggerId: 'T59', priority: 'ordinary', deadlineMs: 6000, clip: 'workout-partial' },
  'safety-stop': { triggerId: 'T65', priority: 'safety', deadlineMs: 3000, clip: 'safety-stop' },
  'pain-stop': { triggerId: 'T66', priority: 'safety', deadlineMs: 3000, clip: 'pain-stop' },
} satisfies Record<CueKind, CueSpec>)

export function cueClipId(kind: CueKind, value: number | null): string | null {
  if (kind === 'count') return Number.isInteger(value) && value! >= 1 && value! <= MAX_COUNT_CLIP ? `count-${value}` : null
  if (kind === 'countdown') return value === 1 || value === 2 || value === 3 ? `countdown-${value}` : null
  return CUE_SPECS[kind].clip
}

/** Required local clips that E09 preloads before an active set. */
export const REQUIRED_LOCAL_CLIPS: readonly string[] = Object.freeze([
  ...Array.from({ length: REQUIRED_COUNT_CLIPS }, (_, index) => `count-${index + 1}`),
  'countdown-1', 'countdown-2', 'countdown-3',
  ...[...new Set(Object.values(CUE_SPECS).map(spec => spec.clip).filter((clip): clip is string => clip !== null))],
])
