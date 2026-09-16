import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Camera, ChevronDown } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { ProgressData, Stage4Period } from '@/entities/stage4/model/types'
import { stage4Periods } from '@/mocks/stage4-data'
import { FatigueScreen } from '@/screens/fatigue/fatigue-screen'
import { apiGet, resolveApiAssetUrl } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { PhotoCaptureDialog } from '@/shared/ui/photo/photo-capture-dialog'
import { BarChartCard, LineChartCard, Panel } from '@/shared/ui/stage4/screen-components'
import { useAppStore } from '@/stores/app-store'

type ProgressTab = 'overview' | 'strength' | 'body' | 'photo' | 'recovery'
type PhotoAsset = { id: number; view: 'front' | 'side' | 'back'; takenAt: string; thumbnailUrl: string }
const tabs: Array<{ id: ProgressTab; label: string }> = [
  { id: 'overview', label: 'Обзор' }, { id: 'strength', label: 'Сила' }, { id: 'body', label: 'Тело' }, { id: 'photo', label: 'Фото' }, { id: 'recovery', label: 'Восстановление' },
]
const fallbackMachine: MachineHealth = { machineState: 'ready', machineLabel: 'Загрузка статуса', leftDrive: 'connected', rightDrive: 'connected', safety: 'enabled', calibration: 'Загрузка...' }

