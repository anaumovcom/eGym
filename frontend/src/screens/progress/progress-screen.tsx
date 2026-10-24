import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Activity, ArrowRight, CalendarCheck, ChevronRight, Dumbbell, ExternalLink, Flame, Lightbulb, Minus, Sparkles, Target, Timer, TrendingDown, TrendingUp, TriangleAlert, Trophy } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router-dom'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { ProgressData, ProgressExerciseInsight, ProgressInsight, ProgressInsights, ProgressKpi, Stage4Period } from '@/entities/stage4/model/types'
import { bodyMeasurementsQuery } from '@/features/body/body-api'
import { BodyMeasurementsView } from '@/features/body/body-measurements-view'
import { BodyWeightPanel } from '@/features/scales/body-weight-panel'
import { apiDelete, apiGet } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { PhotoCaptureDialog } from '@/shared/ui/photo/photo-capture-dialog'
import { useAppStore } from '@/stores/app-store'
import { ActivityHeatmap, SessionTrendChart, Sparkline, VolumeTimeline, type SessionMetric } from './progress-charts'
import { daysAgo, formatDay, formatNumber, plural } from './progress-format'
import { ProgressPhotoGallery, type ProgressPhoto } from './progress-photo-gallery'
import './progress-screen.css'

type ProgressTab = 'overview' | 'strength' | 'body' | 'photo'
const tabs: Array<{ id: ProgressTab; label: string }> = [
  { id: 'overview', label: 'Обзор' }, { id: 'strength', label: 'Сила' }, { id: 'body', label: 'Тело' }, { id: 'photo', label: 'Фото' },
]
const periods: Array<{ id: Stage4Period; label: string }> = [
  { id: '7d', label: '7 дней' }, { id: '30d', label: '30 дней' }, { id: '3m', label: '3 мес' }, { id: '6m', label: '6 мес' }, { id: '1y', label: 'Год' }, { id: 'all', label: 'Всё' },
]
const periodPhrase: Record<Stage4Period, string> = { '7d': 'за 7 дней', '30d': 'за 30 дней', '3m': 'за 3 месяца', '6m': 'за полгода', '1y': 'за год', all: 'за всё время' }
const kpiIcons: Record<ProgressKpi['id'], ReactNode> = { days: <CalendarCheck />, volume: <Dumbbell />, minutes: <Timer />, records: <Trophy /> }
const fallbackMachine: MachineHealth = { machineState: 'ready', machineLabel: 'Загрузка статуса', leftDrive: 'connected', rightDrive: 'connected', safety: 'enabled', calibration: 'Загрузка...' }

