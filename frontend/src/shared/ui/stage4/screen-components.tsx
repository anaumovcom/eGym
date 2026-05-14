import { CircleAlert, RotateCcw, Settings2 } from 'lucide-react'
import { useState } from 'react'
import type { ChartPoint, FatigueMuscle, MetricCard, Stage4DevFlags } from '@/entities/stage4/model/types'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'

const toneTextClasses: Record<NonNullable<MetricCard['tone']>, string> = {
  neutral: 'text-white',
  good: 'text-[#79de83]',
  warning: 'text-[#f2cf87]',
  danger: 'text-[#ff8f84]',
}

const fatigueDotClasses: Record<string, string> = {
  ready: 'bg-[#57c968]',
  light: 'bg-[#a6d94f]',
  medium: 'bg-[#f0bf43]',
  high: 'bg-[#f08b2e]',
  critical: 'bg-[#eb5345]',
  no_data: 'bg-[#677084]',
}

const frontPositionClasses: Record<string, string> = {
  chest: 'top-20 left-1/2 -translate-x-1/2',
  triceps: 'top-24 left-[72%]',
  'front-delta': 'top-16 left-[70%]',
  abs: 'top-40 left-1/2 -translate-x-1/2',
  quads: 'top-[68%] left-1/2 -translate-x-1/2',
}

const backPositionClasses: Record<string, string> = {
  back: 'top-20 left-1/2 -translate-x-1/2',
  'rear-delta': 'top-16 left-[68%]',
  glutes: 'top-[48%] left-1/2 -translate-x-1/2',
  hamstrings: 'top-[66%] left-1/2 -translate-x-1/2',
  calves: 'top-[82%] left-1/2 -translate-x-1/2',
}

function buildPolyline(points: ChartPoint[]) {
  if (points.length === 0) {
    return ''
  }

  const maxValue = Math.max(...points.map((point) => point.value), 1)

  return points
    .map((point, index) => {
      const x = (index / Math.max(points.length - 1, 1)) * 100
      const y = 88 - (point.value / maxValue) * 66
      return `${x},${y}`
    })
    .join(' ')
}

export function SectionTitle({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        {eyebrow ? <div className="text-sm uppercase tracking-[0.24em] text-white/35">{eyebrow}</div> : null}
        <div className="mt-2 font-display text-4xl font-bold tracking-[-0.06em] text-white">{title}</div>
        {description ? <div className="mt-2 max-w-3xl text-base leading-8 text-white/65">{description}</div> : null}
      </div>
      {actions}
    </div>
  )
}

export function PeriodSwitcher({ periods, active, onChange }: { periods: Array<{ id: string; label: string }>; active: string; onChange: (id: string) => void }) {
  return (
    <div className="inline-flex flex-wrap gap-2 rounded-[26px] border border-white/8 bg-white/4 p-2">
      {periods.map((period) => (
        <button
          key={period.id}
          type="button"
          onClick={() => onChange(period.id)}
          className={cn(
            'inline-flex min-h-11 items-center rounded-[18px] px-4 text-sm transition',
            active === period.id ? 'border border-[#d6b05f]/40 bg-[#3b2b11] text-[#f3d18b]' : 'text-white/58 hover:bg-white/4 hover:text-white',
          )}
        >
          {period.label}
        </button>
      ))}
    </div>
  )
}

