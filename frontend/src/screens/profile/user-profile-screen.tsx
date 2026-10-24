import * as Dialog from '@radix-ui/react-dialog'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera, ChevronRight, Dumbbell, Flame, Images, Pencil, Plus, Ruler, Scale, Target, Trophy } from 'lucide-react'
import { useMemo, useState, type Dispatch, type ReactNode, type SetStateAction } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { exerciseCatalogOptions } from '@/entities/exercise/model/catalog'
import type { ExerciseSummary } from '@/entities/exercise/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { ProgressData } from '@/entities/stage4/model/types'
import { BodyMetricCard } from '@/features/body/body-metric-card'
import { BodyMeasurementsView } from '@/features/body/body-measurements-view'
import { bodyMassIndex, bodyMetrics, daysBetween, formatBody, type BodyMeasurement } from '@/features/body/body-metrics'
import { MeasurementDialog } from '@/features/body/measurement-dialogs'
import { ProgressPhotoGallery, PhotoImage, photoViews, type ProgressPhoto } from '@/screens/progress/progress-photo-gallery'
import { apiDelete, apiGet, apiPut, resolveApiAssetUrl } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { PhotoCaptureDialog } from '@/shared/ui/photo/photo-capture-dialog'
import { useAppStore } from '@/stores/app-store'
import './user-profile-screen.css'

type ProfileTab = 'overview' | 'measurements' | 'photo' | 'restrictions'
type CurrentUser = {
  id: string; name: string; readinessPercent: number
  profile: { birthDate: string | null; heightCm: number | null; weightKg: number | null; photoUrl: string | null; notes: string | null } | null
  goals: Array<{ id: number; goalType: string; label: string; targetValue: number | null; targetUnit: string | null; isPrimary: boolean }>
}
type Photo = ProgressPhoto & { imageUrl: string; width: number; height: number }
type ProfileData = { user: CurrentUser; measurements: BodyMeasurement[]; photos: Photo[]; exercises: ExerciseSummary[] }
type EditDraft = { name: string; birthDate: string; heightCm: string; weightKg: string; notes: string; goalLabel: string; goalType: string; targetValue: string; targetUnit: string }

const tabs: Array<{ id: ProfileTab; label: string }> = [
  { id: 'overview', label: 'Обзор' }, { id: 'measurements', label: 'Измерения' }, { id: 'photo', label: 'Фото' }, { id: 'restrictions', label: 'Ограничения' },
]
const fallbackMachine: MachineHealth = { machineState: 'ready', machineLabel: 'Загрузка статуса', leftDrive: 'connected', rightDrive: 'connected', safety: 'enabled', calibration: 'Проверка подключения...' }
const dateFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
const shortFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short' })

