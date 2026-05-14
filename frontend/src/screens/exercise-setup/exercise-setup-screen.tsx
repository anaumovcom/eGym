import { ArrowLeft, Camera, Play } from 'lucide-react'
import { useEffect } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { getRuntimeInitOptions, withSearch } from '@/features/runtime/lib/runtime-query'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { WarningBanner } from '@/shared/ui/status/status-components'
import { CalibrationStatusBlock, LoadSettingsControl, MuscleStatusList, SectionIntro } from '@/shared/ui/stage2/screen-components'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

export function ExerciseSetupScreen() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const session = useRuntimeStore((state) => state.session)
  const ensureSession = useRuntimeStore((state) => state.ensureSession)
  const updateCalibrationState = useRuntimeStore((state) => state.updateCalibrationState)
  const updateLoadSettings = useRuntimeStore((state) => state.updateLoadSettings)
  const openPhotoProgress = useRuntimeStore((state) => state.openPhotoProgress)
  const startExercise = useRuntimeStore((state) => state.startExercise)
  const completeWorkout = useRuntimeStore((state) => state.completeWorkout)

  const initOptions = getRuntimeInitOptions(searchParams)

  useEffect(() => {
    ensureSession(initOptions)
  }, [ensureSession, initOptions])

  useEffect(() => {
    if (session?.view === 'photo-progress' && session.photoProgress.autoPrompt && !session.photoProgress.completed) {
      navigate(withSearch('/photo-progress', location.search), { replace: true })
    }
  }, [location.search, navigate, session])

  if (!session) {
    return null
  }

  const exercise = session.exercises.find((item) => item.id === session.currentExerciseId) ?? session.exercises[0]
  const settings = exercise.loadSettings
  const startBlocked = exercise.kind === 'machine' && exercise.calibrationState === 'missing'

  return (
    <FormaShell userName={getUserName(selectedUserId)} machine={session.machine} onStop={() => setEmergencyStopActive(true)}>
      <SectionIntro
        title="Настройка упражнения"
        description="Подтвердите параметры перед стартом, проверьте калибровку и при необходимости сделайте фотофиксацию перед упражнением."
        actions={
          <Button variant="ghost" iconLeft={<ArrowLeft className="h-4 w-4" />} onClick={() => navigate(-1)}>
            Назад
          </Button>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <section className="glass-panel rounded-[34px] p-6 xl:p-8">
          <div className="text-sm uppercase tracking-[0.24em] text-white/35">Выбранное упражнение</div>
          <div className="mt-2 font-display text-5xl font-bold text-white">{exercise.name}</div>
          <div className="mt-2 text-2xl text-white/45">{exercise.secondaryName}</div>
          <div className="mt-5 flex flex-wrap gap-2">
            {exercise.muscles.map((item) => (
              <span key={item} className="inline-flex items-center rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-white/68">{item}</span>
            ))}
          </div>
          <div className="mt-6 rounded-[30px] border border-white/8 bg-[radial-gradient(circle_at_top,rgba(214,176,95,0.18),transparent_35%),linear-gradient(180deg,#161b22,#0a0c0f)] p-6 text-white/62">
            {exercise.kind === 'machine'
              ? 'Для тренажёрного упражнения важно проверить сохранённую амплитуду и только потом переходить к выполнению.'
              : exercise.kind === 'timed'
                ? 'Для упражнения на время калибровка не требуется. Важнее выбрать удобный режим и убедиться, что таймер вас не будет отвлекать.'
                : 'Для упражнения без тренажёра можно сразу переходить к выполнению. При желании сохраните фото до старта.'}
          </div>

          {session.photoProgress.completed ? <WarningBanner title="Фото сохранены" description="Фотофиксация перед тренировкой завершена, можно запускать упражнение." /> : null}
          {startBlocked ? <WarningBanner title="Нужна калибровка" description="Для тренажёрного упражнения старт заблокирован, пока не будет сохранена амплитуда движения." /> : null}

          <div className="mt-6 space-y-5">
            <LoadSettingsControl
              settings={settings}
              onAdjustWeight={(delta) => updateLoadSettings({ weight: Math.max(0, settings.weight + delta) })}
              onAdjustSets={(delta) => updateLoadSettings({ sets: Math.max(1, settings.sets + delta) })}
              onAdjustReps={(delta) => updateLoadSettings({ reps: Math.max(1, settings.reps + delta) })}
              onAdjustRest={(delta) => updateLoadSettings({ restSeconds: Math.max(15, settings.restSeconds + delta) })}
              onModeChange={(mode) => updateLoadSettings({ mode })}
            />
            <CalibrationStatusBlock calibration={settings.calibration} />
            <div className="flex flex-wrap gap-3">
              <Button variant={exercise.calibrationState === 'saved' ? 'primary' : 'secondary'} onClick={() => updateCalibrationState('saved')}>
                Амплитуда сохранена
              </Button>
              <Button variant={exercise.calibrationState === 'missing' ? 'primary' : 'secondary'} onClick={() => updateCalibrationState('missing')}>
                Нет калибровки
              </Button>
              <Button variant={exercise.calibrationState === 'not-needed' ? 'primary' : 'secondary'} onClick={() => updateCalibrationState('not-needed')}>
                Не требуется
              </Button>
            </div>
          </div>
        </section>

        <aside className="space-y-6">
          <section className="glass-panel rounded-[32px] p-5">
            <div className="font-display text-3xl font-bold text-white">Проверка совместимости</div>
            <div className="mt-4 rounded-[24px] border border-[#d6b05f]/18 bg-[#18140b] p-4 text-[#f2cf87]">
              <div className="font-semibold">{exercise.details.compatibility.title}</div>
              <div className="mt-2 text-sm leading-7">{exercise.details.compatibility.description}</div>
            </div>
            <div className="mt-4">
              <MuscleStatusList muscles={exercise.details.compatibility.affectedMuscles} />
            </div>
            <div className="mt-5 flex flex-col gap-3">
              <Button variant="secondary" iconLeft={<Camera className="h-4 w-4" />} onClick={() => {
                openPhotoProgress(session.photoProgress.mode === 'post-workout' ? 'manual' : session.photoProgress.mode || 'manual')
                navigate(withSearch('/photo-progress', location.search))
              }}>
                Фотофиксация
              </Button>
              <Button className="w-full" disabled={startBlocked} iconLeft={<Play className="h-4 w-4" />} onClick={() => {
                startExercise()
                navigate(withSearch('/exercise-session', location.search))
              }}>
                {startBlocked ? 'Старт недоступен' : 'Запустить упражнение'}
              </Button>
            </div>
          </section>

          <section className="glass-panel rounded-[32px] p-5">
            <div className="font-display text-3xl font-bold text-white">Текущий сценарий</div>
            <div className="mt-4 space-y-3 text-sm text-white/72">
              <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Источник</span><span>{session.source}</span></div>
              <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Режим</span><span>{exercise.kind}</span></div>
              <div className="flex items-center justify-between rounded-2xl border border-white/8 bg-white/4 px-4 py-3"><span>Диапазон</span><span>{exercise.movementRangeLabel}</span></div>
            </div>
            <Button className="mt-5 w-full" variant="secondary" onClick={() => {
              completeWorkout('aborted')
              navigate(withSearch('/workout-summary', location.search))
            }}>
              Завершить тренировку сейчас
            </Button>
          </section>
        </aside>
      </div>

      <EmergencyStopOverlay
        open={emergencyStopActive}
        onOpenChange={setEmergencyStopActive}
        actionLabel="Завершить тренировку как прерванную"
        onAction={() => {
          completeWorkout('aborted')
          setEmergencyStopActive(false)
          navigate(withSearch('/workout-summary', location.search))
        }}
      />
    </FormaShell>
  )
}