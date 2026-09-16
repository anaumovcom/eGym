import * as Dialog from '@radix-ui/react-dialog'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Camera, Pencil, Plus, Trash2 } from 'lucide-react'
import { useMemo, useState, type Dispatch, type ReactNode, type SetStateAction } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { ExerciseCatalogResponse, ExerciseSummary } from '@/entities/exercise/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import { apiDelete, apiGet, apiPost, apiPut, resolveApiAssetUrl } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { PhotoCaptureDialog } from '@/shared/ui/photo/photo-capture-dialog'
import { useAppStore } from '@/stores/app-store'

type ProfileTab = 'overview' | 'measurements' | 'photo' | 'restrictions'
type CurrentUser = {
  id: string; name: string; readinessPercent: number
  profile: { birthDate: string | null; heightCm: number | null; weightKg: number | null; photoUrl: string | null; notes: string | null } | null
  goals: Array<{ id: number; goalType: string; label: string; targetValue: number | null; targetUnit: string | null; isPrimary: boolean }>
}
type Measurement = { id: number; measuredAt: string; weightKg: number | null; bodyFatPercent: number | null; chestCm: number | null; waistCm: number | null; hipsCm: number | null }
type Photo = { id: number; view: 'front' | 'side' | 'back'; takenAt: string; imageUrl: string; thumbnailUrl: string; width: number; height: number }
type ProfileData = { user: CurrentUser; measurements: Measurement[]; photos: Photo[]; exercises: ExerciseSummary[] }
type EditDraft = { name: string; birthDate: string; heightCm: string; weightKg: string; notes: string; goalLabel: string; goalType: string; targetValue: string; targetUnit: string }
type MeasurementDraft = { weightKg: string; bodyFatPercent: string; chestCm: string; waistCm: string; hipsCm: string }

