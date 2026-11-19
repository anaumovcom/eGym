import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, CalendarDays, ChevronDown, RotateCcw, Timer } from 'lucide-react'
import { useCallback, useMemo, useRef, useState, type CSSProperties, type PropsWithChildren } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { FatigueData, FatigueMode, FatigueMuscle } from '@/entities/stage4/model/types'
import { apiGet, apiPost } from '@/shared/api/client'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { fatigueColors, fatigueLabels, fatigueLegend } from '@/shared/ui/stage4/fatigue-appearance'
import { ensureFatigueMuscleCoverage, fatigueRegionKey } from '@/shared/ui/stage4/fatigue-muscle-map'
import { MuscleMapDetailed } from '@/shared/ui/stage4/muscle-map-detailed'
import { useAppStore } from '@/stores/app-store'
import './fatigue-screen.css'

const periods: { id: FatigueMode; label: string }[] = [
  { id: 'current', label: 'Сейчас' },
  { id: 'after-workout', label: 'После тренировки' },
  { id: '7d', label: '7 дней' },
  { id: '30d', label: '30 дней' },
]

function asFatigueMode(value: string | null): FatigueMode {
  if (value === 'current' || value === 'after-workout' || value === '7d' || value === '30d') {
    return value
  }

  return 'current'
}

export function FatigueScreen() {
  const [searchParams, setSearchParams] = useSearchParams()
  const workspace = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const mode = asFatigueMode(searchParams.get('mode'))
  const userId = selectedUserId ?? 'alexey'
  const fatigueFigureGender = selectedUserId === 'elena' ? 'female' : 'male'
  const [resetInProgress, setResetInProgress] = useState(false)
  const [resetError, setResetError] = useState(false)
  const { data, isPlaceholderData, error, refetch } = useQuery({
    queryKey: ['fatigue-screen', userId, mode],
    placeholderData: (previous, query) => query?.queryKey[1] === userId ? previous : undefined,
    queryFn: () => apiGet<FatigueData>(`/api/fatigue?userId=${encodeURIComponent(userId)}&mode=${encodeURIComponent(mode)}`),
  })

  const updateParam = useCallback((key: 'mode' | 'muscle', value: string) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.set(key, value)
      return next
    })
  }, [setSearchParams])
  const selectMuscle = useCallback((id: string) => updateParam('muscle', id), [updateParam])
  const selectFromFigure = useCallback((id: string) => {
    selectMuscle(id)
    if (window.matchMedia?.('(max-width: 760px)').matches) {
      workspace.current?.querySelector('aside')?.scrollIntoView({ block: 'nearest' })
    }
  }, [selectMuscle])

  async function handleResetFatigue() {
    if (resetInProgress) {
      return
    }

    setResetInProgress(true)
    setResetError(false)
    try {
      await apiPost('/api/fatigue/reset', { userId })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['fatigue-screen', userId] }),
        queryClient.invalidateQueries({ queryKey: ['dashboard', userId] }),
      ])
    } catch {
      setResetError(true)
    } finally {
      setResetInProgress(false)
    }
  }

  const muscles = useMemo(() => ensureFatigueMuscleCoverage(data?.muscles ?? []), [data?.muscles])
  const selectedKey = fatigueRegionKey(searchParams.get('muscle') ?? data?.muscles[0]?.id ?? 'chest')
  const selected = muscles.find((item) => fatigueRegionKey(item.id) === selectedKey) ?? muscles[0]

  return (
    <StandaloneFatigueFrame machine={data?.machine}>
      <section className="fatigue-hero" aria-labelledby="fatigue-map-title">
        <header className="atlas-heading">
          <h1 id="fatigue-map-title">Карта мышечной усталости</h1>
          <div className="atlas-periods" role="group" aria-label="Период карты усталости">
            {periods.map(({ id, label }) => (
              <button key={id} type="button" aria-pressed={mode === id} onClick={() => updateParam('mode', id)}>{label}</button>
            ))}
          </div>
        </header>
        {error ? (
          <div className="atlas-state" role="alert">
            <p>Не удалось загрузить данные усталости.</p>
            <button type="button" onClick={() => void refetch()}>Повторить</button>
          </div>
        ) : !data ? <div className="atlas-state" role="status">Загрузка карты усталости…</div> : (
          <div className="atlas-workspace" ref={workspace} aria-busy={isPlaceholderData}>
            <section className="atlas-board" aria-label="Интерактивная карта мышц">
              <div className="fatigue-map">
                <MuscleMapDetailed muscles={muscles} selectedId={selected.id} onSelect={selectFromFigure} figureGender={fatigueFigureGender} userId={userId} />
              </div>
              <ul className="atlas-legend" aria-label="Шкала усталости">
                {fatigueLegend.map(({ status, label }) => (
                  <li key={status}><i aria-hidden="true" data-tone={status} style={{ backgroundColor: fatigueColors[status] }} />{label}</li>
                ))}
              </ul>
            </section>
            <SelectedZone muscle={selected} muscles={muscles} onSelect={selectMuscle} />
          </div>
        )}
      </section>
      {data && !error && (
        <section className="fatigue-details" aria-label="Подробности усталости мышц">
          <div className="atlas-details-heading">
            <h2>Сводка нагрузки</h2>
            <button className="atlas-text-action" type="button" disabled={resetInProgress} onClick={() => void handleResetFatigue()}>
              <RotateCcw aria-hidden="true" />{resetInProgress ? 'Сбрасываю…' : 'Сбросить усталость'}
            </button>
          </div>
          {resetError && <p role="alert">Не удалось сбросить усталость. Попробуйте ещё раз.</p>}
          <dl className="atlas-overview">
            {data.overview.map((item) => (
              <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd>{item.hint && <small>{item.hint}</small>}</div>
            ))}
          </dl>
          <div className="atlas-notes">
            <section>
              <h3>Рекомендация Forma</h3>
              <p>{data.recommendedPlan}</p>
              <Link to="/calendar" className="atlas-text-action"><CalendarDays aria-hidden="true" />Открыть календарь</Link>
            </section>
            <section>
              <h3>Состояние мышц</h3>
              <div className="atlas-muscle-list">
                {muscles.filter((item) => item.status !== 'no_data').map((item) => (
                  <button key={item.id} type="button" aria-pressed={item.id === selected.id} onClick={() => selectMuscle(item.id)}>
                    <i aria-hidden="true" style={{ backgroundColor: fatigueColors[item.status] }} />
                    {item.name}<b>{item.score}</b>
                  </button>
                ))}
                {!muscles.some((item) => item.status !== 'no_data') && <p>Пока нет данных о нагрузке.</p>}
              </div>
            </section>
          </div>
          {(selected.impact.length > 0 || selected.recommendedExercises.length > 0 || selected.avoidExercises.length > 0) && (
            <section className="atlas-history">
              <h3>{selected.name}</h3>
              <div className="atlas-history-columns">
                {selected.impact.length > 0 && <div><h4>Последние нагрузки</h4><ul>{selected.impact.map((item, index) => (
                  <li key={`${item.exercise}-${index}`}><span>{item.exercise}<small>{item.date}</small></span><b>{item.share}</b></li>
                ))}</ul></div>}
                {([{ title: 'Рекомендуется сегодня', exercises: selected.recommendedExercises }, { title: 'Лучше отложить', exercises: selected.avoidExercises }]).map(({ title, exercises }) => (
                  exercises.length > 0 && <div key={title}><h4>{title}</h4><ul>{exercises.map((item) => (
                    <li key={item.name}><span>{item.name}<small>{item.note}</small></span></li>
                  ))}</ul></div>
                ))}
              </div>
            </section>
          )}
        </section>
      )}
    </StandaloneFatigueFrame>
  )
}

