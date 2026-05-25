import * as Dialog from '@radix-ui/react-dialog'
import { useQuery } from '@tanstack/react-query'
import { LoaderCircle, X } from 'lucide-react'
import { apiGet } from '@/shared/api/client'
import { ExerciseDetailsModal } from '@/shared/ui/stage2/screen-components'
import type { ExerciseDetails, ExerciseVideoGender } from '@/entities/exercise/model/types'

export function ExerciseDetailsDialog({
  open,
  onOpenChange,
  userId,
  exerciseSlug,
  exerciseName,
  preferredVideoGender = 'male',
  onOpenFullScreen,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  userId: string
  exerciseSlug?: string | null
  exerciseName?: string
  preferredVideoGender?: ExerciseVideoGender
  onOpenFullScreen?: () => void
}) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['exercise-details-dialog', userId, exerciseSlug],
    queryFn: () => apiGet<ExerciseDetails>(`/api/exercises/${encodeURIComponent(exerciseSlug ?? '')}?userId=${encodeURIComponent(userId)}`),
    enabled: open && Boolean(exerciseSlug),
  })

  if (!open) {
    return null
  }

  if (data) {
    return (
      <ExerciseDetailsModal
        exercise={data}
        open={open}
        onOpenChange={onOpenChange}
        onOpenFullScreen={onOpenFullScreen}
        preferredVideoGender={preferredVideoGender}
      />
    )
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[min(640px,calc(100vw-24px))] -translate-x-1/2 -translate-y-1/2 rounded-[34px] border border-white/10 bg-[#0c0f14] p-6 text-white shadow-[0_30px_100px_rgba(0,0,0,0.55)] xl:p-8">
          <Dialog.Close aria-label="Закрыть модальное окно" title="Закрыть модальное окно" className="absolute right-6 top-6 inline-flex h-12 w-12 items-center justify-center rounded-full border border-white/10 bg-white/4 text-white/65 xl:right-8 xl:top-8">
            <X className="h-4 w-4" />
          </Dialog.Close>
          <div className="pr-16 xl:pr-20">
            <div>
              <Dialog.Title className="font-display text-4xl font-bold tracking-[-0.05em] text-white">{exerciseName ?? 'Карточка упражнения'}</Dialog.Title>
              <Dialog.Description className="mt-2 text-sm leading-7 text-white/62">
                {isError ? 'Не удалось загрузить детальную карточку упражнения.' : 'Загружаю детальную карточку упражнения...'}
              </Dialog.Description>
            </div>
          </div>
          <div className="mt-8 flex min-h-40 items-center justify-center rounded-[28px] border border-white/8 bg-white/4">
            {isError ? <div className="text-sm text-white/65">Данные упражнения временно недоступны.</div> : <LoaderCircle className="h-8 w-8 animate-spin text-white/80" />}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}