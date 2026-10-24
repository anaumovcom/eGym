import { CircleCheck, TriangleAlert } from 'lucide-react'
import { useCallback, useMemo, useState } from 'react'
import type { DashboardWorkoutMuscleLoad } from '@/entities/dashboard/model/types'
import type { MuscleStatus } from '@/entities/muscle/model/types'
import { CompactBodyMapGrid, type CompactBodyMapHover } from '@/shared/ui/stage2/screen-components'

const statusLabels: Record<MuscleStatus, string> = {
  ready: 'готова', light: 'лёгкая усталость', medium: 'умеренная усталость',
  high: 'высокая усталость', critical: 'перегрузка', no_data: 'нет данных',
}
const heavy = new Set<MuscleStatus>(['high', 'critical'])

/** Bars share one scale: 100 points is the overload threshold, longer bars are clipped. */
const barPercent = (score: number) => Math.min(100, Math.max(0, score))

function names(muscles: DashboardWorkoutMuscleLoad[]) {
  return muscles.map((muscle) => muscle.name.toLowerCase()).join(', ')
}

function Verdict({ muscles }: { muscles: DashboardWorkoutMuscleLoad[] }) {
  const tired = muscles.filter((muscle) => heavy.has(muscle.currentStatus))
  const overloaded = muscles.filter((muscle) => !heavy.has(muscle.currentStatus) && heavy.has(muscle.projectedStatus))
  if (!tired.length && !overloaded.length) {
    return (
      <div className="wd-verdict" data-tone="good" role="note">
        <CircleCheck aria-hidden="true" />
        <p><b>Мышцы готовы.</b> Нагрузка не выведет их в зону высокой усталости.</p>
      </div>
    )
  }
  return (
    <div className="wd-verdict" data-tone="warning" role="note">
      <TriangleAlert aria-hidden="true" />
      <p>
        {tired.length ? <>Ещё не восстановились: <b>{names(tired)}</b>. </> : null}
        {overloaded.length ? <>После тренировки будет высокая усталость: <b>{names(overloaded)}</b>.</> : null}
      </p>
    </div>
  )
}

/**
 * Two dialog columns: a vertical front/back map where only the muscles this
 * workout loads blink (coloured by fatigue after a full run), and their list.
 */
export function WorkoutMuscleLoad({ muscles, figureGender }: { muscles: DashboardWorkoutMuscleLoad[]; figureGender: 'male' | 'female' }) {
  const [active, setActive] = useState<string | null>(null)
  const highlights = useMemo(() => muscles.map((muscle) => ({
    label: muscle.name,
    tone: muscle.projectedStatus,
    description: `${muscle.name}: сейчас ${muscle.currentScore}, после тренировки ${muscle.projectedScore} — ${statusLabels[muscle.projectedStatus]}`,
  })), [muscles])
  const onHighlightHover = useCallback((hover: CompactBodyMapHover | null) => setActive(hover?.label ?? null), [])
  const focus = muscles.filter((muscle) => muscle.role === 'primary').slice(0, 3)

  if (!muscles.length) {
    return (
      <section className="wd-load" aria-labelledby="wd-load-title">
        <h3 id="wd-load-title" className="wd-section-title">Нагрузка на мышцы</h3>
        <p className="wd-load-empty">Упражнения этой тренировки не создают заметной усталости мышц.</p>
      </section>
    )
  }

  return (
    <>
      <section className="wd-map" aria-label="Карта нагрузки">
        <CompactBodyMapGrid highlights={highlights} figureGender={figureGender} plainFigures showFigureTitles={false}
          className="wd-load-map" figureContainerClassName="wd-load-figure" figureMarkupClassName="wd-load-figure-svg"
          onHighlightHover={onHighlightHover} />
        <div className="wd-scale" aria-label="Цвет — усталость после тренировки: от готовности к перегрузке">
          <div aria-hidden="true" /><p><span>Готова</span><span>Перегрузка</span></p>
        </div>
      </section>
      <section className="wd-load" aria-labelledby="wd-load-title">
        <h3 id="wd-load-title" className="wd-section-title">Нагрузка на мышцы</h3>
        <Verdict muscles={muscles} />
        {focus.length ? <p className="wd-focus">Акцент: <b>{names(focus)}</b></p> : null}
        <ul className="wd-load-list" aria-label="Мышцы, которые нагрузит тренировка">
          {muscles.map((muscle) => (
            <li key={muscle.name} data-tone={muscle.projectedStatus} data-active={active === muscle.name || undefined}
              onPointerEnter={() => setActive(muscle.name)} onPointerLeave={() => setActive(null)}>
              <span className="wd-load-name">
                <span className="recovery-dot" aria-hidden="true" />
                <strong>{muscle.name}</strong>
                {muscle.role === 'primary' ? <span className="wd-load-role">основная</span> : null}
              </span>
              <span className="wd-load-score" aria-label={`Усталость сейчас ${muscle.currentScore}, после тренировки ${muscle.projectedScore}`}>
                {muscle.currentScore} <span aria-hidden="true">→</span> <b>{muscle.projectedScore}</b>
              </span>
              <span className="wd-load-bar" aria-hidden="true">
                <span className="wd-load-bar-current" style={{ width: `${barPercent(muscle.currentScore)}%` }} />
                <span className="wd-load-bar-added" style={{ width: `${barPercent(muscle.projectedScore) - barPercent(muscle.currentScore)}%` }} />
              </span>
            </li>
          ))}
        </ul>
        <p className="wd-load-hint">Шкала усталости: 0 — восстановлена, 100 — перегрузка. Прогноз — если выполнить все подходы плана.</p>
      </section>
    </>
  )
}