export function UserProfileScreen() {
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const blacklisted = useAppStore((state) => state.blacklistedExerciseSlugs)
  const toggleBlacklisted = useAppStore((state) => state.toggleBlacklistedExercise)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const userId = selectedUserId ?? 'alexey'
  const userName = userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
  const tab = asTab(params.get('tab'))
  const [editOpen, setEditOpen] = useState(false)
  const [measureOpen, setMeasureOpen] = useState(false)
  const [photoOpen, setPhotoOpen] = useState(false)
  const [editDraft, setEditDraft] = useState<EditDraft | null>(null)
  const [pending, setPending] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['user-profile-screen', userId],
    enabled: userId !== 'guest',
    queryFn: async (): Promise<ProfileData> => {
      const [user, measurements, photos, catalog] = await Promise.all([
        apiGet<CurrentUser>('/api/users/current'),
        apiGet<{ measurements: BodyMeasurement[] }>(`/api/body-measurements?userId=${encodeURIComponent(userId)}`),
        apiGet<{ photos: Photo[] }>(`/api/photo-progress?userId=${encodeURIComponent(userId)}`),
        queryClient.fetchQuery(exerciseCatalogOptions(userId)),
      ])
      return {
        user,
        measurements: [...measurements.measurements].sort((left, right) => new Date(right.measuredAt).getTime() - new Date(left.measuredAt).getTime()),
        photos: [...photos.photos].sort((left, right) => new Date(right.takenAt).getTime() - new Date(left.takenAt).getTime()),
        exercises: catalog.items,
      }
    },
  })
  // Same key as the progress page, so both screens share one request.
  const training = useQuery({
    queryKey: ['progress-screen', userId, '30d'],
    queryFn: () => apiGet<ProgressData>(`/api/progress?userId=${encodeURIComponent(userId)}&period=30d`),
    enabled: userId !== 'guest' && tab === 'overview',
  })

  const guest = useMemo<ProfileData>(() => ({ user: { id: 'guest', name: 'Гость', readinessPercent: 0, profile: null, goals: [] }, measurements: [], photos: [], exercises: [] }), [])
  const profile = data ?? guest
  const primaryGoal = profile.user.goals.find((goal) => goal.isPrimary) ?? profile.user.goals[0]
  const age = calculateAge(profile.user.profile?.birthDate)
  const weight = profile.user.profile?.weightKg ?? null
  const bmi = bodyMassIndex(weight, profile.user.profile?.heightCm)
  const target = primaryGoal?.targetValue != null ? `${primaryGoal.targetValue} ${primaryGoal.targetUnit ?? ''}`.trim() : 'Ориентир не задан'
  const excludedExercises = blacklisted.map((slug) => profile.exercises.find((item) => item.slug === slug) ?? { slug, name: humanizeSlug(slug), imageUrl: undefined } as ExerciseSummary)

  function updateTab(next: ProfileTab) {
    setParams((current) => { const nextParams = new URLSearchParams(current); if (next === 'overview') nextParams.delete('tab'); else nextParams.set('tab', next); return nextParams })
  }

  function openEdit() {
    setEditDraft({
      name: profile.user.name, birthDate: profile.user.profile?.birthDate ?? '', heightCm: String(profile.user.profile?.heightCm ?? ''), weightKg: String(profile.user.profile?.weightKg ?? ''),
      notes: profile.user.profile?.notes ?? '', goalLabel: primaryGoal?.label ?? 'Поддержание активности', goalType: primaryGoal?.goalType ?? 'habit',
      targetValue: String(primaryGoal?.targetValue ?? ''), targetUnit: primaryGoal?.targetUnit ?? '',
    })
    setFormError(null); setEditOpen(true)
  }

  async function saveProfile() {
    if (!editDraft || pending) return
    setPending(true); setFormError(null)
    try {
      await apiPut(`/api/users/${encodeURIComponent(userId)}/profile`, {
        name: editDraft.name.trim(), birthDate: editDraft.birthDate || null, heightCm: optionalNumber(editDraft.heightCm), weightKg: optionalNumber(editDraft.weightKg), notes: editDraft.notes || null,
        goalLabel: editDraft.goalLabel.trim(), goalType: editDraft.goalType, targetValue: optionalNumber(editDraft.targetValue), targetUnit: editDraft.targetUnit || null,
      })
      await queryClient.invalidateQueries({ queryKey: ['user-profile-screen', userId] })
      setEditOpen(false)
    } catch (saveError) { setFormError(saveError instanceof Error ? saveError.message : 'Не удалось сохранить профиль.') }
    finally { setPending(false) }
  }

  async function deletePhoto(id: number) {
    await apiDelete(`/api/photo-progress/${id}?confirm=true`)
    await Promise.all([queryClient.invalidateQueries({ queryKey: ['user-profile-screen', userId] }), queryClient.invalidateQueries({ queryKey: ['progress-photos', userId] })])
  }

  if (isPending && userId !== 'guest') return <FormaShell userName={userName} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}><div className="forma-state" role="status">Загрузка профиля…</div></FormaShell>
  if (error && userId !== 'guest') return <FormaShell userName={userName} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}><div className="forma-state" role="alert"><p>Не удалось загрузить профиль.</p><Button onClick={() => void refetch()}>Повторить</Button></div></FormaShell>

  return (
    <FormaShell userName={userName} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
      <section className="profile-center" aria-labelledby="profile-name">
        <header className="profile-hero">
          <div className="profile-avatar">
            {profile.user.profile?.photoUrl ? <img src={resolveApiAssetUrl(profile.user.profile.photoUrl) ?? profile.user.profile.photoUrl} alt="Фотография пользователя" /> : <span aria-hidden="true">{profile.user.name.charAt(0).toUpperCase()}</span>}
          </div>
          <div className="profile-identity">
            <h1 id="profile-name" className="font-display font-bold text-white">{profile.user.name}</h1>
            <ul className="profile-chips" aria-label="Персональные данные">
              {age != null ? <li>{age} {plural(age, 'год', 'года', 'лет')}</li> : null}
              {profile.user.profile?.heightCm ? <li>{profile.user.profile.heightCm} см</li> : null}
              {weight ? <li>{formatBody(weight)} кг</li> : null}
              {bmi ? <li data-tone={bmi.tone}>ИМТ {formatBody(bmi.value)} · {bmi.category}</li> : null}
              {age == null && !profile.user.profile?.heightCm && !weight ? <li>Персональные данные не заполнены</li> : null}
            </ul>
            <div className="profile-goal"><span className="profile-goal-icon" aria-hidden="true"><Target /></span><div><span>Основная цель</span><strong>{primaryGoal?.label ?? 'Поддержание активности'}</strong><small>Ближайший ориентир: {target}</small></div></div>
          </div>
          <Button variant="secondary" iconLeft={<Pencil aria-hidden="true" />} onClick={openEdit} disabled={userId === 'guest'}>Редактировать</Button>
        </header>

        <nav className="profile-tabs" aria-label="Разделы профиля">
          {tabs.map((item) => <button key={item.id} type="button" aria-current={tab === item.id ? 'page' : undefined} onClick={() => updateTab(item.id)}>{item.label}</button>)}
        </nav>

        {tab === 'overview' ? (
          <div className="profile-overview">
            <ProfilePanel className="profile-body" title="Тело" description={profile.measurements.length ? `Последнее измерение ${dateFormat.format(new Date(profile.measurements[0].measuredAt))}` : 'Измерений пока нет'} action={<Button variant="secondary" iconLeft={<Plus aria-hidden="true" />} onClick={() => setMeasureOpen(true)} disabled={userId === 'guest'}>Добавить измерение</Button>}>
              <div className="profile-body-cards">{bodyMetrics.filter((metric) => metric.key !== 'bodyFatPercent').map((metric) => <BodyMetricCard key={metric.key} metric={metric} measurements={profile.measurements} />)}</div>
              <button type="button" className="profile-more" onClick={() => updateTab('measurements')}>Все измерения и графики<ChevronRight aria-hidden="true" /></button>
            </ProfilePanel>
            <LatestPhotoPanel photos={profile.photos} onPhoto={() => setPhotoOpen(true)} onOpen={() => updateTab('photo')} />
            <TrainingPanel data={training.data} loading={training.isPending && userId !== 'guest'} />
            <TimelinePanel measurements={profile.measurements} photos={profile.photos} training={training.data} />
          </div>
        ) : null}

        {tab === 'measurements' ? (
          <BodyMeasurementsView key={userId} userId={userId} measurements={profile.measurements} title="История измерений" description="Вес, процент жира и объёмы. Нажмите на показатель, чтобы увидеть его график." />
        ) : null}

        {tab === 'photo' ? (
          <ProgressPhotoGallery key={userId} mode="manage" photos={profile.photos} loading={false} error={false} onRetry={() => void refetch()} onPhoto={() => setPhotoOpen(true)} onDelete={deletePhoto} />
        ) : null}

        {tab === 'restrictions' ? (
          <ProfilePanel title="Исключённые упражнения" description="Исключённые упражнения не предлагаются в рекомендациях. Нажмите карточку, чтобы изменить состояние.">
            {excludedExercises.length ? <div className="profile-restrictions">{excludedExercises.map((exercise) => <button key={exercise.slug} type="button" aria-pressed="true" onClick={() => toggleBlacklisted(exercise.slug)}><div className="profile-exercise-image">{exercise.imageUrl ? <img src={resolveApiAssetUrl(exercise.imageUrl) ?? exercise.imageUrl} alt="" /> : <span aria-hidden="true">{exercise.name.charAt(0)}</span>}</div><span><strong>{exercise.name}</strong><small>{exercise.muscles?.slice(0, 2).join(' · ') || 'Упражнение'}</small></span><em>Исключено · нажмите, чтобы разрешить</em></button>)}</div> : <ProfileEmpty text="Исключённых упражнений нет. Добавить ограничение можно из карточки упражнения в каталоге." />}
            {excludedExercises.length ? <p className="profile-restrictions-count">Исключено: {excludedExercises.length}</p> : null}
          </ProfilePanel>
        ) : null}
      </section>

      <EditProfileDialog open={editOpen} onOpenChange={setEditOpen} draft={editDraft} setDraft={setEditDraft} pending={pending} error={formError} onSave={saveProfile} />
      <MeasurementDialog open={measureOpen} onOpenChange={setMeasureOpen} userId={userId} measurements={profile.measurements} />
      <PhotoCaptureDialog open={photoOpen} onOpenChange={setPhotoOpen} userId={userId} />
      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}