function SelectedZone({ muscle, muscles, onSelect }: { muscle: FatigueMuscle; muscles: FatigueMuscle[]; onSelect: (id: string) => void }) {
  const hasData = muscle.status !== 'no_data'
  const name = fatigueRegionKey(muscle.id) === 'chest' && muscle.name === 'Грудь' ? 'Грудные мышцы' : muscle.name
  const recovery = muscle.status === 'ready' ? 'Готова' : `≈ ${muscle.recoveryHours} ч`
  return (
    <aside className="atlas-inspector" aria-labelledby="atlas-zone-title" style={{ '--tone': fatigueColors[muscle.status] } as CSSProperties}>
      <div className="atlas-region-picker">
        <label htmlFor="atlas-zone-picker">Выбранная зона</label>
        <div>
          <h2 id="atlas-zone-title">{name}</h2><ChevronDown aria-hidden="true" />
          <select id="atlas-zone-picker" value={muscle.id} onChange={(event) => onSelect(event.target.value)}>
            {muscles.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
      </div>
      <div className="atlas-score-section" aria-live="polite" aria-atomic="true">
        <div className="atlas-score"><strong>{hasData ? muscle.score : '—'}</strong>{hasData && <span>/ 100</span>}</div>
        <div className="atlas-score-label">Баллы усталости</div>
        <div className="atlas-meter" aria-hidden="true"><i style={{ width: `${hasData ? Math.min(100, Math.max(0, muscle.score)) : 0}%` }} /></div>
        <span className="atlas-badge" data-tone={muscle.status}>{fatigueLabels[muscle.status]}</span>
      </div>
      <dl className="atlas-recovery">
        <div><dt><Timer aria-hidden="true" />Восстановление</dt><dd>{hasData ? recovery : '—'}</dd></div>
        <div><dt>Готовность</dt><dd>{hasData ? `${muscle.readinessPercent}%` : '—'}</dd></div>
      </dl>
      <p className="atlas-advice">{hasData ? muscle.recommendation : 'После тренировки с нагрузкой на эту зону здесь появится оценка восстановления.'}</p>
      <Link to="/dashboard" className="atlas-workout-link">Выбрать тренировку<ArrowRight aria-hidden="true" /></Link>
    </aside>
  )
}

function StandaloneFatigueFrame({ machine, children }: PropsWithChildren<{ machine?: MachineHealth }>) {
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const userName = selectedUserId === 'elena' ? 'Елена' : selectedUserId === 'guest' ? 'Гость' : 'Алексей'
  const fallbackMachine: MachineHealth = {
    machineState: 'ready',
    machineLabel: 'Загрузка статуса',
    leftDrive: 'connected',
    rightDrive: 'connected',
    safety: 'enabled',
    calibration: 'Загрузка...',
  }

  return (
    <div className="atlas-page"><FormaShell legacy userName={userName} machine={machine ?? fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
      {children}
      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell></div>
  )
}
