import * as Dialog from '@radix-ui/react-dialog'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, Check, Dumbbell, SearchX, Star, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useExerciseCatalog } from '@/entities/exercise/model/catalog'
import { emptyCatalogSelection, type CatalogFilterKey } from '@/entities/exercise/model/catalog-filters'
import type { ExerciseDetails, ExerciseSummary } from '@/entities/exercise/model/types'
import { apiGet } from '@/shared/api/client'
import { Button } from '@/shared/ui/button'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { ExerciseVideoPlayer } from '@/shared/ui/stage2/screen-components'
import { ExerciseDiscoveryActiveFilters, ExerciseDiscoveryFilters, ExerciseDiscoveryToolbar } from './exercise-discovery'
import { ValueStepper } from '@/shared/ui/training/value-stepper'
import { useAppStore } from '@/stores/app-store'

export type ExercisePickerModalProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  userId: string
  mode: 'replace' | 'add'
  currentExerciseSlug?: string
  currentExerciseName?: string
  excludeSlugs?: string[]
  /** Opens directly on the configuration step for this exercise (e.g. "add to workout" from the catalog). */
  initialSlug?: string | null
  title?: string
  description?: string
  onSelect: (details: ExerciseDetails) => void | Promise<void>
}

type StagedSets = { sets: number; reps: number; weight: number; restSeconds: number }

const PAGE_SIZE = 24

