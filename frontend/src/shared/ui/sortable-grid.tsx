import { DndContext, MouseSensor, TouchSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core'
import { SortableContext, arrayMove, rectSortingStrategy, useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { useRef, type ButtonHTMLAttributes, type HTMLAttributes, type MouseEvent } from 'react'
import { cn } from '@/shared/lib/cn'

type SortableGridProps = HTMLAttributes<HTMLDivElement> & {
  ids: string[]
  onReorder: (ids: string[]) => void
}

/**
 * Grid whose cards can be dragged into a new order: mouse after a short move,
 * touch after a long press, so taps and scrolling keep working as before.
 */
export function SortableGrid({ ids, onReorder, children, onClickCapture, ...props }: SortableGridProps) {
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 300, tolerance: 8 } }),
  )
  // The release that ends a drag must not also open the card it was dropped on.
  const suppressClickRef = useRef(false)

  function handleDragEnd({ active, over }: DragEndEvent) {
    suppressClickRef.current = true
    window.setTimeout(() => { suppressClickRef.current = false }, 0)
    if (!over || active.id === over.id) return
    const from = ids.indexOf(String(active.id))
    const to = ids.indexOf(String(over.id))
    if (from < 0 || to < 0) return
    onReorder(arrayMove(ids, from, to))
  }

  function handleClickCapture(event: MouseEvent<HTMLDivElement>) {
    if (suppressClickRef.current) {
      event.preventDefault()
      event.stopPropagation()
      return
    }
    onClickCapture?.(event)
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd} onDragCancel={() => { suppressClickRef.current = false }}>
      <SortableContext items={ids} strategy={rectSortingStrategy}>
        <div {...props} onClickCapture={handleClickCapture}>{children}</div>
      </SortableContext>
    </DndContext>
  )
}

type SortableCardProps = ButtonHTMLAttributes<HTMLButtonElement> & { sortableId: string }

export function SortableCard({ sortableId, className, style, onClick, ...props }: SortableCardProps) {
  const { setNodeRef, listeners, transform, transition, isDragging } = useSortable({ id: sortableId })
  return (
    <button
      ref={setNodeRef}
      type="button"
      {...props}
      {...listeners}
      onClick={onClick}
      className={cn('sortable-card', className)}
      data-dragging={isDragging || undefined}
      style={{ ...style, transform: CSS.Translate.toString(transform), transition }}
    />
  )
}
