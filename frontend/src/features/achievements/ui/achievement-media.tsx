import { Award, HelpCircle, Pause, Play, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { AchievementRarity, AchievementTier } from '@/entities/achievement/model/types'
import { rarityLabels } from '@/entities/achievement/model/types'
import { resolveApiAssetUrl } from '@/shared/api/client'
import { useAppStore } from '@/stores/app-store'
import { useStage4Store } from '@/stores/stage4-store'

export function RarityBadge({ rarity }: { rarity: AchievementRarity }) {
  return <span className="ach-rarity" data-rarity={rarity}><Sparkles aria-hidden="true" />{rarityLabels[rarity]}</span>
}

export function AchievementImage({ tier, className = '', decorative = false }: { tier: AchievementTier; className?: string; decorative?: boolean }) {
  const [failed, setFailed] = useState(false)
  const locked = !tier.earned
  const url = locked ? undefined : resolveApiAssetUrl(tier.thumbnailUrl ?? tier.imageUrl ?? undefined)
  useEffect(() => { setFailed(false) }, [url])
  return (
    <div className={`ach-image ${className}`} data-rarity={tier.rarity} data-locked={locked || undefined}
      data-fallback={!url || failed || undefined} aria-label={locked && !decorative ? 'Награда ещё не открыта' : undefined}
      aria-hidden={decorative || undefined}>
      {url && !failed
        ? <img src={url} alt={decorative ? '' : `Иконка достижения «${tier.title}»`} loading="lazy" decoding="async" onError={() => setFailed(true)} />
        : locked ? <HelpCircle aria-hidden="true" /> : <Award aria-hidden="true" />}
    </div>
  )
}

type AudioProps = {
  tier: AchievementTier
  compact?: boolean
  autoPlay?: boolean
  onPlaybackStart?: () => void
}

export function AchievementAudioButton({ tier, compact = false, autoPlay = false, onPlaybackStart }: AudioProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const playbackRevision = useRef(0)
  const autoPlayAttempted = useRef<string | null>(null)
  const [playing, setPlaying] = useState(false)
  const [error, setError] = useState(false)
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergency = useAppStore((state) => state.emergencyStopActive)
  const soundEnabled = useStage4Store((state) => state.settingsSaved.soundEnabled)
  const voiceEnabled = useStage4Store((state) => state.settingsSaved.voiceHintsEnabled)
  const volume = useStage4Store((state) => state.settingsSaved.signalVolume)
  const url = tier.earned ? resolveApiAssetUrl(tier.audioUrl ?? undefined) : undefined
  const disabled = !url || soundEnabled !== true || voiceEnabled !== true || emergency
  const playbackKey = `${selectedUserId ?? ''}:${tier.id}:${url ?? ''}`
  const accessibleTitle = `«${tier.title}»`

  useEffect(() => {
    playbackRevision.current += 1
    const audio = audioRef.current
    if (audio) {
      audio.pause()
      audio.currentTime = 0
    }
    setPlaying(false)
  }, [selectedUserId, emergency, tier.id, url, disabled])

  useEffect(() => () => { playbackRevision.current += 1; audioRef.current?.pause() }, [])

  async function startPlayback() {
    const audio = audioRef.current
    if (!audio || disabled) return
    audio.volume = Math.max(0, Math.min(1, Number(String(volume).replace('%', '')) / 100))
    for (const other of document.querySelectorAll('audio')) {
      if (other !== audio) other.pause()
    }
    setError(false)
    const revision = ++playbackRevision.current
    try {
      await audio.play()
    } catch {
      if (revision === playbackRevision.current) {
        setPlaying(false)
        setError(true)
      }
      return
    }
    if (revision !== playbackRevision.current) { audio.pause(); return }
    setPlaying(true)
    onPlaybackStart?.()
  }

  function toggle() {
    if (playing) {
      const audio = audioRef.current
      audio?.pause()
      if (audio) audio.currentTime = 0
      setPlaying(false)
      return
    }
    void startPlayback()
  }

  useEffect(() => {
    if (!autoPlay || disabled || autoPlayAttempted.current === playbackKey) return
    autoPlayAttempted.current = playbackKey
    void startPlayback()
    // One attempt per tier/page open; rerenders must not replay unrelated clips.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoPlay, disabled, playbackKey])

  // Speech of a reward that has not been earned is neither rendered nor loadable.
  if (!tier.earned) return null

  return (
    <span className="ach-audio-control">
      <audio ref={audioRef} src={url} preload="none" onPlay={() => setPlaying(true)}
        onEnded={() => setPlaying(false)} onPause={() => setPlaying(false)} />
      <button type="button" className="ach-audio" disabled={disabled} aria-pressed={playing}
        title={disabled ? 'Включите звук и голосовые подсказки в настройках' : `Прослушать фразу ${accessibleTitle}`}
        aria-label={`${playing ? 'Остановить' : 'Прослушать'} фразу ${accessibleTitle}`} onClick={toggle}>
        {playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
        {!compact && <span>{playing ? 'Остановить' : 'Прослушать'}</span>}
      </button>
      {error && <span className="ach-audio-error" role="status">Автовоспроизведение недоступно. Нажмите «Прослушать».</span>}
    </span>
  )
}