export function ProgressScreen() {
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const userId = selectedUserId ?? 'alexey'
  const userName = userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
  const tab = asTab(params.get('tab'))
  const period = asPeriod(params.get('period'))
  const exerciseSlug = params.get('exercise')
  const [photoOpen, setPhotoOpen] = useState(false)

  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['progress-screen', userId, period],
    queryFn: () => apiGet<ProgressData>(`/api/progress?userId=${encodeURIComponent(userId)}&period=${encodeURIComponent(period)}`),
    enabled: params.get('tab') !== 'recovery',
    placeholderData: (previous) => previous,
  })
  const bodyQuery = useQuery({ ...bodyMeasurementsQuery(userId), enabled: tab === 'body' || tab === 'photo' })
  const currentUser = useQuery({ queryKey: ['users-current', userId], queryFn: () => apiGet<{ profile: { heightCm: number | null } | null }>('/api/users/current'), enabled: tab === 'body' })
  const photoQuery = useQuery({
    queryKey: ['progress-photos', userId],
    queryFn: () => apiGet<{ photos: ProgressPhoto[] }>(`/api/photo-progress?userId=${encodeURIComponent(userId)}`),
    enabled: tab === 'photo',
  })

  function update(patch: Record<string, string | null>) {
    setParams((current) => { const next = new URLSearchParams(current); for (const [key, value] of Object.entries(patch)) { if (value) next.set(key, value); else next.delete(key) } return next })
  }

  async function deletePhoto(id: number) {
    await apiDelete(`/api/photo-progress/${id}?confirm=true`)
    queryClient.setQueryData<{ photos: ProgressPhoto[] }>(['progress-photos', userId], (current) => current ? { photos: current.photos.filter((photo) => photo.id !== id) } : current)
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['progress-photos', userId] }),
      queryClient.invalidateQueries({ queryKey: ['user-profile-screen', userId] }),
    ])
  }

  if (params.get('tab') === 'recovery') {
    const next = new URLSearchParams(params)
    next.delete('tab')
    return <Navigate to={`/fatigue${next.size ? `?${next}` : ''}`} replace />
  }

  const showPeriod = tab === 'overview' || tab === 'strength'
  const days = data?.insights?.kpis.find((item) => item.id === 'days')?.value

  return (
    <FormaShell userName={userName} machine={data?.machine ?? fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
      <section className="progress-center" aria-labelledby="progress-title">
        <header className="progress-heading">
          <div>
            <h1 id="progress-title" className="font-display font-bold text-white">Прогресс</h1>
            <p>{days ? `${days} ${plural(days, 'тренировочный день', 'тренировочных дня', 'тренировочных дней')} ${periodPhrase[period]}` : 'Результаты тренировок, изменения тела и фото.'}</p>
          </div>
          {showPeriod ? (
            <div className="pv-periods" role="group" aria-label="Период прогресса">
              {periods.map((item) => <button key={item.id} type="button" aria-pressed={period === item.id} onClick={() => update({ period: item.id === '30d' ? null : item.id })}>{item.label}</button>)}
            </div>
          ) : null}
        </header>
        <nav className="progress-tabs" aria-label="Разделы прогресса">{tabs.map((item) => <button key={item.id} type="button" aria-current={tab === item.id ? 'page' : undefined} onClick={() => update({ tab: item.id === 'overview' ? null : item.id })}>{item.label}</button>)}</nav>
        {tab === 'body' ? (
          <BodyWeightPanel key={userId} userId={userId} userName={userName} heightCm={currentUser.data?.profile?.heightCm}>
            {bodyQuery.data ? <BodyMeasurementsView key={`body-${userId}`} userId={userId} measurements={bodyQuery.data} metrics={['waistCm', 'chestCm', 'hipsCm', 'bodyFatPercent']} mode="summary" title="Объёмы тела" description="Талия, грудь, бёдра и процент жира. Нажмите на показатель, чтобы увидеть его график." /> : bodyQuery.isError ? <div className="forma-state" role="alert"><p>Не удалось загрузить измерения.</p><Button onClick={() => void bodyQuery.refetch()}>Повторить</Button></div> : null}
          </BodyWeightPanel>
        ) : tab === 'photo'
          ? <ProgressPhotoGallery key={userId} photos={photoQuery.data?.photos ?? []} measurements={bodyQuery.data ?? []} loading={photoQuery.isPending} error={photoQuery.isError} onRetry={() => void photoQuery.refetch()} onPhoto={() => setPhotoOpen(true)} onDelete={deletePhoto} />
          : error ? <div className="forma-state" role="alert"><p>Не удалось загрузить прогресс.</p><Button onClick={() => void refetch()}>Повторить</Button></div>
          : isPending || !data ? <ProgressSkeleton />
          : <ProgressContent data={data} tab={tab} period={period} exerciseSlug={exerciseSlug} onExercise={(slug) => update({ exercise: slug })} />}
      </section>
      <PhotoCaptureDialog open={photoOpen} onOpenChange={setPhotoOpen} userId={userId} />
      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}

function ProgressSkeleton() {
  return <div className="pv-skeleton" role="status" aria-label="Загрузка прогресса"><div>{[0, 1, 2, 3].map((item) => <span key={item} />)}</div><span /><span /></div>
}

function ProgressContent({ data, tab, period, exerciseSlug, onExercise }: { data: ProgressData; tab: ProgressTab; period: Stage4Period; exerciseSlug: string | null; onExercise: (slug: string) => void }) {
  const insights = data.insights
  const hasHistory = Boolean(insights?.exercises.length) && !data.emptyState
  if ((tab === 'overview' || tab === 'strength') && (!insights || !hasHistory)) {
    return <ProgressEmpty title={data.emptyState?.title ?? 'Недостаточно данных для аналитики'} text={data.emptyState?.description ?? 'Сохраните тренировку, и здесь появятся графики и рекомендации.'} action={<Button asChild iconLeft={<ArrowRight aria-hidden="true" />}><Link to="/dashboard">Завершить тренировку</Link></Button>} />
  }
  if (tab === 'overview' && insights) return <ProgressOverview insights={insights} period={period} />
  if (tab === 'strength' && insights) return <ProgressStrength insights={insights} exerciseSlug={exerciseSlug} onExercise={onExercise} />
  return null
}

function ProgressOverview({ insights, period }: { insights: ProgressInsights; period: Stage4Period }) {
  const periodActive = insights.timeline.points.some((point) => point.days > 0)
  return (
    <div className="pv-overview">
      <div className="progress-metrics pv-kpis">{insights.kpis.map((kpi) => <KpiCard key={kpi.id} kpi={kpi} previousLabel={insights.previousLabel} period={period} />)}</div>
      {insights.insights.length ? <div className="pv-insights">{insights.insights.map((item) => <InsightCard key={item.title} insight={item} />)}</div> : null}
      <div className="pv-row pv-row-main">
        <PvCard title="Динамика объёма" subtitle={`Поднятый вес ${periodPhrase[period]}, ${insights.timeline.granularity === 'day' ? 'по дням' : insights.timeline.granularity === 'week' ? 'по неделям' : 'по месяцам'}`}>
          {periodActive ? <VolumeTimeline points={insights.timeline.points} granularity={insights.timeline.granularity} /> : <p className="pv-muted">За выбранный период тренировок не было.</p>}
        </PvCard>
        <PvCard title="Регулярность" subtitle="Последние 20 недель">
          <div className="pv-streak">
            <div><Flame aria-hidden="true" /><strong>{insights.activity.streakWeeks}</strong><span>{plural(insights.activity.streakWeeks, 'неделя', 'недели', 'недель')} подряд</span></div>
            <div><CalendarCheck aria-hidden="true" /><strong>{insights.activity.activeDays}</strong><span>{plural(insights.activity.activeDays, 'активный день', 'активных дня', 'активных дней')}</span></div>
          </div>
          <ActivityHeatmap weeks={insights.activity.weeks} />
        </PvCard>
      </div>
      <div className="pv-row pv-row-three">
        <PvCard title="Лидеры роста" subtitle="Прирост расчётного максимума">
          {insights.movers.length ? (
            <ol className="pv-list">
              {insights.movers.map((mover) => (
                <li key={mover.slug}>
                  <Link to={`/progress?tab=strength&exercise=${encodeURIComponent(mover.slug)}`} className="pv-list-row">
                    <span className="pv-list-main"><b>{mover.name}</b><small>{formatNumber(mover.fromValue)} → {formatNumber(mover.toValue)} кг</small></span>
                    <Sparkline values={mover.series} label={`Динамика: ${mover.name}`} />
                    <span className="pv-delta" data-tone="good"><TrendingUp aria-hidden="true" />+{formatNumber(mover.deltaPct)}%</span>
                  </Link>
                </li>
              ))}
            </ol>
          ) : <p className="pv-muted">Пока без роста за период. Попробуйте добавить вес или повтор — подсказка есть во вкладке «Сила».</p>}
        </PvCard>
        <PvCard title="Личные рекорды" subtitle={insights.recordCount ? `${insights.recordCount} ${plural(insights.recordCount, 'рекорд', 'рекорда', 'рекордов')} ${periodPhrase[period]}` : 'Новые максимумы появятся здесь'}>
          {insights.records.length ? (
            <ol className="pv-list">
              {insights.records.map((record) => (
                <li key={`${record.exerciseSlug}-${record.date}`}>
                  <Link to={`/progress?tab=strength&exercise=${encodeURIComponent(record.exerciseSlug)}`} className="pv-list-row">
                    <span className="pv-trophy"><Trophy aria-hidden="true" /></span>
                    <span className="pv-list-main"><b>{record.exerciseName}</b><small>{formatDay(record.date)} · {formatNumber(record.weightKg)} кг × {record.repsPerSet}</small></span>
                    <span className="pv-list-value"><strong>{formatNumber(record.e1rm)} кг</strong><small>+{formatNumber(record.e1rm - record.previous)} кг</small></span>
                  </Link>
                </li>
              ))}
            </ol>
          ) : <p className="pv-muted">Побейте свой расчётный максимум в любом упражнении — и рекорд окажется здесь.</p>}
        </PvCard>
        <PvCard title="Баланс нагрузки" subtitle="Рабочие подходы по зонам" action={<Link className="pv-link" to="/fatigue">Карта усталости<ChevronRight aria-hidden="true" /></Link>}>
          <MuscleBalance items={insights.muscleBalance} />
        </PvCard>
      </div>
    </div>
  )
}

function KpiCard({ kpi, previousLabel, period }: { kpi: ProgressKpi; previousLabel?: string | null; period: Stage4Period }) {
  const delta = kpi.deltaPct
  const tone = delta === null || delta === undefined ? 'none' : delta > 0 ? 'good' : delta < 0 ? 'bad' : 'flat'
  return (
    <article className="pv-kpi" data-kpi={kpi.id}>
      <header><span className="pv-kpi-icon" aria-hidden="true">{kpiIcons[kpi.id]}</span><span>{kpi.label}</span></header>
      <strong>{formatNumber(kpi.value)}{kpi.unit ? <small> {kpi.unit}</small> : null}</strong>
      <footer>
        {tone === 'none' ? <span className="pv-kpi-note">{period === 'all' ? 'за всё время' : 'первый период с данными'}</span> : (
          <>
            <span className="pv-delta" data-tone={tone}>{tone === 'good' ? <TrendingUp aria-hidden="true" /> : tone === 'bad' ? <TrendingDown aria-hidden="true" /> : <Minus aria-hidden="true" />}{delta! > 0 ? '+' : ''}{delta}%</span>
            <span className="pv-kpi-note" title={previousLabel ? `по сравнению с ${previousLabel}` : undefined}>было {formatNumber(kpi.previous ?? 0)}{kpi.unit ? ` ${kpi.unit}` : ''}</span>
          </>
        )}
      </footer>
      <Sparkline values={kpi.spark} label={`${kpi.label} по периодам`} />
    </article>
  )
}

function InsightCard({ insight }: { insight: ProgressInsight }) {
  const icon = insight.tone === 'good' ? <Sparkles aria-hidden="true" /> : insight.tone === 'warning' ? <TriangleAlert aria-hidden="true" /> : <Lightbulb aria-hidden="true" />
  const body = <><span className="pv-insight-icon">{icon}</span><span><b>{insight.title}</b><small>{insight.text}</small></span>{insight.href ? <ChevronRight className="pv-insight-arrow" aria-hidden="true" /> : null}</>
  return insight.href ? <Link className="pv-insight" data-tone={insight.tone} to={insight.href}>{body}</Link> : <div className="pv-insight" data-tone={insight.tone}>{body}</div>
}

function MuscleBalance({ items }: { items: ProgressInsights['muscleBalance'] }) {
  const max = Math.max(...items.map((item) => item.sets), 1)
  if (!items.some((item) => item.sets)) return <p className="pv-muted">Нет силовых подходов за период.</p>
  return (
    <ul className="pv-balance">
      {items.map((item) => (
        <li key={item.id} data-empty={!item.sets || undefined}>
          <span>{item.name}</span>
          <span className="pv-balance-track"><i style={{ width: `${Math.max(item.sets ? 3 : 0, (item.sets / max) * 100)}%` }} /></span>
          <b>{item.sets}</b>
          <small>{Math.round(item.share * 100)}%</small>
        </li>
      ))}
    </ul>
  )
}

function ProgressStrength({ insights, exerciseSlug, onExercise }: { insights: ProgressInsights; exerciseSlug: string | null; onExercise: (slug: string) => void }) {
  const active = insights.exercises.filter((item) => item.sessionsInPeriod > 0)
  const [showAll, setShowAll] = useState(false)
  const visible = showAll || !active.length ? insights.exercises : active
  const selected = insights.exercises.find((item) => item.slug === exerciseSlug) ?? visible[0]
  const hidden = insights.exercises.length - active.length
  return (
    <div className="ps-layout">
      <aside className="ps-list" aria-label="Упражнения">
        <h2>Упражнения <span>{visible.length}</span></h2>
        <div className="ps-list-scroll">
          {visible.map((item) => (
            <button key={item.slug} type="button" aria-pressed={item.slug === selected.slug} onClick={() => onExercise(item.slug)}>
              <span className="ps-list-main"><b>{item.name}</b><small>{item.sessionsInPeriod ? `${item.sessionsInPeriod} ${plural(item.sessionsInPeriod, 'тренировка', 'тренировки', 'тренировок')}` : 'вне периода'} · {daysAgo(item.lastDate)}</small></span>
              <TrendChip value={item.trendPct} />
            </button>
          ))}
        </div>
        {hidden > 0 && active.length ? <button type="button" className="ps-list-more" onClick={() => setShowAll((value) => !value)}>{showAll ? 'Только за период' : `Ещё ${hidden} вне периода`}</button> : null}
      </aside>
      <ExerciseDetail key={selected.slug} exercise={selected} />
    </div>
  )
}

function TrendChip({ value }: { value?: number | null }) {
  if (value === null || value === undefined) return <span className="pv-delta" data-tone="none">—</span>
  const tone = value > 0 ? 'good' : value < 0 ? 'bad' : 'flat'
  return <span className="pv-delta" data-tone={tone}>{tone === 'good' ? <TrendingUp aria-hidden="true" /> : tone === 'bad' ? <TrendingDown aria-hidden="true" /> : <Minus aria-hidden="true" />}{value > 0 ? '+' : ''}{formatNumber(value)}%</span>
}

function ExerciseDetail({ exercise }: { exercise: ProgressExerciseInsight }) {
  const weighted = exercise.kind === 'weighted'
  const metrics: Array<{ id: SessionMetric; label: string }> = weighted
    ? [{ id: 'e1rm', label: '1ПМ' }, { id: 'weight', label: 'Вес' }, { id: 'volume', label: 'Объём' }]
    : [{ id: 'reps', label: exercise.unit === 'сек' ? 'Время' : 'Повторы' }]
  const [metric, setMetric] = useState<SessionMetric>(metrics[0].id)
  const inPeriod = exercise.sessions.slice(-exercise.sessionsInPeriod || undefined)
  const chartSessions = exercise.sessionsInPeriod >= 2 ? inPeriod : exercise.sessions
  const withWeight = exercise.sessions.filter((session) => session.weightKg > 0)
  const chartable = weighted ? chartSessions.filter((session) => session.weightKg > 0) : chartSessions
  const stats = weighted
    ? [
        { label: 'Расчётный максимум', value: `${formatNumber(exercise.bestE1rm ?? 0)} кг`, hint: 'по формуле Эпли' },
        { label: 'Лучший рабочий вес', value: `${formatNumber(exercise.bestWeight)} кг`, hint: `из ${withWeight.length} ${plural(withWeight.length, 'тренировки', 'тренировок', 'тренировок')}` },
        { label: 'Лучший объём', value: `${formatNumber(exercise.bestVolume)} кг`, hint: 'за одну тренировку' },
        { label: 'Тренировок', value: String(exercise.sessions.length), hint: `последняя ${daysAgo(exercise.lastDate)}` },
      ]
    : [
        { label: exercise.unit === 'сек' ? 'Лучшее время' : 'Лучший подход', value: `${exercise.bestReps} ${exercise.unit}`, hint: 'в одном подходе' },
        { label: 'Тренировок', value: String(exercise.sessions.length), hint: `последняя ${daysAgo(exercise.lastDate)}` },
      ]
  const history = [...exercise.sessions].reverse().slice(0, 10)

  return (
    <section className="ps-detail" aria-labelledby="ps-detail-title">
      <header className="ps-detail-head">
        <div><h2 id="ps-detail-title">{exercise.name}</h2><p>{exercise.sessionsInPeriod ? `${exercise.sessionsInPeriod} ${plural(exercise.sessionsInPeriod, 'тренировка', 'тренировки', 'тренировок')} за период` : 'Нет тренировок за выбранный период — показана вся история'}</p></div>
        <Link className="pv-link" to={`/catalog/${encodeURIComponent(exercise.slug)}`}>Об упражнении<ExternalLink aria-hidden="true" /></Link>
      </header>
      <div className="ps-stats">{stats.map((item) => <div key={item.label}><span>{item.label}</span><strong>{item.value}</strong><small>{item.hint}</small></div>)}</div>
      <div className="ps-main" data-single={!exercise.nextTarget || undefined}>
        <PvCard
          title="Динамика"
          subtitle={exercise.sessionsInPeriod >= 2 ? 'Тренировки за период' : 'Вся история упражнения'}
          action={metrics.length > 1 ? <div className="pv-segment" role="group" aria-label="Показатель графика">{metrics.map((item) => <button key={item.id} type="button" aria-pressed={metric === item.id} onClick={() => setMetric(item.id)}>{item.label}</button>)}</div> : null}
        >
          {chartable.length ? <SessionTrendChart sessions={chartable} metric={metric} unit={exercise.unit} /> : <p className="pv-muted">Нет тренировок с весом.</p>}
          {chartable.some((session) => session.isPr) ? <p className="ps-legend"><i aria-hidden="true" />личный рекорд</p> : null}
        </PvCard>
        {exercise.nextTarget ? (
          <article className="ps-target">
            <header><Target aria-hidden="true" /><span>Цель на следующую тренировку</span></header>
            <strong>{formatNumber(exercise.nextTarget.weightKg)} <small>кг</small></strong>
            <p className="ps-target-scheme">{exercise.nextTarget.sets} × {exercise.nextTarget.repsPerSet} повт.</p>
            <p>{exercise.nextTarget.note}</p>
            <Button asChild variant="secondary" iconLeft={<Activity aria-hidden="true" />}><Link to={`/catalog/${encodeURIComponent(exercise.slug)}`}>К упражнению</Link></Button>
          </article>
        ) : null}
      </div>
      <PvCard title="История" subtitle={`Последние ${history.length} ${plural(history.length, 'тренировка', 'тренировки', 'тренировок')}`}>
        <div className="ps-table-wrap">
          <table className="ps-table">
            <thead><tr><th>Дата</th>{weighted ? <th>Вес</th> : null}<th>Подходы</th><th>{weighted ? 'Объём' : 'Всего'}</th><th>RPE</th>{weighted ? <th>1ПМ</th> : null}</tr></thead>
            <tbody>
              {history.map((session, index) => (
                <tr key={`${session.date}-${index}`} data-pr={session.isPr || undefined}>
                  <td>{formatDay(session.date, true)}{session.isPr ? <span className="ps-pr"><Trophy aria-hidden="true" />рекорд</span> : null}</td>
                  {weighted ? <td>{session.weightKg > 0 ? `${formatNumber(session.weightKg)} кг` : '—'}</td> : null}
                  <td>{session.sets} × {session.repsPerSet}{weighted ? '' : ` ${exercise.unit}`}</td>
                  <td>{weighted ? `${formatNumber(session.volumeKg)} кг` : `${session.reps} ${exercise.unit}`}</td>
                  <td>{session.rpe}</td>
                  {weighted ? <td>{session.e1rm ? `${formatNumber(session.e1rm)} кг` : '—'}</td> : null}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </PvCard>
    </section>
  )
}

function PvCard({ title, subtitle, action, children }: { title: string; subtitle?: string; action?: ReactNode; children: ReactNode }) {
  return <section className="pv-card"><header><div><h3>{title}</h3>{subtitle ? <p>{subtitle}</p> : null}</div>{action}</header>{children}</section>
}

function ProgressEmpty({ title, text, action }: { title: string; text: string; action: ReactNode }) { return <div className="progress-empty"><h2>{title}</h2><p>{text}</p>{action}</div> }
function asPeriod(value: string | null): Stage4Period { return value === '7d' || value === '30d' || value === '3m' || value === '6m' || value === '1y' || value === 'all' ? value : '30d' }
function asTab(value: string | null): ProgressTab { if (value === 'strength' || value === 'body' || value === 'photo') return value; if (value === 'exercise' || value === 'regularity' || value === 'muscles') return 'strength'; return 'overview' }