const tabs: Array<{ id: ProfileTab; label: string }> = [
  { id: 'overview', label: 'Обзор' }, { id: 'measurements', label: 'Измерения' }, { id: 'photo', label: 'Фото' }, { id: 'restrictions', label: 'Ограничения' },
]
const fallbackMachine: MachineHealth = { machineState: 'ready', machineLabel: 'Загрузка статуса', leftDrive: 'connected', rightDrive: 'connected', safety: 'enabled', calibration: 'Проверка подключения...' }

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
  const [measurementDraft, setMeasurementDraft] = useState<MeasurementDraft>({ weightKg: '', bodyFatPercent: '', chestCm: '', waistCm: '', hipsCm: '' })
  const [pending, setPending] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [deletingPhotoId, setDeletingPhotoId] = useState<number | null>(null)

  const { data, isPending, error, refetch } = useQuery({
    queryKey: ['user-profile-screen', userId],
    enabled: userId !== 'guest',
    queryFn: async (): Promise<ProfileData> => {
      const [user, measurements, photos, catalog] = await Promise.all([
        apiGet<CurrentUser>('/api/users/current'),
        apiGet<{ measurements: Measurement[] }>(`/api/body-measurements?userId=${encodeURIComponent(userId)}`),
        apiGet<{ photos: Photo[] }>(`/api/photo-progress?userId=${encodeURIComponent(userId)}`),
        apiGet<ExerciseCatalogResponse>(`/api/exercises?userId=${encodeURIComponent(userId)}`),
      ])
      return {
        user,
        measurements: [...measurements.measurements].sort((left, right) => new Date(right.measuredAt).getTime() - new Date(left.measuredAt).getTime()),
        photos: [...photos.photos].sort((left, right) => new Date(right.takenAt).getTime() - new Date(left.takenAt).getTime()),
        exercises: catalog.items,
      }
    },
  })

  const guest = useMemo<ProfileData>(() => ({ user: { id: 'guest', name: 'Гость', readinessPercent: 0, profile: null, goals: [] }, measurements: [], photos: [], exercises: [] }), [])
  const profile = data ?? guest
  const primaryGoal = profile.user.goals.find((goal) => goal.isPrimary) ?? profile.user.goals[0]
  const latestMeasurement = profile.measurements[0]
  const latestPhotos = latestPhotoSet(profile.photos)
  const age = calculateAge(profile.user.profile?.birthDate)
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

  async function saveMeasurement() {
    if (pending) return
    setPending(true); setFormError(null)
    try {
      await apiPost('/api/body-measurements', { userId, measuredAt: new Date().toISOString(), ...Object.fromEntries(Object.entries(measurementDraft).map(([key, value]) => [key, optionalNumber(value)])) })
      await Promise.all([queryClient.invalidateQueries({ queryKey: ['user-profile-screen', userId] }), queryClient.invalidateQueries({ queryKey: ['progress-screen', userId] })])
      setMeasureOpen(false); setMeasurementDraft({ weightKg: '', bodyFatPercent: '', chestCm: '', waistCm: '', hipsCm: '' })
    } catch (saveError) { setFormError(saveError instanceof Error ? saveError.message : 'Не удалось сохранить измерение.') }
    finally { setPending(false) }
  }

  async function deletePhoto(id: number) {
    if (deletingPhotoId != null) return
    setDeletingPhotoId(id)
    try { await apiDelete(`/api/photo-progress/${id}?confirm=true`); await queryClient.invalidateQueries({ queryKey: ['user-profile-screen', userId] }) }
    finally { setDeletingPhotoId(null) }
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
            <p>{[age != null ? `${age} лет` : null, profile.user.profile?.heightCm ? `${profile.user.profile.heightCm} см` : null, profile.user.profile?.weightKg ? `${profile.user.profile.weightKg} кг` : null].filter(Boolean).join(' · ') || 'Персональные данные не заполнены'}</p>
            <div className="profile-goal"><span>Основная цель</span><strong>{primaryGoal?.label ?? 'Поддержание активности'}</strong><small>Ближайший ориентир: {target}</small></div>
          </div>
          <Button iconLeft={<Pencil aria-hidden="true" />} onClick={openEdit} disabled={userId === 'guest'}>Редактировать</Button>
        </header>

        <nav className="profile-tabs" aria-label="Разделы профиля">
          {tabs.map((item) => <button key={item.id} type="button" aria-current={tab === item.id ? 'page' : undefined} onClick={() => updateTab(item.id)}>{item.label}</button>)}
        </nav>

        {tab === 'overview' ? (
          <div className="profile-overview">
            <ProfilePanel title="Текущие показатели">
              <dl className="profile-metrics">
                <Metric label="Вес" value={profile.user.profile?.weightKg ? `${profile.user.profile.weightKg} кг` : '—'} />
                <Metric label="Талия" value={metric(latestMeasurement?.waistCm, 'см')} />
                <Metric label="Грудь" value={metric(latestMeasurement?.chestCm, 'см')} />
                <Metric label="Бёдра" value={metric(latestMeasurement?.hipsCm, 'см')} />
              </dl>
            </ProfilePanel>
            <ProfilePanel title="Изменения">
              {profile.measurements.length >= 2 ? <MeasurementChanges latest={profile.measurements[0]} first={profile.measurements.at(-1)!} /> : <ProfileEmpty text="Добавьте минимум два измерения, чтобы увидеть изменения." action={<Button variant="secondary" onClick={() => setMeasureOpen(true)}>Добавить измерение</Button>} />}
            </ProfilePanel>
            <ProfilePanel title="Последнее фото">
              {latestPhotos.length ? <div className="profile-photo-row">{latestPhotos.map((photo) => <img key={photo.id} src={resolveApiAssetUrl(photo.thumbnailUrl) ?? photo.thumbnailUrl} alt={viewLabel(photo.view)} />)}</div> : <ProfileEmpty text="Фото прогресса пока нет." action={<Button variant="secondary" iconLeft={<Camera aria-hidden="true" />} onClick={() => setPhotoOpen(true)}>Фотофиксация</Button>} />}
            </ProfilePanel>
            <ProfilePanel title="Краткая история">
              <ul className="profile-history">
                {profile.measurements.slice(0, 3).map((item) => <li key={item.id}><span>{formatDate(item.measuredAt)}</span><strong>{metric(item.weightKg, 'кг')}</strong></li>)}
                {profile.photos[0] ? <li><span>{formatDate(profile.photos[0].takenAt)}</span><strong>Фотофиксация</strong></li> : null}
                {!profile.measurements.length && !profile.photos.length ? <li><span>История пока пуста</span></li> : null}
              </ul>
            </ProfilePanel>
          </div>
        ) : null}

        {tab === 'measurements' ? (
          <ProfilePanel title="История измерений" action={<Button iconLeft={<Plus aria-hidden="true" />} onClick={() => setMeasureOpen(true)}>Добавить измерение</Button>}>
            {profile.measurements.length ? <div className="profile-measurements">{profile.measurements.map((item) => <div key={item.id}><strong>{formatDate(item.measuredAt)}</strong><span>{metric(item.weightKg, 'кг')}</span><span>Талия {metric(item.waistCm, 'см')}</span><span>Грудь {metric(item.chestCm, 'см')}</span><span>Бёдра {metric(item.hipsCm, 'см')}</span></div>)}</div> : <ProfileEmpty text="Измерений пока нет." action={<Button onClick={() => setMeasureOpen(true)}>Добавить первое измерение</Button>} />}
          </ProfilePanel>
        ) : null}

        {tab === 'photo' ? (
          <ProfilePanel title="Фото прогресса" action={<Button iconLeft={<Camera aria-hidden="true" />} onClick={() => setPhotoOpen(true)}>Фотофиксация</Button>}>
            {profile.photos.length ? <div className="profile-gallery">{profile.photos.map((photo) => <article key={photo.id}><img src={resolveApiAssetUrl(photo.thumbnailUrl) ?? photo.thumbnailUrl} alt={viewLabel(photo.view)} /><div><strong>{viewLabel(photo.view)}</strong><span>{formatDate(photo.takenAt)}</span></div><Button variant="secondary" iconLeft={<Trash2 aria-hidden="true" />} disabled={deletingPhotoId === photo.id} onClick={() => void deletePhoto(photo.id)}>Удалить</Button></article>)}</div> : <ProfileEmpty text="Сделайте первую фотофиксацию — снимки появятся здесь." action={<Button onClick={() => setPhotoOpen(true)}>Сделать фото</Button>} />}
          </ProfilePanel>
        ) : null}

        {tab === 'restrictions' ? (
          <ProfilePanel title="Исключённые упражнения" description="Исключённые упражнения не предлагаются в рекомендациях. Нажмите карточку, чтобы изменить состояние.">
            {excludedExercises.length ? <div className="profile-restrictions">{excludedExercises.map((exercise) => <button key={exercise.slug} type="button" aria-pressed="true" onClick={() => toggleBlacklisted(exercise.slug)}><div className="profile-exercise-image">{exercise.imageUrl ? <img src={resolveApiAssetUrl(exercise.imageUrl) ?? exercise.imageUrl} alt="" /> : <span aria-hidden="true">{exercise.name.charAt(0)}</span>}</div><span><strong>{exercise.name}</strong><small>{exercise.muscles?.slice(0, 2).join(' · ') || 'Упражнение'}</small></span><em>Исключено · нажмите, чтобы разрешить</em></button>)}</div> : <ProfileEmpty text="Исключённых упражнений нет. Добавить ограничение можно из карточки упражнения в каталоге." />}
            {excludedExercises.length ? <p className="profile-restrictions-count">Исключено: {excludedExercises.length}</p> : null}
          </ProfilePanel>
        ) : null}
      </section>

      <EditProfileDialog open={editOpen} onOpenChange={setEditOpen} draft={editDraft} setDraft={setEditDraft} pending={pending} error={formError} onSave={saveProfile} />
      <MeasurementDialog open={measureOpen} onOpenChange={setMeasureOpen} draft={measurementDraft} setDraft={setMeasurementDraft} pending={pending} error={formError} onSave={saveMeasurement} />
      <PhotoCaptureDialog open={photoOpen} onOpenChange={setPhotoOpen} userId={userId} />
      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}