function LatestPhotoPanel({ photos, onPhoto, onOpen }: { photos: Photo[]; onPhoto: () => void; onOpen: () => void }) {
  const latest = photos[0]
  const set = latest ? photoViews.map((view) => photos.find((photo) => photo.view === view.id && new Date(photo.takenAt).toDateString() === new Date(latest.takenAt).toDateString())) : []
  const ago = latest ? daysBetween(latest.takenAt) : 0
  return (
    <ProfilePanel className="profile-photo" title="Последнее фото" description={latest ? `${dateFormat.format(new Date(latest.takenAt))} · ${ago <= 0 ? 'сегодня' : `${ago} ${plural(ago, 'день', 'дня', 'дней')} назад`}` : 'Снимков пока нет'} action={<Button variant="secondary" iconLeft={<Camera aria-hidden="true" />} onClick={onPhoto}>Фотофиксация</Button>}>
      {latest ? (
        <>
          <div className="profile-photo-row">{set.map((photo, index) => <figure key={photoViews[index].id}>{photo ? <PhotoImage photo={photo} /> : <span className="profile-photo-missing">нет снимка</span>}<figcaption>{photoViews[index].label}</figcaption></figure>)}</div>
          {ago >= 21 ? <p className="profile-photo-nudge">Прошло больше трёх недель — сделайте новые снимки, чтобы сравнить изменения.</p> : null}
          <div className="profile-photo-links"><button type="button" className="profile-more" onClick={onOpen}>Все снимки<ChevronRight aria-hidden="true" /></button><Link className="profile-more" to="/progress?tab=photo">Сравнить до и после<ChevronRight aria-hidden="true" /></Link></div>
        </>
      ) : <ProfileEmpty icon={<Images aria-hidden="true" />} text="Сделайте снимки спереди, сзади и сбоку — через пару недель здесь можно будет увидеть изменения." />}
    </ProfilePanel>
  )
}

