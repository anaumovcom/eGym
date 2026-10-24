import * as Dialog from '@radix-ui/react-dialog'
import { BellRing, CalendarDays, Camera, ChevronLeft, ChevronRight, Expand, ImageOff, Images, Trash2, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { resolveApiAssetUrl } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { daysBetween, type BodyMeasurement } from '@/features/body/body-metrics'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { PhotoCompare } from './progress-photo-compare'
import './progress-photo-gallery.css'

export type ProgressPhoto = { id: number; view: 'front' | 'back' | 'side'; takenAt: string; thumbnailUrl: string; imageUrl?: string }
export const photoViews = [{ id: 'front', label: 'Спереди' }, { id: 'back', label: 'Сзади' }, { id: 'side', label: 'Сбоку' }] as const
const dateFormat = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
const dayFormat = new Intl.DateTimeFormat('en-CA', { year: 'numeric', month: '2-digit', day: '2-digit' })

// Keep every photo, including repeated captures of the same view on one day.
export function groupProgressPhotos(photos: ProgressPhoto[]) {
  const days = new Map<string, ProgressPhoto[]>()
  for (const photo of [...photos].sort((a, b) => Date.parse(b.takenAt) - Date.parse(a.takenAt))) {
    const day = dayFormat.format(new Date(photo.takenAt))
    const group = days.get(day) ?? []
    group.push(photo)
    days.set(day, group)
  }
  return [...days].map(([day, items]) => {
    const byView = photoViews.map((view) => items.filter((photo) => photo.view === view.id))
    const rows = Array.from({ length: Math.max(...byView.map((items) => items.length)) }, (_, index) => byView.map((items) => items[index]))
    return { day, date: dateFormat.format(new Date(items[0].takenAt)), rows, count: items.length }
  })
}

export function PhotoImage({ photo, full = false, alt }: { photo: ProgressPhoto; full?: boolean; alt?: string }) {
  const [failed, setFailed] = useState(false)
  const label = alt ?? photoViews.find((view) => view.id === photo.view)!.label
  const source = full ? photo.imageUrl || photo.thumbnailUrl : photo.thumbnailUrl
  return failed ? <span className="photo-gallery-unavailable"><ImageOff aria-hidden="true" /><span>Снимок недоступен</span></span> : <img src={resolveApiAssetUrl(source) ?? source} alt={label} loading={full ? 'eager' : 'lazy'} onError={() => setFailed(true)} />
}

export function ProgressPhotoGallery({ photos, loading, error, onRetry, onPhoto, onDelete, measurements = [], mode = 'progress' }: { photos: ProgressPhoto[]; loading: boolean; error: boolean; onRetry: () => void; onPhoto: () => void; onDelete: (id: number) => Promise<void>; measurements?: BodyMeasurement[]; mode?: 'progress' | 'manage' }) {
  const groups = groupProgressPhotos(photos)
  const ordered = groups.flatMap((group) => group.rows.flat().filter((photo): photo is ProgressPhoto => Boolean(photo)))
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const viewerRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ProgressPhoto | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const deleteLock = useRef(false)
  const cancelDeleteRef = useRef<HTMLButtonElement>(null)
  async function confirmDelete() {
    if (!deleteTarget || deleteLock.current) return
    deleteLock.current = true
    setDeleting(true)
    setDeleteError(null)
    try {
      await onDelete(deleteTarget.id)
      setDeleteTarget(null)
    } catch {
      setDeleteError('Не удалось удалить фото. Попробуйте ещё раз.')
    } finally {
      deleteLock.current = false
      setDeleting(false)
    }
  }
  const selectedIndex = ordered.findIndex((photo) => photo.id === selectedId)
  const selected = ordered[selectedIndex]
  function move(direction: number) {
    const next = ordered[selectedIndex + direction]
    if (next) {
      setSelectedId(next.id)
      // A navigation button may become disabled at the edge; retain keyboard focus.
      viewerRef.current?.focus()
    }
  }

  return <section className="photo-gallery" aria-labelledby="photo-gallery-title">
    <header className="photo-gallery-heading">
      <div><span className="photo-gallery-eyebrow"><Images aria-hidden="true" /> ВАША ИСТОРИЯ ИЗМЕНЕНИЙ</span><h2 id="photo-gallery-title">Фото прогресса</h2><p>Маленькие изменения. Большой путь. Всё видно в сравнении.</p></div>
      <Button iconLeft={<Camera aria-hidden="true" />} onClick={onPhoto}>Фотофиксация</Button>
    </header>
    {loading ? <div className="photo-gallery-state" role="status">Загрузка фотографий…</div> : error ? <div className="photo-gallery-state" role="alert"><ImageOff aria-hidden="true" /><h3>Не удалось загрузить фотографии</h3><Button variant="secondary" onClick={onRetry}>Повторить</Button></div> : groups.length ? <>
      <PhotoStats groups={groups} onPhoto={onPhoto} />
      {mode === 'progress' ? <PhotoCompare photos={photos} measurements={measurements} onPhoto={onPhoto} /> : null}
      <div className="photo-gallery-meta"><span>Все фото <b>{photos.length}</b><span className="photo-gallery-meta-divider" /> По дате · сначала новые</span>{mode === 'progress' ? <Link to="/profile?tab=photo">Управление снимками <ChevronRight aria-hidden="true" /></Link> : <Link to="/progress?tab=photo">Сравнить до и после <ChevronRight aria-hidden="true" /></Link>}</div>
      <div className="photo-gallery-timeline">{groups.map((group, groupIndex) => <section className="photo-gallery-session" key={group.day} aria-label={group.date}>
        <header className="photo-gallery-date"><div><CalendarDays aria-hidden="true" /><h3>{group.date}</h3>{groupIndex === 0 ? <span className="photo-gallery-latest">Последняя съёмка</span> : null}</div><span>{group.count} фото</span></header>
        {group.rows.map((row, rowIndex) => <div className="photo-gallery-grid" key={rowIndex}>{photoViews.map((view, index) => {
          const photo = row[index]
          return <article className="photo-gallery-card" key={view.id}>
            {photo ? <button type="button" className="photo-gallery-shot" onClick={(event) => { triggerRef.current = event.currentTarget; setSelectedId(photo.id) }} aria-label={`Открыть фото: ${view.label}, ${group.date}`}><PhotoImage key={photo.id} photo={photo} /><span className="photo-gallery-expand"><Expand aria-hidden="true" /></span></button> : <div className="photo-gallery-missing"><span className="photo-gallery-silhouette" aria-hidden="true"><svg viewBox="0 0 100 180" fill="none"><circle cx="50" cy="23" r="15" /><path d={view.id === 'side' ? 'M43 45C66 43 68 65 61 88L66 113L59 166H44L42 115L36 88L39 58M55 55L61 99' : 'M35 46L18 54L8 105L19 108L32 72L34 110L29 166H44L50 121L56 166H71L66 110L68 72L81 108L92 105L82 54L65 46Z'} /></svg></span><span>Ракурс не добавлен</span><button type="button" onClick={onPhoto}>Сделать фото <Camera aria-hidden="true" /></button></div>}
            <footer><span className="photo-gallery-view-number">0{index + 1}</span><strong>{view.label}</strong><span>{photo ? new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' }).format(new Date(photo.takenAt)) : 'Нет снимка'}</span></footer>
            {photo ? <button type="button" className="photo-gallery-delete" aria-label={`Удалить фото: ${view.label}, ${group.date}`} onClick={() => { setDeleteError(null); setDeleteTarget(photo) }}><Trash2 aria-hidden="true" />Удалить</button> : null}
          </article>
        })}</div>)}
      </section>)}</div>
      <p className="photo-gallery-tip"><Camera aria-hidden="true" /> Одинаковые свет, расстояние и поза помогут точнее видеть изменения.</p>
    </> : <div className="photo-gallery-state"><span className="photo-gallery-empty-icon"><Images aria-hidden="true" /></span><h3>Здесь начинается ваша история</h3><p>Сделайте первые фото спереди, сзади и сбоку.<br />Сохраняйте новые снимки и наблюдайте за изменениями.</p><Button iconLeft={<Camera aria-hidden="true" />} onClick={onPhoto}>Сделать первые фото</Button></div>}
    <Dialog.Root open={Boolean(selected)} onOpenChange={(open) => { if (!open) setSelectedId(null) }}><Dialog.Portal><Dialog.Overlay className="photo-gallery-overlay" /><SafetyDialogContent ref={viewerRef} className="photo-gallery-viewer" onCloseAutoFocus={(event) => { event.preventDefault(); triggerRef.current?.focus() }} onKeyDown={(event) => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); move(event.key === 'ArrowLeft' ? -1 : 1) } }}>
      {selected ? <><header><div><Dialog.Title>{photoViews.find((view) => view.id === selected.view)!.label}</Dialog.Title><Dialog.Description>{dateFormat.format(new Date(selected.takenAt))} · {selectedIndex + 1} / {ordered.length}</Dialog.Description></div><Dialog.Close asChild><button type="button" className="photo-gallery-icon-button" aria-label="Закрыть просмотр"><X aria-hidden="true" /></button></Dialog.Close></header><div className="photo-gallery-viewer-stage"><button type="button" className="photo-gallery-icon-button" aria-label="Предыдущее фото" disabled={selectedIndex === 0} onClick={() => move(-1)}><ChevronLeft aria-hidden="true" /></button><PhotoImage key={selected.id} photo={selected} full /><button type="button" className="photo-gallery-icon-button" aria-label="Следующее фото" disabled={selectedIndex === ordered.length - 1} onClick={() => move(1)}><ChevronRight aria-hidden="true" /></button></div><div className="photo-gallery-viewer-caption">{selectedIndex + 1} из {ordered.length}<span>Листайте кнопками или клавишами ← →</span></div></> : null}
    </SafetyDialogContent></Dialog.Portal></Dialog.Root>
    <Dialog.Root open={Boolean(deleteTarget)} onOpenChange={(open) => { if (!open && !deleteLock.current) setDeleteTarget(null) }}><Dialog.Portal><Dialog.Overlay className="photo-gallery-overlay" /><SafetyDialogContent className="photo-gallery-delete-dialog" onOpenAutoFocus={(event) => { event.preventDefault(); cancelDeleteRef.current?.focus() }}>
      <Dialog.Title>Удалить фото?</Dialog.Title>
      <Dialog.Description>{deleteTarget ? `${photoViews.find((view) => view.id === deleteTarget.view)!.label} · ${dateFormat.format(new Date(deleteTarget.takenAt))}. ` : ''}Снимок будет удалён из галереи и профиля. Остальные фото сохранятся.</Dialog.Description>
      {deleteError ? <p role="alert">{deleteError}</p> : null}
      <div className="photo-gallery-delete-actions"><Dialog.Close asChild><Button ref={cancelDeleteRef} variant="secondary" disabled={deleting}>Отмена</Button></Dialog.Close><Button className="photo-gallery-delete-confirm" iconLeft={<Trash2 aria-hidden="true" />} disabled={deleting} onClick={() => void confirmDelete()}>{deleting ? 'Удаление…' : 'Удалить фото'}</Button></div>
    </SafetyDialogContent></Dialog.Portal></Dialog.Root>
  </section>
}
const shortDate = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
const refreshAfterDays = 21

