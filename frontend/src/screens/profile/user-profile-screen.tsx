import { useQuery } from '@tanstack/react-query'
import { Camera, Check, Pencil, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { ExerciseCatalogResponse } from '@/entities/exercise/model/types'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { ProfileTab } from '@/entities/stage4/model/types'
import type { UserProfileData } from '@/entities/stage4/model/types'
import { apiGet } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { Panel, PhotoPreviewCard, SectionTitle, TabStrip } from '@/shared/ui/stage4/screen-components'
import { useAppStore } from '@/stores/app-store'

type CurrentUserResponse = {
  id: string
  name: string
  role: string
  readinessPercent: number
  accent: 'gold' | 'green'
  profile: {
    birthDate: string | null
    heightCm: number | null
    weightKg: number | null
    photoUrl: string | null
    notes: string | null
  } | null
  goals: Array<{
    id: number
    goalType: string
    label: string
    targetValue: number | null
    targetUnit: string | null
    isPrimary: boolean
  }>
}

type BodyMeasurementsResponse = {
  measurements: Array<{
    id: number
    measuredAt: string
    weightKg: number | null
    bodyFatPercent: number | null
    chestCm: number | null
    waistCm: number | null
    hipsCm: number | null
  }>
}

type ProgressPhotosResponse = {
  photos: Array<{
    id: number
    mode: string
    view: 'front' | 'side' | 'back'
    takenAt: string
    imageUrl: string
    thumbnailUrl: string
    width: number
    height: number
    note: string | null
  }>
}

type AchievementsResponse = {
  achievements: Array<{
    id: string
    title: string
    description: string
    unlocked: boolean
    unlockedAt: string | null
  }>
}

const profileTabs: Array<{ id: ProfileTab; label: string }> = [
  { id: 'summary', label: 'Сводка' },
  { id: 'general', label: 'Общее' },
  { id: 'goals', label: 'Цели' },
  { id: 'body', label: 'Данные тела' },
  { id: 'photo', label: 'Фото прогресса' },
  { id: 'blacklist', label: 'Чёрный список упражнений' },
]

function formatDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }).format(new Date(value))
}

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value))
}

function buildGuestProfile(): UserProfileData {
  return {
    id: 'guest',
    name: 'Гость',
    avatarLabel: 'Г',
    goal: 'Ознакомительный режим',
    heightCm: 0,
    weightKg: 0,
    level: 'не задан',
    email: '',
    notes: '',
    locale: 'Русский',
    units: 'kg / cm',
    theme: 'Тёмная',
    createdAt: 'Сегодня',
    trainingFrequency: 'не задано',
    workoutDuration: 'не задано',
    workoutStyle: 'ознакомительный режим',
    autoPrograms: false,
    priorityMuscles: [],
    considerationNotes: ['Выберите пользователя, чтобы загрузить персональные данные и историю.'],
    bodyMeasurements: [],
    photos: [],
  }
}

function buildProfileData(currentUser: CurrentUserResponse, measurements: BodyMeasurementsResponse['measurements'], photos: ProgressPhotosResponse['photos'], achievements: AchievementsResponse['achievements']): UserProfileData {
  const sortedMeasurements = [...measurements].sort((left, right) => new Date(right.measuredAt).getTime() - new Date(left.measuredAt).getTime())
  const unlockedAchievements = achievements.filter((item) => item.unlocked)
  const groupedPhotos = new Map<string, { id: string; date: string; views: Array<{ id: 'front' | 'side' | 'back'; label: string }> }>()

  photos.forEach((photo) => {
    const key = formatDate(photo.takenAt)
    const existing = groupedPhotos.get(key) ?? { id: String(photo.id), date: key, views: [] }
    if (!existing.views.some((item) => item.id === photo.view)) {
      existing.views.push({
        id: photo.view,
        label: photo.view === 'front' ? 'Спереди' : photo.view === 'side' ? 'Сбоку' : 'Сзади',
      })
    }
    groupedPhotos.set(key, existing)
  })

  const primaryGoal = currentUser.goals.find((item) => item.isPrimary) ?? currentUser.goals[0]
  const latestMeasurement = sortedMeasurements[0]
  const avatarLabel = currentUser.name.trim().charAt(0).toUpperCase() || 'П'
  const readiness = currentUser.readinessPercent
  const level = readiness >= 80 ? 'продвинутый' : readiness >= 55 ? 'средний' : 'начальный'
  const createdAt = sortedMeasurements.at(-1)?.measuredAt ?? photos.at(-1)?.takenAt ?? new Date().toISOString()

  return {
    id: currentUser.id,
    name: currentUser.name,
    avatarLabel,
    goal: primaryGoal?.label ?? 'Поддержание активности',
    heightCm: currentUser.profile?.heightCm ?? 0,
    weightKg: currentUser.profile?.weightKg ?? latestMeasurement?.weightKg ?? 0,
    level,
    email: '',
    notes: currentUser.profile?.notes ?? '',
    locale: 'Русский',
    units: 'kg / cm',
    theme: 'Тёмная',
    createdAt: formatDate(createdAt),
    trainingFrequency: unlockedAchievements.length > 0 ? `${Math.max(unlockedAchievements.length, 1)} активных вех` : 'недостаточно данных',
    workoutDuration: latestMeasurement ? '45 минут' : 'не задано',
    workoutStyle: primaryGoal?.label ?? 'индивидуальный режим',
    autoPrograms: currentUser.id !== 'guest',
    priorityMuscles: primaryGoal?.label.toLowerCase().includes('сила') ? ['Спина', 'Грудь'] : primaryGoal?.label.toLowerCase().includes('актив') ? ['Ноги', 'Кор'] : [],
    considerationNotes: unlockedAchievements.length > 0 ? unlockedAchievements.slice(0, 3).map((item) => item.title) : ['Недостаточно истории для персональных рекомендаций.'],
    bodyMeasurements: sortedMeasurements.map((item) => ({
      date: formatShortDate(item.measuredAt),
      weight: item.weightKg ?? 0,
      waistCm: item.waistCm ?? 0,
      chestCm: item.chestCm ?? 0,
      hipsCm: item.hipsCm ?? 0,
      shouldersCm: 0,
      bicepsCm: 0,
    })),
    photos: Array.from(groupedPhotos.values()),
  }
}