function TrainingPanel({ data, loading }: { data?: ProgressData; loading: boolean }) {
  const kpis = data?.insights?.kpis
  const value = (id: string) => kpis?.find((item) => item.id === id)?.value ?? 0
  const streak = data?.insights?.activity.streakWeeks ?? 0
  return (
    <ProfilePanel className="profile-training" title="Тренировки за 30 дней" action={<Link className="profile-more" to="/progress">Прогресс<ChevronRight aria-hidden="true" /></Link>}>
      {loading ? <p className="profile-muted" role="status">Загрузка…</p> : kpis ? (
        <dl className="profile-stat-grid">
          <div><dt><Dumbbell aria-hidden="true" />Тренировочных дней</dt><dd>{value('days')}</dd></div>
          <div><dt><Flame aria-hidden="true" />Недель подряд</dt><dd>{streak}</dd></div>
          <div><dt><Ruler aria-hidden="true" />Поднятый объём</dt><dd>{formatBody(value('volume'))} <small>кг</small></dd></div>
          <div><dt><Trophy aria-hidden="true" />Личных рекордов</dt><dd>{value('records')}</dd></div>
        </dl>
      ) : <ProfileEmpty text="Статистика тренировок появится после первой сохранённой тренировки." action={<Button asChild variant="secondary"><Link to="/dashboard">Выбрать тренировку</Link></Button>} />}
    </ProfilePanel>
  )
}

