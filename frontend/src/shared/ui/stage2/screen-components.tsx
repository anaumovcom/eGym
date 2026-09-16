import * as Dialog from '@radix-ui/react-dialog'
import { CalendarDays, ChevronRight, CircleAlert, Dumbbell, Flame, Grid2x2, List, LoaderCircle, Play, Search, ShieldAlert, Star, X } from 'lucide-react'
import { memo, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { ExerciseDetails, ExerciseLoadSettings, ExerciseSummary } from '@/entities/exercise/model/types'
import type { MuscleCard } from '@/entities/muscle/model/types'
import type { ProgramDetails, ProgramSummary } from '@/entities/program/model/types'
import type { WorkoutExerciseRow as WorkoutExerciseRowData } from '@/entities/workout/model/types'
import { resolveApiAssetUrl } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { resolveSvgIdsForBodyMapLabel, svgIdsByView, type BodyMapView } from '@/shared/ui/stage4/fatigue-muscle-map'

const toneClasses = {
  recommended: 'border-[#57c968]/35 bg-[#163720] text-[#9ef0a8]',
  okay: 'border-white/10 bg-white/6 text-white/70',
  caution: 'border-[#d6a54f]/35 bg-[#3a2b14] text-[#f2cf87]',
  blocked: 'border-[#b83d38]/35 bg-[#3a1816] text-[#ffafa7]',
} as const

const muscleDotClasses: Record<MuscleCard['status'], string> = {
  ready: 'bg-[#69d46b]',
  light: 'bg-[#d8ca56]',
  medium: 'bg-[#df9840]',
  high: 'bg-[#ec5f49]',
  critical: 'bg-[#8f3034]',
  no_data: 'bg-[#677084]',
}

type CompactFigureGender = 'male' | 'female'
type CompactMapTone = MuscleCard['status'] | 'primary' | 'secondary' | 'stabilizer'
type CompactMapHighlight = { label: string; tone: CompactMapTone; description?: string }
export type CompactBodyMapHover = { label: string; tone: CompactMapTone; anchor?: { top: number; left: number } }

const compactInlineSvgCache = new Map<string, string>()

const compactToneColors: Record<CompactMapTone, string> = {
  primary: '#d6b05f',
  secondary: '#8da4c8',
  stabilizer: '#7fae90',
  ready: '#57c968',
  light: '#a6d94f',
  medium: '#f0bf43',
  high: '#f08b2e',
  critical: '#eb5345',
  no_data: '#667287',
}

const compactToneHoverColors: Record<CompactMapTone, string> = {
  primary: '#e4c980',
  secondary: '#a9bcda',
  stabilizer: '#97c3a7',
  ready: '#78df84',
  light: '#bae56c',
  medium: '#f5cf67',
  high: '#f5a04f',
  critical: '#f07064',
  no_data: '#7a869a',
}

const compactTonePriority: Record<CompactMapTone, number> = {
  critical: 9,
  high: 8,
  medium: 7,
  light: 6,
  ready: 5,
  primary: 4,
  secondary: 3,
  stabilizer: 2,
  no_data: 1,
}

const compactSvgPathByGenderAndView: Record<CompactFigureGender, Record<BodyMapView, string>> = {
  male: {
    front: '/male-muscles-front.svg',
    back: '/male-muscles-back.svg',
  },
  female: {
    front: '/female-muscles-front.svg',
    back: '/female-muscles-back.svg',
  },
}

function prefixCompactSvgMarkup(svgMarkup: string, prefix: string) {
  return svgMarkup
    .replace(/\sclass="([^"]*)"/g, (_match, className: string) => {
      const sanitizedClassName = className
        .split(/\s+/)
        .filter((token) => token && token !== 'bodymap' && !token.startsWith('text-mw-') && !token.startsWith('active:text-mw-') && !token.startsWith('lg:hover:text-mw-'))
        .join(' ')

      return sanitizedClassName ? ` class="${sanitizedClassName}"` : ''
    })
    .replace(/id="([^"]+)"/g, (_match, id: string) => `id="${prefix}${id}"`)
    .replace(/url\(#([^\)]+)\)/g, (_match, id: string) => `url(#${prefix}${id})`)
}

function buildHighlightToneMap(highlights: CompactMapHighlight[]) {
  const highlightDataMap = buildHighlightDataMap(highlights)
  const bySvgId = new Map<string, CompactMapTone>()

  for (const [svgId, highlight] of highlightDataMap) {
    bySvgId.set(svgId, highlight.tone)
  }

  return bySvgId
}

function buildHighlightDataMap(highlights: CompactMapHighlight[]) {
  const bySvgId = new Map<string, CompactMapHighlight>()

  for (const highlight of highlights) {
    for (const svgId of resolveSvgIdsForBodyMapLabel(highlight.label)) {
      const currentHighlight = bySvgId.get(svgId)

      if (!currentHighlight || compactTonePriority[highlight.tone] >= compactTonePriority[currentHighlight.tone]) {
        bySvgId.set(svgId, highlight)
      }
    }
  }

  return bySvgId
}

function applyCompactHighlightStyle(element: SVGElement, tone: CompactMapTone | undefined, hovered = false) {
  const hasTone = Boolean(tone)

  element.style.color = tone ? hovered ? compactToneHoverColors[tone] : compactToneColors[tone] : '#4f5867'
  element.style.opacity = hasTone ? '0.92' : '0.26'
  element.style.filter = hasTone ? 'drop-shadow(0 0 10px rgba(214,176,95,0.16))' : 'none'
  element.style.transition = 'none'
}

export function SectionIntro({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
      <div>
        {eyebrow ? <div className="text-xs uppercase tracking-[0.28em] text-white/32">{eyebrow}</div> : null}
        <h1 className="mt-2 font-display text-5xl font-bold tracking-[-0.06em] text-white">{title}</h1>
        <p className="mt-3 max-w-3xl text-base leading-8 text-white/68">{description}</p>
      </div>
      {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
    </div>
  )
}

export function SearchField({ value, placeholder, onChange }: { value: string; placeholder: string; onChange: (value: string) => void }) {
  return (
    <label className="flex min-h-14 items-center gap-3 rounded-[24px] border border-white/8 bg-[#0b0f15] px-4 text-white/70 focus-within:border-[#d6b05f]/45">
      <Search className="h-5 w-5 text-white/35" />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="w-full bg-transparent text-sm outline-none placeholder:text-white/28"
      />
    </label>
  )
}

export function FilterChip({ label, active, onClick }: { label: string; active?: boolean; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex min-h-11 items-center rounded-2xl border px-4 text-sm font-medium transition',
        active
          ? 'border-[#d6b05f]/50 bg-[#281e0f] text-[#f5d998]'
          : 'border-white/8 bg-white/4 text-white/68 hover:border-white/14 hover:bg-white/6 hover:text-white',
      )}
    >
      {label}
    </button>
  )
}

