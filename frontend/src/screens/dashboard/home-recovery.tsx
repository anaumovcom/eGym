import { useQuery } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useInRouterContext } from 'react-router-dom'
import type { MuscleCard } from '@/entities/muscle/model/types'
import type { FatigueData } from '@/entities/stage4/model/types'
import { apiGet } from '@/shared/api/client'
import { CompactBodyMapGrid, type CompactBodyMapHover } from '@/shared/ui/stage2/screen-components'
import { fatigueColors, fatigueLabels, fatiguePaletteStyle } from '@/shared/ui/stage4/fatigue-appearance'
import { ensureFatigueMuscleCoverage, fatigueStatusPriority, resolveSvgIdsForBodyMapLabel } from '@/shared/ui/stage4/fatigue-muscle-map'
import './dashboard-fatigue.css'

const placeholders: MuscleCard[] = ensureFatigueMuscleCoverage([]).map(({ name }) => ({ name, status: 'no_data', score: 0 }))

type RecoveryProps = { muscles: MuscleCard[]; figureGender?: 'male' | 'female'; selectedUserId?: string | null }

export function DashboardRecovery({ selectedUserId, ...props }: RecoveryProps) {
  const [selection, setSelection] = useState<string | null>(null)
  // Dashboard rows have names, not atlas IDs. Look up the actual targets only
  // after a deliberate selection, sharing the destination's per-profile cache.
  const { data, isError } = useQuery({
    queryKey: ['fatigue-screen', selectedUserId, 'current'],
    queryFn: () => apiGet<FatigueData>(`/api/fatigue?userId=${encodeURIComponent(selectedUserId!)}&mode=current`),
    enabled: Boolean(selectedUserId && selection),
  })
  const matches = data && ensureFatigueMuscleCoverage(data.muscles).filter(({ name }) => name === selection)
  const target = !isError && matches?.length === 1 ? matches[0].id : null
  return <HomeRecovery {...props} selectedUserId={selectedUserId} atlasTarget={target} onMuscleSelect={setSelection} />
}

export function HomeRecovery({ muscles, figureGender = 'male', selectedUserId, atlasTarget, onMuscleSelect }: RecoveryProps & {
  atlasTarget?: string | null; onMuscleSelect?: (label: string | null) => void
}) {
  const inRouter = useInRouterContext()
  const href = atlasTarget ? `/fatigue?muscle=${encodeURIComponent(atlasTarget)}` : '/fatigue'
  const panel = useRef<HTMLElement>(null)
  const hideTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const [hover, setHover] = useState<CompactBodyMapHover | null>(null)
  const byName = useMemo(() => {
    const covered = new Set(muscles.flatMap(({ name }) => resolveSvgIdsForBodyMapLabel(name)))
    const missing = placeholders.filter(({ name }) => !resolveSvgIdsForBodyMapLabel(name).some((id) => covered.has(id)))
    // The API returns names, not IDs; a legacy and a canonical row can share a name.
    const ranked = [...muscles].sort((a, b) => fatigueStatusPriority[b.status] - fatigueStatusPriority[a.status] || b.score - a.score)
    const winners = new Map<string, MuscleCard>()
    for (const muscle of [...ranked, ...missing]) {
      if (!winners.has(muscle.name)) winners.set(muscle.name, muscle)
    }
    return winners
  }, [muscles])
  // Compact maps take the last highlight at equal severity: send the winner last.
  const highlights = useMemo(() => [...byName.values()].reverse().map((muscle) => ({
    label: muscle.name, tone: muscle.status, score: muscle.score,
    description: `${muscle.name}: ${fatigueLabels[muscle.status]}${muscle.status === 'no_data' ? '' : `, ${muscle.score} балл.`}`,
  })), [byName])
  const cancelHide = useCallback(() => clearTimeout(hideTimer.current), [])
  const onHighlightHover = useCallback((next: CompactBodyMapHover | null) => {
    cancelHide()
    if (next) setHover(next)
    else hideTimer.current = setTimeout(() => setHover(null), 120)
  }, [cancelHide])
  useEffect(() => () => clearTimeout(hideTimer.current), [])
  const muscle = hover ? byName.get(hover.label) : undefined
  const anchor = hover?.anchor
  const bounds = anchor && panel.current?.getBoundingClientRect()
  const placeAbove = bounds && anchor && anchor.top - bounds.top > bounds.bottom - anchor.bottom
  const hintOffset = bounds?.height && anchor
    ? (placeAbove ? bounds.bottom - anchor.top : anchor.bottom - bounds.top) / bounds.height : 0
  const hasData = muscles.some(({ status }) => status !== 'no_data')
  const hasMappedData = muscles.some(({ name, status }) => status !== 'no_data' && resolveSvgIdsForBodyMapLabel(name).length > 0)

  return (
    <section ref={panel} className="home-recovery" style={fatiguePaletteStyle} aria-label="Восстановление мышц" onKeyDown={(event) => {
      if (event.key === 'Escape') { cancelHide(); setHover(null); onMuscleSelect?.(null) }
    }}>
      <header className="home-recovery-heading">
        <div><h2>Усталость мышц</h2>
          <p>{hasMappedData ? 'Нажмите на мышцу' : hasData ? 'Для этих мышц нет области на карте' : 'Пока нет данных о нагрузке'}</p>
        </div>
        {inRouter ? <Link className="home-atlas-link" to={href}>Открыть атлас</Link> : <a className="home-atlas-link" href={href}>Открыть атлас</a>}
      </header>
      <CompactBodyMapGrid highlights={highlights} figureGender={figureGender} portraitUserId={selectedUserId} plainFigures showFigureTitles={false}
        className="home-recovery-figures fatigue-compact" figureContainerClassName="home-recovery-figure" figureMarkupClassName="home-recovery-figure-svg"
        onHighlightHover={onHighlightHover} onHighlightSelect={onMuscleSelect} />
      <div className="home-recovery-scale" aria-label="Цветовая шкала: от готовности к перегрузке; серый — нет данных">
        <div className="fatigue-scale-ramp" aria-hidden="true" /><p><span>Готовность</span><span>{fatigueLabels.critical}</span></p>
      </div>
      {muscle ? <div role="tooltip" className="home-recovery-hint" data-tone={muscle.status} data-placement={placeAbove ? 'above' : 'below'}
        style={{ ['--hint-offset' as string]: `${hintOffset * 100}%`, ['--recovery-tone' as string]: fatigueColors[muscle.status] }}
        onPointerEnter={cancelHide} onPointerLeave={() => onHighlightHover(null)}>
        <strong>{muscle.name}</strong>
        <p><span className="recovery-dot" aria-hidden="true" />{fatigueLabels[muscle.status]}</p>
        {muscle.status !== 'no_data' ? <div className="home-recovery-score">{muscle.score}<span> балл. усталости</span></div> : <p>Нет сохранённых данных о нагрузке</p>}
      </div> : null}
    </section>
  )
}