type TimelineEntry = { id: string; date: string; icon: ReactNode; title: string; text: string }

function TimelinePanel({ measurements, photos, training }: { measurements: BodyMeasurement[]; photos: Photo[]; training?: ProgressData }) {
  const entries: TimelineEntry[] = []
  const weighIns = new Map<string, BodyMeasurement[]>()
  for (const item of measurements) {
    const values = bodyMetrics.filter((metric) => item[metric.key] != null && Number(item[metric.key]) > 0)
    if (values.length === 1 && values[0].key === 'weightKg') {
      // Scales can log several weigh-ins a day; one line per day keeps the timeline readable.
      const key = new Date(item.measuredAt).toDateString()
      weighIns.set(key, [...(weighIns.get(key) ?? []), item])
    } else if (values.length) {
      entries.push({ id: `m${item.id}`, date: item.measuredAt, icon: <Ruler aria-hidden="true" />, title: 'Измерение тела', text: values.map((metric) => `${metric.label.toLowerCase()} ${formatBody(Number(item[metric.key]))} ${metric.unit}`).join(', ') })
    }
  }
  for (const [key, items] of weighIns) {
    const weights = items.map((item) => Number(item.weightKg))
    const range = Math.min(...weights) === Math.max(...weights) ? `${formatBody(weights[0])} кг` : `${formatBody(Math.min(...weights))}–${formatBody(Math.max(...weights))} кг`
    entries.push({ id: `w${key}`, date: items[0].measuredAt, icon: <Scale aria-hidden="true" />, title: items.length > 1 ? `Взвешивания · ${items.length}` : 'Взвешивание', text: range })
  }
  const sessions = new Map<string, Photo[]>()
  for (const photo of photos) { const key = new Date(photo.takenAt).toDateString(); sessions.set(key, [...(sessions.get(key) ?? []), photo]) }
  for (const [key, items] of sessions) entries.push({ id: `p${key}`, date: items[0].takenAt, icon: <Camera aria-hidden="true" />, title: 'Фотофиксация', text: `${items.length} ${plural(items.length, 'снимок', 'снимка', 'снимков')}: ${[...new Set(items.map((photo) => photoViews.find((view) => view.id === photo.view)!.label.toLowerCase()))].join(', ')}` })
  for (const record of training?.insights?.records ?? []) entries.push({ id: `r${record.exerciseSlug}${record.date}`, date: record.date, icon: <Trophy aria-hidden="true" />, title: 'Личный рекорд', text: `${record.exerciseName}: ${formatBody(record.e1rm)} кг расчётный максимум` })
  const recent = entries.sort((a, b) => Date.parse(b.date) - Date.parse(a.date)).slice(0, 6)
  return (
    <ProfilePanel className="profile-timeline" title="Хронология">
      {recent.length ? <ol className="profile-timeline-list">{recent.map((entry) => <li key={entry.id}><span className="profile-timeline-icon">{entry.icon}</span><div><b>{entry.title}</b><small>{entry.text}</small></div><time dateTime={entry.date}>{shortFormat.format(new Date(entry.date)).replace('.', '')}</time></li>)}</ol> : <ProfileEmpty text="История пока пуста" />}
    </ProfilePanel>
  )
}