export function ViewModeToggle({ mode, onChange }: { mode: 'grid' | 'list'; onChange: (mode: 'grid' | 'list') => void }) {
  return (
    <div className="inline-flex rounded-[22px] border border-[#d6b05f]/20 bg-white/4 p-1">
      <button
        type="button"
        onClick={() => onChange('grid')}
        className={cn('inline-flex min-h-11 items-center gap-2 rounded-[18px] px-4 text-sm transition', mode === 'grid' ? 'bg-[#3b2b11] text-[#f3d18b]' : 'text-white/58')}
      >
        <Grid2x2 className="h-4 w-4" />
        Плитки
      </button>
      <button
        type="button"
        onClick={() => onChange('list')}
        className={cn('inline-flex min-h-11 items-center gap-2 rounded-[18px] px-4 text-sm transition', mode === 'list' ? 'bg-[#3b2b11] text-[#f3d18b]' : 'text-white/58')}
      >
        <List className="h-4 w-4" />
        Список
      </button>
    </div>
  )
}

function MetricTag({ label }: { label: string }) {
  return <span className="inline-flex items-center rounded-xl border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/68">{label}</span>
}

function CompatibilityBadge({ tone, text }: { tone: ExerciseSummary['compatibilityTone']; text: string }) {
  return <span className={cn('inline-flex items-center rounded-full border px-3 py-1 text-xs font-medium', toneClasses[tone])}>{text}</span>
}

export function ExerciseVideoPlayer({
  videoUrl,
  videoLabel,
  wrapperClassName,
  videoClassName,
  lazyLoad = false,
}: {
  videoUrl?: string
  videoLabel: string
  wrapperClassName?: string
  videoClassName?: string
  lazyLoad?: boolean
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const resolvedVideoUrl = resolveApiAssetUrl(videoUrl)
  const [shouldLoad, setShouldLoad] = useState(Boolean(videoUrl) && !lazyLoad)
  const [isPlaybackVisible, setIsPlaybackVisible] = useState(Boolean(videoUrl) && !lazyLoad)
  const [isLoading, setIsLoading] = useState(Boolean(videoUrl) && !lazyLoad)

  useEffect(() => {
    setShouldLoad(Boolean(videoUrl) && !lazyLoad)
    setIsPlaybackVisible(Boolean(videoUrl) && !lazyLoad)
    setIsLoading(Boolean(videoUrl) && !lazyLoad)
  }, [lazyLoad, videoUrl])

  useEffect(() => {
    if (!resolvedVideoUrl || !lazyLoad || shouldLoad || typeof IntersectionObserver === 'undefined') {
      return
    }

    const node = containerRef.current

    if (!node) {
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setShouldLoad(true)
          setIsLoading(true)
          observer.disconnect()
        }
      },
      { rootMargin: '720px 0px' },
    )

    observer.observe(node)

    return () => observer.disconnect()
  }, [lazyLoad, resolvedVideoUrl, shouldLoad])

  useEffect(() => {
    if (!resolvedVideoUrl || !lazyLoad || typeof IntersectionObserver === 'undefined') {
      return
    }

    const node = containerRef.current

    if (!node) {
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        setIsPlaybackVisible(entries.some((entry) => entry.isIntersecting))
      },
      { rootMargin: '240px 0px' },
    )

    observer.observe(node)

    return () => observer.disconnect()
  }, [lazyLoad, resolvedVideoUrl])

  useEffect(() => {
    if (!resolvedVideoUrl || !shouldLoad) {
      return
    }

    const node = videoRef.current

    if (!node) {
      return
    }

    if (!isPlaybackVisible) {
      node.pause()
      return
    }

    setIsLoading(true)

    const frameId = requestAnimationFrame(() => {
      const playPromise = node.play()

      if (playPromise) {
        void playPromise.catch(() => {})
      }
    })

    return () => cancelAnimationFrame(frameId)
  }, [isPlaybackVisible, resolvedVideoUrl, shouldLoad])

  return (
    <div ref={containerRef} className={cn('relative aspect-video overflow-hidden rounded-[24px] bg-[radial-gradient(circle_at_top,rgba(214,176,95,0.18),transparent_38%),linear-gradient(180deg,#161b22,#0a0c0f)]', wrapperClassName)}>
      {resolvedVideoUrl && shouldLoad && isPlaybackVisible ? (
        <video
          ref={videoRef}
          key={resolvedVideoUrl}
          className={cn('absolute inset-0 h-full w-full object-cover', videoClassName)}
          autoPlay
          muted
          loop
          playsInline
          preload={lazyLoad ? 'metadata' : 'auto'}
          aria-label={videoLabel}
          onLoadedData={() => {
            const node = videoRef.current

            if (!node) {
              return
            }

            if (node.currentTime === 0 && Number.isFinite(node.duration) && node.duration > 0.12) {
              try {
                node.currentTime = 0.12
              } catch {}
            }

            const playPromise = node.play()

            if (playPromise) {
              void playPromise.catch(() => setIsLoading(false))
            }
          }}
          onCanPlay={() => {
            const node = videoRef.current

            if (!node) {
              return
            }

            const playPromise = node.play()

            if (playPromise) {
              void playPromise.catch(() => setIsLoading(false))
            }
          }}
          onPlaying={() => setIsLoading(false)}
          onSeeked={() => setIsLoading(false)}
          onTimeUpdate={() => setIsLoading(false)}
          onError={() => setIsLoading(false)}
        >
          <source src={resolvedVideoUrl} type="video/mp4" />
        </video>
      ) : null}
      {resolvedVideoUrl && shouldLoad && isPlaybackVisible && isLoading ? (
        <div className="absolute inset-0 flex items-center justify-center bg-black/28">
          <LoaderCircle className="h-8 w-8 animate-spin text-white/85" aria-hidden="true" />
        </div>
      ) : null}
    </div>
  )
}

