import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { machineScenarios } from '@/mocks/data'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { captureFrame, PhotoCaptureDialog } from '@/shared/ui/photo/photo-capture-dialog'

let client: QueryClient
const stopTrack = vi.fn()
const getUserMedia = vi.fn()
const onSaved = vi.fn()
const onOpenChange = vi.fn()
const stream = { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream

function renderDialog(open = true) {
  return render(<QueryClientProvider client={client}><MemoryRouter><FormaShell userName="Алексей" machine={machineScenarios.ready} onStop={vi.fn()}><PhotoCaptureDialog open={open} onOpenChange={onOpenChange} userId="alexey" onSaved={onSaved} /></FormaShell></MemoryRouter></QueryClientProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  getUserMedia.mockResolvedValue(stream)
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia } })
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue()
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue({ drawImage: vi.fn() } as unknown as CanvasRenderingContext2D)
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/jpeg;base64,photo')
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).startsWith('data:')) return new Response('photo', { headers: { 'Content-Type': 'image/jpeg' } })
    if (String(input).includes('/api/photo-progress') && init?.method === 'POST') return new Response(JSON.stringify({ id: 1 }), { status: 200 })
    throw new Error(`Unexpected fetch ${String(input)}`)
  }))
})
afterEach(() => { cleanup(); client.clear(); vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('PhotoCaptureDialog', () => {
  it.each([[720, 1280, 720, 1280], [2560, 1440, 1920, 1080]])('keeps the whole %ix%i camera frame for server-side person cropping', (width, height, targetWidth, targetHeight) => {
    const video = document.createElement('video')
    Object.defineProperties(video, {
      readyState: { value: 4 }, videoWidth: { value: width }, videoHeight: { value: height },
    })
    captureFrame(video)
    const context = video.ownerDocument.createElement('canvas').getContext('2d')!
    expect(context.drawImage).toHaveBeenCalledWith(video, 0, 0, width, height, 0, 0, targetWidth, targetHeight)
  })
  it('requests camera only when opened and stops every track on close', async () => {
    const view = renderDialog(false)
    expect(getUserMedia).not.toHaveBeenCalled()
    view.rerender(<QueryClientProvider client={client}><MemoryRouter><FormaShell userName="Алексей" machine={machineScenarios.ready} onStop={vi.fn()}><PhotoCaptureDialog open onOpenChange={onOpenChange} userId="alexey" /></FormaShell></MemoryRouter></QueryClientProvider>)
    expect(await screen.findByRole('dialog', { name: 'Фотофиксация' })).toBeVisible()
    expect(getUserMedia).toHaveBeenCalledTimes(1)
    view.unmount()
    expect(stopTrack).toHaveBeenCalled()
  })

  it('captures selected views, allows retake and uploads only after Save', async () => {
    const user = userEvent.setup()
    const view = renderDialog()
    const dialogElement = await screen.findByRole('dialog', { name: 'Фотофиксация' })
    const dialog = within(dialogElement)
    const video = dialogElement.querySelector('video')!
    Object.defineProperty(video, 'readyState', { configurable: true, value: 4 })
    Object.defineProperty(video, 'videoWidth', { configurable: true, value: 1280 })
    Object.defineProperty(video, 'videoHeight', { configurable: true, value: 720 })

    expect(dialog.getByRole('button', { name: 'Сохранить', exact: false })).toBeDisabled()
    await user.click(dialog.getByRole('button', { name: 'Без', exact: true }))
    await user.click(dialog.getByRole('button', { name: 'Снять', exact: true }))
    expect(dialog.getByRole('img', { name: 'Предпросмотр: спереди' })).toBeVisible()
    expect(dialog.getByText('1/3')).toBeVisible()
    expect(vi.mocked(fetch)).not.toHaveBeenCalledWith(expect.stringContaining('/api/photo-progress'), expect.anything())
    await user.click(dialog.getByRole('button', { name: 'Переснять', exact: true }))
    expect(dialog.queryByRole('img')).not.toBeInTheDocument()

    await user.click(dialog.getByRole('button', { name: 'Снять', exact: true }))
    await user.click(dialog.getByRole('tab', { name: /Сбоку/ }))
    const sideVideo = dialogElement.querySelector('video')!
    Object.defineProperty(sideVideo, 'readyState', { configurable: true, value: 4 })
    Object.defineProperty(sideVideo, 'videoWidth', { configurable: true, value: 1280 })
    Object.defineProperty(sideVideo, 'videoHeight', { configurable: true, value: 720 })
    await user.click(dialog.getByRole('button', { name: 'Снять', exact: true }))
    await user.click(dialog.getByRole('button', { name: /Сохранить \(2\)/ }))

    await waitFor(() => {
      expect(dialog.queryByRole('alert')?.textContent ?? '').toBe('')
      expect(onSaved).toHaveBeenCalledOnce()
    })
    const uploads = vi.mocked(fetch).mock.calls.filter(([input, init]) => String(input).includes('/api/photo-progress') && init?.method === 'POST')
    expect(uploads).toHaveLength(2)
    expect(onSaved).toHaveBeenCalledOnce()
    expect(onOpenChange).toHaveBeenCalledWith(false)
    view.unmount()
    await waitFor(() => expect(stopTrack).toHaveBeenCalled())
  })

  it.each([3, 5, 10])('counts down %i seconds before taking a photo', async (seconds) => {
    renderDialog()
    const dialog = within(await screen.findByRole('dialog', { name: 'Фотофиксация' }))
    const video = document.querySelector('video')!
    Object.defineProperty(video, 'readyState', { configurable: true, value: 4 })
    expect(dialog.getByRole('button', { name: '5 с', exact: true })).toHaveAttribute('aria-pressed', 'true')
    vi.useFakeTimers()
    fireEvent.click(dialog.getByRole('button', { name: `${seconds} с`, exact: true }))
    fireEvent.click(dialog.getByRole('button', { name: `Снять через ${seconds} с`, exact: true }))
    expect(dialog.getByRole('timer')).toHaveTextContent(`Снимок через${seconds}`)
    expect(dialog.getByRole('tab', { name: /Сбоку/ })).toBeDisabled()
    expect(dialog.getByRole('button', { name: '3 с', exact: true })).toBeDisabled()
    for (let remaining = seconds - 1; remaining >= 1; remaining--) {
      await act(async () => { vi.advanceTimersByTime(1000) })
      expect(dialog.getByRole('timer')).toHaveTextContent(`Снимок через${remaining}`)
      expect(dialog.queryByRole('img')).not.toBeInTheDocument()
      expect(HTMLCanvasElement.prototype.toDataURL).not.toHaveBeenCalled()
    }
    await act(async () => { vi.advanceTimersByTime(1000) })
    expect(dialog.queryByRole('timer')).not.toBeInTheDocument()
    expect(dialog.getByRole('img', { name: 'Предпросмотр: спереди' })).toBeVisible()
    expect(HTMLCanvasElement.prototype.toDataURL).toHaveBeenCalledOnce()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('cancels the countdown without taking a photo and allows changing the view', async () => {
    renderDialog()
    const dialog = within(await screen.findByRole('dialog', { name: 'Фотофиксация' }))
    vi.useFakeTimers()
    fireEvent.click(dialog.getByRole('button', { name: 'Снять через 5 с', exact: true }))
    await act(async () => { vi.advanceTimersByTime(1000) })
    fireEvent.click(dialog.getByRole('button', { name: 'Отменить снимок', exact: true }))
    await act(async () => { vi.advanceTimersByTime(10000) })
    expect(dialog.queryByRole('timer')).not.toBeInTheDocument()
    expect(HTMLCanvasElement.prototype.toDataURL).not.toHaveBeenCalled()
    fireEvent.click(dialog.getByRole('tab', { name: /Сбоку/ }))
    expect(dialog.getByRole('tab', { name: /Сбоку/ })).toHaveAttribute('aria-selected', 'true')
  })

  it.each([3, 5, 10])('takes front, side and back with a full %i-second countdown before each shot', async (seconds) => {
    renderDialog()
    const dialog = within(await screen.findByRole('dialog', { name: 'Фотофиксация' }))
    Object.defineProperty(document.querySelector('video')!, 'readyState', { configurable: true, value: 4 })
    vi.useFakeTimers()
    fireEvent.click(dialog.getByRole('button', { name: `${seconds} с`, exact: true }))
    fireEvent.click(dialog.getByRole('tab', { name: /Сзади/ }))
    fireEvent.click(dialog.getByRole('button', { name: 'Снять серию', exact: true }))
    const labels = ['Спереди', 'Сбоку', 'Сзади']
    for (let index = 0; index < labels.length; index++) {
      expect(dialog.getByRole('timer')).toHaveTextContent(`Серия · кадр ${index + 1} из 3 · ${labels[index]}`)
      expect(dialog.getByRole('tab', { name: new RegExp(labels[index]) })).toHaveAttribute('aria-selected', 'true')
      expect(dialog.getByRole('tab', { name: /Спереди/ })).toBeDisabled()
      expect(dialog.getByRole('button', { name: /^Сохранить/ })).toBeDisabled()
      expect(dialog.getByRole('button', { name: `${seconds} с`, exact: true })).toBeDisabled()
      for (let remaining = seconds; remaining >= 1; remaining--) {
        expect(dialog.getByRole('timer')).toHaveTextContent(`Снимок через${remaining}`)
        expect(HTMLCanvasElement.prototype.toDataURL).toHaveBeenCalledTimes(index)
        await act(async () => { vi.advanceTimersByTime(1000) })
      }
    }
    expect(HTMLCanvasElement.prototype.toDataURL).toHaveBeenCalledTimes(3)
    expect(dialog.queryByRole('timer')).not.toBeInTheDocument()
    expect(dialog.getByText('3/3')).toBeVisible()
    expect(dialog.getByRole('button', { name: 'Сохранить (3)' })).toBeEnabled()
    expect(dialog.getByRole('img', { name: 'Предпросмотр: сзади' })).toBeVisible()
    expect(fetch).not.toHaveBeenCalled()
    vi.useRealTimers()
    fireEvent.click(dialog.getByRole('button', { name: 'Сохранить (3)' }))
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce())
    const uploads = vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === 'POST')
    expect(uploads.map(([, init]) => (init!.body as FormData).get('view'))).toEqual(['front', 'side', 'back'])
  })

  it('cancels the rest of a series while keeping completed shots', async () => {
    renderDialog()
    const dialog = within(await screen.findByRole('dialog', { name: 'Фотофиксация' }))
    Object.defineProperty(document.querySelector('video')!, 'readyState', { configurable: true, value: 4 })
    vi.useFakeTimers()
    fireEvent.click(dialog.getByRole('button', { name: 'Снять серию' }))
    for (let tick = 0; tick < 5; tick++) await act(async () => { vi.advanceTimersByTime(1000) })
    expect(dialog.getByRole('timer')).toHaveTextContent('кадр 2 из 3 · Сбоку')
    fireEvent.click(dialog.getByRole('button', { name: 'Отменить серию' }))
    await act(async () => { vi.advanceTimersByTime(30000) })
    expect(HTMLCanvasElement.prototype.toDataURL).toHaveBeenCalledOnce()
    expect(dialog.getByText('1/3')).toBeVisible()
    expect(dialog.getByRole('button', { name: 'Сохранить', exact: true })).toBeEnabled()
    expect(dialog.queryByRole('timer')).not.toBeInTheDocument()
    fireEvent.click(dialog.getByRole('tab', { name: /Спереди/ }))
    expect(dialog.getByRole('img', { name: 'Предпросмотр: спереди' })).toBeVisible()
  })

  it('stops a series if the camera cannot provide the next frame', async () => {
    renderDialog()
    const dialog = within(await screen.findByRole('dialog', { name: 'Фотофиксация' }))
    vi.useFakeTimers()
    fireEvent.click(dialog.getByRole('button', { name: 'Снять серию' }))
    for (let tick = 0; tick < 5; tick++) await act(async () => { vi.advanceTimersByTime(1000) })
    expect(dialog.getByRole('alert')).toHaveTextContent('Камера ещё не готова')
    expect(dialog.queryByRole('timer')).not.toBeInTheDocument()
    expect(dialog.getByRole('button', { name: 'Снять серию' })).toBeDisabled()
    await act(async () => { vi.advanceTimersByTime(30000) })
    expect(HTMLCanvasElement.prototype.toDataURL).not.toHaveBeenCalled()
  })

  it('captures a series without a delay when the timer is off', async () => {
    renderDialog()
    const dialog = within(await screen.findByRole('dialog', { name: 'Фотофиксация' }))
    Object.defineProperty(document.querySelector('video')!, 'readyState', { configurable: true, value: 4 })
    vi.useFakeTimers()
    fireEvent.click(dialog.getByRole('button', { name: 'Без', exact: true }))
    fireEvent.click(dialog.getByRole('button', { name: 'Снять серию' }))
    for (let tick = 0; tick < 3; tick++) await act(async () => { vi.runOnlyPendingTimers() })
    expect(HTMLCanvasElement.prototype.toDataURL).toHaveBeenCalledTimes(3)
    expect(dialog.getByText('3/3')).toBeVisible()
    expect(dialog.queryByRole('timer')).not.toBeInTheDocument()
  })

  it('keeps a live video during a new series over existing drafts and stops on close', async () => {
    const view = renderDialog()
    const dialog = within(await screen.findByRole('dialog', { name: 'Фотофиксация' }))
    const video = document.querySelector('video')!
    Object.defineProperty(video, 'readyState', { configurable: true, value: 4 })
    fireEvent.click(dialog.getByRole('button', { name: 'Без', exact: true }))
    fireEvent.click(dialog.getByRole('button', { name: 'Снять', exact: true }))
    expect(video).not.toBeVisible()
    fireEvent.click(dialog.getByRole('button', { name: '5 с', exact: true }))
    vi.useFakeTimers()
    fireEvent.click(dialog.getByRole('button', { name: 'Снять серию' }))
    expect(video).toBeVisible()
    expect(dialog.queryByRole('img')).not.toBeInTheDocument()
    view.rerender(<QueryClientProvider client={client}><PhotoCaptureDialog open={false} onOpenChange={onOpenChange} userId="alexey" /></QueryClientProvider>)
    await act(async () => { vi.advanceTimersByTime(30000) })
    expect(HTMLCanvasElement.prototype.toDataURL).toHaveBeenCalledOnce()
    expect(stopTrack).toHaveBeenCalled()
  })

  it('clears the countdown when closed and reopened', async () => {
    const view = renderDialog()
    await screen.findByRole('dialog', { name: 'Фотофиксация' })
    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: 'Снять через 5 с', exact: true }))
    view.rerender(<QueryClientProvider client={client}><PhotoCaptureDialog open={false} onOpenChange={onOpenChange} userId="alexey" /></QueryClientProvider>)
    await act(async () => { vi.advanceTimersByTime(10000) })
    view.rerender(<QueryClientProvider client={client}><PhotoCaptureDialog open onOpenChange={onOpenChange} userId="alexey" /></QueryClientProvider>)
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()
    expect(HTMLCanvasElement.prototype.toDataURL).not.toHaveBeenCalled()
  })

  it('does not start a countdown when camera permission is denied', async () => {
    getUserMedia.mockRejectedValueOnce(new Error('NotAllowedError'))
    renderDialog()
    expect(await screen.findByRole('alert')).toHaveTextContent('Не удалось открыть камеру')
    expect(screen.getByRole('button', { name: 'Снять через 5 с', exact: true })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Снять серию', exact: true })).toBeDisabled()
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()
  })

  it('keeps the single emergency stop inside the active modal', async () => {
    renderDialog()
    const dialog = within(await screen.findByRole('dialog', { name: 'Фотофиксация' }))
    expect(screen.getAllByRole('button', { name: 'Аварийная остановка', exact: true, hidden: true })).toHaveLength(1)
    expect(dialog.getByRole('button', { name: 'Аварийная остановка', exact: true })).toBeVisible()
  })
})
