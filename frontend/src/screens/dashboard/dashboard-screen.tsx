import { useQuery } from '@tanstack/react-query'
import { Activity, ArrowRight, ChevronRight, Dumbbell, Sparkles, TrendingUp } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import type { DashboardData } from '@/entities/dashboard/model/types'
import { apiGet } from '@/shared/api/client'
import { getDriveLabel, getDriveTone, getMachineHeadlineClass, getMachineTone, getSafetyLabel, getSafetyTone } from '@/shared/lib/machine-status'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { BlockingAlert, DriveStatusBadge, MachineStatusBadge, PrimaryActionBar, ReadinessIndicator, SafetyStatusBadge, WarningBanner } from '@/shared/ui/status/status-components'
import { ActionSheet, ConfirmDialog, EmergencyStopOverlay, PopoverCard, SidePanel, ToastNotification } from '@/shared/ui/overlays/surface-components'
import { useAppStore } from '@/stores/app-store'

const statusColors: Record<string, string> = {
  ready: 'bg-[#6ed36d]',
  light: 'bg-[#d7c748]',
  medium: 'bg-[#e7903b]',
  high: 'bg-[#eb5345]',
  critical: 'bg-[#832f32]',
}

const recommendationTone: Record<string, string> = {
  'Рекомендуется': 'text-[#8ce48b]',
  'Можно выполнить': 'text-[#f0d08c]',
}

export type DashboardViewProps = {
  data: DashboardData
  userName: string
  emergencyStopActive: boolean
  onStop: () => void
  onEmergencyStopChange: (open: boolean) => void
}

export function DashboardScreen() {
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const [searchParams] = useSearchParams()
  const scenario = searchParams.get('scenario') ?? 'default'
  const userId = selectedUserId ?? 'alexey'

  const { data } = useQuery({
    queryKey: ['dashboard', userId, scenario],
    queryFn: () => apiGet<DashboardData>(`/api/dashboard?userId=${encodeURIComponent(userId)}&scenario=${encodeURIComponent(scenario)}`),
  })

  if (!data) {
    return null
  }

  return (
    <DashboardView
      data={data}
      userName={selectedUserId === 'elena' ? 'Елена' : selectedUserId === 'guest' ? 'Гость' : 'Алексей'}
      emergencyStopActive={emergencyStopActive}
      onEmergencyStopChange={setEmergencyStopActive}
      onStop={() => setEmergencyStopActive(true)}
    />
  )
}