function ExerciseMedia({
  title,
  accent,
  videoUrl,
  videoLabel,
  lazyLoadVideo,
  onClick,
}: {
  title: string
  accent?: string
  videoUrl?: string
  videoLabel?: string
  lazyLoadVideo?: boolean
  onClick?: () => void
}) {
  const media = videoUrl ? (
    <ExerciseVideoPlayer videoUrl={videoUrl} videoLabel={videoLabel ?? `Видео упражнения ${title}`} lazyLoad={lazyLoadVideo} />
  ) : (
    <div className="flex aspect-video items-center justify-center bg-[radial-gradient(circle_at_top,rgba(214,176,95,0.2),transparent_38%),linear-gradient(180deg,#181a1e,#090b0e)] p-4 text-center text-sm text-white/55">
      Техника и медиа упражнения
    </div>
  )

  return (
    <div className={cn('overflow-hidden rounded-[24px] border border-white/8', accent)}>
      {onClick && videoUrl ? (
        <button type="button" onClick={onClick} className="group relative block w-full text-left">
          {media}
        </button>
      ) : media}
    </div>
  )
}

function resolvePreferredExerciseVideo(exercise: ExerciseDetails, preferredVideoGender: ExerciseDetails['videos'][number]['gender']) {
  return exercise.videos.find((video) => video.gender === preferredVideoGender && video.view === 'side')
    ?? exercise.videos.find((video) => video.gender === preferredVideoGender)
    ?? exercise.videos[0]
}

function resolveExerciseVideoSequence(exercise: ExerciseDetails, preferredVideoGender: ExerciseDetails['videos'][number]['gender']) {
  const videos = exercise.videos
  const secondaryGender = preferredVideoGender === 'female' ? 'male' : 'female'
  const orderedKeys = [
    `${preferredVideoGender}:side`,
    `${preferredVideoGender}:front`,
    `${secondaryGender}:side`,
    `${secondaryGender}:front`,
  ]
  const sequence: ExerciseDetails['videos'] = []

  for (const key of orderedKeys) {
    const [gender, view] = key.split(':') as [ExerciseDetails['videos'][number]['gender'], ExerciseDetails['videos'][number]['view']]
    const match = videos.find((video) => video.gender === gender && video.view === view)
    if (match && !sequence.some((item) => item.url === match.url)) {
      sequence.push(match)
    }
  }

  for (const video of videos) {
    if (!sequence.some((item) => item.url === video.url)) {
      sequence.push(video)
    }
  }

  return sequence
}

export function ExercisePreviewCard({ exercise, onOpen, onFavorite }: { exercise: ExerciseSummary; onOpen?: () => void; onFavorite?: () => void }) {
  const compatibilityText = exercise.compatibilityTone === 'recommended' ? 'Рекомендуется' : exercise.compatibilityTone === 'blocked' ? 'Блокировка' : exercise.compatibilityTone === 'caution' ? 'Осторожно' : 'Можно выполнять'
  return (
    <article className="catalog-card" aria-label={exercise.name}>
      <ExerciseMedia
        title={exercise.name}
        accent={exercise.recommended ? 'ring-1 ring-[#6ecf71]/25' : undefined}
        videoUrl={exercise.previewVideoUrl}
        videoLabel={exercise.previewVideoUrl ? `${exercise.name} · превью` : undefined}
        lazyLoadVideo={Boolean(exercise.previewVideoUrl)}
      />
      <div className="catalog-card-body">
        <div className="catalog-card-heading">
          <h3 className="font-display font-bold text-white">{exercise.name}</h3>
          <button
            type="button"
            onClick={onFavorite}
            aria-pressed={exercise.favorite}
            aria-label={exercise.favorite ? `Убрать из избранного: ${exercise.name}` : `Добавить в избранное: ${exercise.name}`}
            className="catalog-card-favorite"
          >
            <Star className={cn('h-5 w-5', exercise.favorite ? 'fill-[#f3d18b] text-[#f3d18b]' : '')} aria-hidden="true" />
          </button>
        </div>
        <p className="catalog-card-muscles">{exercise.muscles.slice(0, 2).join(' · ') || exercise.equipment}</p>
        <div className="catalog-card-footer">
          <CompatibilityBadge tone={exercise.compatibilityTone} text={compatibilityText} />
          <Button variant="secondary" onClick={onOpen} aria-label={`Открыть ${exercise.name}`}>Открыть</Button>
        </div>
      </div>
    </article>
  )
}

export function ExerciseActionBar({ onStart, onAdd, onOpenFullScreen }: { onStart?: () => void; onAdd?: () => void; onOpenFullScreen?: () => void }) {
  return (
    <div className="flex flex-wrap gap-3">
      {onStart ? (
        <Button iconLeft={<Play className="h-4 w-4" />} onClick={onStart}>
          Начать
        </Button>
      ) : null}
      {onAdd ? (
        <Button variant="secondary" iconLeft={<Dumbbell className="h-4 w-4" />} onClick={onAdd}>
          Добавить в тренировку
        </Button>
      ) : null}
      {onOpenFullScreen ? (
        <Button variant="secondary" onClick={onOpenFullScreen}>
          Открыть подробно
        </Button>
      ) : null}
    </div>
  )
}

export function LoadModeSelector({ value, options, onChange }: { value: string; options: string[]; onChange?: (value: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => (
        <FilterChip key={option} label={option} active={option === value} onClick={onChange ? () => onChange(option) : undefined} />
      ))}
    </div>
  )
}

