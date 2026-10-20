import { useEffect, useRef } from 'react'
import { useStage4Store } from '@/stores/stage4-store'
import { getCoachAudibleCount, subscribeAudioPriority } from '@/shared/lib/audio-priority'

type ExerciseSound = 'upper' | 'lower' | 'error' | 'success'
const sources: Record<ExerciseSound, string> = {
  upper: '/audio/pop-up.mp3',
  lower: '/audio/pop-down.mp3',
  error: '/audio/error-notification.mp3',
  success: '/audio/success.mp3',
}

// Preserve the user's signal-volume multiplier and mute. Endpoint feedback
// has its own fixed 50% channel, independent of coach/count playback.
const EFFECT_BASE = 0.12
const POP_GAIN = 0.5
const VOICE_DUCK = 0.1
const EFFECT_LIFETIME_MS = 15_000
const MAX_EFFECTS = 16
const activeEffects = new Set<() => void>()

function effectVolume(kind: ExerciseSound): number {
  const settings = useStage4Store.getState().settingsSaved
  const volume = Number(String(settings.signalVolume).replace('%', '')) / 100
  const pop = kind === 'upper' || kind === 'lower'
  const gain = pop ? POP_GAIN : EFFECT_BASE
  const duck = !pop && getCoachAudibleCount() > 0 ? VOICE_DUCK : 1
  return settings.soundEnabled && Number.isFinite(volume)
    ? Math.min(1, Math.max(0, volume)) * gain * duck : 0
}

/** Sound failure must never interrupt the exercise or create another error notification. */
export function playExerciseEventSound(kind: ExerciseSound) {
  if (effectVolume(kind) === 0 || typeof Audio === 'undefined') return
  let cleanup = () => {}
  try {
    if (activeEffects.size >= MAX_EFFECTS) activeEffects.values().next().value?.()
    const audio = new Audio(sources[kind])
    let closed = false
    let offPriority = () => {}
    let offSettings = () => {}
    let timer: ReturnType<typeof setTimeout> | undefined
    cleanup = () => {
      if (closed) return
      closed = true
      activeEffects.delete(cleanup)
      offPriority(); offSettings(); clearTimeout(timer)
      audio.removeEventListener('ended', cleanup)
      audio.removeEventListener('error', cleanup)
      // Also abort a pending play request; never wait for its promise to settle.
      audio.pause()
    }
    const update = () => { audio.volume = effectVolume(kind) }
    activeEffects.add(cleanup)
    audio.addEventListener('ended', cleanup)
    audio.addEventListener('error', cleanup)
    offPriority = subscribeAudioPriority(update)
    offSettings = useStage4Store.subscribe(update)
    timer = setTimeout(cleanup, EFFECT_LIFETIME_MS)
    update()
    void audio.play().then(() => { if (closed) audio.pause() }, cleanup)
  } catch {
    cleanup()
    // Autoplay restrictions and unavailable audio devices are non-fatal.
  }
}

export function useExerciseEventSounds(scope: string, position: 'upper' | 'lower' | 'neutral' | null, problems: string[], partialReps: number) {
  const previous = useRef<{ scope: string; position: typeof position; problems: Set<string>; partialReps: number } | null>(null)
  const problemsKey = JSON.stringify([...new Set(problems)].sort())
  useEffect(() => {
    const old = previous.current?.scope === scope ? previous.current : null
    const currentProblems = new Set<string>(JSON.parse(problemsKey))
    const newProblem = [...currentProblems].some(problem => !old?.problems.has(problem))
      || (old !== null && partialReps > old.partialReps)
    // Initial telemetry establishes a baseline, not a new arrival at an endpoint.
    if (newProblem) playExerciseEventSound('error')
    else if (old && position && position !== 'neutral' && position !== old.position) playExerciseEventSound(position)
    previous.current = { scope, position, problems: currentProblems, partialReps }
  }, [scope, position, problemsKey, partialReps])
}