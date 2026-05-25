import { useQueryClient } from '@tanstack/react-query'
import { Camera, CheckCircle2, ChevronLeft, ChevronRight, RefreshCcw, ScanLine, TimerReset } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import type { RuntimePhotoView } from '@/entities/runtime/model/types'
import { getRuntimeInitOptions, withSearch } from '@/features/runtime/lib/runtime-query'
import { resolveApiAssetUrl } from '@/shared/api/client'
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
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const resolvedUserId = selectedUserId ?? 'alexey'
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
  const captureSequenceRef = useRef(0)
  const webcamVideoRef = useRef<HTMLVideoElement | null>(null)
  const fullscreenVideoRef = useRef<HTMLVideoElement | null>(null)
  const webcamStreamRef = useRef<MediaStream | null>(null)
  const [webcamError, setWebcamError] = useState<string | null>(null)
  const [countdownValue, setCountdownValue] = useState<number | null>(null)
  const [countdownShotView, setCountdownShotView] = useState<RuntimePhotoView | null>(null)
  const [sequenceQueue, setSequenceQueue] = useState<RuntimePhotoView[]>([])
  const [captureInFlight, setCaptureInFlight] = useState(false)

  const initOptions = useMemo(() => getRuntimeInitOptions(searchParams), [searchParams])
  const usesBackendBuilderSession = initOptions.source === 'builder' && Boolean(initOptions.programId)
  const sessionId = session?.id
  const photoState = session?.photoProgress
  const currentShot = photoState?.shots.find((shot) => shot.view === photoState.currentView) ?? photoState?.shots[0] ?? null
  const activeCountdownShot = photoState?.shots.find((shot) => shot.view === countdownShotView) ?? currentShot
  const readyShots = photoState?.shots.filter((shot) => shot.status === 'ready').length ?? 0
  const isPostWorkout = photoState?.mode === 'post-workout'
  const photoTimerSeconds = photoState?.timerSeconds ?? 0
  const photoShotsKey = photoState?.shots.map((shot) => `${shot.view}:${shot.status}:${shot.imageUrl ?? ''}`).join('|') ?? ''
  const countdownOpen = countdownValue != null
  const sequenceMode = sequenceQueue.length > 0

  useEffect(() => {
    if (hasSyncedSessionRef.current) {
      return
    }

    if (!session) {
      if (usesBackendBuilderSession) {
        navigate(withSearch('/exercise-setup', location.search), { replace: true })
        return
      }

      ensureSession(initOptions)
      return
    }

    if (session.view !== 'photo-progress') {
      openPhotoProgress(initOptions.photoMode ?? 'manual')
    }

    hasSyncedSessionRef.current = true
  }, [ensureSession, initOptions, location.search, navigate, openPhotoProgress, session, usesBackendBuilderSession])

  useEffect(() => {
    if (!sessionId) {
      return
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      setWebcamError('Браузер не поддерживает доступ к веб-камере.')
      return
    }

    let cancelled = false
    setWebcamError(null)

    void navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: 'user',
        width: { ideal: 1280 },
        height: { ideal: 720 },
        aspectRatio: { ideal: 16 / 9 },
      },
      audio: false,
    })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop())
          return
        }

        webcamStreamRef.current = stream
        attachStreamToVideo(webcamVideoRef.current, stream)
      })
      .catch(() => {
        if (!cancelled) {
          setWebcamError('Не удалось открыть веб-камеру. Разрешите доступ к камере и обновите экран.')
        }
      })

    return () => {
      cancelled = true
      webcamStreamRef.current?.getTracks().forEach((track) => track.stop())
      webcamStreamRef.current = null
    }
  }, [sessionId])

  useEffect(() => {
    if (!countdownOpen || !fullscreenVideoRef.current || !webcamStreamRef.current) {
      return
    }

    attachStreamToVideo(fullscreenVideoRef.current, webcamStreamRef.current)
  }, [countdownOpen])

  useEffect(() => {
    if (!photoState || countdownValue == null || !countdownShotView || captureInFlight) {
      return
    }

    if (countdownValue <= 0) {
      const targetView = countdownShotView
      const takenAtIso = new Date().toISOString()
      const captureSequenceId = captureSequenceRef.current
      const imageDataUrl = captureFrameFromVideo(webcamVideoRef.current ?? fullscreenVideoRef.current)
      const [nextQueuedView, ...remainingQueue] = sequenceQueue

      if (!imageDataUrl) {
        setWebcamError('Не удалось получить кадр с веб-камеры.')
        setCountdownValue(null)
        setCountdownShotView(null)
        setSequenceQueue([])
        return
      }

      completePhotoShot(targetView, imageDataUrl, formatTakenAt(takenAtIso))
      setCountdownValue(null)
      setCaptureInFlight(true)

      void (async () => {
        try {
          await uploadProgressPhoto({
            userId: resolvedUserId,
            mode: photoState.mode,
            view: targetView,
            takenAtIso,
            imageDataUrl,
          })

          await Promise.all([
            queryClient.invalidateQueries({ queryKey: ['user-profile-screen', resolvedUserId] }),
            queryClient.invalidateQueries({ queryKey: ['progress-screen', resolvedUserId] }),
          ])

          if (captureSequenceRef.current !== captureSequenceId) {
            return
          }

          setCaptureInFlight(false)

          if (nextQueuedView) {
            setSequenceQueue(remainingQueue)
            setCountdownShotView(nextQueuedView)
            setCountdownValue(photoTimerSeconds)
            return
          }

          setCountdownShotView(null)
          setSequenceQueue([])
        } catch (error) {
          if (captureSequenceRef.current !== captureSequenceId) {
            return
          }

          setCaptureInFlight(false)
          setWebcamError(error instanceof Error ? error.message : 'Не удалось сохранить снимок на backend.')
          setCountdownShotView(null)
          setSequenceQueue([])
        }
      })()

      return
    }

    const timeoutId = window.setTimeout(() => {
      setCountdownValue((current) => (current == null ? current : current - 1))
    }, 1000)

    return () => window.clearTimeout(timeoutId)
  }, [captureInFlight, completePhotoShot, countdownShotView, countdownValue, photoShotsKey, photoState, photoTimerSeconds, queryClient, resolvedUserId, sequenceQueue])

  if (!session || !photoState || !currentShot) {
    return null
  }

  function captureFrameFromVideo(video: HTMLVideoElement | null) {
    if (!video || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
      return null
    }

    const width = 1280
    const height = 720
    const sourceWidth = video.videoWidth || width
    const sourceHeight = video.videoHeight || height
    const sourceAspect = sourceWidth / sourceHeight
    const targetAspect = width / height
    let sx = 0
    let sy = 0
    let sw = sourceWidth
    let sh = sourceHeight

    if (sourceAspect > targetAspect) {
      sw = sourceHeight * targetAspect
      sx = (sourceWidth - sw) / 2
    } else if (sourceAspect < targetAspect) {
      sh = sourceWidth / targetAspect
      sy = (sourceHeight - sh) / 2
    }

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const context = canvas.getContext('2d')

    if (!context) {
      return null
    }

    context.drawImage(video, sx, sy, sw, sh, 0, 0, width, height)
    return canvas.toDataURL('image/jpeg', 0.92)
  }

  function startCountdown(view: RuntimePhotoView) {
    setCountdownShotView(view)
    setCountdownValue(photoTimerSeconds)
  }

  function handleTakePhoto() {
    if (captureInFlight) {
      return
    }

    const pendingViews = photoState.shots.filter((shot) => shot.status !== 'ready').map((shot) => shot.view)
    const [firstView, ...remainingViews] = pendingViews.length > 0 ? pendingViews : [currentShot.view]

    setSequenceQueue(remainingViews)
    startCountdown(firstView)
  }

  function handleRetakeShot(view: RuntimePhotoView) {
    if (captureInFlight) {
      return
    }

    setSequenceQueue([])
    startCountdown(view)
  }

  function handleResetPhotos() {
    if (!photoState) {
      return
    }

    captureSequenceRef.current += 1
    setCountdownValue(null)
    setCountdownShotView(null)
    setSequenceQueue([])
    setCaptureInFlight(false)
    setWebcamError(null)
    openPhotoProgress(photoState.mode)
  }

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

      <div className="grid gap-5 xl:h-[calc(100vh-228px)] xl:grid-cols-[minmax(0,1fr)_360px]">
        <section className="glass-panel relative flex min-h-0 flex-col overflow-hidden rounded-[34px] p-5 xl:p-6">
          <div className="flex flex-wrap items-center justify-end gap-4 xl:absolute xl:right-6 xl:top-6 xl:z-10">
            <div className="rounded-[26px] border border-[#d6b05f]/18 bg-[#18140b] px-5 py-4 text-[#f2cf87] shadow-[0_18px_36px_rgba(0,0,0,0.22)]">
              <div className="text-xs uppercase tracking-[0.22em] text-[#f2cf87]/65">Готово</div>
              <div className="mt-2 font-display text-4xl font-bold">{readyShots}/{photoState.shots.length}</div>
            </div>
          </div>

          <div className="mt-5 grid gap-4 xl:mt-0 xl:h-full xl:grid-cols-[minmax(0,1fr)_290px] xl:flex-1 xl:min-h-0">
            <div className="flex min-h-0 flex-col xl:h-full xl:items-center xl:justify-center">
              <div className="relative w-full aspect-video overflow-hidden rounded-[30px] border border-white/10 bg-black/30 shadow-[0_24px_60px_rgba(0,0,0,0.3)] xl:h-auto xl:max-h-full">
                <video ref={webcamVideoRef} className="absolute inset-0 h-full w-full object-cover object-center" autoPlay muted playsInline />
                <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(7,10,14,0.06),rgba(7,10,14,0.42)_68%,rgba(7,10,14,0.72))]" />
                <div className="pointer-events-none absolute inset-[5%] rounded-[24px] border border-dashed border-white/18 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.05)]" />
                {webcamError ? (
                  <div className="absolute inset-0 z-20 flex flex-col items-center justify-center px-6">
                    <div className="inline-flex h-20 w-20 items-center justify-center rounded-full border border-white/10 bg-white/6 text-[#f2cf87]">
                      <ScanLine className="h-10 w-10" />
                    </div>
                    <div className="mt-5 max-w-xl text-sm leading-7 text-white/68">{webcamError}</div>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="grid content-start gap-4 xl:content-center">
              <div className="flex min-h-[152px] flex-col justify-center rounded-[28px] border border-white/10 bg-white/[0.035] px-4 py-3">
                <div className="flex items-center gap-3 text-white">
                  <div className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-[#d6b05f]/24 bg-[radial-gradient(circle_at_top,rgba(242,207,135,0.18),transparent_58%),#1b140a] text-[#f2cf87] shadow-[0_10px_24px_rgba(0,0,0,0.22)]">
                    <TimerReset className="h-5 w-5" />
                  </div>
                  <div>
                    <div className="font-semibold">Таймер съёмки</div>
                    <div className="text-xs text-white/45">Обратный отсчёт запускается перед каждым кадром.</div>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap justify-center gap-2">
                  {[2, 3, 5].map((value) => (
                    <FilterChip
                      key={value}
                      label={`${value} сек`}
                      active={photoState.timerSeconds === value}
                      onClick={() => setPhotoTimer(value as 2 | 3 | 5)}
                    />
                  ))}
                </div>
              </div>

              <div className="grid gap-3">
                {!photoState.completed ? (
                  <Button className="w-full" iconLeft={<Camera className="h-4 w-4" />} onClick={handleTakePhoto}>
                    Сделать все снимки
                  </Button>
                ) : null}
                <Button
                  className="min-h-16 w-full text-base"
                  iconLeft={<ChevronRight className="h-5 w-5" />}
                  onClick={() =>
                    photoState.completed
                      ? isPostWorkout
                        ? (setView('workout-summary'), navigate(withSearch('/workout-summary', location.search)))
                        : (continueAfterPhoto(), navigate(withSearch('/exercise-setup', location.search)))
                      : (skipPhotoProgress(), navigate(withSearch('/exercise-setup', location.search)))
                  }
                >
                  Продолжить
                </Button>
              </div>
            </div>
          </div>
        </section>

        <aside className="grid min-h-0 gap-4 xl:grid-rows-[auto_1fr]">
          <section className="glass-panel rounded-[32px] p-5">
            <Button
              className="w-full"
              variant="secondary"
              iconLeft={<RefreshCcw className="h-4 w-4" />}
              onClick={handleResetPhotos}
              disabled={readyShots === 0 && !countdownOpen && !captureInFlight}
            >
              Сбросить всё
            </Button>
          </section>

          <section className="glass-panel min-h-0 overflow-hidden rounded-[32px] p-4 xl:p-5">
            <div className="grid gap-3 xl:grid-rows-3">
              {photoState.shots.map((shot) => (
                <button
                  key={shot.view}
                  type="button"
                  onClick={() => handleRetakeShot(shot.view)}
                  className="w-full rounded-[24px] border border-white/8 bg-white/4 p-3 text-left text-white/74 transition hover:border-[#d6b05f]/30 hover:bg-white/7"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="font-semibold text-white">{shot.title}</div>
                    {shot.status === 'ready' ? <CheckCircle2 className="h-5 w-5 text-[#92e09a]" /> : <Camera className="h-5 w-5 text-white/35" />}
                  </div>
                  <div className="mt-2 aspect-video overflow-hidden rounded-[18px] border border-white/8 bg-black/30">
                    {shot.imageUrl ? (
                      <img src={shot.imageUrl} alt={`Снимок ${shot.title.toLowerCase()}`} className="h-full w-full object-cover" />
                    ) : (
                      <div className="flex h-full items-center justify-center text-sm text-white/35">Снимок ещё не сделан</div>
                    )}
                  </div>
                </button>
              ))}
            </div>
          </section>
        </aside>
      </div>

      {countdownValue != null ? (
        <div className="fixed inset-0 z-[120] bg-black">
          <video ref={fullscreenVideoRef} className="h-full w-full object-cover" autoPlay muted playsInline />
          <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(0,0,0,0.12),rgba(0,0,0,0.35)_55%,rgba(0,0,0,0.78))]" />
          <div className="absolute left-0 right-0 top-8 px-8 text-center">
            <div className="inline-flex rounded-full border border-white/12 bg-black/45 px-5 py-3 text-sm font-semibold uppercase tracking-[0.22em] text-white/72 backdrop-blur-md">
              {activeCountdownShot?.title ?? currentShot.title}
            </div>
          </div>
          <div className="absolute bottom-10 left-0 right-0 flex flex-col items-center justify-center px-6 text-center">
            <div className="text-base font-semibold uppercase tracking-[0.22em] text-white/72">
              {sequenceMode ? 'Съёмка серии кадров' : 'Пересъём выбранного кадра'}
            </div>
            <div className="text-sm font-semibold uppercase tracking-[0.28em] text-white/65">Снимок через</div>
            <div className="mt-4 font-display text-[148px] font-bold leading-none text-white drop-shadow-[0_12px_40px_rgba(0,0,0,0.72)] md:text-[220px]">
              {countdownValue}
            </div>
          </div>
        </div>
      ) : null}

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}

function attachStreamToVideo(video: HTMLVideoElement | null, stream: MediaStream) {
  if (!video) {
    return
  }

  if (video.srcObject !== stream) {
    video.srcObject = stream
  }

  void video.play().catch(() => undefined)
}

async function uploadProgressPhoto({
  userId,
  mode,
  view,
  takenAtIso,
  imageDataUrl,
}: {
  userId: string
  mode: string
  view: RuntimePhotoView
  takenAtIso: string
  imageDataUrl: string
}) {
  const blob = await fetch(imageDataUrl).then((response) => response.blob())
  const formData = new FormData()
  formData.append('userId', userId)
  formData.append('mode', mode)
  formData.append('view', view)
  formData.append('takenAt', takenAtIso)
  formData.append('file', new File([blob], `progress-${view}.jpg`, { type: 'image/jpeg' }))

  const response = await fetch(resolveApiAssetUrl('/api/photo-progress') ?? '/api/photo-progress', {
    method: 'POST',
    body: formData,
  })

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    const message = typeof payload === 'object' && payload !== null && 'detail' in payload ? String(payload.detail) : 'Не удалось сохранить фото на backend.'
    throw new Error(message)
  }

  await response.json().catch(() => null)
}

function formatTakenAt(value: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}