function StepperControl({ label, value, suffix, onDecrease, onIncrease }: { label: string; value: string; suffix?: string; onDecrease?: () => void; onIncrease?: () => void }) {
  return (
    <div className="rounded-[24px] border border-white/8 bg-white/4 p-4">
      <div className="text-sm text-white/45">{label}</div>
      <div className="mt-2 flex items-center justify-between gap-3">
        <button type="button" onClick={onDecrease} className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-[#0d1116] text-white/72">-</button>
        <div className="text-center">
          <div className="font-display text-3xl font-bold text-white">{value}</div>
          {suffix ? <div className="text-xs text-white/35">{suffix}</div> : null}
        </div>
        <button type="button" onClick={onIncrease} className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-[#0d1116] text-white/72">+</button>
      </div>
    </div>
  )
}

export function LoadSettingsControl({ settings, onAdjustWeight, onAdjustSets, onAdjustReps, onAdjustRest, onModeChange }: { settings: ExerciseLoadSettings; onAdjustWeight?: (delta: number) => void; onAdjustSets?: (delta: number) => void; onAdjustReps?: (delta: number) => void; onAdjustRest?: (delta: number) => void; onModeChange?: (mode: string) => void }) {
  return (
    <section className="rounded-[30px] border border-white/8 bg-[#111419] p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-sm uppercase tracking-[0.24em] text-white/35">Быстрая настройка</div>
          <div className="mt-2 font-display text-3xl font-bold text-white">Параметры нагрузки</div>
        </div>
        <div className="text-sm text-white/45">Безопасный диапазон {settings.safeRange[0]}–{settings.safeRange[1]} кг</div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StepperControl label="Вес" value={`${settings.weight}`} suffix="кг" onDecrease={onAdjustWeight ? () => onAdjustWeight(-2.5) : undefined} onIncrease={onAdjustWeight ? () => onAdjustWeight(2.5) : undefined} />
        <StepperControl label="Подходы" value={`${settings.sets}`} onDecrease={onAdjustSets ? () => onAdjustSets(-1) : undefined} onIncrease={onAdjustSets ? () => onAdjustSets(1) : undefined} />
        <StepperControl label="Повторы" value={`${settings.reps}`} onDecrease={onAdjustReps ? () => onAdjustReps(-1) : undefined} onIncrease={onAdjustReps ? () => onAdjustReps(1) : undefined} />
        <StepperControl label="Отдых" value={`${settings.restSeconds}`} suffix="сек" onDecrease={onAdjustRest ? () => onAdjustRest(-15) : undefined} onIncrease={onAdjustRest ? () => onAdjustRest(15) : undefined} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[1fr_auto] xl:items-end">
        <div>
          <div className="mb-2 text-sm text-white/45">Режим нагрузки</div>
          <LoadModeSelector value={settings.mode} options={['Обычный вес', 'Контроль техники', 'Лёгкий режим']} onChange={onModeChange} />
        </div>
        <div className="rounded-[24px] border border-[#d6b05f]/18 bg-[#18140b] px-4 py-3 text-sm text-[#f2cf87]">{settings.recommendation}</div>
      </div>
    </section>
  )
}

export function CalibrationStatusBlock({ calibration }: { calibration: ExerciseLoadSettings['calibration'] }) {
  const text = calibration === 'required' ? 'Потребуется перед упражнением' : calibration === 'recommended' ? 'Рекомендуется перед стартом' : calibration === 'ready' ? 'Калибровка сохранена' : 'Недоступно'
  const tone = calibration === 'required' || calibration === 'recommended' ? 'caution' : calibration === 'unavailable' ? 'blocked' : 'recommended'

  return (
    <div className={cn('rounded-[24px] border p-4', toneClasses[tone])}>
      <div className="flex items-center gap-3 font-semibold">
        <ShieldAlert className="h-5 w-5" />
        Калибровка
      </div>
      <div className="mt-2 text-sm text-current/85">{text}</div>
    </div>
  )
}

export function MuscleStatusList({ muscles }: { muscles: MuscleCard[] }) {
  return (
    <div className="space-y-3">
      {muscles.map((muscle) => (
        <div key={muscle.name} className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3 text-sm text-white/78">
          <div className="flex items-center gap-3">
            <span className={cn('inline-flex h-3 w-3 rounded-full', muscleDotClasses[muscle.status])} />
            {muscle.name}
          </div>
          <div>{muscle.score}</div>
        </div>
      ))}
    </div>
  )
}

export const CompactBodyMapGrid = memo(function CompactBodyMapGrid({
  highlights,
  figureGender = 'male',
  onHighlightHover,
  showFigureTitles = true,
  plainFigures = false,
  figureContainerClassName,
  figureMarkupClassName,
  className,
}: {
  highlights: CompactMapHighlight[]
  figureGender?: CompactFigureGender
  onHighlightHover?: (highlight: CompactBodyMapHover | null) => void
  showFigureTitles?: boolean
  plainFigures?: boolean
  figureContainerClassName?: string
  figureMarkupClassName?: string
  className?: string
}) {
  const highlightDataMap = useMemo(() => buildHighlightDataMap(highlights), [highlights])
  const highlightToneMap = useMemo(() => buildHighlightToneMap(highlights), [highlights])

  return (
    <div className={cn('grid items-start gap-4 [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))]', className)}>
      <CompactBodyMapFigure title="Передняя цепь" view="front" figureGender={figureGender} highlightToneMap={highlightToneMap} highlightDataMap={highlightDataMap} onHighlightHover={onHighlightHover} showTitle={showFigureTitles} plain={plainFigures} containerClassName={figureContainerClassName} markupClassName={figureMarkupClassName} />
      <CompactBodyMapFigure title="Задняя цепь" view="back" figureGender={figureGender} highlightToneMap={highlightToneMap} highlightDataMap={highlightDataMap} onHighlightHover={onHighlightHover} showTitle={showFigureTitles} plain={plainFigures} containerClassName={figureContainerClassName} markupClassName={figureMarkupClassName} />
    </div>
  )
})

export function MuscleMapCompact({ primary, secondary, stabilizers, figureGender = 'male' }: { primary: string[]; secondary: string[]; stabilizers: string[]; figureGender?: CompactFigureGender }) {
  const highlights: CompactMapHighlight[] = [
    ...primary.map((label) => ({ label, tone: 'primary' as const })),
    ...secondary.map((label) => ({ label, tone: 'secondary' as const })),
    ...stabilizers.map((label) => ({ label, tone: 'stabilizer' as const })),
  ]

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1fr_0.9fr]">
      <div className="rounded-[30px] border border-white/8 bg-[#111419] p-5">
        <div className="mb-4 text-sm uppercase tracking-[0.24em] text-white/35">Мышечная карта</div>
        <CompactBodyMapGrid highlights={highlights} figureGender={figureGender} />
      </div>
      <div className="space-y-4 lg:col-span-2">
        <RolePanel title="Основные мышцы" items={primary} tone="recommended" />
        <RolePanel title="Дополнительные мышцы" items={secondary} tone="okay" />
        <RolePanel title="Стабилизаторы" items={stabilizers} tone="caution" />
      </div>
    </div>
  )
}

