import { Camera, CheckCircle2, ChevronLeft, Clock3, ScanLine, ShieldCheck } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { getRuntimeInitOptions, withSearch } from '@/features/runtime/lib/runtime-query'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { FilterChip, SectionIntro } from '@/shared/ui/stage2/screen-components'
import { useAppStore } from '@/stores/app-store'
import { useRuntimeStore } from '@/stores/runtime-store'

function getUserName(userId: string | null) {
  return userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
}

export function PhotoProgressScreen() {
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const session = useRuntimeStore((state) => state.session)
  const ensureSession = useRuntimeStore((state) => state.ensureSession)
  const completePhotoShot = useRuntimeStore((state) => state.completePhotoShot)
  const openPhotoProgress = useRuntimeStore((state) => state.openPhotoProgress)
  const continueAfterPhoto = useRuntimeStore((state) => state.continueAfterPhoto)
  const skipPhotoProgress = useRuntimeStore((state) => state.skipPhotoProgress)
  const setPhotoTimer = useRuntimeStore((state) => state.setPhotoTimer)
  const setView = useRuntimeStore((state) => state.setView)
  const hasSyncedSessionRef = useRef(false)

  const initOptions = getRuntimeInitOptions(searchParams)

  useEffect(() => {
    if (hasSyncedSessionRef.current) {
      return
    }

    if (!session) {
      ensureSession(initOptions)
      return
    }

    if (session.view !== 'photo-progress') {
      openPhotoProgress(initOptions.photoMode ?? 'manual')
    }

    hasSyncedSessionRef.current = true
  }, [ensureSession, initOptions, openPhotoProgress, session])

  if (!session) {
    return null
  }

  const photoState = session.photoProgress
  const currentShot = photoState.shots.find((shot) => shot.view === photoState.currentView) ?? photoState.shots[0]
  const readyShots = photoState.shots.filter((shot) => shot.status === 'ready').length
  const isPostWorkout = photoState.mode === 'post-workout'

  return (
    <FormaShell userName={getUserName(selectedUserId)} machine={session.machine} onStop={() => setEmergencyStopActive(true)}>
      <SectionIntro
        title={isPostWorkout ? 'Фото после тренировки' : photoState.mode === 'manual' ? 'Фото прогресса' : 'Фото до тренировки'}
        description={photoState.readyMessage}
        actions={
          <Button variant="ghost" iconLeft={<ChevronLeft className="h-4 w-4" />} onClick={() => navigate(-1)}>
            Назад
          </Button>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <section className="glass-panel rounded-[34px] p-6 xl:p-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="text-sm uppercase tracking-[0.24em] text-white/35">Текущий кадр</div>
              <div className="mt-2 font-display text-5xl font-bold text-white">{currentShot.title}</div>
              <div className="mt-2 max-w-2xl text-base leading-8 text-white/65">{currentShot.hint}</div>
            </div>
            <div className="rounded-[26px] border border-[#d6b05f]/18 bg-[#18140b] px-5 py-4 text-[#f2cf87]">
              <div className="text-xs uppercase tracking-[0.22em] text-[#f2cf87]/65">Готово</div>
              <div className="mt-2 font-display text-4xl font-bold">{readyShots}/{photoState.shots.length}</div>
            </div>
          </div>

          <div className="mt-6 rounded-[32px] border border-white/8 bg-[radial-gradient(circle_at_top,rgba(214,176,95,0.16),transparent_38%),linear-gradient(180deg,#171b22,#090c11)] p-6">
            <div className="flex min-h-[360px] flex-col items-center justify-center rounded-[28px] border border-dashed border-white/14 bg-black/20 text-center">
              <div className="inline-flex h-20 w-20 items-center justify-center rounded-full border border-white/10 bg-white/6 text-[#f2cf87]">
                <ScanLine className="h-10 w-10" />
              </div>
              <div className="mt-6 font-display text-4xl font-bold text-white">{currentShot.title}</div>
              <div className="mt-3 max-w-xl text-sm leading-7 text-white/58">Совместите силуэт в рамке, держите нейтральную стойку и сохраняйте освещение стабильным.</div>
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {[0, 3, 5, 10].map((value) => (
                  <FilterChip
                    key={value}
                    label={value === 0 ? 'Без таймера' : `${value} сек`}
                    active={photoState.timerSeconds === value}
                    onClick={() => setPhotoTimer(value as 3 | 5 | 10 | 0)}
                  />
                ))}
              </div>
              <div className="mt-8 flex flex-wrap justify-center gap-3">
                {!photoState.completed ? (
                  <Button iconLeft={<Camera className="h-4 w-4" />} onClick={() => completePhotoShot(currentShot.view)}>
                    Сделать снимок
                  </Button>
                ) : null}
                <Button
                  variant="secondary"
                  iconLeft={<Clock3 className="h-4 w-4" />}
                  onClick={() =>
                    photoState.completed
                      ? isPostWorkout
                        ? (setView('workout-summary'), navigate(withSearch('/workout-summary', location.search)))
                        : (continueAfterPhoto(), navigate(withSearch('/exercise-setup', location.search)))
                      : (skipPhotoProgress(), navigate(withSearch('/exercise-setup', location.search)))
                  }
                >
                  {photoState.completed ? (isPostWorkout ? 'Вернуться к итогу тренировки' : 'Продолжить к настройке') : 'Сделать позже'}
                </Button>
              </div>
            </div>
          </div>
        </section>

        <aside className="space-y-6">
          <section className="glass-panel rounded-[32px] p-5">
            <div className="font-display text-3xl font-bold text-white">Список кадров</div>
            <div className="mt-4 space-y-3">
              {photoState.shots.map((shot) => (
                <div key={shot.view} className="rounded-[24px] border border-white/8 bg-white/4 px-4 py-4 text-white/74">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="font-semibold text-white">{shot.title}</div>
                      <div className="mt-1 text-sm text-white/45">{shot.hint}</div>
                    </div>
                    {shot.status === 'ready' ? <CheckCircle2 className="h-5 w-5 text-[#92e09a]" /> : <Camera className="h-5 w-5 text-white/35" />}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="glass-panel rounded-[32px] p-5">
            <div className="flex items-center gap-3 text-[#92e09a]"><ShieldCheck className="h-5 w-5" />Приватность</div>
            <div className="mt-3 text-sm leading-7 text-white/65">{photoState.privacyNote}</div>
          </section>
        </aside>
      </div>

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}