export function DashboardView({ data, userName, emergencyStopActive, onStop, onEmergencyStopChange }: DashboardViewProps) {
  return (
    <FormaShell userName={userName} machine={data.machine} onStop={onStop}>
      {data.alerts.length > 0 ? (
        <div className="grid gap-4">
          {data.alerts.map((alert) =>
            alert.tone === 'blocked' ? (
              <BlockingAlert key={alert.title} title={alert.title} description={alert.description} />
            ) : (
              <WarningBanner key={alert.title} title={alert.title} description={alert.description} />
            ),
          )}
        </div>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.5fr_0.95fr_0.95fr]">
        <section className="glass-panel rounded-[34px] p-6 xl:p-8">
          <div className="grid gap-6 xl:grid-cols-[220px_1fr]">
            <div className="flex items-center justify-center">
              <ReadinessIndicator value={data.readinessPercent} />
            </div>
            <div className="space-y-5">
              <div>
                <div className="font-display text-5xl font-bold tracking-[-0.06em] text-white">{data.greeting}</div>
                <div className="mt-3 text-2xl font-semibold text-[#f0d08c]">{data.recommendationTitle}</div>
                <p className="mt-3 max-w-2xl text-base leading-8 text-white/72">{data.recommendationText}</p>
              </div>
              <div className="flex flex-wrap gap-3">
                <Button iconLeft={<Sparkles className="h-4 w-4" />}>Начать сегодняшнюю тренировку</Button>
                <Button variant="secondary" iconLeft={<Dumbbell className="h-4 w-4" />}>Быстрый старт</Button>
              </div>
              <WarningBanner
                title="Проверка необходимости фото прогресса"
                description="Логика фото прогресса уже заложена в поток, но не вынесена в отдельный экран запуска в рамках первого этапа."
              />
            </div>
          </div>
        </section>

        <section className="glass-panel rounded-[34px] p-6">
          {data.todayWorkout ? (
            <>
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <div className="text-sm uppercase tracking-[0.25em] text-white/35">Сегодняшняя тренировка</div>
                  <div className="mt-2 font-display text-3xl font-bold text-white">{data.todayWorkout.title}</div>
                </div>
              </div>
              <div className="mb-4 grid grid-cols-3 gap-3 text-sm text-white/65">
                <div>{data.todayWorkout.exercises} упражнений</div>
                <div>{data.todayWorkout.sets} подходов</div>
                <div>{data.todayWorkout.duration}</div>
              </div>
              <div className="space-y-3">
                {data.todayWorkout.list.map((item, index) => (
                  <div key={item} className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3 text-sm text-white/80">
                    <div className="flex items-center gap-3">
                      <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-white/8 text-xs">{index + 1}</span>
                      {item}
                    </div>
                    <ChevronRight className="h-4 w-4 text-white/40" />
                  </div>
                ))}
              </div>
              <div className="mt-5 flex gap-3">
                <Button className="flex-1">Начать</Button>
                <Button variant="secondary" className="flex-1">Открыть план</Button>
              </div>
            </>
          ) : (
            <div className="flex h-full min-h-[280px] flex-col justify-between">
              <div>
                <div className="text-sm uppercase tracking-[0.25em] text-white/35">Сегодняшняя тренировка</div>
                <div className="mt-2 font-display text-3xl font-bold text-white">Сегодня нет сохранённой тренировки</div>
                <p className="mt-4 text-base leading-8 text-white/68">
                  В этом mock-сценарии пользователь не получил план на сегодня. Можно перейти в быстрый старт или открыть каталог упражнений.
                </p>
              </div>
              <div className="mt-5 flex gap-3">
                <Button className="flex-1">Быстрый старт</Button>
                <Button variant="secondary" className="flex-1">Открыть каталог</Button>
              </div>
            </div>
          )}
        </section>

        <section className="glass-panel rounded-[34px] p-6">
          <div className="text-sm uppercase tracking-[0.25em] text-white/35">Статус тренажёра</div>
          <div className={cn('mt-3 font-display text-4xl font-bold', getMachineHeadlineClass(data.machine.machineState))}>{data.machine.machineLabel}</div>
          <div className="mt-5 space-y-3">
            <MachineStatusBadge label={data.machine.machineLabel} tone={getMachineTone(data.machine.machineState)} />
            <DriveStatusBadge label={getDriveLabel('left', data.machine.leftDrive)} tone={getDriveTone(data.machine.leftDrive)} />
            <DriveStatusBadge label={getDriveLabel('right', data.machine.rightDrive)} tone={getDriveTone(data.machine.rightDrive)} />
            <SafetyStatusBadge label={getSafetyLabel(data.machine.safety)} tone={getSafetyTone(data.machine.safety)} />
            <div className="glass-panel rounded-2xl px-4 py-3 text-sm text-white/70">{data.machine.calibration}</div>
          </div>
          <div className="mt-5 flex gap-3">
            <ConfirmDialog trigger={<Button variant="secondary" className="flex-1">Диагностика</Button>} />
          </div>
        </section>
      </div>

      <section className="glass-panel rounded-[34px] p-6">
        <div className="mb-5 flex items-center justify-between">
          <div>
            <div className="text-sm uppercase tracking-[0.25em] text-white/35">Подробная карта усталости мышц</div>
            <div className="mt-2 font-display text-3xl font-bold text-white">Краткая аналитика готовности</div>
          </div>
          <PopoverCard
            trigger={<Button variant="ghost">Что означает готовность</Button>}
            content={<div>Чем ниже fatigueScore, тем выше готовность мышцы к следующей нагрузке.</div>}
          />
        </div>
        <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr_0.8fr]">
          <div className="space-y-3 text-sm text-white/70">
            <LegendRow color="bg-[#6ed36d]" label="Готова к нагрузке" />
            <LegendRow color="bg-[#d7c748]" label="Лёгкая усталость" />
            <LegendRow color="bg-[#e7903b]" label="Умеренная усталость" />
            <LegendRow color="bg-[#eb5345]" label="Высокая усталость" />
            <LegendRow color="bg-[#677084]" label="Нет данных" />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            {['Передняя цепь', 'Задняя цепь'].map((label, index) => (
              <div key={label} className="rounded-[30px] border border-white/8 bg-linear-to-b from-white/6 to-transparent p-5">
                <div className="mb-4 text-sm uppercase tracking-[0.25em] text-white/35">{label}</div>
                <div className="flex h-[240px] items-center justify-center rounded-[26px] border border-dashed border-white/10 bg-[radial-gradient(circle_at_top,rgba(214,176,95,0.18),transparent_30%)] text-white/24">
                  <div className="text-center">
                    <div className="font-display text-4xl font-bold">{index === 0 ? 'Front' : 'Back'}</div>
                    <div className="mt-2 text-sm">Интерактивная карта будет расширена на следующих экранах</div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <SidePanel title="Состояние мышц">
            <div className="space-y-3">
              {data.muscles.map((muscle) => (
                <div key={muscle.name} className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3 text-sm text-white/78">
                  <div className="flex items-center gap-3">
                    <span className={`status-dot ${statusColors[muscle.status] ?? 'bg-[#677084]'}`} />
                    {muscle.name}
                  </div>
                  <div>{muscle.score} из 100</div>
                </div>
              ))}
            </div>
            <Button variant="secondary" className="mt-4 w-full">Открыть экран усталости</Button>
          </SidePanel>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="glass-panel rounded-[34px] p-6">
          <div className="mb-4 flex items-center justify-between">
            <div className="font-display text-3xl font-bold text-white">Рекомендовано сегодня</div>
            <ArrowRight className="h-5 w-5 text-white/30" />
          </div>
          <div className="space-y-3">
            {data.recommendedExercises.map((item) => (
              <div key={item.name} className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3 text-sm text-white/82">
                <div>
                  <div className="font-semibold text-white">{item.name}</div>
                  <div className="text-white/45">{item.muscles}</div>
                </div>
                <div className={cn('font-medium', recommendationTone[item.status] ?? 'text-white/65')}>{item.status}</div>
              </div>
            ))}
          </div>
          <Button variant="secondary" className="mt-4 w-full">Открыть каталог</Button>
        </section>

        <section className="glass-panel rounded-[34px] p-6">
          <div className="mb-4 flex items-center justify-between">
            <div className="font-display text-3xl font-bold text-white">Быстрый старт</div>
            <ArrowRight className="h-5 w-5 text-white/30" />
          </div>
          <div className="space-y-3">
            {data.quickStart.map((item) => (
              <div key={item.name} className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3 text-sm text-white/82">
                <div>
                  <div className="font-semibold text-white">{item.name}</div>
                  <div className="text-white/45">{item.stats}</div>
                </div>
                <div className="text-white/50">{item.last}</div>
              </div>
            ))}
          </div>
          <Button variant="secondary" className="mt-4 w-full">Выбрать упражнение</Button>
        </section>
      </div>

      <PrimaryActionBar>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {data.progress.map((item, index) => (
            <div key={item.label} className="flex items-center gap-4 rounded-2xl border border-white/8 bg-white/4 px-4 py-4">
              {index % 2 === 0 ? <TrendingUp className="h-5 w-5 text-[#d6b05f]" /> : <Activity className="h-5 w-5 text-[#d6b05f]" />}
              <div>
                <div className="font-display text-3xl font-bold text-white">{item.value}</div>
                <div className="text-sm text-white/45">{item.label}</div>
              </div>
            </div>
          ))}
        </div>
      </PrimaryActionBar>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <ActionSheet title="Панель поверхностей" items={['Modal', 'SidePanel', 'Popover', 'ActionSheet']} />
        <div className="space-y-4">
          <BlockingAlert title="Блокирующее состояние" description="Если правый привод не подключён или безопасность аварийно отключена, старт тренировки блокируется прямо в shell." />
          <ToastNotification title="Toast готов" description="Короткие системные сообщения уже можно подключать без изменения layout-компонентов." />
        </div>
      </div>

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={onEmergencyStopChange} />
    </FormaShell>
  )
}

function LegendRow({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className={`status-dot ${color}`} />
      {label}
    </div>
  )
}