function ProfilePanel({ title, description, action, children }: { title: string; description?: string; action?: ReactNode; children: ReactNode }) { return <section className="profile-panel"><header><div><h2>{title}</h2>{description ? <p>{description}</p> : null}</div>{action}</header>{children}</section> }
function Metric({ label, value }: { label: string; value: string }) { return <div><dt>{label}</dt><dd>{value}</dd></div> }
function ProfileEmpty({ text, action }: { text: string; action?: ReactNode }) { return <div className="profile-empty"><p>{text}</p>{action}</div> }
function MeasurementChanges({ latest, first }: { latest: Measurement; first: Measurement }) { const rows: Array<[string, number | null, number | null, string]> = [['Вес', latest.weightKg, first.weightKg, 'кг'], ['Талия', latest.waistCm, first.waistCm, 'см'], ['Грудь', latest.chestCm, first.chestCm, 'см']]; return <dl className="profile-changes">{rows.map(([label, now, before, unit]) => <div key={label}><dt>{label}</dt><dd>{now != null && before != null ? `${(now - before) >= 0 ? '+' : ''}${(now - before).toFixed(1)} ${unit}` : '—'}</dd></div>)}</dl> }

function EditProfileDialog({ open, onOpenChange, draft, setDraft, pending, error, onSave }: { open: boolean; onOpenChange: (open: boolean) => void; draft: EditDraft | null; setDraft: Dispatch<SetStateAction<EditDraft | null>>; pending: boolean; error: string | null; onSave: () => Promise<void> }) {
  if (!draft) return null
  const field = (key: keyof EditDraft, label: string, type = 'text') => <label className="profile-field"><span>{label}</span><input type={type} value={draft[key]} onChange={(event) => setDraft((current) => current ? { ...current, [key]: event.target.value } : current)} /></label>
  return <Dialog.Root open={open} onOpenChange={(next) => { if (!pending) onOpenChange(next) }}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" /><SafetyDialogContent className="profile-dialog"><Dialog.Title className="font-display text-3xl font-bold">Редактировать профиль</Dialog.Title><Dialog.Description className="mt-2 text-sm text-white/60">Основные данные и ближайший измеримый ориентир.</Dialog.Description><div className="profile-form">{field('name', 'Имя')}{field('birthDate', 'Дата рождения', 'date')}{field('heightCm', 'Рост, см', 'number')}{field('weightKg', 'Вес, кг', 'number')}{field('goalLabel', 'Основная цель')}{field('targetValue', 'Целевое значение', 'number')}{field('targetUnit', 'Единица цели')}<label className="profile-field profile-field-wide"><span>Заметки</span><textarea value={draft.notes} onChange={(event) => setDraft((current) => current ? { ...current, notes: event.target.value } : current)} /></label></div>{error ? <p role="alert" className="text-[#ffb4a7]">{error}</p> : null}<div className="profile-dialog-actions"><Dialog.Close asChild><Button variant="secondary" disabled={pending}>Отмена</Button></Dialog.Close><Button disabled={pending || !draft.name.trim() || !draft.goalLabel.trim()} onClick={() => void onSave()}>{pending ? 'Сохранение…' : 'Сохранить'}</Button></div></SafetyDialogContent></Dialog.Portal></Dialog.Root>
}

function MeasurementDialog({ open, onOpenChange, draft, setDraft, pending, error, onSave }: { open: boolean; onOpenChange: (open: boolean) => void; draft: MeasurementDraft; setDraft: Dispatch<SetStateAction<MeasurementDraft>>; pending: boolean; error: string | null; onSave: () => Promise<void> }) {
  const labels: Record<keyof MeasurementDraft, string> = { weightKg: 'Вес, кг', bodyFatPercent: 'Жир, %', chestCm: 'Грудь, см', waistCm: 'Талия, см', hipsCm: 'Бёдра, см' }
  return <Dialog.Root open={open} onOpenChange={(next) => { if (!pending) onOpenChange(next) }}><Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" /><SafetyDialogContent className="profile-dialog"><Dialog.Title className="font-display text-3xl font-bold">Новое измерение</Dialog.Title><Dialog.Description className="mt-2 text-sm text-white/60">Заполните доступные значения. Пустые поля не сохраняются.</Dialog.Description><div className="profile-form">{(Object.keys(labels) as Array<keyof MeasurementDraft>).map((key) => <label key={key} className="profile-field"><span>{labels[key]}</span><input type="number" step="0.1" value={draft[key]} onChange={(event) => setDraft((current) => ({ ...current, [key]: event.target.value }))} /></label>)}</div>{error ? <p role="alert" className="text-[#ffb4a7]">{error}</p> : null}<div className="profile-dialog-actions"><Dialog.Close asChild><Button variant="secondary" disabled={pending}>Отмена</Button></Dialog.Close><Button disabled={pending || !Object.values(draft).some(Boolean)} onClick={() => void onSave()}>{pending ? 'Сохранение…' : 'Сохранить измерение'}</Button></div></SafetyDialogContent></Dialog.Portal></Dialog.Root>
}

function asTab(value: string | null): ProfileTab { return value === 'measurements' || value === 'photo' || value === 'restrictions' ? value : 'overview' }
function optionalNumber(value: string) { const parsed = Number(value.replace(',', '.')); return value.trim() && Number.isFinite(parsed) ? parsed : null }
function calculateAge(value: string | null | undefined) { if (!value) return null; const birth = new Date(`${value}T00:00:00`); const now = new Date(); let age = now.getFullYear() - birth.getFullYear(); if (now.getMonth() < birth.getMonth() || (now.getMonth() === birth.getMonth() && now.getDate() < birth.getDate())) age--; return age }
function metric(value: number | null | undefined, unit: string) { return value != null && value > 0 ? `${value} ${unit}` : '—' }
function formatDate(value: string) { return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value)) }
function latestPhotoSet(photos: Photo[]) { if (!photos.length) return []; const date = photos[0].takenAt.slice(0, 10); return photos.filter((photo) => photo.takenAt.startsWith(date)).slice(0, 3) }
function viewLabel(view: Photo['view']) { return view === 'front' ? 'Спереди' : view === 'side' ? 'Сбоку' : 'Сзади' }
function humanizeSlug(slug: string) { return slug.split('-').map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' ') }
