import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { groupProgressPhotos, ProgressPhotoGallery, type ProgressPhoto } from './progress-photo-gallery'

afterEach(cleanup)
const front: ProgressPhoto = { id: 1, view: 'front', takenAt: '2026-09-15T10:00:00Z', thumbnailUrl: '/front-thumb.jpg', imageUrl: '/front.jpg' }
const back: ProgressPhoto = { id: 2, view: 'back', takenAt: '2026-09-15T10:01:00Z', thumbnailUrl: '/back-thumb.jpg', imageUrl: '/back.jpg' }
const side: ProgressPhoto = { id: 3, view: 'side', takenAt: '2026-09-15T10:02:00Z', thumbnailUrl: '/side-thumb.jpg' }
function show(photos: ProgressPhoto[] = [], overrides = {}) {
  const props = { photos, loading: false, error: false, onPhoto: vi.fn(), onRetry: vi.fn(), onDelete: vi.fn(async (_id: number) => {}), ...overrides }
  render(<MemoryRouter><ProgressPhotoGallery {...props} /></MemoryRouter>)
  return props
}

describe('ProgressPhotoGallery', () => {
  it('confirms deletion of only the selected photo and supports cancellation', async () => {
    const user = userEvent.setup()
    const props = show([front, back, side])
    await user.click(screen.getByRole('button', { name: /Удалить фото: Спереди/ }))
    expect(screen.getByRole('dialog', { name: 'Удалить фото?' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Отмена' })).toHaveFocus()
    expect(props.onDelete).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Отмена' }))
    expect(props.onDelete).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: /Удалить фото: Сзади/ }))
    await user.click(screen.getByRole('button', { name: 'Удалить фото', exact: true }))
    expect(props.onDelete).toHaveBeenCalledExactlyOnceWith(back.id)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('keeps confirmation open and offers retry after deletion fails', async () => {
    const user = userEvent.setup()
    const props = show([front])
    props.onDelete.mockRejectedValueOnce(new Error('offline'))
    await user.click(screen.getByRole('button', { name: /Удалить фото: Спереди/ }))
    await user.click(screen.getByRole('button', { name: 'Удалить фото', exact: true }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось удалить фото')
    expect(screen.getByRole('img', { name: 'Спереди', hidden: true })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Удалить фото', exact: true }))
    expect(props.onDelete).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('groups all history newest first with fixed front, back, side columns', () => {
    show([side, { ...front, id: 4, takenAt: '2026-08-10T10:00:00Z' }, front, back])
    const rows = document.querySelectorAll('.photo-gallery-grid')
    expect(rows).toHaveLength(2)
    expect(within(rows[0] as HTMLElement).getAllByRole('img').map((image) => image.getAttribute('alt'))).toEqual(['Спереди', 'Сзади', 'Сбоку'])
    expect(screen.getByText('Последняя съёмка').closest('header')).toHaveTextContent('15 сентября 2026')
    expect(screen.getAllByText('Ракурс не добавлен')).toHaveLength(2)
  })

  it('does not discard duplicate shots of a view on the same day', () => {
    const groups = groupProgressPhotos([front, back, side, { ...front, id: 4, takenAt: '2026-09-15T11:00:00Z' }])
    expect(groups).toHaveLength(1)
    expect(groups[0].rows).toHaveLength(2)
    expect(groups[0].rows[0].map((photo) => photo?.id)).toEqual([4, 2, 3])
    expect(groups[0].rows[1].map((photo) => photo?.id)).toEqual([1, undefined, undefined])
    expect(groups[0].count).toBe(4)
  })

  it('opens full size photos, navigates with buttons and keys, closes with Escape', async () => {
    const user = userEvent.setup()
    show([side, front, back])
    await user.click(screen.getByRole('button', { name: /Открыть фото: Спереди/ }))
    const dialog = screen.getByRole('dialog', { name: 'Спереди' })
    expect(within(dialog).getByRole('img')).toHaveAttribute('src', expect.stringContaining('/front.jpg'))
    expect(within(dialog).getByRole('button', { name: 'Предыдущее фото' })).toBeDisabled()
    await user.click(within(dialog).getByRole('button', { name: 'Следующее фото' }))
    expect(screen.getByRole('dialog', { name: 'Сзади' })).toBeVisible()
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('dialog', { name: 'Сбоку' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Следующее фото' })).toBeDisabled()
    await user.keyboard('{ArrowLeft}')
    expect(screen.getByRole('dialog', { name: 'Сзади' })).toBeVisible()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Открыть фото: Спереди/ })).toHaveFocus()
  })

  it('offers capture for missing views', async () => {
    const props = show([front])
    await userEvent.click(screen.getAllByRole('button', { name: 'Сделать фото' })[0])
    expect(props.onPhoto).toHaveBeenCalledOnce()
  })

  it('handles unavailable images without showing broken image icons', () => {
    show([front])
    fireEvent.error(screen.getByRole('img', { name: 'Спереди' }))
    expect(screen.getByText('Снимок недоступен')).toBeVisible()
    expect(screen.queryByRole('img', { name: 'Спереди' })).not.toBeInTheDocument()
  })

  it('shows an actionable empty state', async () => {
    const props = show()
    await userEvent.click(screen.getByRole('button', { name: 'Сделать первые фото' }))
    expect(props.onPhoto).toHaveBeenCalledOnce()
    expect(screen.getByText('Здесь начинается ваша история')).toBeVisible()
  })

  it('shows loading rather than an empty gallery', () => {
    show([], { loading: true })
    expect(screen.getByRole('status')).toHaveTextContent('Загрузка фотографий')
    expect(screen.queryByText('Здесь начинается ваша история')).not.toBeInTheDocument()
  })

  it('offers retry when loading fails', async () => {
    const props = show([], { error: true })
    expect(screen.getByRole('alert')).toHaveTextContent('Не удалось загрузить фотографии')
    await userEvent.click(screen.getByRole('button', { name: 'Повторить' }))
    expect(props.onRetry).toHaveBeenCalledOnce()
  })

  it('compares the first and latest shots of a view with the weight measured around them', async () => {
    const user = userEvent.setup()
    const early = { ...front, id: 4, takenAt: '2026-08-10T10:00:00Z', imageUrl: '/early.jpg' }
    const measurements = [
      { id: 1, measuredAt: '2026-08-12T08:00:00Z', weightKg: 86, bodyFatPercent: null, chestCm: null, waistCm: null, hipsCm: null },
      { id: 2, measuredAt: '2026-09-14T08:00:00Z', weightKg: 84.2, bodyFatPercent: null, chestCm: null, waistCm: null, hipsCm: null },
    ]
    show([front, back, early], { measurements })
    const compare = screen.getByRole('heading', { name: 'Сравнение до и после' }).closest('section')!
    expect(within(compare).getByText('36 дней между снимками')).toBeVisible()
    expect(within(compare).getByRole('img', { name: 'До: Спереди' })).toHaveAttribute('src', expect.stringContaining('/early.jpg'))
    expect(within(compare).getByRole('img', { name: 'После: Спереди' })).toHaveAttribute('src', expect.stringContaining('/front.jpg'))
    expect(within(compare).getByText('−1,8 кг')).toBeVisible()
    fireEvent.change(within(compare).getByRole('slider', { name: 'Положение шторки' }), { target: { value: '20' } })
    expect(compare.querySelector('.photo-compare-before')).toHaveStyle({ clipPath: 'inset(0 80% 0 0)' })
    await user.click(within(compare).getByRole('button', { name: 'Рядом' }))
    expect(compare.querySelectorAll('.photo-compare-side figure')).toHaveLength(2)
    await user.click(within(compare).getByRole('button', { name: 'Сзади' }))
    expect(within(compare).getByText(/Это первый снимок ракурса «сзади»/)).toBeVisible()
    expect(within(compare).getByRole('button', { name: 'Сбоку' })).toBeDisabled()
  })

  it('nudges to refresh photos when the latest session is old', async () => {
    const user = userEvent.setup()
    const props = show([{ ...front, takenAt: '2020-01-10T10:00:00Z' }])
    await user.click(screen.getByRole('button', { name: /Пора обновить фото/ }))
    expect(props.onPhoto).toHaveBeenCalledOnce()
    expect(screen.getByText('одна съёмка')).toBeVisible()
  })
})
