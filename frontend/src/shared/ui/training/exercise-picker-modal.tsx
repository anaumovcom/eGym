import * as Dialog from '@radix-ui/react-dialog'
import { useQuery } from '@tanstack/react-query'
import { Search, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type { ExerciseCatalogResponse, ExerciseDetails, ExerciseSummary } from '@/entities/exercise/model/types'
import { apiGet } from '@/shared/api/client'
import { cn } from '@/shared/lib/cn'
import { ExerciseVideoPlayer, SearchField } from '@/shared/ui/stage2/screen-components'

export type ExercisePickerModalProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  userId: string
  mode: 'replace' | 'add'
  currentExerciseSlug?: string
  currentExerciseName?: string
  excludeSlugs?: string[]
  title?: string
  description?: string
  onSelect: (details: ExerciseDetails) => void | Promise<void>
}

export function ExercisePickerModal({
  open,
  onOpenChange,
  userId,
  mode,
  currentExerciseSlug,
  currentExerciseName,
  excludeSlugs,
  title,
  description,
  onSelect,
}: ExercisePickerModalProps) {
  const [search, setSearch] = useState('')
  const [pendingSlug, setPendingSlug] = useState<string | null>(null)
  const [selectedMuscles, setSelectedMuscles] = useState<string[]>([])
  const [selectedEquipment, setSelectedEquipment] = useState<string[]>([])
  const [initializedFilterSlug, setInitializedFilterSlug] = useState<string | null>(null)

  useEffect(() => {
    if (!open) {
      setSearch('')
      setPendingSlug(null)
      setSelectedMuscles([])
      setSelectedEquipment([])
      setInitializedFilterSlug(null)
    }
  }, [open])

  const { data: currentExerciseDetails } = useQuery({
    queryKey: ['exercise-picker-current-exercise', userId, currentExerciseSlug],
    queryFn: () => apiGet<ExerciseDetails>(`/api/exercises/${encodeURIComponent(currentExerciseSlug ?? '')}?userId=${encodeURIComponent(userId)}`),
    enabled: open && mode === 'replace' && Boolean(currentExerciseSlug),
  })

  useEffect(() => {
    if (!open || mode !== 'replace' || !currentExerciseSlug || !currentExerciseDetails || initializedFilterSlug === currentExerciseSlug) {
      return
    }

    setSelectedMuscles(currentExerciseDetails.muscles)
    setInitializedFilterSlug(currentExerciseSlug)
  }, [currentExerciseDetails, currentExerciseSlug, initializedFilterSlug, mode, open])

  const queryString = useMemo(() => {
    const params = new URLSearchParams()
    params.set('userId', userId)
    if (search.trim()) {
      params.set('search', search.trim())
    }
    if (selectedMuscles.length > 0) {
      params.set('muscles', selectedMuscles.join(','))
    }
    if (selectedEquipment.length > 0) {
      params.set('equipment', selectedEquipment.join(','))
    }
    return params.toString()
  }, [search, selectedEquipment, selectedMuscles, userId])

  const { data, isLoading } = useQuery({
    queryKey: ['exercise-picker-catalog', userId, search, selectedMuscles.join(','), selectedEquipment.join(',')],
    queryFn: () => apiGet<ExerciseCatalogResponse>(`/api/exercises?${queryString}`),
    enabled: open,
  })

  const muscleFilters = useMemo(() => {
    const ordered = [...(currentExerciseDetails?.muscles ?? []), ...(data?.availableFilters.muscles ?? [])]
    return ordered.filter((item, index) => ordered.indexOf(item) === index).slice(0, 16)
  }, [currentExerciseDetails?.muscles, data?.availableFilters.muscles])

  const equipmentFilters = useMemo(() => data?.availableFilters.equipment ?? [], [data?.availableFilters.equipment])

  const items = useMemo(() => {
    const blocked = new Set(excludeSlugs ?? [])
    if (currentExerciseSlug && mode === 'replace') {
      blocked.add(currentExerciseSlug)
    }

    return (data?.items ?? []).filter((item) => {
      if (blocked.has(item.slug)) {
        return false
      }

      if (selectedMuscles.length === 0) {
        if (selectedEquipment.length === 0) {
          return true
        }

        return selectedEquipment.includes(item.equipment)
      }

      if (!selectedMuscles.every((muscle) => item.muscles.includes(muscle))) {
        return false
      }

      if (selectedEquipment.length === 0) {
        return true
      }

      return selectedEquipment.includes(item.equipment)
    })
  }, [currentExerciseSlug, data?.items, excludeSlugs, mode, selectedEquipment, selectedMuscles])

  async function handleSelect(item: ExerciseSummary) {
    try {
      setPendingSlug(item.slug)
      const details = await apiGet<ExerciseDetails>(`/api/exercises/${encodeURIComponent(item.slug)}?userId=${encodeURIComponent(userId)}`)
      await onSelect(details)
      onOpenChange(false)
    } finally {
      setPendingSlug(null)
    }
  }

  function toggleMuscleFilter(value: string) {
    setSelectedMuscles((current) => (current.includes(value) ? current.filter((item) => item !== value) : [...current, value]))
  }

  function toggleEquipmentFilter(value: string) {
    setSelectedEquipment((current) => (current.includes(value) ? current.filter((item) => item !== value) : [...current, value]))
  }

  const resolvedTitle = title ?? (mode === 'replace' ? 'Замена упражнения' : 'Добавить упражнение')
  const resolvedDescription = description ?? (mode === 'replace'
    ? `Выберите новое упражнение вместо «${currentExerciseName ?? 'текущего'}». Каталог открыт в режиме быстрой замены без дополнительных действий.`
    : 'Выберите упражнение, которое нужно добавить в текущую тренировку.')
  const actionLabel = mode === 'replace' ? 'Выбрать' : 'Добавить'

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/78 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(1040px,calc(100vw-24px))] max-h-[calc(100vh-32px)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-[34px] border border-white/10 bg-[#0c1016] text-white shadow-[0_30px_100px_rgba(0,0,0,0.55)]">
          <div className="border-b border-white/8 px-6 py-5 xl:px-8">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <Dialog.Title className="font-display text-4xl font-bold tracking-[-0.05em] text-white">{resolvedTitle}</Dialog.Title>
                <Dialog.Description className="mt-2 text-sm leading-7 text-white/62">{resolvedDescription}</Dialog.Description>
              </div>
              <Dialog.Close className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/5 text-white/70 transition hover:bg-white/8 hover:text-white">
                <X className="h-4 w-4" />
              </Dialog.Close>
            </div>
            <div className="mt-5 grid gap-4 xl:grid-cols-[1fr_auto] xl:items-center">
              <SearchField value={search} placeholder={mode === 'replace' ? 'Найти упражнение для замены...' : 'Найти упражнение для добавления...'} onChange={setSearch} />
              <div className="text-sm text-white/42">Найдено: {items.length}</div>
            </div>
            <div className="mt-4 space-y-3">
              <div>
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-white/38">Группы мышц</div>
                <div className="flex flex-wrap items-center gap-2">
                  {muscleFilters.map((muscle) => (
                    <button
                      key={muscle}
                      type="button"
                      onClick={() => toggleMuscleFilter(muscle)}
                      className={cn(
                        'inline-flex min-h-9 items-center rounded-full border px-3 py-2 text-xs font-semibold transition',
                        selectedMuscles.includes(muscle)
                          ? 'border-[#d6b05f]/28 bg-[#d6b05f]/12 text-[#f0d08c]'
                          : 'border-white/8 bg-white/5 text-white/68 hover:bg-white/8 hover:text-white',
                      )}
                    >
                      {muscle}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-white/38">Инвентарь</div>
                <div className="flex flex-wrap items-center gap-2">
                  {equipmentFilters.map((equipment) => (
                    <button
                      key={equipment}
                      type="button"
                      onClick={() => toggleEquipmentFilter(equipment)}
                      className={cn(
                        'inline-flex min-h-9 items-center rounded-full border px-3 py-2 text-xs font-semibold transition',
                        selectedEquipment.includes(equipment)
                          ? 'border-[#d6b05f]/28 bg-[#d6b05f]/12 text-[#f0d08c]'
                          : 'border-white/8 bg-white/5 text-white/68 hover:bg-white/8 hover:text-white',
                      )}
                    >
                      {equipment}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedMuscles([])
                      setSelectedEquipment([])
                      setSearch('')
                    }}
                    className="inline-flex min-h-9 items-center rounded-full border border-white/10 bg-white/4 px-3 py-2 text-xs font-semibold text-white/65 transition hover:bg-white/8 hover:text-white"
                  >
                    Сбросить
                  </button>
                </div>
              </div>
            </div>
            {mode === 'replace' && currentExerciseDetails?.muscles.length ? (
              <div className="mt-3 text-xs text-white/45">
                По умолчанию выбраны мышцы заменяемого упражнения: {currentExerciseDetails.muscles.join(', ')}.
              </div>
            ) : null}
          </div>

          <div className="max-h-[calc(100vh-240px)] overflow-y-auto px-6 py-5 xl:px-8">
            {isLoading ? (
              <div className="rounded-[24px] border border-white/8 bg-white/[0.03] px-5 py-10 text-center text-sm text-white/55">Загружаю каталог...</div>
            ) : items.length > 0 ? (
              <div className="space-y-3">
                {items.map((item) => (
                  <button
                    key={item.slug}
                    type="button"
                    onClick={() => void handleSelect(item)}
                    disabled={pendingSlug !== null}
                    className="grid w-full gap-4 rounded-[26px] border border-white/8 bg-white/[0.035] px-4 py-4 text-left transition hover:border-[#d6b05f]/28 hover:bg-white/[0.06] disabled:cursor-wait disabled:opacity-60 md:grid-cols-[156px_minmax(0,1fr)_auto] md:items-center"
                  >
                    <ExercisePickerPreview videoUrl={item.previewVideoUrl} title={item.name} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.22em] text-white/35">
                        <Search className="h-3.5 w-3.5" />
                        Каталог упражнений
                      </div>
                      <div className="mt-2 truncate font-display text-3xl font-bold tracking-[-0.04em] text-white">{item.name}</div>
                      <div className="mt-1 truncate text-sm text-white/45">{item.secondaryName}</div>
                      <div className="mt-3 flex flex-wrap gap-2 text-xs text-white/62">
                        {item.muscles.slice(0, 3).map((muscle) => (
                          <span key={muscle} className="rounded-full border border-white/8 bg-white/5 px-2.5 py-1">{muscle}</span>
                        ))}
                        <span className="rounded-full border border-white/8 bg-white/5 px-2.5 py-1">{item.equipment}</span>
                        <span className="rounded-full border border-white/8 bg-white/5 px-2.5 py-1">{item.difficultyLabel}</span>
                      </div>
                    </div>
                    <div className="flex items-center justify-end">
                      <span className={cn('inline-flex min-h-11 items-center rounded-2xl px-4 py-2 text-sm font-semibold', pendingSlug === item.slug ? 'bg-white/8 text-white/65' : 'sand-glow bg-linear-to-r from-[#b5852f] via-[#d6b05f] to-[#aa7b26] text-[#1b1303]')}>
                        {pendingSlug === item.slug ? (mode === 'replace' ? 'Заменяю...' : 'Добавляю...') : actionLabel}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="rounded-[24px] border border-dashed border-white/10 bg-white/[0.03] px-5 py-10 text-center text-sm text-white/55">
                По текущему запросу упражнений не найдено.
              </div>
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function ExercisePickerPreview({ videoUrl, title }: { videoUrl?: string; title: string }) {
  if (!videoUrl) {
    return <div className="hidden h-[92px] rounded-[18px] border border-white/8 bg-[#0b1017] md:block" />
  }

  return (
    <ExerciseVideoPlayer
      videoUrl={videoUrl}
      videoLabel={`${title} · превью`}
      lazyLoad
      wrapperClassName="hidden h-[92px] aspect-auto rounded-[18px] border border-white/8 bg-[#0b1017] md:block"
    />
  )
}