import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { machineScenarios } from '@/mocks/data'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { PhotoCaptureDialog } from '@/shared/ui/photo/photo-capture-dialog'

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
    if (String(input).startsWith('data:')) return new Response(new Blob(['photo'], { type: 'image/jpeg' }))
    if (String(input).includes('/api/photo-progress') && init?.method === 'POST') return new Response(JSON.stringify({ id: 1 }), { status: 200 })
    throw new Error(`Unexpected fetch ${String(input)}`)
  }))
})
afterEach(() => { cleanup(); client.clear(); vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('PhotoCaptureDialog', () => {
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

    const uploads = vi.mocked(fetch).mock.calls.filter(([input, init]) => String(input).includes('/api/photo-progress') && init?.method === 'POST')
    expect(uploads).toHaveLength(2)
    expect(onSaved).toHaveBeenCalledOnce()
    expect(onOpenChange).toHaveBeenCalledWith(false)
    view.unmount()
    await waitFor(() => expect(stopTrack).toHaveBeenCalled())
  })

  it('keeps the single emergency stop inside the active modal', async () => {
    renderDialog()
    const dialog = within(await screen.findByRole('dialog', { name: 'Фотофиксация' }))
    expect(screen.getAllByRole('button', { name: 'Аварийная остановка', exact: true, hidden: true })).toHaveLength(1)
    expect(dialog.getByRole('button', { name: 'Аварийная остановка', exact: true })).toBeVisible()
  })
})
