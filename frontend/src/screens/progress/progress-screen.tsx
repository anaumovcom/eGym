import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Camera, ChevronDown, ChevronRight, RefreshCw } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { ProgressData } from '@/entities/stage4/model/types'
import type { ProgressExerciseHistoryRow, ProgressTab, Stage4Period } from '@/entities/stage4/model/types'
import { progressTabs, stage4Periods } from '@/mocks/stage4-data'
import { apiGet } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { MuscleStatusList } from '@/shared/ui/stage2/screen-components'
import { BarChartCard, EmptyStatePanel, LineChartCard, MetricCardGrid, Panel, PeriodSwitcher, PhotoPreviewCard, SectionTitle, TabStrip, ToneBadge } from '@/shared/ui/stage4/screen-components'
import { useAppStore } from '@/stores/app-store'

function asPeriod(value: string | null): Stage4Period {
  if (value === '7d' || value === '30d' || value === '3m' || value === '6m' || value === '1y' || value === 'all') {
    return value
  }

  return '30d'
}

function asProgressTab(value: string | null): ProgressTab {
  if (value === 'summary' || value === 'exercise' || value === 'strength' || value === 'regularity' || value === 'muscles' || value === 'body' || value === 'photo') {
    return value
  }

  return 'summary'
}

export function ProgressScreen() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)

  const period = asPeriod(searchParams.get('period'))
  const tab = asProgressTab(searchParams.get('tab'))
  const selectedExerciseSlug = searchParams.get('exercise') ?? 'machine-pulldown'
  const userId = selectedUserId ?? 'alexey'

  const { data, isLoading, error } = useQuery({
    queryKey: ['progress-screen', userId, period, selectedExerciseSlug],
    queryFn: () => apiGet<ProgressData>(`/api/progress?userId=${encodeURIComponent(userId)}&period=${encodeURIComponent(period)}&exerciseSlug=${encodeURIComponent(selectedExerciseSlug)}`),
  })

  const fallbackMachine: MachineHealth = {
    machineState: 'ready',
    machineLabel: 'Загрузка статуса',
    leftDrive: 'connected',
    rightDrive: 'connected',
    safety: 'enabled',
    calibration: 'Загрузка...',
  }

  const userName = selectedUserId === 'elena' ? 'Елена' : selectedUserId === 'guest' ? 'Гость' : 'Алексей'

  function updateParams(patch: Record<string, string | null>) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)

      Object.entries(patch).forEach(([key, value]) => {
        if (!value) {
          next.delete(key)
        } else {
          next.set(key, value)
        }
      })

      return next
    })
  }

  if (error) {
    return (
      <FormaShell userName={userName} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
        <div className="glass-panel rounded-[34px] border border-[#eb5345]/25 bg-[#1b0f10] p-8 text-[#ffb4a7]">Не удалось загрузить прогресс. Проверьте backend API.</div>
      </FormaShell>
    )
  }

  if (isLoading || !data) {
    return (
      <FormaShell userName={userName} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
        <div className="glass-panel rounded-[34px] p-8 text-white/72">Загрузка прогресса…</div>
      </FormaShell>
    )
  }

  const activeExercise = data.exerciseOptions.find((item) => item.slug === selectedExerciseSlug) ?? data.exerciseOptions[0]

  return (
    <FormaShell userName={userName} machine={data.machine} onStop={() => setEmergencyStopActive(true)}>
      <SectionTitle
        title={data.title}
        description={data.subtitle}
        actions={<PeriodSwitcher periods={stage4Periods} active={period} onChange={(value) => updateParams({ period: value })} />}
      />

      <TabStrip tabs={progressTabs} active={tab} onChange={(value) => updateParams({ tab: value })} />

      {tab === 'summary' ? (
        <div className="space-y-6">
          <MetricCardGrid items={data.summaryCards} columns="xl:grid-cols-6" />
          {data.emptyState ? <EmptyStatePanel title={data.emptyState.title} description={data.emptyState.description} /> : null}
          <div className="grid gap-6 xl:grid-cols-[1.35fr_0.65fr]">
            <LineChartCard
              title="Динамика объёма"
              subtitle="Общий объём по выбранному периоду"
              points={data.summaryVolumeSeries}
              summary={
                <>
                  <div className="rounded-[24px] border border-white/8 bg-white/4 p-4">
                    <div className="text-sm text-white/45">Главный прогресс</div>
                    <div className="mt-3 font-display text-3xl font-bold text-white">{data.mainProgress.exercise}</div>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <div className="rounded-[20px] border border-white/8 bg-black/15 p-3 text-white/74">
                        <div className="text-xs text-white/35">Было</div>
                        <div className="mt-2 font-semibold text-white">{data.mainProgress.from}</div>
                      </div>
                      <div className="rounded-[20px] border border-white/8 bg-black/15 p-3 text-white/74">
                        <div className="text-xs text-white/35">Стало</div>
                        <div className="mt-2 font-semibold text-white">{data.mainProgress.to}</div>
                      </div>
                    </div>
                    <div className="mt-4 text-lg font-semibold text-[#79de83]">{data.mainProgress.delta}</div>
                  </div>
                  <div className="rounded-[24px] border border-white/8 bg-white/4 p-4">
                    <div className="text-sm text-white/45">Что стало лучше</div>
                    <div className="mt-3 space-y-2 text-sm text-white/72">
                      {data.improvements.map((item) => (
                        <div key={item} className="rounded-2xl border border-white/8 bg-black/15 px-3 py-3">{item}</div>
                      ))}
                    </div>
                  </div>
                </>
              }
            />
            <div className="space-y-6">
              <Panel title="Итог периода">
                <div className="space-y-3">
                  {data.periodSummary.map((item) => (
                    <div key={item.label} className="flex items-center justify-between gap-3 rounded-[22px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75">
                      <span>{item.label}</span>
                      <span className={item.tone === 'good' ? 'text-[#79de83]' : 'text-white'}>{item.value}</span>
                    </div>
                  ))}
                </div>
              </Panel>
              <Panel title="Рекомендация Forma">
                <div className="text-sm leading-7 text-white/68">{data.recommendation}</div>
                <Button className="mt-5 w-full" variant="secondary" iconLeft={<ArrowRight className="h-4 w-4" />} onClick={() => navigate('/today')}>
                  Перейти к сегодняшнему плану
                </Button>
              </Panel>
            </div>
          </div>
        </div>
      ) : null}

      {tab === 'exercise' ? (
        <div className="space-y-6">
          <Panel
            title="Аналитика по упражнению"
            action={
              <label className="inline-flex min-h-11 items-center gap-3 rounded-[18px] border border-white/8 bg-white/4 px-4 text-sm text-white/72">
                <span>Выберите упражнение</span>
                <select
                  value={activeExercise?.slug ?? 'machine-pulldown'}
                  onChange={(event) => updateParams({ exercise: event.target.value })}
                  title="Выбрать упражнение"
                  aria-label="Выбрать упражнение"
                  className="bg-transparent text-white outline-none"
                >
                  {data.exerciseOptions.map((option) => (
                    <option key={option.slug} value={option.slug} className="bg-[#0d1116]">{option.name}</option>
                  ))}
                </select>
                <ChevronDown className="h-4 w-4 text-white/45" />
              </label>
            }
          >
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
              <StatTile title="Последний результат" value={data.selectedExercise.lastResult} />
              <StatTile title="Лучший результат" value={data.selectedExercise.bestResult} />
              <StatTile title="Лучший объём" value={data.selectedExercise.bestVolume} />
              <StatTile title="Выполнений" value={data.selectedExercise.completedTimes} />
              <StatTile title="Средняя амплитуда" value={data.selectedExercise.averageAmplitude} />
            </div>
          </Panel>

          {data.emptyState ? <EmptyStatePanel title={data.emptyState.title} description={data.emptyState.description} /> : null}

          <div className="grid gap-6 xl:grid-cols-[1.35fr_0.65fr]">
            <LineChartCard title="Динамика рабочего веса" subtitle="Средний рабочий вес по тренировкам" points={data.selectedExercise.workWeightSeries} />
            <Panel title="Итог упражнения">
              <div className="space-y-3 text-sm text-white/72">
                <div className="flex items-center justify-between rounded-[22px] border border-white/8 bg-white/4 px-4 py-4"><span>Тренировок</span><span>{data.selectedExercise.completedTimes}</span></div>
                <div className="flex items-center justify-between rounded-[22px] border border-white/8 bg-white/4 px-4 py-4"><span>Общий объём</span><span>{data.selectedExercise.volumeSeries.at(-1)?.value ?? '—'} кг</span></div>
                <div className="flex items-center justify-between rounded-[22px] border border-white/8 bg-white/4 px-4 py-4"><span>Темп прогресса</span><span>{data.selectedExercise.tempoTrend}</span></div>
              </div>
              <div className="mt-4 rounded-[22px] border border-white/8 bg-white/4 p-4 text-sm leading-7 text-white/68">{data.selectedExercise.recommendation}</div>
              <div className="mt-4">
                <MuscleStatusList muscles={data.selectedExercise.affectedMuscles} />
              </div>
            </Panel>
          </div>

          <BarChartCard title="Объём упражнения" subtitle="Выполненный объём по ключевым сессиям" points={data.selectedExercise.volumeSeries} />

          <Panel title="История подходов">
            {data.selectedExercise.history.length === 0 ? (
              <EmptyStatePanel title="Нет истории подходов" description="После завершения нескольких тренировок здесь появится таблица по весу, объёму и амплитуде." />
            ) : (
              <HistoryTable rows={data.selectedExercise.history} />
            )}
          </Panel>
        </div>
      ) : null}

      {tab === 'strength' ? (
        <div className="space-y-6">
          <MetricCardGrid items={data.strengthCards} columns="xl:grid-cols-6" />
          <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
            <LineChartCard title="Объём по неделям" subtitle="Общий объём по тренировочным неделям" points={data.summaryVolumeSeries} />
            <Panel title="Топ упражнений по объёму">
              <div className="space-y-3">
                {data.volumeTopExercises.map((item) => (
                  <div key={item.rank} className="flex items-center justify-between gap-4 rounded-[22px] border border-white/8 bg-white/4 px-4 py-4 text-white/75">
                    <div className="flex items-center gap-3">
                      <span className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-[#d6b05f]/30 bg-[#20170b] font-display text-xl text-[#f3d18b]">{item.rank}</span>
                      <span>{item.name}</span>
                    </div>
                    <span className="font-semibold text-white">{item.value}</span>
                  </div>
                ))}
              </div>
            </Panel>
          </div>
        </div>
      ) : null}

      {tab === 'regularity' ? (
        <div className="space-y-6">
          <MetricCardGrid items={data.regularityCards} columns="xl:grid-cols-5" />
          <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
            <Panel title="Календарь активности">
              {data.activityCalendar.length === 0 ? (
                <EmptyStatePanel title="Нет календаря активности" description="После первых тренировок здесь появится распределение выполненных, частичных и пропущенных дней." />
              ) : (
                <>
                  <div className="grid grid-cols-7 gap-2">
                    {['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'].map((label) => <div key={label} className="px-2 pb-1 text-xs text-white/35">{label}</div>)}
                    {data.activityCalendar.map((item) => (
                      <div key={item.id} className="rounded-[16px] border border-white/8 bg-white/4 p-2 text-center text-sm text-white/72">
                        <div>{item.day}</div>
                        <div className="mt-2 flex justify-center"><span className={activityDotClass(item.state)} /></div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 flex flex-wrap gap-4 text-xs text-white/45">
                    <LegendItem label="Выполнено" state="done" />
                    <LegendItem label="Частично" state="partial" />
                    <LegendItem label="Пропущено" state="missed" />
                    <LegendItem label="Отдых" state="rest" />
                  </div>
                </>
              )}
            </Panel>
            <BarChartCard title="Распределение по дням недели" subtitle="Сколько тренировок попадает на каждый день" points={data.dayDistribution} />
          </div>
          <div className="grid gap-6 xl:grid-cols-2">
            <BarChartCard title="Тренировки по неделям" subtitle="Количество сессий" points={data.weeklyTrainingSeries} />
            <LineChartCard title="Минуты по неделям" subtitle="Суммарная длительность сессий" points={data.weeklyMinuteSeries} />
          </div>
          <Panel title="Последние недели">
            {data.recentWeeks.length === 0 ? (
              <EmptyStatePanel title="История недель пока пуста" description="После накопления недельных данных здесь появится регулярность по неделям." />
            ) : (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
                {data.recentWeeks.map((item) => (
                  <div key={item.label} className="rounded-[22px] border border-white/8 bg-white/4 p-4 text-white/74">
                    <div className="font-semibold text-white">{item.label}</div>
                    <div className="mt-3 text-sm">{item.trainings}</div>
                    <div className="mt-1 text-sm">{item.minutes}</div>
                    <div className="mt-4 flex items-center justify-between text-sm"><span>Выполнение</span><span>{item.completion}</span></div>
                    <div className="mt-2 flex items-center gap-2"><ToneBadge status={item.status} /><span className="text-xs text-white/45">{item.status}</span></div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      ) : null}

      {tab === 'muscles' ? (
        <div className="space-y-6">
          <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <Panel title="Анализ мышечной нагрузки" description="Средняя нагрузка на группы мышц за выбранный период">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {data.muscleLoad.map((item) => (
                  <div key={item.name} className="rounded-[22px] border border-white/8 bg-white/4 px-4 py-4 text-white/76">
                    <div className="flex items-center gap-2"><ToneBadge status={item.status} /><span className="font-semibold text-white">{item.name}</span></div>
                    <div className="mt-3 text-3xl font-display font-bold text-white">{item.score}%</div>
                  </div>
                ))}
              </div>
            </Panel>
            <div className="space-y-6">
              <Panel title="Нагрузка по группам мышц">
                <div className="space-y-3">
                  {data.muscleSplit.map((item) => (
                    <div key={item.rank} className="grid grid-cols-[48px_1fr_auto] items-center gap-3 rounded-[22px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75">
                      <div className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-white/10 bg-black/15">{item.rank}</div>
                      <div>
                        <div className="font-medium text-white">{item.name}</div>
                        <div className="mt-1 text-xs text-white/35">{item.value}</div>
                      </div>
                      <ToneBadge status={item.status} />
                    </div>
                  ))}
                </div>
              </Panel>
              <Panel title="Рекомендация Forma">
                <div className="text-sm leading-7 text-white/68">{data.muscleRecommendation}</div>
              </Panel>
            </div>
          </div>
          <Panel title="Сколько тренировок задействовали каждую группу">
            <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-9">
              {data.muscleCoverage.map((item) => (
                <div key={item.name} className="rounded-[20px] border border-white/8 bg-white/4 p-4 text-center text-white/75">
                  <div className="font-medium text-white">{item.name}</div>
                  <div className="mt-2 text-sm">{item.count}</div>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      ) : null}

      {tab === 'body' ? (
        <div className="space-y-6">
          <MetricCardGrid items={data.bodyCards} columns="xl:grid-cols-5" />
          <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
            <LineChartCard title="Вес по датам" subtitle="Изменение веса по измерениям" points={data.bodyWeightSeries} />
            <Panel title="Замеры">
              {data.bodyMeasurements.length === 0 ? (
                <EmptyStatePanel title="Нет замеров" description="Подключите устройство или введите данные вручную, чтобы отслеживать изменения тела." />
              ) : (
                <div className="space-y-3">
                  {data.bodyMeasurements.map((item) => (
                    <div key={item.label} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 rounded-[22px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75">
                      <span>{item.label}</span>
                      <span className="text-white">{item.current}</span>
                      <span className={item.tone === 'good' ? 'text-[#79de83]' : item.tone === 'warning' ? 'text-[#ff8f84]' : 'text-white/45'}>{item.delta}</span>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </div>
          <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr_0.8fr]">
            <Panel title="Источник данных">
              <div className="rounded-[24px] border border-white/8 bg-white/4 p-4 text-white/75">
                <div className="font-semibold text-white">{data.smartScale.label}</div>
                <div className="mt-3 text-sm leading-7 text-white/55">{data.smartScale.hint}</div>
                <div className="mt-4 flex flex-col gap-3">
                  <Button variant="secondary" iconLeft={<RefreshCw className="h-4 w-4" />}>Синхронизировать</Button>
                  <Button variant="secondary">Ввести вручную</Button>
                </div>
              </div>
            </Panel>
            <Panel title="Измерения за период">
              <div className="space-y-3">
                {data.periodSummary.map((item) => (
                  <div key={item.label} className="flex items-center justify-between gap-3 rounded-[22px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75">
                    <span>{item.label}</span>
                    <span>{item.value}</span>
                  </div>
                ))}
              </div>
            </Panel>
            <Panel title="Рекомендация Forma">
              <div className="text-sm leading-7 text-white/68">{data.photoRecommendation}</div>
            </Panel>
          </div>
        </div>
      ) : null}

      {tab === 'photo' ? (
        <div className="space-y-6">
          <MetricCardGrid items={data.photoStats} columns="xl:grid-cols-4" />
          {data.photoEntries.length === 0 ? (
            <EmptyStatePanel title="Нет фото прогресса" description={data.photoRecommendation} action={<Button iconLeft={<Camera className="h-4 w-4" />} onClick={() => navigate('/photo-progress?source=progress&photo=manual')}>Сделать первое фото</Button>} />
          ) : (
            <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
              <Panel title="История фотофиксаций">
                <div className="space-y-4">
                  {data.photoEntries.map((item) => (
                    <div key={item.id} className="grid gap-4 rounded-[24px] border border-white/8 bg-white/4 p-4 xl:grid-cols-[180px_1fr]">
                      <div>
                        <div className="font-display text-4xl font-bold text-white">{item.date}</div>
                        <div className="text-white/45">{item.year}</div>
                        {item.isLatest ? <div className="mt-4 inline-flex rounded-full border border-[#d6b05f]/30 bg-[#20170b] px-3 py-1 text-xs text-[#f3d18b]">Последняя</div> : null}
                      </div>
                      <div className="grid gap-3 md:grid-cols-3">
                        {item.views.map((view) => (
                          <PhotoPreviewCard key={view.id} title={view.label} label={view.label} />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-5 flex flex-wrap gap-3">
                  <Button iconLeft={<Camera className="h-4 w-4" />} onClick={() => navigate('/photo-progress?source=progress&photo=manual')}>Сделать новое фото</Button>
                  <Button variant="secondary">Сравнить фото</Button>
                  <Button variant="secondary">Открыть галерею</Button>
                </div>
              </Panel>
              <div className="space-y-6">
                <Panel title="Сравнить фото">
                  <div className="grid gap-3 md:grid-cols-2">
                    {data.photoEntries.slice(0, 2).map((entry) => (
                      <div key={entry.id} className="rounded-[22px] border border-white/8 bg-white/4 p-4 text-white/76">
                        <div className="font-semibold text-white">{entry.date}</div>
                        <div className="mt-2 text-sm text-white/45">{entry.year}</div>
                      </div>
                    ))}
                  </div>
                  <Button className="mt-4 w-full" variant="secondary" iconLeft={<ChevronRight className="h-4 w-4" />}>Показать сравнение</Button>
                </Panel>
                <Panel title="Рекомендация Forma">
                  <div className="text-sm leading-7 text-white/68">{data.photoRecommendation}</div>
                </Panel>
              </div>
            </div>
          )}
        </div>
      ) : null}

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}

function StatTile({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-[24px] border border-white/8 bg-white/4 p-4">
      <div className="text-sm text-white/45">{title}</div>
      <div className="mt-2 font-display text-3xl font-bold text-white">{value}</div>
    </div>
  )
}

function HistoryTable({ rows }: { rows: ProgressExerciseHistoryRow[] }) {
  return (
    <div className="overflow-hidden rounded-[24px] border border-white/8">
      <div className="grid grid-cols-[160px_120px_120px_1fr_140px_120px] bg-white/4 px-4 py-3 text-sm text-white/45">
        <div>Дата</div>
        <div>Вес</div>
        <div>Подходы</div>
        <div>Повторы</div>
        <div>Объём</div>
        <div>Амплитуда</div>
      </div>
      {rows.map((row) => (
        <div key={row.date} className="grid grid-cols-[160px_120px_120px_1fr_140px_120px] border-t border-white/8 px-4 py-4 text-sm text-white/74">
          <div>{row.date}</div>
          <div>{row.weight}</div>
          <div>{row.sets}</div>
          <div>{row.reps}</div>
          <div>{row.volume}</div>
          <div>{row.amplitude}</div>
        </div>
      ))}
    </div>
  )
}

function activityDotClass(state: 'done' | 'partial' | 'missed' | 'rest') {
  if (state === 'done') {
    return 'inline-flex h-3 w-3 rounded-full bg-[#57c968]'
  }

  if (state === 'partial') {
    return 'inline-flex h-3 w-3 rounded-full bg-[#f0bf43]'
  }

  if (state === 'missed') {
    return 'inline-flex h-3 w-3 rounded-full bg-[#eb5345]'
  }

  return 'inline-flex h-3 w-3 rounded-full bg-[#687083]'
}

function LegendItem({ label, state }: { label: string; state: 'done' | 'partial' | 'missed' | 'rest' }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className={activityDotClass(state)} />
      {label}
    </span>
  )
}