import * as Dialog from '@radix-ui/react-dialog'
import { useQueryClient } from '@tanstack/react-query'
import { Camera, Check, RefreshCcw, Save, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { RuntimePhotoView } from '@/entities/runtime/model/types'
import { resolveApiAssetUrl } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'

const views: Array<{ id: RuntimePhotoView; label: string; hint: string }> = [
  { id: 'front', label: 'Спереди', hint: 'Встаньте лицом к камере' },
  { id: 'side', label: 'Сбоку', hint: 'Повернитесь боком к камере' },
  { id: 'back', label: 'Сзади', hint: 'Повернитесь спиной к камере' },
]

type Drafts = Partial<Record<RuntimePhotoView, string>>

export function PhotoCaptureDialog({ open, onOpenChange, userId, onSaved }: { open: boolean; onOpenChange: (open: boolean) => void; userId: string; onSaved?: () => void | Promise<void> }) {
  const queryClient = useQueryClient()
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const [view, setView] = useState<RuntimePhotoView>('front')
  const [drafts, setDrafts] = useState<Drafts>({})
  const [cameraError, setCameraError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      stopStream(streamRef.current)
      streamRef.current = null
      setView('front')
      setDrafts({})
      setCameraError(null)
      setSaveError(null)
      setSaving(false)
      return
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError('Браузер не поддерживает доступ к камере.')
      return
    }

    let cancelled = false
    void navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 }, aspectRatio: { ideal: 16 / 9 } }, audio: false })
      .then((stream) => {
        if (cancelled) {
          stopStream(stream)
          return
        }
        streamRef.current = stream
        attachStream(videoRef.current, stream)
      })
      .catch(() => {
        if (!cancelled) setCameraError('Не удалось открыть камеру. Разрешите доступ и попробуйте снова.')
      })

    return () => {
      cancelled = true
      stopStream(streamRef.current)
      streamRef.current = null
    }
  }, [open])

  useEffect(() => {
    if (open && videoRef.current && streamRef.current) attachStream(videoRef.current, streamRef.current)
  }, [open, view, drafts])

  function capture() {
    const image = captureFrame(videoRef.current)
    if (!image) {
      setCameraError('Камера ещё не готова. Попробуйте снова через несколько секунд.')
      return
    }
    setDrafts((current) => ({ ...current, [view]: image }))
    setCameraError(null)
  }

  function retake() {
    setDrafts((current) => {
      const next = { ...current }
      delete next[view]
      return next
    })
  }

  async function save() {
    const entries = Object.entries(drafts) as Array<[RuntimePhotoView, string]>
    if (!entries.length || saving) return
    setSaving(true)
    setSaveError(null)
    try {
      const takenAt = new Date().toISOString()
      for (const [photoView, imageDataUrl] of entries) {
        await uploadPhoto({ userId, view: photoView, imageDataUrl, takenAt })
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['user-profile-screen', userId] }),
        queryClient.invalidateQueries({ queryKey: ['progress-screen', userId] }),
        queryClient.invalidateQueries({ queryKey: ['progress-photos', userId] }),
      ])
      await onSaved?.()
      onOpenChange(false)
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'Не удалось сохранить фото. Попробуйте ещё раз.')
    } finally {
      setSaving(false)
    }
  }

  const current = views.find((item) => item.id === view)!
  const draft = drafts[view]
  const count = Object.keys(drafts).length

  return (
    <Dialog.Root open={open} onOpenChange={(next) => { if (!saving) onOpenChange(next) }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/85 backdrop-blur-sm" />
        <SafetyDialogContent className="photo-capture-panel" aria-busy={saving}>
          <header className="photo-capture-heading">
            <div>
              <Dialog.Title className="font-display text-3xl font-bold text-white">Фотофиксация</Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-white/60">Выберите ракурс, сделайте снимок и сохраните готовые кадры. Тренировка не запускается.</Dialog.Description>
            </div>
            <Dialog.Close asChild><Button variant="secondary" aria-label="Закрыть фотофиксацию" disabled={saving}><X aria-hidden="true" /></Button></Dialog.Close>
          </header>

          <div className="photo-capture-views" role="tablist" aria-label="Ракурс фотографии">
            {views.map((item) => (
              <button key={item.id} type="button" role="tab" aria-selected={view === item.id} onClick={() => setView(item.id)}>
                {drafts[item.id] ? <Check aria-hidden="true" /> : <Camera aria-hidden="true" />}{item.label}
              </button>
            ))}
          </div>

          <div className="photo-capture-stage">
            <div className="photo-capture-preview">
              <video ref={videoRef} autoPlay muted playsInline hidden={Boolean(draft)} />
              {draft ? <img src={draft} alt={`Предпросмотр: ${current.label.toLowerCase()}`} /> : null}
              <div className="photo-capture-guide" aria-hidden="true" />
              {cameraError && !draft ? <p role="alert" className="photo-capture-error">{cameraError}</p> : null}
            </div>
            <aside className="photo-capture-side">
              <div>
                <p className="text-sm text-white/60">Текущий ракурс</p>
                <h3 className="mt-1 font-display text-3xl font-bold text-white">{current.label}</h3>
                <p className="mt-2 text-white/70">{current.hint}</p>
              </div>
              <div className="photo-capture-progress"><strong>{count}/3</strong><span>ракурсов готово</span></div>
              {draft
                ? <Button iconLeft={<RefreshCcw aria-hidden="true" />} onClick={retake}>Переснять</Button>
                : <Button iconLeft={<Camera aria-hidden="true" />} onClick={capture} disabled={Boolean(cameraError)}>Снять</Button>}
            </aside>
          </div>

          {saveError ? <p role="alert" className="text-[#ffb4a7]">{saveError}</p> : null}
          <footer className="photo-capture-actions">
            <Dialog.Close asChild><Button variant="secondary" disabled={saving}>Закрыть</Button></Dialog.Close>
            <Button iconLeft={<Save aria-hidden="true" />} disabled={!count || saving} onClick={() => void save()}>{saving ? 'Сохранение…' : `Сохранить${count > 1 ? ` (${count})` : ''}`}</Button>
          </footer>
        </SafetyDialogContent>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function attachStream(video: HTMLVideoElement | null, stream: MediaStream) {
  if (!video) return
  if (video.srcObject !== stream) video.srcObject = stream
  void video.play().catch(() => undefined)
}

function stopStream(stream: MediaStream | null) {
  stream?.getTracks().forEach((track) => track.stop())
}

export function captureFrame(video: HTMLVideoElement | null) {
  if (!video || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return null
  const width = 1280
  const height = 720
  const sourceWidth = video.videoWidth || width
  const sourceHeight = video.videoHeight || height
  const sourceAspect = sourceWidth / sourceHeight
  const targetAspect = width / height
  let sx = 0; let sy = 0; let sw = sourceWidth; let sh = sourceHeight
  if (sourceAspect > targetAspect) { sw = sourceHeight * targetAspect; sx = (sourceWidth - sw) / 2 }
  else if (sourceAspect < targetAspect) { sh = sourceWidth / targetAspect; sy = (sourceHeight - sh) / 2 }
  const canvas = document.createElement('canvas')
  canvas.width = width; canvas.height = height
  const context = canvas.getContext('2d')
  if (!context) return null
  context.drawImage(video, sx, sy, sw, sh, 0, 0, width, height)
  return canvas.toDataURL('image/jpeg', 0.92)
}

async function uploadPhoto({ userId, view, imageDataUrl, takenAt }: { userId: string; view: RuntimePhotoView; imageDataUrl: string; takenAt: string }) {
  const blob = await fetch(imageDataUrl).then((response) => response.blob())
  const formData = new FormData()
  formData.append('userId', userId)
  formData.append('mode', 'manual')
  formData.append('view', view)
  formData.append('takenAt', takenAt)
  formData.append('file', new File([blob], `progress-${view}.jpg`, { type: 'image/jpeg' }))
  const response = await fetch(resolveApiAssetUrl('/api/photo-progress') ?? '/api/photo-progress', { method: 'POST', body: formData })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(typeof payload === 'object' && payload !== null && 'detail' in payload ? String(payload.detail) : 'Не удалось сохранить фото. Попробуйте ещё раз.')
  }
}