function ProfilePanel({ title, description, action, children, className }: { title: string; description?: string; action?: ReactNode; children: ReactNode; className?: string }) { return <section className={`profile-panel${className ? ` ${className}` : ''}`}><header><div><h2>{title}</h2>{description ? <p>{description}</p> : null}</div>{action}</header>{children}</section> }
function ProfileEmpty({ text, action, icon }: { text: string; action?: ReactNode; icon?: ReactNode }) { return <div className="profile-empty">{icon ? <span className="profile-empty-icon">{icon}</span> : null}<p>{text}</p>{action}</div> }

function EditProfileDialog({ open, onOpenChange, draft, setDraft, pending, error, onSave }: { open: boolean; onOpenChange: (open: boolean) => void; draft: EditDraft | null; setDraft: Dispatch<SetStateAction<EditDraft | null>>; pending: boolean; error: string | null; onSave: () => Promise<void> }) {
  if (!draft) return null
  const field = (key: keyof EditDraft, label: string, type = 'text') => <label className="profile-field"><span>{label}</span><input type={type} value={draft[key]} onChange={(event) => setDraft((current) => current ? { ...current, [key]: event.target.value } : current)} /></label>
  return <Dialog.Root open={open} onOpenChange={(next) => { if (!pending) onOpenChange(next) }}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" /><SafetyDialogContent className="profile-dialog"><Dialog.Title className="font-display text-3xl font-bold">Редактировать профиль</Dialog.Title><Dialog.Description className="mt-2 text-sm text-white/60">Основные данные и ближайший измеримый ориентир.</Dialog.Description><div className="profile-form">{field('name', 'Имя')}{field('birthDate', 'Дата рождения', 'date')}{field('heightCm', 'Рост, см', 'number')}{field('weightKg', 'Вес, кг', 'number')}{field('goalLabel', 'Основная цель')}{field('targetValue', 'Целевое значение', 'number')}{field('targetUnit', 'Единица цели')}<label className="profile-field profile-field-wide"><span>Заметки</span><textarea value={draft.notes} onChange={(event) => setDraft((current) => current ? { ...current, notes: event.target.value } : current)} /></label></div>{error ? <p role="alert" className="text-[#ffb4a7]">{error}</p> : null}<div className="profile-dialog-actions"><Dialog.Close asChild><Button variant="secondary" disabled={pending}>Отмена</Button></Dialog.Close><Button disabled={pending || !draft.name.trim() || !draft.goalLabel.trim()} onClick={() => void onSave()}>{pending ? 'Сохранение…' : 'Сохранить'}</Button></div></SafetyDialogContent></Dialog.Portal></Dialog.Root>
}

function asTab(value: string | null): ProfileTab { return value === 'measurements' || value === 'photo' || value === 'restrictions' ? value : 'overview' }
function optionalNumber(value: string) { const parsed = Number(value.replace(',', '.')); return value.trim() && Number.isFinite(parsed) ? parsed : null }
function calculateAge(value: string | null | undefined) { if (!value) return null; const birth = new Date(`${value}T00:00:00`); const now = new Date(); let age = now.getFullYear() - birth.getFullYear(); if (now.getMonth() < birth.getMonth() || (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate())) age--; return age }
function plural(value: number, one: string, few: string, many: string) { const mod10 = value % 10; const mod100 = value % 100; if (mod10 === 1 && mod100 !== 11) return one; if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few; return many }
function humanizeSlug(slug: string) { return slug.split('-').map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' ') }