/** How the photo diary is going: sessions, span and a nudge when the last session is getting old. */
function PhotoStats({ groups, onPhoto }: { groups: ReturnType<typeof groupProgressPhotos>; onPhoto: () => void }) {
  const latest = groups[0].rows.flat().find(Boolean)!.takenAt
  const first = groups.at(-1)!.rows.flat().find(Boolean)!.takenAt
  const sinceLast = daysBetween(latest)
  const span = daysBetween(first, latest)
  return (
    <div className="photo-gallery-stats">
      <div><span>Фотосессий</span><strong>{groups.length}</strong></div>
      <div><span>Первая съёмка</span><strong>{shortDate.format(new Date(first))}</strong></div>
      <div><span>Период наблюдения</span><strong>{groups.length > 1 ? `${span} дн.` : 'одна съёмка'}</strong></div>
      <div data-stale={sinceLast >= refreshAfterDays || undefined}><span>С последней съёмки</span><strong>{sinceLast <= 0 ? 'сегодня' : `${sinceLast} дн.`}</strong></div>
      {sinceLast >= refreshAfterDays ? <button type="button" className="photo-gallery-nudge" onClick={onPhoto}><BellRing aria-hidden="true" /><span><b>Пора обновить фото</b><small>Снимки раз в 2–4 недели лучше всего показывают изменения</small></span><Camera aria-hidden="true" /></button> : null}
    </div>
  )
}