export function ExercisePickerModal({ open, onOpenChange, userId, mode, currentExerciseSlug, currentExerciseName, excludeSlugs, initialSlug, title, description, onSelect }: ExercisePickerModalProps) {
  const [search, setSearch] = useState('')
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const [pendingSlug, setPendingSlug] = useState<string | null>(null)
  const [selected, setSelected] = useState(emptyCatalogSelection)
  const [favoritesOnly, setFavoritesOnly] = useState(false)
  const favoriteSlugs = useAppStore((state) => state.favoriteExerciseSlugs)
  const toggleFavorite = useAppStore((state) => state.toggleFavoriteExercise)
  const [initializedFilterSlug, setInitializedFilterSlug] = useState<string | null>(null)
  const [staged, setStaged] = useState<ExerciseDetails | null>(null)
  const [stagedSets, setStagedSets] = useState<StagedSets | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      setSearch(''); setPendingSlug(null); setSelected(emptyCatalogSelection()); setFavoritesOnly(false)
      setInitializedFilterSlug(null); setStaged(null); setStagedSets(null); setSubmitting(false); setError(null)
    }
  }, [open])

  useEffect(() => {
    setVisibleCount(PAGE_SIZE)
  }, [open, userId, search, selected, favoritesOnly])

  const { data: currentExerciseDetails } = useQuery({
    queryKey: ['exercise-picker-current-exercise', userId, currentExerciseSlug],
    queryFn: () => apiGet<ExerciseDetails>(`/api/exercises/${encodeURIComponent(currentExerciseSlug ?? '')}?userId=${encodeURIComponent(userId)}`),
    enabled: open && mode === 'replace' && Boolean(currentExerciseSlug),
  })

  useEffect(() => {
    if (!open || mode !== 'replace' || !currentExerciseSlug || !currentExerciseDetails || initializedFilterSlug === currentExerciseSlug) return
    setSelected((value) => ({ ...value, muscles: currentExerciseDetails.muscles }))
    setInitializedFilterSlug(currentExerciseSlug)
  }, [currentExerciseDetails, currentExerciseSlug, initializedFilterSlug, mode, open])

  // Catalog → "add to workout" arrives with a chosen exercise: skip straight to set configuration.
  useEffect(() => {
    if (!open || !initialSlug || staged) return
    let cancelled = false
    setPendingSlug(initialSlug)
    apiGet<ExerciseDetails>(`/api/exercises/${encodeURIComponent(initialSlug)}?userId=${encodeURIComponent(userId)}`)
      .then((details) => { if (!cancelled) stage(details) })
      .catch(() => { if (!cancelled) setError('Не удалось загрузить упражнение. Выберите его из списка.') })
      .finally(() => { if (!cancelled) setPendingSlug(null) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSlug, open, userId])

  const { data, isLoading, isError: catalogError, refetch: reloadCatalog } = useExerciseCatalog(userId, {
    search, ...selected,
  }, open && !staged)

  const items = useMemo(() => {
    const blocked = new Set(excludeSlugs ?? [])
    if (currentExerciseSlug && mode === 'replace') blocked.add(currentExerciseSlug)
    return (data?.items ?? []).filter((item) => !blocked.has(item.slug) && (!favoritesOnly || item.favorite))
  }, [currentExerciseSlug, data?.items, excludeSlugs, mode, favoritesOnly])

  function stage(details: ExerciseDetails) {
    setStaged(details)
    setStagedSets({ sets: details.loadSettings.sets, reps: details.loadSettings.reps, weight: Math.max(0, details.loadSettings.weight), restSeconds: details.loadSettings.restSeconds })
    setError(null)
  }

  async function handlePick(item: ExerciseSummary) {
    setPendingSlug(item.slug)
    setError(null)
    try {
      stage(await apiGet<ExerciseDetails>(`/api/exercises/${encodeURIComponent(item.slug)}?userId=${encodeURIComponent(userId)}`))
    } catch {
      setError('Не удалось загрузить упражнение. Попробуйте ещё раз.')
    } finally {
      setPendingSlug(null)
    }
  }

  async function handleConfirm() {
    if (!staged || !stagedSets || submitting) return
    setSubmitting(true)
    setError(null)
    try {
      await onSelect({ ...staged, loadSettings: { ...staged.loadSettings, ...stagedSets } })
      onOpenChange(false)
    } catch {
      setError(mode === 'replace' ? 'Не удалось заменить упражнение. Попробуйте ещё раз.' : 'Не удалось добавить упражнение. Попробуйте ещё раз.')
    } finally {
      setSubmitting(false)
    }
  }

  function toggleFilter(key: CatalogFilterKey, value: string) {
    setSelected((current) => ({ ...current, [key]: current[key].includes(value) ? current[key].filter((item) => item !== value) : [...current[key], value] }))
  }
  function clearFilters() { setSelected(emptyCatalogSelection()); setSearch(''); setFavoritesOnly(false) }
  const resolvedTitle = title ?? (mode === 'replace' ? 'Замена упражнения' : 'Добавить упражнение')
  const resolvedDescription = description ?? (mode === 'replace' ? `Вместо «${currentExerciseName ?? 'текущего упражнения'}». Подходы и нагрузка настраиваются на следующем шаге.` : 'Найдите упражнение, затем настройте подходы — и оно появится в тренировке.')
  const confirmLabel = mode === 'replace' ? 'Заменить в тренировке' : 'Добавить в тренировку'
  const weightless = staged ? isWeightlessEquipment(staged.equipment) : false

  return (
    <Dialog.Root open={open} onOpenChange={(next) => { if (!submitting) onOpenChange(next) }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
        <SafetyDialogContent className="picker-panel" rootClassName="picker-fullscreen-root" aria-busy={submitting}>
          <header className="picker-heading">
            <div className="min-w-0">
              <div className="discovery-eyebrow"><Dumbbell aria-hidden="true" /> ВАША ТРЕНИРОВКА</div>
              <Dialog.Title className="font-display text-3xl font-bold text-white">{staged ? (mode === 'replace' ? 'Настройте замену' : 'Настройте подходы') : resolvedTitle}</Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-white/60">{staged ? staged.name : resolvedDescription}</Dialog.Description>
            </div>
            <ol className="picker-steps" aria-label="Этапы добавления"><li aria-current={!staged ? 'step' : undefined}><span>{staged ? <Check aria-hidden="true" /> : '1'}</span>Выбор упражнения</li><li aria-current={staged ? 'step' : undefined}><span>2</span>Подходы и нагрузка</li></ol>
            <Dialog.Close asChild><Button variant="secondary" aria-label="Закрыть выбор упражнения" disabled={submitting}><X aria-hidden="true" /></Button></Dialog.Close>
          </header>

          {staged && stagedSets ? (
            <div className="picker-configure">
              <div className="picker-configure-media">
                {staged.previewVideoUrl ? <ExerciseVideoPlayer videoUrl={staged.previewVideoUrl} videoLabel={`${staged.name} · превью`} wrapperClassName="aspect-video w-full rounded-[22px] border border-white/8 bg-[#0b1017]" /> : <div className="aspect-video w-full rounded-[22px] border border-white/8 bg-[#0b1017]" />}
                <p className="mt-3 text-sm text-white/70">{[...staged.muscles.slice(0, 3), staged.equipment].join(' · ')}</p>
              </div>
              <div className="picker-configure-controls">
                <ValueStepper label="Подходы" value={stagedSets.sets} onChange={(delta) => setStagedSets((s) => s && ({ ...s, sets: Math.min(10, Math.max(1, s.sets + delta)) }))} onValueCommit={(value) => setStagedSets((s) => s && ({ ...s, sets: Math.min(10, Math.max(1, value ?? s.sets)) }))} />
                <ValueStepper label="Повторы" value={stagedSets.reps} onChange={(delta) => setStagedSets((s) => s && ({ ...s, reps: Math.max(1, s.reps + delta) }))} onValueCommit={(value) => setStagedSets((s) => s && ({ ...s, reps: Math.max(1, value ?? s.reps) }))} />
                <ValueStepper label="Вес" unit="кг" value={weightless ? null : stagedSets.weight} emptyLabel={weightless ? 'вес тела' : '—'} readOnly={weightless} onChange={(delta) => setStagedSets((s) => s && ({ ...s, weight: Math.max(0, s.weight + delta) }))} onValueCommit={(value) => setStagedSets((s) => s && ({ ...s, weight: Math.max(0, value ?? 0) }))} />
                <ValueStepper label="Отдых" unit="сек" value={stagedSets.restSeconds} onChange={(delta) => setStagedSets((s) => s && ({ ...s, restSeconds: Math.max(15, s.restSeconds + delta * 15) }))} onValueCommit={(value) => setStagedSets((s) => s && ({ ...s, restSeconds: Math.max(15, value ?? s.restSeconds) }))} />
              </div>
              {error ? <p role="alert" className="text-[#ffb4a7]">{error}</p> : null}
              <div className="picker-actions">
                <Button variant="secondary" iconLeft={<ArrowLeft aria-hidden="true" />} disabled={submitting} onClick={() => { setStaged(null); setStagedSets(null); setError(null) }}>К списку</Button>
                <Button disabled={submitting} onClick={() => void handleConfirm()}>{submitting ? 'Сохранение…' : confirmLabel}</Button>
              </div>
            </div>
          ) : (
            <div className="discovery-layout picker-discovery">
              <ExerciseDiscoveryFilters selected={selected} available={data?.availableFilters} onToggle={toggleFilter} onClear={clearFilters} />
              <div className="discovery-content">
              <ExerciseDiscoveryToolbar search={search} onSearch={setSearch} favoritesOnly={favoritesOnly} onFavoritesChange={() => setFavoritesOnly((value) => !value)} favoriteCount={favoriteSlugs.length} count={items.length} loading={isLoading} />
              <ExerciseDiscoveryActiveFilters selected={selected} onToggle={toggleFilter} onClear={clearFilters} />
              {error ? <p role="alert" className="mt-3 text-[#ffb4a7]">{error}</p> : null}
              <div className="picker-results" aria-live="polite">
                {isLoading || (pendingSlug && initialSlug) ? <div className="picker-empty">Загрузка каталога…</div> : catalogError ? (
                  <div className="picker-empty" role="alert">Не удалось загрузить каталог. <Button variant="secondary" onClick={() => void reloadCatalog()}>Повторить</Button></div>
                ) : items.length ? (
                  <ul className="picker-list" aria-label="Результаты поиска">
                    {items.slice(0, visibleCount).map((item) => (
                      <li key={item.slug} className="picker-result-row">
                        <button type="button" className="picker-item" disabled={pendingSlug !== null} aria-label={`Выбрать ${item.name}`} onClick={() => void handlePick(item)}>
                          <ExercisePickerPreview videoUrl={item.previewVideoUrl} title={item.name} />
                          <span className="picker-item-body">
                            <span className="picker-item-name">{item.name}</span>
                            <span className="picker-item-meta">{item.muscles.slice(0, 3).join(' · ')}</span>
                            <span className="picker-item-tags"><span><Dumbbell aria-hidden="true" />{item.equipment}</span><span>{item.difficultyLabel}</span></span>
                          </span>
                          <span className="picker-item-action">{pendingSlug === item.slug ? 'Загрузка…' : 'Выбрать'}<ArrowRight aria-hidden="true" /></span>
                        </button>
                        <button type="button" className="picker-favorite" aria-pressed={item.favorite} aria-label={`${item.favorite ? 'Убрать из избранного' : 'Добавить в избранное'}: ${item.name}`} onClick={() => toggleFavorite(item.slug)}><Star aria-hidden="true" /></button>
                      </li>
                    ))}
                    {items.length > visibleCount ? <li><Button variant="secondary" onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}>Показать ещё</Button></li> : null}
                  </ul>
                ) : <div className="picker-empty"><SearchX aria-hidden="true" /><h2>{favoritesOnly && !favoriteSlugs.length ? 'В избранном пока пусто' : 'По текущему запросу упражнений не найдено.'}</h2><p>{favoritesOnly && !favoriteSlugs.length ? 'Отмечайте упражнения звёздочкой — они появятся здесь.' : 'Попробуйте другое название или уберите часть фильтров.'}</p><Button variant="secondary" onClick={clearFilters}>{favoritesOnly && !favoriteSlugs.length ? 'Все упражнения' : 'Сбросить фильтры'}</Button></div>}
              </div>
              <footer className="picker-browse-footer"><span>Выберите упражнение — затем настройте нагрузку</span><span>Шаг 1 из 2</span></footer>
              </div>
            </div>
          )}
        </SafetyDialogContent>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export function isWeightlessEquipment(equipment: string) {
  return ['Bodyweight', 'Собственный вес', 'Stretches', 'Растяжка', 'Recovery', 'Восстановление', 'Yoga', 'Йога', 'Cardio', 'Кардио'].includes(equipment)
}

export function isRecoveryEquipment(equipment: string) {
  return equipment === 'Recovery' || equipment === 'Восстановление'
}

function ExercisePickerPreview({ videoUrl, title }: { videoUrl?: string; title: string }) {
  if (!videoUrl) return <span className="picker-item-preview" aria-hidden="true" />
  return <ExerciseVideoPlayer videoUrl={videoUrl} videoLabel={`${title} · превью`} lazyLoad wrapperClassName="picker-item-preview" />
}