export function TabStrip({ tabs, active, onChange }: { tabs: Array<{ id: string; label: string }>; active: string; onChange: (id: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2 border-b border-white/8 pb-3">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onChange(tab.id)}
          className={cn(
            'rounded-[18px] px-4 py-2 text-sm transition',
            active === tab.id ? 'bg-[#20170b] text-[#f1d391] shadow-[inset_0_-1px_0_rgba(214,176,95,0.7)]' : 'text-white/55 hover:bg-white/4 hover:text-white',
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}

export function MetricCardGrid({ items, columns = 'xl:grid-cols-4' }: { items: MetricCard[]; columns?: string }) {
  return (
    <div className={cn('grid gap-4 md:grid-cols-2', columns)}>
      {items.map((item) => (
        <div key={`${item.label}-${item.value}`} className="rounded-[24px] border border-white/8 bg-white/4 p-4">
          <div className="text-sm text-white/45">{item.label}</div>
          <div className={cn('mt-2 font-display text-3xl font-bold', toneTextClasses[item.tone ?? 'neutral'])}>{item.value}</div>
          {item.hint ? <div className="mt-1 text-xs text-white/35">{item.hint}</div> : null}
        </div>
      ))}
    </div>
  )
}

export function Panel({ title, description, children, action }: { title: string; description?: string; children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <section className="glass-panel rounded-[32px] p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <div className="font-display text-3xl font-bold text-white">{title}</div>
          {description ? <div className="mt-2 text-sm leading-7 text-white/55">{description}</div> : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  )
}

export function EmptyStatePanel({ title, description, action }: { title: string; description: string; action?: React.ReactNode }) {
  return (
    <div className="rounded-[30px] border border-dashed border-white/10 bg-white/4 p-8 text-center text-white/62">
      <div className="font-display text-3xl font-bold text-white">{title}</div>
      <div className="mt-3 max-w-2xl text-base leading-8 mx-auto">{description}</div>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  )
}

export function LineChartCard({ title, subtitle, points, summary }: { title: string; subtitle?: string; points: ChartPoint[]; summary?: React.ReactNode }) {
  const polyline = buildPolyline(points)
  const maxValue = Math.max(...points.map((point) => point.value), 1)

  return (
    <Panel title={title} description={subtitle}>
      {points.length === 0 ? (
        <EmptyStatePanel title="Нет данных для графика" description="После появления новых измерений или тренировок здесь появится динамика по выбранному периоду." />
      ) : (
        <div className="grid gap-5 xl:grid-cols-[1fr_0.42fr]">
          <div className="rounded-[26px] border border-white/8 bg-[#111419] p-4">
            <svg viewBox="0 0 100 100" className="h-[280px] w-full" role="img" aria-label={title}>
              <defs>
                <linearGradient id="stage4-line-fill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="rgba(214,176,95,0.24)" />
                  <stop offset="100%" stopColor="rgba(214,176,95,0.02)" />
                </linearGradient>
              </defs>
              {[20, 40, 60, 80].map((y) => <line key={y} x1="0" x2="100" y1={y} y2={y} stroke="rgba(255,255,255,0.06)" strokeWidth="0.4" />)}
              <polyline fill="none" points={polyline} stroke="#d6b05f" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              {points.map((point, index) => {
                const x = (index / Math.max(points.length - 1, 1)) * 100
                const y = 88 - (point.value / maxValue) * 66
                return <circle key={point.label} cx={x} cy={y} r={point.accent ? '1.8' : '1.2'} fill={point.accent ? '#f3d18b' : '#d6b05f'} />
              })}
            </svg>
            <div className="mt-2 flex flex-wrap justify-between gap-2 text-xs text-white/35">
              {points.map((point) => (
                <span key={point.label}>{point.label}</span>
              ))}
            </div>
          </div>
          {summary ? <div className="space-y-3">{summary}</div> : null}
        </div>
      )}
    </Panel>
  )
}

export function BarChartCard({ title, subtitle, points }: { title: string; subtitle?: string; points: ChartPoint[] }) {
  const maxValue = Math.max(...points.map((point) => point.value), 1)

  return (
    <Panel title={title} description={subtitle}>
      {points.length === 0 ? (
        <EmptyStatePanel title="Нет данных для графика" description="Недостаточно записей, чтобы построить диаграмму по выбранному периоду." />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {points.map((point) => {
            const heightClass = point.value / maxValue > 0.8 ? 'h-32' : point.value / maxValue > 0.6 ? 'h-24' : point.value / maxValue > 0.4 ? 'h-20' : point.value / maxValue > 0.2 ? 'h-14' : 'h-10'
            return (
              <div key={point.label} className="rounded-[22px] border border-white/8 bg-[#111419] p-4">
                <div className="flex h-36 items-end justify-center rounded-[18px] border border-dashed border-white/8 bg-black/20 p-3">
                  <div className={cn('w-12 rounded-t-[18px] bg-linear-to-t from-[#8a6422] via-[#d6b05f] to-[#f3d18b]', heightClass)} />
                </div>
                <div className="mt-3 font-semibold text-white">{point.value}</div>
                <div className="text-sm text-white/45">{point.label}</div>
              </div>
            )
          })}
        </div>
      )}
    </Panel>
  )
}

export function ToneBadge({ status }: { status: string }) {
  return <span className={cn('inline-flex h-3 w-3 rounded-full', fatigueDotClasses[status] ?? fatigueDotClasses.no_data)} />
}

export function MuscleMapDetailed({ muscles, selectedId, onSelect }: { muscles: FatigueMuscle[]; selectedId: string; onSelect: (id: string) => void }) {
  const front = muscles.filter((muscle) => muscle.group === 'front')
  const back = muscles.filter((muscle) => muscle.group === 'back')

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <MuscleFigure title="Вид спереди" muscles={front} selectedId={selectedId} onSelect={onSelect} positions={frontPositionClasses} />
      <MuscleFigure title="Вид сзади" muscles={back} selectedId={selectedId} onSelect={onSelect} positions={backPositionClasses} />
    </div>
  )
}

function MuscleFigure({ title, muscles, selectedId, onSelect, positions }: { title: string; muscles: FatigueMuscle[]; selectedId: string; onSelect: (id: string) => void; positions: Record<string, string> }) {
  return (
    <div className="rounded-[30px] border border-white/8 bg-[#111419] p-5">
      <div className="mb-4 text-sm uppercase tracking-[0.24em] text-white/35">{title}</div>
      <div className="relative flex min-h-[420px] items-center justify-center overflow-hidden rounded-[26px] border border-dashed border-white/10 bg-[radial-gradient(circle_at_top,rgba(214,176,95,0.15),transparent_36%),linear-gradient(180deg,#161a20,#0b0e12)]">
        <div className="absolute top-10 h-16 w-16 rounded-full border border-white/10 bg-white/5" />
        <div className="absolute top-24 h-32 w-28 rounded-[36px] border border-white/10 bg-white/5" />
        <div className="absolute top-32 left-[calc(50%-82px)] h-28 w-9 rounded-full border border-white/10 bg-white/5" />
        <div className="absolute top-32 right-[calc(50%-82px)] h-28 w-9 rounded-full border border-white/10 bg-white/5" />
        <div className="absolute top-52 h-26 w-20 rounded-[32px] border border-white/10 bg-white/5" />
        <div className="absolute top-72 left-[calc(50%-48px)] h-28 w-10 rounded-full border border-white/10 bg-white/5" />
        <div className="absolute top-72 right-[calc(50%-48px)] h-28 w-10 rounded-full border border-white/10 bg-white/5" />
        {muscles.map((muscle) => (
          <button
            key={muscle.id}
            type="button"
            title={`${muscle.name}: ${muscle.score} из 100`}
            aria-label={`${muscle.name}: ${muscle.score} из 100`}
            onClick={() => onSelect(muscle.id)}
            className={cn(
              'absolute rounded-full border px-3 py-1 text-xs font-semibold transition',
              positions[muscle.id],
              selectedId === muscle.id ? 'border-[#f3d18b] bg-[#3c2b12] text-[#f3d18b]' : 'border-white/8 bg-black/35 text-white/72 hover:border-white/18 hover:text-white',
            )}
          >
            <span className="mr-2 inline-flex align-middle"><ToneBadge status={muscle.status} /></span>
            {muscle.shortName}
          </button>
        ))}
      </div>
    </div>
  )
}

export function MuscleSelectionPanel({ muscle }: { muscle: FatigueMuscle }) {
  return (
    <Panel title={muscle.name} description={`${muscle.score} из 100 · ${muscle.status === 'critical' ? 'критическая усталость' : muscle.status === 'high' ? 'высокая усталость' : muscle.status === 'medium' ? 'средняя усталость' : muscle.status === 'light' ? 'лёгкая усталость' : 'готова к нагрузке'}`}>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-[22px] border border-white/8 bg-white/4 p-4">
          <div className="text-sm text-white/45">Готовность</div>
          <div className="mt-2 font-display text-4xl font-bold text-white">{muscle.readinessPercent}%</div>
        </div>
        <div className="rounded-[22px] border border-white/8 bg-white/4 p-4">
          <div className="text-sm text-white/45">Ожидаемое восстановление</div>
          <div className="mt-2 font-display text-4xl font-bold text-white">≈ {muscle.recoveryHours} ч</div>
        </div>
      </div>
      <div className="mt-4 text-sm leading-7 text-white/65">{muscle.recommendation}</div>
      <div className="mt-4 grid gap-3 xl:grid-cols-2">
        <div className="rounded-[22px] border border-white/8 bg-white/4 p-4">
          <div className="font-semibold text-[#8ce48b]">Рекомендуется сегодня</div>
          <div className="mt-3 space-y-2">
            {muscle.recommendedExercises.map((exercise) => (
              <div key={exercise.name} className="flex items-center justify-between gap-3 rounded-2xl border border-white/8 bg-black/15 px-3 py-3 text-sm text-white/75">
                <span>{exercise.name}</span>
                <span className="text-[#8ce48b]">{exercise.note}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-[22px] border border-white/8 bg-white/4 p-4">
          <div className="font-semibold text-[#ffb38e]">Лучше отложить</div>
          <div className="mt-3 space-y-2">
            {muscle.avoidExercises.length > 0 ? muscle.avoidExercises.map((exercise) => (
              <div key={exercise.name} className="flex items-center justify-between gap-3 rounded-2xl border border-white/8 bg-black/15 px-3 py-3 text-sm text-white/75">
                <span>{exercise.name}</span>
                <span className="text-[#ff8f84]">{exercise.note}</span>
              </div>
            )) : <div className="rounded-2xl border border-dashed border-white/10 bg-black/15 px-3 py-3 text-sm text-white/45">Нет упражнений с жёстким ограничением.</div>}
          </div>
        </div>
      </div>
    </Panel>
  )
}

export function PhotoPreviewCard({ title, label }: { title: string; label: string }) {
  return (
    <div className="flex min-h-[130px] flex-col justify-end rounded-[22px] border border-white/8 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.08),transparent_35%),linear-gradient(180deg,#171a1f,#0d0f13)] p-4 text-white/74">
      <div className="mx-auto mb-4 flex h-16 w-12 items-center justify-center rounded-[18px] border border-white/8 bg-white/4 text-xs text-white/35">{label}</div>
      <div className="text-sm text-white">{title}</div>
    </div>
  )
}

export function Stage4DevPanel({ value, onChange, onReset }: { value: Stage4DevFlags; onChange: (patch: Partial<Stage4DevFlags>) => void; onReset: () => void }) {
  const [open, setOpen] = useState(false)

  if (!import.meta.env.DEV) {
    return null
  }

  return (
    <div className="fixed bottom-4 right-4 z-40 w-[360px]">
      <div className="rounded-[24px] border border-[#d6b05f]/20 bg-[#0b1017]/95 p-4 shadow-[0_24px_60px_rgba(0,0,0,0.45)] backdrop-blur-md">
        <div className="flex items-center justify-between gap-3">
          <button type="button" onClick={() => setOpen((current) => !current)} className="flex items-center gap-3 text-left text-white">
            <div className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-white/10 bg-white/4 text-[#f3d18b]">
              <Settings2 className="h-5 w-5" />
            </div>
            <div>
              <div className="font-semibold">Dev панель mock-состояний</div>
              <div className="text-xs text-white/45">Готовность тренажёра, фото, усталость, история</div>
            </div>
          </button>
          <Button variant="ghost" className="min-h-10 px-3 py-2" iconLeft={<RotateCcw className="h-4 w-4" />} onClick={onReset}>
            Сбросить
          </Button>
        </div>

        {open ? (
          <div className="mt-4 space-y-3">
            <DevToggle label="Тренажёр готов" checked={value.machineReady} onChange={(checked) => onChange({ machineReady: checked })} />
            <DevToggle label="Ошибка левого привода" checked={value.leftDriveError} onChange={(checked) => onChange({ leftDriveError: checked })} />
            <DevToggle label="Ошибка правого привода" checked={value.rightDriveError} onChange={(checked) => onChange({ rightDriveError: checked })} />
            <DevToggle label="Аварийный СТОП" checked={value.emergencyStop} onChange={(checked) => onChange({ emergencyStop: checked })} />
            <DevToggle label="Безопасность выключена" checked={value.safetyDisabled} onChange={(checked) => onChange({ safetyDisabled: checked })} />
            <DevToggle label="Нет калибровки" checked={value.noCalibration} onChange={(checked) => onChange({ noCalibration: checked })} />
            <DevToggle label="Высокая усталость" checked={value.highFatigue} onChange={(checked) => onChange({ highFatigue: checked, criticalFatigue: checked ? false : value.criticalFatigue })} />
            <DevToggle label="Критическая усталость 100+" checked={value.criticalFatigue} onChange={(checked) => onChange({ criticalFatigue: checked, highFatigue: checked ? false : value.highFatigue })} />
            <DevToggle label="Нет истории" checked={value.noHistory} onChange={(checked) => onChange({ noHistory: checked })} />
            <DevToggle label="Нет фото" checked={value.noPhotos} onChange={(checked) => onChange({ noPhotos: checked })} />
            <div className="rounded-[18px] border border-white/8 bg-white/4 px-4 py-3">
              <div className="flex items-center gap-2 text-sm text-white"><CircleAlert className="h-4 w-4 text-[#f3d18b]" />Сервер был выключен</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {[0, 6, 12, 24, 72].map((hours) => (
                  <button
                    key={hours}
                    type="button"
                    onClick={() => onChange({ offlineHours: hours })}
                    className={cn('rounded-[14px] px-3 py-2 text-xs transition', value.offlineHours === hours ? 'bg-[#3c2b12] text-[#f3d18b]' : 'bg-black/20 text-white/58 hover:text-white')}
                  >
                    {hours === 0 ? '0 ч' : `${hours} ч`}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function DevToggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className="flex items-center justify-between gap-3 rounded-[18px] border border-white/8 bg-white/4 px-4 py-3 text-sm text-white/76">
      <span>{label}</span>
      <button type="button" title={label} aria-label={label} onClick={() => onChange(!checked)} className={cn('inline-flex h-7 w-12 items-center rounded-full border px-1 transition', checked ? 'border-[#d6b05f]/40 bg-[#3c2b12] justify-end' : 'border-white/10 bg-black/25 justify-start')}>
        <span className={cn('h-5 w-5 rounded-full', checked ? 'bg-[#f3d18b]' : 'bg-white/35')} />
      </button>
    </label>
  )
}