function formatMetric(value: number, suffix: string) {
  return value > 0 ? `${value} ${suffix}` : '—'
}

function asProfileTab(value: string | null): ProfileTab {
  if (value === 'summary' || value === 'general' || value === 'goals' || value === 'body' || value === 'photo' || value === 'blacklist') {
    return value
  }

  return 'summary'
}

export function UserProfileScreen() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const blacklistedExerciseSlugs = useAppStore((state) => state.blacklistedExerciseSlugs)
  const toggleBlacklistedExercise = useAppStore((state) => state.toggleBlacklistedExercise)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const tab = asProfileTab(searchParams.get('tab'))
  const resolvedUserId = selectedUserId ?? 'alexey'
  const userName = resolvedUserId === 'elena' ? 'Елена' : resolvedUserId === 'guest' ? 'Гость' : 'Алексей'
  const fallbackMachine: MachineHealth = {
    machineState: 'ready',
    machineLabel: 'Загрузка статуса',
    leftDrive: 'connected',
    rightDrive: 'connected',
    safety: 'enabled',
    calibration: 'Проверка подключения...',
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ['user-profile-screen', resolvedUserId],
    enabled: resolvedUserId !== 'guest',
    queryFn: async () => {
      const [currentUser, measurements, photos, achievements, catalog] = await Promise.all([
        apiGet<CurrentUserResponse>('/api/users/current'),
        apiGet<BodyMeasurementsResponse>(`/api/body-measurements?userId=${encodeURIComponent(resolvedUserId)}`),
        apiGet<ProgressPhotosResponse>(`/api/photo-progress?userId=${encodeURIComponent(resolvedUserId)}`),
        apiGet<AchievementsResponse>(`/api/achievements?userId=${encodeURIComponent(resolvedUserId)}`),
        apiGet<ExerciseCatalogResponse>(`/api/exercises?userId=${encodeURIComponent(resolvedUserId)}`),
      ])

      return {
        profile: buildProfileData(currentUser, measurements.measurements, photos.photos, achievements.achievements),
        exerciseChoices: catalog.items.map((exercise) => ({ slug: exercise.slug, name: exercise.name, secondaryName: exercise.secondaryName })),
      }
    },
  })

  const guestProfile = useMemo(() => buildGuestProfile(), [])
  const [profileOverride, setProfileOverride] = useState<UserProfileData | null>(null)
  const [profileDraft, setProfileDraft] = useState<UserProfileData | null>(null)

  useEffect(() => {
    setProfileOverride(null)
    setProfileDraft(null)
  }, [resolvedUserId])

  const profile = profileOverride ?? data?.profile ?? guestProfile
  const exerciseChoices = data?.exerciseChoices ?? []

  const viewProfile = profileDraft ?? profile
  const editing = Boolean(profileDraft)
  const latestMeasurement = viewProfile.bodyMeasurements[0]

  function startProfileEdit() {
    setProfileDraft(structuredClone(viewProfile))
  }

  function updateProfileDraft<K extends keyof UserProfileData>(key: K, value: UserProfileData[K]) {
    setProfileDraft((state) => (state ? { ...state, [key]: value } : state))
  }

  function saveProfileDraft() {
    if (!profileDraft) {
      return
    }

    setProfileOverride(structuredClone(profileDraft))
    setProfileDraft(null)
  }

  function cancelProfileEdit() {
    setProfileDraft(null)
  }

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

  if ((isLoading && resolvedUserId !== 'guest') || !viewProfile) {
    return (
      <FormaShell userName={userName} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
        <div className="glass-panel rounded-[34px] p-8 text-white/72">Загрузка профиля…</div>
      </FormaShell>
    )
  }

  if (error && resolvedUserId !== 'guest') {
    return (
      <FormaShell userName={userName} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
        <div className="glass-panel rounded-[34px] border border-[#eb5345]/25 bg-[#1b0f10] p-8 text-[#ffb4a7]">Не удалось загрузить профиль пользователя. Проверьте backend API.</div>
      </FormaShell>
    )
  }

  return (
    <FormaShell userName={userName} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
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
                ['Рекомендация', viewProfile.considerationNotes[0] ?? 'Нет персональной рекомендации'],
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
                ['Плечи', formatMetric(latestMeasurement.shouldersCm, 'см')],
                ['Бицепс', formatMetric(latestMeasurement.bicepsCm, 'см')],
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
                  <span>{formatMetric(item.weight, 'кг')}</span>
                  <span>{formatMetric(item.waistCm, 'см')}</span>
                  <span>{formatMetric(item.chestCm, 'см')}</span>
                  <span>{formatMetric(item.hipsCm, 'см')}</span>
                  <span>{formatMetric(item.bicepsCm, 'см')}</span>
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