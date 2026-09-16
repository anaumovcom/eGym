import * as Dialog from '@radix-ui/react-dialog'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { ExerciseCatalogResponse, ExerciseDetails, ExerciseSummary } from '@/entities/exercise/model/types'
import { apiGet } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { ExerciseVideoPlayer, SearchField } from '@/shared/ui/stage2/screen-components'
import { ValueStepper } from '@/shared/ui/training/value-stepper'

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

const CHIP_LIMIT = 10

export function ExercisePickerModal({ open, onOpenChange, userId, mode, currentExerciseSlug, currentExerciseName, excludeSlugs, initialSlug, title, description, onSelect }: ExercisePickerModalProps) {
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [pendingSlug, setPendingSlug] = useState<string | null>(null)
  const [selectedMuscles, setSelectedMuscles] = useState<string[]>([])
  const [selectedEquipment, setSelectedEquipment] = useState<string[]>([])
  const [initializedFilterSlug, setInitializedFilterSlug] = useState<string | null>(null)
  const [staged, setStaged] = useState<ExerciseDetails | null>(null)
  const [stagedSets, setStagedSets] = useState<StagedSets | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      setSearch(''); setDebouncedSearch(''); setPendingSlug(null); setSelectedMuscles([]); setSelectedEquipment([])
      setInitializedFilterSlug(null); setStaged(null); setStagedSets(null); setSubmitting(false); setError(null)
    }
  }, [open])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => setDebouncedSearch(search.trim()), 400)
    return () => window.clearTimeout(timeoutId)
  }, [search])

  const { data: currentExerciseDetails } = useQuery({
    queryKey: ['exercise-picker-current-exercise', userId, currentExerciseSlug],
    queryFn: () => apiGet<ExerciseDetails>(`/api/exercises/${encodeURIComponent(currentExerciseSlug ?? '')}?userId=${encodeURIComponent(userId)}`),
    enabled: open && mode === 'replace' && Boolean(currentExerciseSlug),
  })

  useEffect(() => {
    if (!open || mode !== 'replace' || !currentExerciseSlug || !currentExerciseDetails || initializedFilterSlug === currentExerciseSlug) return
    setSelectedMuscles(currentExerciseDetails.muscles)
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

  const queryString = useMemo(() => {
    const params = new URLSearchParams({ userId })
    if (debouncedSearch) params.set('search', debouncedSearch)
    if (selectedMuscles.length) params.set('muscles', selectedMuscles.join(','))
    if (selectedEquipment.length) params.set('equipment', selectedEquipment.join(','))
    return params.toString()
  }, [debouncedSearch, selectedEquipment, selectedMuscles, userId])

  const { data, isLoading } = useQuery({
    queryKey: ['exercise-picker-catalog', userId, debouncedSearch, selectedMuscles.join(','), selectedEquipment.join(',')],
    queryFn: () => apiGet<ExerciseCatalogResponse>(`/api/exercises?${queryString}`),
    enabled: open && !staged,
  })

  const muscleFilters = useMemo(() => {
    const ordered = [...selectedMuscles, ...(currentExerciseDetails?.muscles ?? []), ...(data?.availableFilters.muscles ?? [])]
    return ordered.filter((item, index) => ordered.indexOf(item) === index).slice(0, CHIP_LIMIT)
  }, [currentExerciseDetails?.muscles, data?.availableFilters.muscles, selectedMuscles])
  const equipmentFilters = useMemo(() => {
    const ordered = [...selectedEquipment, ...(data?.availableFilters.equipment ?? [])]
    return ordered.filter((item, index) => ordered.indexOf(item) === index).slice(0, CHIP_LIMIT)
  }, [data?.availableFilters.equipment, selectedEquipment])

  const items = useMemo(() => {
    const blocked = new Set(excludeSlugs ?? [])
    if (currentExerciseSlug && mode === 'replace') blocked.add(currentExerciseSlug)
    return (data?.items ?? []).filter((item) => !blocked.has(item.slug))
  }, [currentExerciseSlug, data?.items, excludeSlugs, mode])

  function stage(details: ExerciseDetails) {
    setStaged(details)
    setStagedSets({ sets: details.loadSettings.sets, reps: details.loadSettings.reps, weight: Math.round(details.loadSettings.weight), restSeconds: details.loadSettings.restSeconds })
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

  const toggle = (setter: typeof setSelectedMuscles) => (value: string) => setter((current) => (current.includes(value) ? current.filter((item) => item !== value) : [...current, value]))
  const resolvedTitle = title ?? (mode === 'replace' ? 'Замена упражнения' : 'Добавить упражнение')
  const resolvedDescription = description ?? (mode === 'replace' ? `Вместо «${currentExerciseName ?? 'текущего упражнения'}». Подходы и нагрузка настраиваются на следующем шаге.` : 'Найдите упражнение, затем настройте подходы — и оно появится в тренировке.')
  const confirmLabel = mode === 'replace' ? 'Заменить в тренировке' : 'Добавить в тренировку'
  const weightless = staged ? isWeightlessEquipment(staged.equipment) : false

  return (
    <Dialog.Root open={open} onOpenChange={(next) => { if (!submitting) onOpenChange(next) }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
        <SafetyDialogContent className="picker-panel" aria-busy={submitting}>
          <header className="picker-heading">
            <div className="min-w-0">
              <Dialog.Title className="font-display text-3xl font-bold text-white">{staged ? (mode === 'replace' ? 'Настройте замену' : 'Настройте подходы') : resolvedTitle}</Dialog.Title>
              <Dialog.Description className="mt-1 text-sm text-white/60">{staged ? `${staged.name} · шаг 2 из 2` : `${resolvedDescription} Шаг 1 из 2.`}</Dialog.Description>
            </div>
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
            <>
              <div className="picker-search">
                <SearchField value={search} placeholder="Найти упражнение..." onChange={setSearch} />
                <div className="picker-chips">
                  {muscleFilters.map((muscle) => <button key={muscle} type="button" aria-pressed={selectedMuscles.includes(muscle)} className={cn('picker-chip', selectedMuscles.includes(muscle) && 'picker-chip-active')} onClick={() => toggle(setSelectedMuscles)(muscle)}>{muscle}</button>)}
                </div>
                <div className="picker-chips">
                  {equipmentFilters.map((equipment) => <button key={equipment} type="button" aria-pressed={selectedEquipment.includes(equipment)} className={cn('picker-chip', selectedEquipment.includes(equipment) && 'picker-chip-active')} onClick={() => toggle(setSelectedEquipment)(equipment)}>{equipment}</button>)}
                  {selectedMuscles.length || selectedEquipment.length || search ? <button type="button" className="picker-chip" onClick={() => { setSelectedMuscles([]); setSelectedEquipment([]); setSearch('') }}>Сбросить</button> : null}
                </div>
              </div>
              {error ? <p role="alert" className="mt-3 text-[#ffb4a7]">{error}</p> : null}
              <div className="picker-results" aria-live="polite">
                {isLoading || (pendingSlug && initialSlug) ? <div className="picker-empty">Загрузка каталога…</div> : items.length ? (
                  <ul className="picker-list" aria-label="Результаты поиска">
                    {items.map((item) => (
                      <li key={item.slug}>
                        <button type="button" className="picker-item" disabled={pendingSlug !== null} aria-label={`Выбрать ${item.name}`} onClick={() => void handlePick(item)}>
                          <ExercisePickerPreview videoUrl={item.previewVideoUrl} title={item.name} />
                          <span className="picker-item-body">
                            <span className="picker-item-name">{item.name}</span>
                            <span className="picker-item-meta">{[...item.muscles.slice(0, 2), item.equipment].join(' · ')}</span>
                          </span>
                          <span className="picker-item-action">{pendingSlug === item.slug ? 'Загрузка…' : 'Выбрать'}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : <div className="picker-empty">По текущему запросу упражнений не найдено.</div>}
              </div>
            </>
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
