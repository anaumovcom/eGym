import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { MuscleCard, MuscleStatus } from '@/entities/muscle/model/types'
import { CompactBodyMapGrid, type CompactBodyMapHover } from '@/shared/ui/stage2/screen-components'
import { ensureFatigueMuscleCoverage } from '@/shared/ui/stage4/fatigue-muscle-map'

const labels: Record<MuscleStatus, string> = {
  ready: 'Готова к нагрузке', light: 'Лёгкая усталость', medium: 'Умеренная усталость',
  high: 'Высокая усталость', critical: 'Перегрузка', no_data: 'Нет данных',
}
const placeholders: MuscleCard[] = ensureFatigueMuscleCoverage([]).map(({ name }) => ({ name, status: 'no_data', score: 0 }))

export function HomeRecovery({ muscles, figureGender = 'male' }: { muscles: MuscleCard[]; figureGender?: 'male' | 'female' }) {
  const panel = useRef<HTMLElement>(null)
  const hideTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const [hover, setHover] = useState<CompactBodyMapHover | null>(null)
  const byName = useMemo(() => new Map([...placeholders, ...muscles].map((muscle) => [muscle.name, muscle])), [muscles])
  const highlights = useMemo(() => [...byName.values()].map((muscle) => ({
    label: muscle.name, tone: muscle.status,
    description: `${muscle.name}: ${labels[muscle.status]}${muscle.status === 'no_data' ? '' : `, ${muscle.score} балл.`}`,
  })), [byName])
  const cancelHide = useCallback(() => clearTimeout(hideTimer.current), [])
  const onHighlightHover = useCallback((next: CompactBodyMapHover | null) => {
    cancelHide()
    if (next) setHover(next)
    else hideTimer.current = setTimeout(() => setHover(null), 120)
  }, [cancelHide])
  useEffect(() => () => clearTimeout(hideTimer.current), [])
  const muscle = hover ? byName.get(hover.label) : undefined
  const panelBounds = panel.current?.getBoundingClientRect()
  const hintTop = panelBounds && hover?.anchor
    ? Math.max(0, Math.min(panelBounds.height - 140, hover.anchor.top - panelBounds.top)) : 0

  return (
    <section ref={panel} className="home-recovery" aria-label="Восстановление мышц" onKeyDown={(event) => {
      if (event.key === 'Escape') { cancelHide(); setHover(null) }
    }}>
      <header className="home-recovery-heading">
        <h2>Усталость мышц</h2>
        <p>{muscles.some((item) => item.status !== 'no_data') ? 'Наведите на мышцу' : 'Пока нет данных о нагрузке'}</p>
      </header>
      <CompactBodyMapGrid highlights={highlights} figureGender={figureGender} plainFigures showFigureTitles={false}
        className="home-recovery-figures" figureContainerClassName="home-recovery-figure" figureMarkupClassName="home-recovery-figure-svg"
        onHighlightHover={onHighlightHover} />
      <div className="home-recovery-scale" aria-label="Цветовая шкала: от готовности к перегрузке; серый — нет данных">
        <div aria-hidden="true" /><p><span>Готовность</span><span>Перегрузка</span></p>
      </div>
      {muscle ? <div role="tooltip" className="home-recovery-hint" data-tone={muscle.status} style={{ top: hintTop }}
        onPointerEnter={cancelHide} onPointerLeave={() => onHighlightHover(null)}>
        <strong>{muscle.name}</strong>
        <p><span className="recovery-dot" aria-hidden="true" />{labels[muscle.status]}</p>
        {muscle.status !== 'no_data' ? <div className="home-recovery-score">{muscle.score}<span> балл. усталости</span></div> : <p>Нет сохранённых данных о нагрузке</p>}
      </div> : null}
    </section>
  )
}
