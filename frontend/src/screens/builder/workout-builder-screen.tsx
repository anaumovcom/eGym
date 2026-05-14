import { useQuery } from '@tanstack/react-query'
import { ListTree, Plus, Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { WorkoutBuilderData } from '@/entities/builder/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import { apiGet } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { BuilderWarningPanel, FilterChip, LoadModeSelector, SearchField, SectionIntro, SupportCard } from '@/shared/ui/stage2/screen-components'
import { useAppStore } from '@/stores/app-store'

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

export function WorkoutBuilderScreen() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)

  const selectedExerciseId = searchParams.get('selectedExerciseId') ?? 'group-pullups-1'

  const fallbackMachine: MachineHealth = {
    machineState: 'ready',
    machineLabel: 'Загрузка статуса',
    leftDrive: 'connected',
    rightDrive: 'connected',
    safety: 'enabled',
    calibration: 'Проверка подключения...',
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ['workout-builder', selectedExerciseId],
    queryFn: () => apiGet<WorkoutBuilderData>(`/api/builder?selectedExerciseId=${encodeURIComponent(selectedExerciseId)}`),
  })

  const [editor, setEditor] = useState(data?.selectedExercise ?? null)

  useEffect(() => {
    setEditor(data?.selectedExercise ?? null)
  }, [data?.selectedExercise])

  if (isLoading || !data || !editor) {
    return (
      <FormaShell userName={getUserName(selectedUserId)} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
        <div className="glass-panel rounded-[34px] p-8 text-white/72">Загрузка конструктора тренировки…</div>
      </FormaShell>
    )
  }

  if (error) {
    return (
      <FormaShell userName={getUserName(selectedUserId)} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
        <div className="glass-panel rounded-[34px] border border-[#eb5345]/25 bg-[#1b0f10] p-8 text-[#ffb4a7]">Не удалось загрузить конструктор тренировки. Проверьте backend API.</div>
      </FormaShell>
    )
  }

  return (
    <FormaShell userName={getUserName(selectedUserId)} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
      <SectionIntro
        title={data.title}
        description={data.subtitle}
        actions={
          <div className="flex flex-wrap gap-3">
            <Button iconLeft={<Plus className="h-4 w-4" />}>Новая тренировка</Button>
            <Button variant="secondary">Сгенерировать</Button>
            <Button variant="secondary">Мои программы</Button>
            <Button variant="secondary" iconLeft={<Save className="h-4 w-4" />}>Сохранить программу</Button>
          </div>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1.35fr_0.85fr]">
        <section className="space-y-6">
          <div className="glass-panel rounded-[32px] p-5">
            <div className="grid gap-4 xl:grid-cols-5">
              <InfoField label="Название" value={data.info.name} />
              <InfoField label="Тип" value={data.info.type} />
              <InfoField label="Длительность" value={data.info.duration} />
              <InfoField label="Сложность" value={data.info.difficulty} />
              <InfoField label="Описание" value={data.info.description} />
            </div>
          </div>

          <section className="glass-panel rounded-[32px] p-5">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <div className="text-sm uppercase tracking-[0.24em] text-white/35">План тренировки</div>
                <div className="mt-2 font-display text-3xl font-bold text-white">Структура плана</div>
              </div>
              <div className="flex flex-wrap gap-3">
                <Button variant="secondary" iconLeft={<Plus className="h-4 w-4" />}>Добавить упражнение</Button>
                <Button variant="secondary">Добавить группу</Button>
              </div>
            </div>

            <div className="space-y-4">
              {data.groups.map((group, index) => (
                <div key={group.id} className="rounded-[28px] border border-white/8 bg-[#111419] p-5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-sm uppercase tracking-[0.24em] text-white/35">{group.kind === 'alternating' ? 'Группа чередования' : group.kind === 'superset' ? 'Суперсет' : group.kind === 'circuit' ? 'Круг' : 'Обычное упражнение'}</div>
                      <div className="mt-2 font-display text-3xl font-bold text-white">{index + 1}. {group.title}</div>
                      <div className="mt-2 text-sm text-white/45">{group.rounds ?? 'Основной блок'} {group.betweenExercisesRest ? `• Отдых между упражнениями ${group.betweenExercisesRest}` : ''}</div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <FilterChip label="Редактировать" />
                      <FilterChip label="Копировать" />
                      <FilterChip label="Удалить" />
                    </div>
                  </div>

                  <div className="mt-4 overflow-hidden rounded-[24px] border border-white/8">
                    <div className="grid grid-cols-[1fr_140px_120px_120px] bg-white/4 px-4 py-3 text-sm text-white/45">
                      <div>Упражнение</div>
                      <div>Вес</div>
                      <div>Подходы</div>
                      <div>Отдых</div>
                    </div>
                    {group.items.map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() =>
                          setSearchParams((current) => {
                            const next = new URLSearchParams(current)
                            next.set('selectedExerciseId', item.id)
                            return next
                          })
                        }
                        className="grid w-full grid-cols-[1fr_140px_120px_120px] border-t border-white/8 px-4 py-4 text-left text-sm text-white/74 transition hover:bg-white/4"
                      >
                        <div>
                          <div className="font-medium text-white">{item.name}</div>
                          <div className="mt-1 text-white/45">{item.muscleGroup}</div>
                        </div>
                        <div>{item.load}</div>
                        <div>{item.sets}</div>
                        <div>{item.rest}</div>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <div className="grid gap-6 xl:grid-cols-[1fr_1fr_1fr]">
            <section className="glass-panel rounded-[32px] p-5">
              <div className="mb-4 font-display text-3xl font-bold text-white">Добавить упражнение</div>
              <SearchField value="" placeholder="Поиск упражнения..." onChange={() => {}} />
              <div className="mt-4 flex flex-wrap gap-2">
                {['Все', 'Спина', 'Грудь', 'Ноги', 'Руки', 'Кор', 'Другое'].map((filter) => (
                  <FilterChip key={filter} label={filter} active={filter === 'Все'} />
                ))}
              </div>
              <div className="mt-4 space-y-3">
                {data.addSuggestions.map((item) => (
                  <div key={item.slug} className="rounded-[22px] border border-white/8 bg-white/4 px-4 py-3 text-white/74">
                    <div className="font-medium text-white">{item.name}</div>
                    <div className="mt-1 text-sm text-white/45">{item.muscles}</div>
                  </div>
                ))}
              </div>
            </section>

            <section className="glass-panel rounded-[32px] p-5 xl:col-span-2">
              <div className="mb-4 flex items-center gap-3 text-white/45"><ListTree className="h-4 w-4" />Сводка тренировки</div>
              <div className="grid gap-4 md:grid-cols-4">
                {data.summaryCards.map((card) => (
                  <div key={card.label} className="rounded-[24px] border border-white/8 bg-white/4 p-4">
                    <div className="font-display text-4xl font-bold text-white">{card.value}</div>
                    <div className="mt-2 text-sm text-white/45">{card.label}</div>
                    <div className="mt-1 text-xs text-white/32">{card.hint}</div>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </section>

        <aside className="space-y-6">
          <section className="glass-panel rounded-[32px] p-5">
            <div className="font-display text-3xl font-bold text-white">Выбранное упражнение</div>
            <div className="mt-2 text-white/45">{editor.subtitle}</div>

            <div className="mt-5 grid gap-4 md:grid-cols-3">
              <ControlBlock label="Повторы" value={`${editor.setParams.reps}`} onChange={(delta) => setEditor((state) => (state ? { ...state, setParams: { ...state.setParams, reps: Math.max(1, state.setParams.reps + delta) } } : state))} />
              <ControlBlock label="Вес" value={`${editor.setParams.weight}`} suffix="кг" onChange={(delta) => setEditor((state) => (state ? { ...state, setParams: { ...state.setParams, weight: Math.max(0, state.setParams.weight + delta) } } : state))} />
              <ControlBlock label="Отдых" value={`${editor.setParams.restSeconds}`} suffix="сек" onChange={(delta) => setEditor((state) => (state ? { ...state, setParams: { ...state.setParams, restSeconds: Math.max(15, state.setParams.restSeconds + delta * 15) } } : state))} />
            </div>

            <div className="mt-5 space-y-4">
              <div>
                <div className="mb-2 text-sm text-white/45">Режим нагрузки</div>
                <LoadModeSelector value={editor.loadMode} options={['Обычный вес', 'Контроль техники', 'Лёгкий режим']} onChange={(mode) => setEditor((state) => (state ? { ...state, loadMode: mode } : state))} />
              </div>
              <div>
                <div className="mb-2 text-sm text-white/45">Темп выполнения</div>
                <LoadModeSelector value={editor.tempo} options={['Обычный', 'Плавный', 'Контроль эксцентрики']} onChange={(tempo) => setEditor((state) => (state ? { ...state, tempo } : state))} />
              </div>
              <div>
                <div className="mb-2 text-sm text-white/45">Комментарий</div>
                <textarea
                  value={editor.note}
                  onChange={(event) => setEditor((state) => (state ? { ...state, note: event.target.value } : state))}
                  aria-label="Комментарий к упражнению"
                  title="Комментарий к упражнению"
                  placeholder="Добавьте заметку по технике или нагрузке"
                  className="min-h-28 w-full rounded-[24px] border border-white/8 bg-white/4 px-4 py-3 text-sm text-white outline-none placeholder:text-white/24"
                />
              </div>
            </div>

            <div className="mt-5 flex flex-col gap-3">
              <Button>Применить изменения</Button>
              <Button variant="secondary" onClick={() => navigate('/exercise-setup?source=builder')}>
                Запустить runtime группы
              </Button>
              <Button variant="secondary" onClick={() => navigate('/catalog')}>Заменить упражнение</Button>
              <Button variant="secondary">Удалить упражнение</Button>
            </div>
          </section>

          <section className="space-y-4">
            {data.warnings.map((warning) => (
              <BuilderWarningPanel key={warning.title} title={warning.title} description={warning.description} tone={warning.tone} />
            ))}
          </section>

          <SupportCard />
        </aside>
      </div>

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}

function InfoField({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[24px] border border-white/8 bg-white/4 p-4">
      <div className="text-sm text-white/45">{label}</div>
      <div className="mt-2 text-white">{value}</div>
    </div>
  )
}

function ControlBlock({ label, value, suffix, onChange }: { label: string; value: string; suffix?: string; onChange: (delta: number) => void }) {
  return (
    <div className="rounded-[24px] border border-white/8 bg-white/4 p-4">
      <div className="text-sm text-white/45">{label}</div>
      <div className="mt-3 flex items-center justify-between gap-3">
        <button type="button" onClick={() => onChange(-1)} className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-[#0d1116] text-white/72">-</button>
        <div className="text-center">
          <div className="font-display text-3xl font-bold text-white">{value}</div>
          {suffix ? <div className="text-xs text-white/35">{suffix}</div> : null}
        </div>
        <button type="button" onClick={() => onChange(1)} className="inline-flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-[#0d1116] text-white/72">+</button>
      </div>
    </div>
  )
}