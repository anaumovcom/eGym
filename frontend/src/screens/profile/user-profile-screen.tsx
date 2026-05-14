import { Camera, Check, Pencil, X } from 'lucide-react'
import { useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { ProfileTab } from '@/entities/stage4/model/types'
import { getExerciseChoices, profileTabs } from '@/mocks/stage4-data'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { Panel, PhotoPreviewCard, SectionTitle, Stage4DevPanel, TabStrip } from '@/shared/ui/stage4/screen-components'
import { useStage4Screen } from '@/features/stage4/lib/use-stage4-screen'
import { useStage4Store } from '@/stores/stage4-store'

function asProfileTab(value: string | null): ProfileTab {
  if (value === 'summary' || value === 'general' || value === 'goals' || value === 'body' || value === 'photo' || value === 'blacklist') {
    return value
  }

  return 'summary'
}

export function UserProfileScreen() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const {
    userName,
    profile,
    profileDraft,
    blacklistedExerciseSlugs,
    toggleBlacklistedExercise,
    emergencyStopActive,
    setEmergencyStopActive,
    dev,
    patchDevFlags,
    resetDevFlags,
  } = useStage4Screen()
  const tab = asProfileTab(searchParams.get('tab'))
  const startProfileEdit = useStage4Store((state) => state.startProfileEdit)
  const updateProfileDraft = useStage4Store((state) => state.updateProfileDraft)
  const saveProfileDraft = useStage4Store((state) => state.saveProfileDraft)
  const cancelProfileEdit = useStage4Store((state) => state.cancelProfileEdit)

  const viewProfile = profileDraft ?? profile
  const editing = Boolean(profileDraft)
  const exerciseChoices = useMemo(() => getExerciseChoices(), [])
  const latestMeasurement = viewProfile.bodyMeasurements[0]

  function updateTab(nextTab: string) {
    setSearchParams((current) => {
      const next = new URLSearchParams(current)
      next.set('tab', nextTab)
      return next
    })
  }

  function togglePriority(name: string) {
    const current = new Set(viewProfile.priorityMuscles)
    if (current.has(name)) {
      current.delete(name)
    } else {
      current.add(name)
    }
    updateProfileDraft('priorityMuscles', [...current])
  }

  return (
    <FormaShell userName={userName} machine={{ machineState: dev.machineReady ? 'ready' : 'warning', machineLabel: dev.machineReady ? 'Тренажёр готов' : 'Есть предупреждения', leftDrive: dev.leftDriveError ? 'error' : 'connected', rightDrive: dev.rightDriveError ? 'error' : 'connected', safety: dev.safetyDisabled ? 'disabled' : dev.emergencyStop ? 'emergency_stop' : 'enabled', calibration: dev.noCalibration ? 'Нет калибровки' : 'Калибровка сохранена' }} onStop={() => setEmergencyStopActive(true)}>
      <SectionTitle
        title="Профиль пользователя"
        description="Данные пользователя, цели, тело, фото прогресса и персональные ограничения."
        actions={
          <div className="flex flex-wrap gap-3">
            {!editing ? (
              <Button variant="secondary" iconLeft={<Pencil className="h-4 w-4" />} onClick={startProfileEdit}>
                Редактировать профиль
              </Button>
            ) : null}
            <Button variant="secondary" iconLeft={<Camera className="h-4 w-4" />} onClick={() => navigate('/photo-progress?source=profile&photo=manual')}>
              Сделать фото прогресса
            </Button>
          </div>
        }
      />

      <section className="glass-panel rounded-[34px] p-6 xl:p-8">
        <div className="grid gap-6 xl:grid-cols-[220px_1fr_auto]">
          <div className="flex items-center justify-center">
            <div className="flex h-40 w-40 items-center justify-center rounded-full border border-[#d6b05f]/20 bg-[radial-gradient(circle_at_top,rgba(214,176,95,0.16),transparent_40%),linear-gradient(180deg,#171a20,#0d0f13)] text-6xl font-display font-bold text-[#f3d18b]">
              {viewProfile.avatarLabel}
            </div>
          </div>
          <div>
            <div className="font-display text-6xl font-bold tracking-[-0.07em] text-white">{viewProfile.name}</div>
            <div className="mt-5 grid gap-4 md:grid-cols-4">
              <ProfileStat label="Цель" value={viewProfile.goal} />
              <ProfileStat label="Рост" value={`${viewProfile.heightCm} см`} />
              <ProfileStat label="Вес" value={viewProfile.weightKg > 0 ? `${viewProfile.weightKg} кг` : '—'} />
              <ProfileStat label="Уровень" value={viewProfile.level} />
            </div>
          </div>
          {editing ? (
            <div className="flex flex-col gap-3">
              <Button iconLeft={<Check className="h-4 w-4" />} onClick={saveProfileDraft}>Сохранить изменения</Button>
              <Button variant="secondary" iconLeft={<X className="h-4 w-4" />} onClick={cancelProfileEdit}>Отменить</Button>
            </div>
          ) : null}
        </div>
      </section>

      <TabStrip tabs={profileTabs} active={tab} onChange={updateTab} />

      {tab === 'summary' ? (
        <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <div className="space-y-6">
            <Panel title="Основная информация">
              <InfoGrid rows={[
                ['Имя', viewProfile.name],
                ['Рост', `${viewProfile.heightCm} см`],
                ['Вес', viewProfile.weightKg > 0 ? `${viewProfile.weightKg} кг` : '—'],
                ['Уровень', viewProfile.level],
                ['Основная цель', viewProfile.goal],
              ]} />
            </Panel>
            <div className="grid gap-6 xl:grid-cols-2">
              <Panel title="Последние данные тела">
                {latestMeasurement ? (
                  <InfoGrid rows={[
                    ['Вес', `${latestMeasurement.weight} кг`],
                    ['Талия', `${latestMeasurement.waistCm} см`],
                    ['Грудь', `${latestMeasurement.chestCm} см`],
                    ['Бёдра', `${latestMeasurement.hipsCm} см`],
                  ]} />
                ) : (
                  <div className="text-sm text-white/45">Данных пока нет.</div>
                )}
              </Panel>
              <Panel title="Фото прогресса">
                <div className="grid gap-3 md:grid-cols-3">
                  {(viewProfile.photos[0]?.views ?? []).map((view) => (
                    <PhotoPreviewCard key={view.id} title={view.label} label={view.label} />
                  ))}
                </div>
              </Panel>
            </div>
          </div>
          <div className="space-y-6">
            <Panel title="Краткая сводка">
              <InfoGrid rows={[
                ['Дата последнего фото', viewProfile.photos[0]?.date ?? 'Нет данных'],
                ['Текущий вес', viewProfile.weightKg > 0 ? `${viewProfile.weightKg} кг` : '—'],
                ['Цель', viewProfile.goal],
                ['Частота тренировок', viewProfile.trainingFrequency],
                ['Рекомендация', 'Сегодня лучше спина'],
              ]} />
            </Panel>
            <Panel title="Чёрный список упражнений">
              {blacklistedExerciseSlugs.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {blacklistedExerciseSlugs.map((slug) => (
                    <button key={slug} type="button" onClick={() => toggleBlacklistedExercise(slug)} className="rounded-full border border-white/10 bg-white/4 px-3 py-2 text-sm text-white/74">{slug}</button>
                  ))}
                </div>
              ) : (
                <div className="text-sm text-white/45">Нет исключённых упражнений.</div>
              )}
            </Panel>
          </div>
        </div>
      ) : null}

      {tab === 'general' ? (
        <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
          <Panel title="Основные данные">
            <EditableField label="Имя" value={viewProfile.name} editing={editing} onChange={(value) => updateProfileDraft('name', value)} />
            <EditableField label="Рост" value={String(viewProfile.heightCm)} editing={editing} suffix="см" onChange={(value) => updateProfileDraft('heightCm', Number(value) || 0)} />
            <EditableField label="Вес" value={String(viewProfile.weightKg)} editing={editing} suffix="кг" onChange={(value) => updateProfileDraft('weightKg', Number(value) || 0)} />
            <EditableField label="Уровень подготовки" value={viewProfile.level} editing={editing} onChange={(value) => updateProfileDraft('level', value)} />
            <EditableField label="Основная цель" value={viewProfile.goal} editing={editing} onChange={(value) => updateProfileDraft('goal', value)} />
            <EditableField label="Дата создания профиля" value={viewProfile.createdAt} editing={editing} onChange={(value) => updateProfileDraft('createdAt', value)} />
          </Panel>
          <div className="space-y-6">
            <Panel title="Профиль и персонализация">
              <EditableField label="Язык интерфейса" value={viewProfile.locale} editing={editing} onChange={(value) => updateProfileDraft('locale', value)} />
              <EditableField label="Единицы измерения" value={viewProfile.units} editing={editing} onChange={(value) => updateProfileDraft('units', value)} />
              <EditableField label="Тема интерфейса" value={viewProfile.theme} editing={editing} onChange={(value) => updateProfileDraft('theme', value)} />
            </Panel>
            <Panel title="Контакт и заметки">
              <EditableField label="Email" value={viewProfile.email || 'не указан'} editing={editing} onChange={(value) => updateProfileDraft('email', value === 'не указан' ? '' : value)} />
              <EditableTextarea label="Личные заметки" value={viewProfile.notes} editing={editing} onChange={(value) => updateProfileDraft('notes', value)} />
            </Panel>
          </div>
        </div>
      ) : null}

      {tab === 'goals' ? (
        <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
          <Panel title="Главная цель">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {['Сила + общая форма', 'Мышечная масса', 'Поддержание активности', 'Выносливость', 'Восстановительный режим'].map((item) => (
                <button
                  key={item}
                  type="button"
                  disabled={!editing}
                  onClick={() => updateProfileDraft('goal', item.toLowerCase())}
                  className={`rounded-[20px] border px-4 py-4 text-left text-sm transition ${viewProfile.goal.toLowerCase() === item.toLowerCase() ? 'border-[#d6b05f]/40 bg-[#20170b] text-[#f3d18b]' : 'border-white/8 bg-white/4 text-white/72'}`}
                >
                  {item}
                </button>
              ))}
            </div>
          </Panel>
          <Panel title="Параметры тренировок">
            <EditableField label="Частота" value={viewProfile.trainingFrequency} editing={editing} onChange={(value) => updateProfileDraft('trainingFrequency', value)} />
            <EditableField label="Длительность" value={viewProfile.workoutDuration} editing={editing} onChange={(value) => updateProfileDraft('workoutDuration', value)} />
            <EditableField label="Стиль" value={viewProfile.workoutStyle} editing={editing} onChange={(value) => updateProfileDraft('workoutStyle', value)} />
            <EditableBoolean label="Автогенерация программ" value={viewProfile.autoPrograms} editing={editing} onChange={(value) => updateProfileDraft('autoPrograms', value)} />
          </Panel>
          <Panel title="Приоритетные мышечные группы">
            <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
              {['Грудь', 'Спина', 'Ноги', 'Плечи', 'Руки', 'Кор'].map((item) => (
                <button
                  key={item}
                  type="button"
                  disabled={!editing}
                  onClick={() => togglePriority(item)}
                  className={`rounded-[20px] border px-4 py-4 text-sm transition ${viewProfile.priorityMuscles.includes(item) ? 'border-[#d6b05f]/40 bg-[#20170b] text-[#f3d18b]' : 'border-white/8 bg-white/4 text-white/72'}`}
                >
                  {item}
                </button>
              ))}
            </div>
          </Panel>
          <Panel title="Что учитывать при подборе">
            <EditableList items={viewProfile.considerationNotes} editing={editing} onChange={(items) => updateProfileDraft('considerationNotes', items)} />
          </Panel>
        </div>
      ) : null}

      {tab === 'body' ? (
        <div className="grid gap-6 xl:grid-cols-[1fr_1fr_0.7fr]">
          <Panel title="Текущие показатели">
            {latestMeasurement ? (
              <InfoGrid rows={[
                ['Вес', `${latestMeasurement.weight} кг`],
                ['Талия', `${latestMeasurement.waistCm} см`],
                ['Грудь', `${latestMeasurement.chestCm} см`],
                ['Бёдра', `${latestMeasurement.hipsCm} см`],
                ['Плечи', `${latestMeasurement.shouldersCm} см`],
                ['Бицепс', `${latestMeasurement.bicepsCm} см`],
              ]} />
            ) : (
              <div className="text-sm text-white/45">Нет измерений.</div>
            )}
          </Panel>
          <Panel title="История измерений">
            <div className="space-y-3">
              {viewProfile.bodyMeasurements.map((item) => (
                <div key={item.date} className="grid grid-cols-[1fr_repeat(5,auto)] gap-3 rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75">
                  <span>{item.date}</span>
                  <span>{item.weight} кг</span>
                  <span>{item.waistCm} см</span>
                  <span>{item.chestCm} см</span>
                  <span>{item.hipsCm} см</span>
                  <span>{item.bicepsCm} см</span>
                </div>
              ))}
            </div>
          </Panel>
          <Panel title="Краткий вывод">
            <div className="text-sm leading-7 text-white/68">Вес снижается плавно, динамика стабильная.</div>
          </Panel>
        </div>
      ) : null}

      {tab === 'photo' ? (
        <Panel title="Фото прогресса">
          {viewProfile.photos.length === 0 ? (
            <div className="text-sm text-white/45">Фотографии пока не добавлены.</div>
          ) : (
            <div className="space-y-4">
              {viewProfile.photos.map((photo) => (
                <div key={photo.id} className="rounded-[24px] border border-white/8 bg-white/4 p-4">
                  <div className="font-semibold text-white">{photo.date}</div>
                  <div className="mt-4 grid gap-3 md:grid-cols-3">
                    {photo.views.map((view) => (
                      <PhotoPreviewCard key={view.id} title={view.label} label={view.label} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      ) : null}

      {tab === 'blacklist' ? (
        <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
          <Panel title="Исключено упражнений">
            <div className="text-5xl font-display font-bold text-white">{blacklistedExerciseSlugs.length}</div>
            <div className="mt-4 flex flex-wrap gap-2">
              {blacklistedExerciseSlugs.length > 0 ? blacklistedExerciseSlugs.map((slug) => (
                <button key={slug} type="button" onClick={() => toggleBlacklistedExercise(slug)} className="rounded-full border border-white/10 bg-white/4 px-3 py-2 text-sm text-white/74">{slug}</button>
              )) : <span className="text-sm text-white/45">Чёрный список пуст.</span>}
            </div>
          </Panel>
          <Panel title="Управление ограничениями">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {exerciseChoices.map((exercise) => {
                const active = blacklistedExerciseSlugs.includes(exercise.slug)
                return (
                  <button key={exercise.slug} type="button" onClick={() => toggleBlacklistedExercise(exercise.slug)} className={`rounded-[22px] border p-4 text-left ${active ? 'border-[#d6b05f]/40 bg-[#20170b] text-[#f3d18b]' : 'border-white/8 bg-white/4 text-white/72'}`}>
                    <div className="font-medium">{exercise.name}</div>
                    <div className="mt-1 text-xs text-white/45">{exercise.secondaryName}</div>
                    <div className="mt-3 text-xs">{active ? 'Исключено' : 'Разрешено'}</div>
                  </button>
                )
              })}
            </div>
          </Panel>
        </div>
      ) : null}

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
      <Stage4DevPanel value={dev} onChange={patchDevFlags} onReset={resetDevFlags} />
    </FormaShell>
  )
}

function ProfileStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[22px] border border-white/8 bg-white/4 p-4">
      <div className="text-sm text-white/45">{label}</div>
      <div className="mt-2 font-semibold text-white">{value}</div>
    </div>
  )
}

function InfoGrid({ rows }: { rows: Array<[string, string]> }) {
  return (
    <div className="space-y-3">
      {rows.map(([label, value]) => (
        <div key={label} className="grid grid-cols-[200px_1fr] items-center gap-3 rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75">
          <span>{label}</span>
          <span className="text-white">{value}</span>
        </div>
      ))}
    </div>
  )
}

function EditableField({ label, value, editing, onChange, suffix }: { label: string; value: string; editing: boolean; onChange: (value: string) => void; suffix?: string }) {
  return (
    <div className="mb-3 grid grid-cols-[220px_1fr] items-center gap-3 rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75">
      <span>{label}</span>
      {editing ? (
        <div className="flex items-center gap-2">
          <input title={label} aria-label={label} placeholder={label} value={value} onChange={(event) => onChange(event.target.value)} className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-white outline-none" />
          {suffix ? <span className="text-white/45">{suffix}</span> : null}
        </div>
      ) : (
        <span className="text-white">{value}</span>
      )}
    </div>
  )
}

function EditableTextarea({ label, value, editing, onChange }: { label: string; value: string; editing: boolean; onChange: (value: string) => void }) {
  return (
    <div className="rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75">
      <div>{label}</div>
      {editing ? <textarea title={label} aria-label={label} placeholder={label} value={value} onChange={(event) => onChange(event.target.value)} className="mt-3 min-h-28 w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-white outline-none" /> : <div className="mt-3 text-white">{value || '—'}</div>}
    </div>
  )
}

function EditableBoolean({ label, value, editing, onChange }: { label: string; value: boolean; editing: boolean; onChange: (value: boolean) => void }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3 rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75">
      <span>{label}</span>
      {editing ? (
        <button type="button" title={label} aria-label={label} onClick={() => onChange(!value)} className={`inline-flex h-7 w-12 items-center rounded-full border px-1 transition ${value ? 'justify-end border-[#d6b05f]/40 bg-[#20170b]' : 'justify-start border-white/10 bg-black/20'}`}>
          <span className={`h-5 w-5 rounded-full ${value ? 'bg-[#f3d18b]' : 'bg-white/35'}`} />
        </button>
      ) : (
        <span className="text-white">{value ? 'включена' : 'выключена'}</span>
      )}
    </div>
  )
}

function EditableList({ items, editing, onChange }: { items: string[]; editing: boolean; onChange: (value: string[]) => void }) {
  return (
    <div className="space-y-3">
      {items.map((item, index) => (
        <div key={`${item}-${index}`} className="rounded-[20px] border border-white/8 bg-white/4 px-4 py-4 text-sm text-white/75">
          {editing ? <input title={`Пункт ${index + 1}`} aria-label={`Пункт ${index + 1}`} placeholder={`Пункт ${index + 1}`} value={item} onChange={(event) => onChange(items.map((current, itemIndex) => (itemIndex === index ? event.target.value : current)))} className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-white outline-none" /> : item}
        </div>
      ))}
    </div>
  )
}