export function CompactBodyMapMini({
  muscles,
  figureGender = 'male',
  label = 'Мышцы упражнения',
  className,
  figureContainerClassName = 'h-[84px] p-0',
  figureMarkupClassName = 'max-w-[42px]',
}: {
  muscles: string[]
  figureGender?: CompactFigureGender
  label?: string
  className?: string
  figureContainerClassName?: string
  figureMarkupClassName?: string
}) {
  const highlights = useMemo<CompactMapHighlight[]>(() => muscles.map((muscle) => ({ label: muscle, tone: 'primary' })), [muscles])
  const highlightDataMap = useMemo(() => buildHighlightDataMap(highlights), [highlights])
  const highlightToneMap = useMemo(() => buildHighlightToneMap(highlights), [highlights])

  return (
    <div aria-label={label} className={cn('grid grid-cols-2 gap-1 rounded-[16px] border border-white/8 bg-[#0b1017] p-1', className)}>
      <CompactBodyMapFigure title="Передняя цепь" view="front" figureGender={figureGender} highlightToneMap={highlightToneMap} highlightDataMap={highlightDataMap} showTitle={false} plain containerClassName={figureContainerClassName} markupClassName={figureMarkupClassName} />
      <CompactBodyMapFigure title="Задняя цепь" view="back" figureGender={figureGender} highlightToneMap={highlightToneMap} highlightDataMap={highlightDataMap} showTitle={false} plain containerClassName={figureContainerClassName} markupClassName={figureMarkupClassName} />
    </div>
  )
}

function RolePanel({ title, items, tone }: { title: string; items: string[]; tone: keyof typeof toneClasses }) {
  return (
    <div className="rounded-[26px] border border-white/8 bg-[#111419] p-5">
      <div className="mb-3 flex items-center justify-between">
        <div className="font-semibold text-white">{title}</div>
        <CompatibilityBadge tone={tone as ExerciseSummary['compatibilityTone']} text={title} />
      </div>
      <div className="flex flex-wrap gap-2">
        {items.map((item) => (
          <MetricTag key={item} label={item} />
        ))}
      </div>
    </div>
  )
}