export function ProgressScreen() {
  const [params, setParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const userId = selectedUserId ?? 'alexey'
  const userName = userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
  const tab = asTab(params.get('tab'))
  const period = asPeriod(params.get('period'))
  const exerciseSlug = params.get('exercise') ?? 'machine-pulldown'
  const [photoOpen, setPhotoOpen] = useState(false)

  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['progress-screen', userId, period, exerciseSlug],
    queryFn: () => apiGet<ProgressData>(`/api/progress?userId=${encodeURIComponent(userId)}&period=${encodeURIComponent(period)}&exerciseSlug=${encodeURIComponent(exerciseSlug)}`),
    enabled: tab !== 'recovery',
  })
  const { data: photos } = useQuery({
    queryKey: ['progress-photos', userId],
    queryFn: () => apiGet<{ photos: PhotoAsset[] }>(`/api/photo-progress?userId=${encodeURIComponent(userId)}`),
    enabled: tab === 'photo',
  })

  function update(patch: Record<string, string | null>) {
    setParams((current) => { const next = new URLSearchParams(current); for (const [key, value] of Object.entries(patch)) { if (value) next.set(key, value); else next.delete(key) } return next })
  }

  return (
    <FormaShell userName={userName} machine={data?.machine ?? fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
      <section className="progress-center" aria-labelledby="progress-title">
        <header className="progress-heading">
          <div><h1 id="progress-title" className="font-display font-bold text-white">Прогресс</h1><p>Результаты тренировок, изменения тела, фото и восстановление.</p></div>
          {tab !== 'recovery' ? <label className="progress-period"><span>Период</span><select aria-label="Период прогресса" value={period} onChange={(event) => update({ period: event.target.value })}>{stage4Periods.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select><ChevronDown aria-hidden="true" /></label> : null}
        </header>
        <nav className="progress-tabs" aria-label="Разделы прогресса">{tabs.map((item) => <button key={item.id} type="button" aria-current={tab === item.id ? 'page' : undefined} onClick={() => update({ tab: item.id === 'overview' ? null : item.id })}>{item.label}</button>)}</nav>

        {tab === 'recovery' ? <FatigueScreen embedded /> : error ? <div className="forma-state" role="alert"><p>Не удалось загрузить прогресс.</p><Button onClick={() => void refetch()}>Повторить</Button></div> : isPending || !data ? <div className="forma-state" role="status">Загрузка прогресса…</div> : <ProgressContent data={data} tab={tab} exerciseSlug={exerciseSlug} update={update} photos={photos?.photos ?? []} onPhoto={() => setPhotoOpen(true)} />}
      </section>
      <PhotoCaptureDialog open={photoOpen} onOpenChange={setPhotoOpen} userId={userId} />
      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}

function ProgressContent({ data, tab, exerciseSlug, update, photos, onPhoto }: { data: ProgressData; tab: Exclude<ProgressTab, 'recovery'>; exerciseSlug: string; update: (patch: Record<string, string | null>) => void; photos: PhotoAsset[]; onPhoto: () => void }) {
  if (data.emptyState && tab === 'overview') {
    return <div className="progress-empty"><h2>{data.emptyState.title}</h2><p>{data.emptyState.description}</p><Button asChild iconLeft={<ArrowRight aria-hidden="true" />}><Link to="/dashboard">Завершить тренировку</Link></Button></div>
  }

  if (tab === 'overview') return (
    <div className="progress-overview">
      <div className="progress-metrics">{data.summaryCards.slice(0, 4).map((item) => <article key={item.label} data-tone={item.tone}><span>{item.label}</span><strong>{item.value}</strong><small>{item.hint}</small></article>)}</div>
      <LineChartCard title="Динамика объёма" subtitle={data.periodLabel} points={data.summaryVolumeSeries} />
      <Panel title="Главный прогресс"><div className="progress-highlight"><h3>{data.mainProgress.exercise}</h3><p>{data.mainProgress.from} → {data.mainProgress.to}</p><strong>{data.mainProgress.delta}</strong></div></Panel>
      <Panel title="Рекомендация Forma"><p className="text-white/70 leading-8">{data.recommendation}</p><Button asChild variant="secondary" className="mt-5"><Link to="/dashboard">Выбрать тренировку</Link></Button></Panel>
    </div>
  )

  if (tab === 'strength') return (
    <div className="progress-section">
      <div className="progress-section-toolbar"><h2>Сила и объём</h2><label><span>Упражнение</span><select aria-label="Выбрать упражнение" value={exerciseSlug} onChange={(event) => update({ exercise: event.target.value })}>{data.exerciseOptions.map((item) => <option key={item.slug} value={item.slug}>{item.name}</option>)}</select></label></div>
      <div className="progress-metrics">{data.strengthCards.slice(0, 4).map((item) => <article key={item.label}><span>{item.label}</span><strong>{item.value}</strong></article>)}</div>
      {data.selectedExercise.history.length ? <><div className="progress-two"><LineChartCard title="Рабочий вес" subtitle="Последние тренировки" points={data.selectedExercise.workWeightSeries} /><BarChartCard title="Объём упражнения" subtitle="По сессиям" points={data.selectedExercise.volumeSeries} /></div><Panel title="Топ упражнений по объёму"><div className="progress-ranking">{data.volumeTopExercises.map((item) => <div key={item.rank}><b>{item.rank}</b><span>{item.name}</span><strong>{item.value}</strong></div>)}</div></Panel></> : <ProgressActionEmpty title="Нет данных о силе" text="Выполните упражнение, чтобы увидеть рабочий вес, объём и историю." action={<Button asChild><Link to="/dashboard">Выбрать тренировку</Link></Button>} />}
    </div>
  )

  if (tab === 'body') return (
    <div className="progress-section">
      <div className="progress-section-toolbar"><h2>Изменения тела</h2><Button asChild variant="secondary"><Link to="/profile?tab=measurements">Добавить измерение</Link></Button></div>
      {data.bodyWeightSeries.length ? <><div className="progress-metrics">{data.bodyCards.slice(0, 4).map((item) => <article key={item.label} data-tone={item.tone}><span>{item.label}</span><strong>{item.value}</strong></article>)}</div><div className="progress-two"><LineChartCard title="Вес" subtitle="По сохранённым измерениям" points={data.bodyWeightSeries} /><Panel title="Объёмы"><div className="progress-ranking">{data.bodyMeasurements.map((item, index) => <div key={item.label}><b>{index + 1}</b><span>{item.label}</span><strong>{item.current} · {item.delta}</strong></div>)}</div></Panel></div></> : <ProgressActionEmpty title="Нет измерений" text="Добавьте вес и объёмы тела — здесь появится динамика." action={<Button asChild><Link to="/profile?tab=measurements">Добавить измерение</Link></Button>} />}
    </div>
  )

  const latestDate = photos[0]?.takenAt.slice(0, 10)
  const latest = latestDate ? photos.filter((photo) => photo.takenAt.startsWith(latestDate)).slice(0, 3) : []
  return (
    <div className="progress-section">
      <div className="progress-section-toolbar"><h2>Фото</h2><Button iconLeft={<Camera aria-hidden="true" />} onClick={onPhoto}>Фотофиксация</Button></div>
      {latest.length ? <div className="progress-photo-summary"><div><h3>Последняя фотофиксация</h3><p>{new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }).format(new Date(latest[0].takenAt))}</p><p className="mt-4 text-white/60">Полная галерея и удаление снимков находятся в профиле.</p><Button asChild variant="secondary" className="mt-5"><Link to="/profile?tab=photo">Открыть галерею</Link></Button></div><div className="progress-photo-row">{latest.map((photo) => <img key={photo.id} src={resolveApiAssetUrl(photo.thumbnailUrl) ?? photo.thumbnailUrl} alt={photo.view === 'front' ? 'Спереди' : photo.view === 'side' ? 'Сбоку' : 'Сзади'} />)}</div></div> : <ProgressActionEmpty title="Нет фото прогресса" text="Сделайте первую фотофиксацию, чтобы начать визуальное отслеживание." action={<Button iconLeft={<Camera aria-hidden="true" />} onClick={onPhoto}>Сделать фото</Button>} />}
    </div>
  )
}

function ProgressActionEmpty({ title, text, action }: { title: string; text: string; action: ReactNode }) { return <div className="progress-empty"><h2>{title}</h2><p>{text}</p>{action}</div> }
function asPeriod(value: string | null): Stage4Period { return value === '7d' || value === '30d' || value === '3m' || value === '6m' || value === '1y' || value === 'all' ? value : '30d' }
function asTab(value: string | null): ProgressTab { if (value === 'strength' || value === 'body' || value === 'photo' || value === 'recovery') return value; if (value === 'exercise' || value === 'regularity' || value === 'muscles') return 'strength'; return 'overview' }