function CompactBodyMapFigure({
  title,
  view,
  figureGender,
  highlightToneMap,
  highlightDataMap,
  onHighlightHover,
  showTitle = true,
  plain = false,
  containerClassName,
  markupClassName,
}: {
  title: string
  view: BodyMapView
  figureGender: CompactFigureGender
  highlightToneMap: Map<string, CompactMapTone>
  highlightDataMap: Map<string, CompactMapHighlight>
  onHighlightHover?: (highlight: CompactBodyMapHover | null) => void
  showTitle?: boolean
  plain?: boolean
  containerClassName?: string
  markupClassName?: string
}) {
  const [markup, setMarkup] = useState<string | null>(null)
  const [loadError, setLoadError] = useState(false)
  const svgIdPrefix = `${useId().replace(/:/g, '')}-compact-`
  const containerId = `${svgIdPrefix}${view}`

  useEffect(() => {
    let cancelled = false
    const svgPath = compactSvgPathByGenderAndView[figureGender][view]
    const cachedMarkup = compactInlineSvgCache.get(svgPath)

    if (cachedMarkup) {
      setMarkup(prefixCompactSvgMarkup(cachedMarkup, svgIdPrefix))
      setLoadError(false)
      return () => {
        cancelled = true
      }
    }

    fetch(svgPath)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Unable to load ${svgPath}`)
        }

        return response.text()
      })
      .then((svgMarkup) => {
        if (cancelled) {
          return
        }

        compactInlineSvgCache.set(svgPath, svgMarkup)
        setMarkup(prefixCompactSvgMarkup(svgMarkup, svgIdPrefix))
        setLoadError(false)
        })
      .catch(() => {
        if (!cancelled) {
          setLoadError(true)
        }
      })

    return () => {
      cancelled = true
    }
  }, [figureGender, svgIdPrefix, view])

  useLayoutEffect(() => {
    const container = document.getElementById(containerId)

    if (!container || !markup) {
      return
    }

    const svgRoot = container.querySelector<SVGSVGElement>('svg')
    const bodyModel = container.querySelector<SVGElement>(`[id="${svgIdPrefix}body"]`)
    const svgHost = svgRoot?.parentElement instanceof HTMLElement ? svgRoot.parentElement : null

    container.querySelectorAll('[data-compact-body-outline-overlay="true"]').forEach((node) => node.remove())

    if (svgRoot) {
      svgRoot.style.color = '#5f6b7b'
      svgRoot.style.display = 'block'
    }

    if (bodyModel) {
      bodyModel.style.opacity = '0'
      bodyModel.style.pointerEvents = 'none'
      bodyModel.querySelectorAll<SVGElement>('path, line, ellipse').forEach((element) => {
        element.style.pointerEvents = 'none'
        if (element.hasAttribute('stroke')) {
          element.setAttribute('stroke', '#596273')
        }
      })
    }

    if (svgRoot && svgHost && bodyModel) {
      svgHost.style.position = 'relative'

      const outlineOverlay = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
      outlineOverlay.setAttribute('data-compact-body-outline-overlay', 'true')
      outlineOverlay.setAttribute('viewBox', svgRoot.getAttribute('viewBox') ?? '0 0 660.46 1206.46')
      outlineOverlay.setAttribute('aria-hidden', 'true')
      outlineOverlay.style.position = 'absolute'
      outlineOverlay.style.inset = '0'
      outlineOverlay.style.width = '100%'
      outlineOverlay.style.height = '100%'
      outlineOverlay.style.pointerEvents = 'none'
      outlineOverlay.style.overflow = 'visible'
      outlineOverlay.style.display = 'block'

      const outlineClone = bodyModel.cloneNode(true)

      if (outlineClone instanceof SVGElement) {
        outlineClone.removeAttribute('id')
        outlineClone.style.opacity = '0.88'
        outlineClone.style.pointerEvents = 'none'
        outlineClone.querySelectorAll<SVGElement>('path, line, ellipse').forEach((element) => {
          element.style.pointerEvents = 'none'
          if (element.hasAttribute('stroke')) {
            element.setAttribute('stroke', '#596273')
          }
        })
        outlineOverlay.appendChild(outlineClone)
        svgHost.appendChild(outlineOverlay)
      }
    }

    for (const svgId of svgIdsByView[view]) {
      const element = container.querySelector<SVGElement>(`[id="${svgIdPrefix}${svgId}"]`)

      if (!element) {
        continue
      }

      const tone = highlightToneMap.get(svgId)
      applyCompactHighlightStyle(element, tone)
    }
  })

  useEffect(() => {
    const container = document.getElementById(containerId)

    if (!container || !markup || !onHighlightHover) {
      return
    }

    const cleanupCallbacks: Array<() => void> = []
    const resetHighlightStyles = (highlight: CompactMapHighlight) => {
      for (const relatedSvgId of resolveSvgIdsForBodyMapLabel(highlight.label)) {
        if (!svgIdsByView[view].includes(relatedSvgId)) {
          continue
        }

        const relatedElement = container.querySelector<SVGElement>(`[id="${svgIdPrefix}${relatedSvgId}"]`)

        if (!relatedElement) {
          continue
        }

        applyCompactHighlightStyle(relatedElement, highlightToneMap.get(relatedSvgId))
      }
    }
    const handlePointerLeave = () => {
      onHighlightHover(null)

      for (const [svgId, tone] of highlightToneMap) {
        if (!svgIdsByView[view].includes(svgId)) {
          continue
        }

        const element = container.querySelector<SVGElement>(`[id="${svgIdPrefix}${svgId}"]`)

        if (element) {
          applyCompactHighlightStyle(element, tone)
        }
      }
    }

    container.addEventListener('pointerleave', handlePointerLeave)
    cleanupCallbacks.push(() => container.removeEventListener('pointerleave', handlePointerLeave))

    for (const svgId of svgIdsByView[view]) {
      const element = container.querySelector<SVGElement>(`[id="${svgIdPrefix}${svgId}"]`)
      const highlight = highlightDataMap.get(svgId)

      if (!element || !highlight) {
        continue
      }

      const handlePointerEnter = () => {
        for (const relatedSvgId of resolveSvgIdsForBodyMapLabel(highlight.label)) {
          if (!svgIdsByView[view].includes(relatedSvgId)) {
            continue
          }

          const relatedElement = container.querySelector<SVGElement>(`[id="${svgIdPrefix}${relatedSvgId}"]`)

          if (relatedElement) {
            applyCompactHighlightStyle(relatedElement, highlightToneMap.get(relatedSvgId), true)
          }
        }

        onHighlightHover({
          label: highlight.label,
          tone: highlight.tone,
          anchor: { top: element.getBoundingClientRect().top, left: element.getBoundingClientRect().left },
        })
      }

      const handlePointerOut = () => {
        resetHighlightStyles(highlight)
        if (highlight.description) onHighlightHover(null)
      }
      const handleKeyDown = (event: KeyboardEvent) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          handlePointerEnter()
        }
      }

      element.style.cursor = 'pointer'
      element.addEventListener('pointerenter', handlePointerEnter)
      element.addEventListener('pointerleave', handlePointerOut)
      // Described regions opt into keyboard/touch access without changing existing maps.
      if (highlight.description) {
        element.setAttribute('tabindex', '0')
        element.setAttribute('role', 'button')
        element.setAttribute('aria-label', highlight.description)
        element.addEventListener('focus', handlePointerEnter)
        element.addEventListener('blur', handlePointerOut)
        element.addEventListener('click', handlePointerEnter)
        element.addEventListener('keydown', handleKeyDown)
      }
      cleanupCallbacks.push(() => {
        element.removeEventListener('pointerenter', handlePointerEnter)
        element.removeEventListener('pointerleave', handlePointerOut)
        if (highlight.description) {
          element.removeAttribute('tabindex')
          element.removeAttribute('role')
          element.removeAttribute('aria-label')
          element.removeEventListener('focus', handlePointerEnter)
          element.removeEventListener('blur', handlePointerOut)
          element.removeEventListener('click', handlePointerEnter)
          element.removeEventListener('keydown', handleKeyDown)
        }
      })
    }

    return () => {
      cleanupCallbacks.forEach((cleanup) => cleanup())
    }
  }, [containerId, highlightDataMap, markup, onHighlightHover, svgIdPrefix, view])

  return (
    <div className={plain ? '' : 'rounded-[24px] border border-white/8 bg-[radial-gradient(circle_at_top,rgba(214,176,95,0.18),transparent_35%)] p-4'}>
      {showTitle ? <div className="mb-4 text-sm uppercase tracking-[0.24em] text-white/35">{title}</div> : null}
      <div id={containerId} className={cn(plain ? 'flex h-[360px] items-center justify-center overflow-hidden p-0' : 'flex h-[360px] items-center justify-center overflow-hidden rounded-[20px] border border-dashed border-white/10 bg-[#0d1116]/50 p-4', containerClassName)}>
        {markup ? <div className={cn('w-full max-w-[180px] text-[#5f6b7b]', markupClassName)} dangerouslySetInnerHTML={{ __html: markup }} /> : <div className="text-sm text-white/35">{loadError ? 'Карта недоступна' : 'Загрузка карты...'}</div>}
      </div>
    </div>
  )
}

export function ExerciseDetailsModal({
  exercise,
  open,
  onOpenChange,
  onStart,
  onAdd,
  onOpenFullScreen,
  preferredVideoGender = 'male',
}: {
  exercise: ExerciseDetails
  open: boolean
  onOpenChange: (open: boolean) => void
  onStart?: () => void
  onAdd?: () => void
  onOpenFullScreen?: () => void
  preferredVideoGender?: ExerciseDetails['videos'][number]['gender']
}) {
  const preferredVideo = useMemo(() => resolvePreferredExerciseVideo(exercise, preferredVideoGender), [exercise, preferredVideoGender])
  const videoSequence = useMemo(() => resolveExerciseVideoSequence(exercise, preferredVideoGender), [exercise, preferredVideoGender])
  const [activeVideoIndex, setActiveVideoIndex] = useState(0)

  useEffect(() => {
    const preferredIndex = Math.max(0, videoSequence.findIndex((video) => video.url === preferredVideo?.url))
    setActiveVideoIndex(preferredIndex)
  }, [exercise.slug, preferredVideo?.url, preferredVideoGender, videoSequence])

  const activeVideo = videoSequence[activeVideoIndex] ?? preferredVideo

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm" />
        <SafetyDialogContent className="fixed left-1/2 top-1/2 z-50 w-[min(1280px,calc(100vw-24px))] max-h-[calc(100vh-24px)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-[34px] border border-white/10 bg-[#0c0f14] p-6 text-white shadow-[0_30px_100px_rgba(0,0,0,0.55)] xl:p-8">
          <Dialog.Close aria-label="Закрыть модальное окно" title="Закрыть модальное окно" className="absolute right-6 top-6 inline-flex h-[var(--ui-control)] w-[var(--ui-control)] items-center justify-center rounded-full border border-white/10 bg-white/4 text-white/65 xl:right-8 xl:top-8">
            <X className="h-4 w-4" />
          </Dialog.Close>
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_360px] xl:items-start">
            <div className="space-y-6">
              <div className="pr-[calc(var(--ui-control)+1rem)]">
                <div className="min-w-0">
                  <Dialog.Title className="font-display text-5xl font-bold tracking-[-0.06em] text-white">{exercise.name}</Dialog.Title>
                  <Dialog.Description className="mt-2 text-2xl text-white/45">{exercise.secondaryName}</Dialog.Description>
                </div>
              </div>

              <div className="overflow-hidden rounded-[30px] border border-white/8 bg-[radial-gradient(circle_at_top,rgba(214,176,95,0.16),transparent_36%),linear-gradient(180deg,#12161d,#090b0f)] p-3 md:p-4">
                <ExerciseMedia
                  title={exercise.name}
                  accent="ring-1 ring-[#d6b05f]/18"
                  videoUrl={activeVideo?.url}
                  videoLabel={activeVideo?.label}
                  onClick={videoSequence.length > 1 ? () => setActiveVideoIndex((current) => (current + 1) % videoSequence.length) : undefined}
                />
                <div className="mt-4 flex flex-wrap gap-2">
                  {exercise.muscles.map((item) => (
                    <MetricTag key={item} label={item} />
                  ))}
                  <MetricTag label={exercise.equipment} />
                  <MetricTag label={exercise.difficultyLabel} />
                </div>
              </div>

              <div className="grid gap-4 lg:grid-cols-[1.05fr_0.95fr]">
                <div className="rounded-[28px] border border-white/8 bg-white/4 p-5">
                  <div className="flex items-center gap-3 text-sm uppercase tracking-[0.24em] text-white/35">
                    <span className="inline-flex h-9 w-9 items-center justify-center rounded-2xl border border-[#d6b05f]/18 bg-[#18140b] text-[#f2cf87]">
                      <Flame className="h-4 w-4" />
                    </span>
                    Фокус упражнения
                  </div>
                  <div className="mt-3 text-base leading-8 text-white/76">{exercise.description}</div>
                  <div className="mt-4 rounded-[22px] border border-[#d6b05f]/16 bg-[#18140b] px-4 py-4 text-sm leading-7 text-[#f2cf87]">{exercise.muscleRoleText}</div>
                </div>

                <div className="rounded-[28px] border border-white/8 bg-white/4 p-5">
                  <div className="font-semibold text-white">Кратко</div>
                  <ol className="mt-4 space-y-3 text-sm leading-7 text-white/72">
                    {exercise.shortSteps.map((step, index) => (
                      <li key={step} className="flex gap-3">
                        <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-[#d6b05f]/28 text-xs text-[#f1d391]">{index + 1}</span>
                        {step}
                      </li>
                    ))}
                  </ol>
                  {onOpenFullScreen ? <button type="button" onClick={onOpenFullScreen} className="mt-4 text-sm text-[#f2cf87] underline-offset-4 hover:underline">Подробнее о технике</button> : null}
                </div>
              </div>
            </div>

            <div className="space-y-4 xl:sticky xl:top-24 xl:pt-[calc(var(--ui-control)+1rem)]">
              <div className={cn('rounded-[28px] border p-5', toneClasses[exercise.compatibility.tone])}>
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3 font-semibold">
                    <span className="inline-flex h-9 w-9 items-center justify-center rounded-2xl border border-current/20 bg-black/10">
                      <CircleAlert className="h-4 w-4" />
                    </span>
                    {exercise.compatibility.title}
                  </div>
                  <CircleAlert className="h-5 w-5" />
                </div>
                <p className="mt-3 text-sm leading-7">{exercise.compatibility.description}</p>
              </div>

              {onStart || onAdd ? (
                <div className="flex flex-col gap-3">
                  {onStart ? <Button onClick={onStart} iconLeft={<Play className="h-4 w-4" />}>Начать упражнение</Button> : null}
                  {onAdd ? <Button variant="secondary" onClick={onAdd} iconLeft={<Dumbbell className="h-4 w-4" />}>Добавить в тренировку</Button> : null}
                </div>
              ) : null}

              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                <DataStat label="Мышцы" value={exercise.muscles.join(', ')} icon={<Dumbbell className="h-4 w-4" />} />
                <DataStat label="Оборудование" value={exercise.equipment} icon={<ShieldAlert className="h-4 w-4" />} />
                <DataStat label="Сложность" value={exercise.difficultyLabel} icon={<Star className="h-4 w-4" />} />
                <DataStat label="Тип усилия" value={exercise.force === 'Push' ? 'Жим / толчок' : exercise.force === 'Pull' ? 'Тяга' : exercise.force === 'Stretch' ? 'Растяжка' : 'Статика'} icon={<Flame className="h-4 w-4" />} />
                <DataStat label="Механика" value={exercise.mechanic === 'Compound' ? 'Базовое' : exercise.mechanic === 'Isolation' ? 'Изолирующее' : 'Мобильность'} icon={<CircleAlert className="h-4 w-4" />} />
                <DataStat label="Хват" value={exercise.grips} icon={<ChevronRight className="h-4 w-4" />} />
              </div>
            </div>
          </div>
        </SafetyDialogContent>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function DataStat({ label, value, icon }: { label: string; value: string; icon?: ReactNode }) {
  return (
    <div className="rounded-[22px] border border-white/8 bg-white/4 px-4 py-3">
      <div className="flex items-center gap-2 text-sm text-white/45">
        {icon ? <span className="text-[#f2cf87]">{icon}</span> : null}
        {label}
      </div>
      <div className="mt-1 text-white">{value}</div>
    </div>
  )
}

export function WorkoutExerciseRow({ row, active, onSelect, actions }: { row: WorkoutExerciseRowData; active?: boolean; onSelect?: () => void; actions?: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'grid w-full gap-4 rounded-[24px] border px-4 py-4 text-left transition md:grid-cols-[1.5fr_0.9fr_0.9fr_0.7fr_auto]',
        active ? 'border-[#d6b05f]/45 bg-[#231b0d]' : 'border-white/8 bg-white/4 hover:border-white/14 hover:bg-white/6',
      )}
    >
      <div>
        <div className="font-semibold text-white">{row.name}</div>
        <div className="mt-1 text-sm text-white/45">{row.muscles}</div>
      </div>
      <div className="text-sm text-white/66">{row.load}</div>
      <div className="text-sm text-white/66">{row.rest}</div>
      <div className="text-sm text-white/66">{row.calibration}</div>
      <div className="flex items-center justify-end gap-2">
        <MetricTag label={row.status === 'up-next' ? 'Следующее' : row.status === 'planned' ? 'Далее' : row.status === 'in-progress' ? 'В работе' : row.status === 'completed' ? 'Готово' : row.status === 'skipped' ? 'Пропуск' : 'Внимание'} />
        {actions ?? <ChevronRight className="h-4 w-4 text-white/35" />}
      </div>
    </button>
  )
}

export function WorkoutPlanList({ rows, activeId, onSelect, footer }: { rows: WorkoutExerciseRowData[]; activeId: string; onSelect: (id: string) => void; footer?: ReactNode }) {
  return (
    <section className="rounded-[32px] border border-white/8 bg-[#111419] p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-sm uppercase tracking-[0.24em] text-white/35">План тренировки</div>
          <div className="mt-2 font-display text-3xl font-bold text-white">Порядок упражнений</div>
        </div>
        <Button variant="ghost">Порядок</Button>
      </div>
      <div className="space-y-3">
        {rows.map((row) => (
          <WorkoutExerciseRow key={row.id} row={row} active={row.id === activeId} onSelect={() => onSelect(row.id)} />
        ))}
      </div>
      {footer ? <div className="mt-4">{footer}</div> : null}
    </section>
  )
}

export function ProgramCard({ program, selected, onSelect }: { program: ProgramSummary; selected?: boolean; onSelect?: () => void }) {
  return (
    <button type="button" onClick={onSelect} className={cn('rounded-[28px] border p-4 text-left transition', selected ? 'border-[#d6b05f]/45 bg-[#231b0d]' : 'border-white/8 bg-[#111419] hover:border-white/14 hover:bg-[#14181e]')}>
      <ExerciseMedia title={program.name} accent={program.recommendedToday ? 'ring-1 ring-[#69d46b]/20' : undefined} />
      <div className="mt-4">
        <div className="font-display text-3xl font-bold text-white">{program.name}</div>
        <div className="mt-1 text-white/45">{program.subtitle}</div>
        <div className="mt-4 grid grid-cols-3 gap-3 text-sm text-white/62">
          <div>{program.exerciseCount} упражнений</div>
          <div>{program.setCount} подходов</div>
          <div>≈ {program.durationMinutes} мин</div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {program.focusTags.map((tag) => (
            <MetricTag key={tag} label={tag} />
          ))}
        </div>
      </div>
    </button>
  )
}

export function ProgramDetailsPanel({ details, onPrimary, onAdapt, onCalendar, onBuilder }: { details: ProgramDetails; onPrimary?: () => void; onAdapt?: () => void; onCalendar?: () => void; onBuilder?: () => void }) {
  return (
    <aside className="rounded-[32px] border border-white/8 bg-[#111419] p-5">
      <div className="font-display text-4xl font-bold text-white">{details.name}</div>
      <div className="mt-2 text-lg text-white/45">{details.subtitle}</div>
      <div className={cn('mt-5 rounded-[24px] border p-4', details.compatibility.tone === 'great' ? toneClasses.recommended : details.compatibility.tone === 'okay' ? toneClasses.okay : toneClasses.caution)}>
        <div className="font-semibold">{details.compatibility.title}</div>
        <p className="mt-2 text-sm leading-7">{details.compatibility.description}</p>
      </div>
      <div className="mt-5 space-y-3">
        {details.exerciseLines.map((line) => (
          <div key={line.order} className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3 text-sm text-white/78">
            <div>
              <div className="font-medium text-white">{line.order}. {line.name}</div>
              <div className="text-white/45">{line.load}</div>
            </div>
            <div className="text-white/45">{line.rest}</div>
          </div>
        ))}
      </div>
      <div className="mt-5 flex flex-col gap-3">
        <Button iconLeft={<Play className="h-4 w-4" />} onClick={onPrimary}>{details.actions.primary}</Button>
        <Button variant="secondary" onClick={onAdapt}>{details.actions.secondary}</Button>
        <Button variant="secondary" onClick={onCalendar}>{details.actions.calendar}</Button>
        <Button variant="secondary" onClick={onBuilder}>{details.actions.builder}</Button>
      </div>
      <div className="mt-5 grid gap-3 md:grid-cols-2">
        <DataStat label="Чёрный список" value={`${details.blacklistIssues} упражнений`} />
        <DataStat label="Оборудование" value={details.equipmentCoverage} />
      </div>
    </aside>
  )
}

export function BuilderWarningPanel({ title, description, tone }: { title: string; description: string; tone: 'warning' | 'blocked' | 'success' }) {
  const classes = tone === 'success' ? 'border-[#57c968]/25 bg-[#122d1d] text-[#91e59d]' : tone === 'blocked' ? toneClasses.blocked : toneClasses.caution
  return (
    <div className={cn('rounded-[24px] border p-4', classes)}>
      <div className="flex items-center gap-3 font-semibold">{tone === 'success' ? <ShieldAlert className="h-4 w-4" /> : <Flame className="h-4 w-4" />}{title}</div>
      <div className="mt-2 text-sm leading-7">{description}</div>
    </div>
  )
}

export function SupportCard() {
  return (
    <div className="rounded-[28px] border border-[#d6b05f]/18 bg-[linear-gradient(180deg,rgba(214,176,95,0.08),rgba(255,255,255,0.02))] p-5 text-white">
      <div className="text-sm text-white/52">Нужна помощь?</div>
      <div className="mt-2 text-base leading-7 text-white/74">Откройте руководство или свяжитесь с поддержкой.</div>
      <Button variant="secondary" className="mt-4 w-full" iconLeft={<CalendarDays className="h-4 w-4" />}>
        Поддержка
      </Button>
    </div>
  )
}