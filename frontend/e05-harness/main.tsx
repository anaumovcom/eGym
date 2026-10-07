/// <reference types="vite/client" />
import { createRoot } from 'react-dom/client'
import { useState } from 'react'
import { MemoryRouter } from 'react-router-dom'
import * as Dialog from '@radix-ui/react-dialog'
import { FormaShell } from '../src/shared/ui/layout/forma-shell'
import { SafetyDialogContent } from '../src/shared/ui/overlays/safety-dialog'
import { CoachLocalPreview } from '../src/features/coach/ui/coach-mini-debug'
import { localAudioRuntime, changeInputs, markTrusted, activations, contextState, history } from './runtime'
import { LOCAL_FIXTURE_CATALOG } from '../src/features/coach/audio/fixture-pack-storage'
import { commands } from './stores'
import { renderOffline } from './offline'
import '../src/app/styles.css'

// Defence in depth: only Vite's explicit local module/style loads are allowed.
const forbidden = () => { throw new Error('Network disabled in E05 harness') }
window.fetch = forbidden
XMLHttpRequest.prototype.open = forbidden
window.WebSocket = class { constructor() { forbidden() } } as unknown as typeof WebSocket
window.EventSource = class { constructor() { forbidden() } } as unknown as typeof EventSource
navigator.sendBeacon = forbidden

const params = new URLSearchParams(location.search)
const scale = Number(params.get('scale') ?? 1)
const nativeSize = parseFloat(getComputedStyle(document.documentElement).fontSize)
document.documentElement.style.fontSize = `${nativeSize * scale}px`

function Harness() {
  const [safety, setSafety] = useState(false)
  const [mute, setMute] = useState(false)
  const openSafety = () => { changeInputs({ emergency: true }); setSafety(true) }
  acceptance.openSafety = openSafety
  return <MemoryRouter><FormaShell userName="TEST only" hideNavigation={params.get('compact') === '1'} onStop={openSafety}
    machine={{ machineState: 'ready', machineLabel: 'TEST — no hardware', safety: 'enabled', leftDrive: 'connected', rightDrive: 'connected', calibration: 'TEST only' }}>
    <h1>E05 isolated acceptance</h1>
    <p>No backend, provider, persistence or motor. Synthetic TEST tones only.</p>
    <div onClickCapture={markTrusted} onKeyDownCapture={markTrusted}><CoachLocalPreview /></div>
    <button className="rt-button" onClick={() => { const next = !mute; setMute(next); changeInputs({ general: { soundEnabled: !next, voiceHintsEnabled: true, volume: 1 } }) }}>{mute ? 'Unmute TEST' : 'Mute TEST'}</button>
    <button className="rt-button" onClick={openSafety}>Open TEST safety modal</button>
    <Dialog.Root open={safety} onOpenChange={value => { setSafety(value); changeInputs({ emergency: value }) }}>
      <Dialog.Portal><Dialog.Overlay className="fixed inset-0 z-50 bg-black/60" />
        <SafetyDialogContent className="glass-panel rounded-2xl p-5">
          <Dialog.Title>TEST safety modal — no motor</Dialog.Title>
          <Dialog.Description>Audio cancelled. AI diagnostics disabled while safety dock is active.</Dialog.Description>
          <Dialog.Close className="rt-button">Close TEST safety modal</Dialog.Close>
        </SafetyDialogContent>
      </Dialog.Portal>
    </Dialog.Root>
  </FormaShell></MemoryRouter>
}

export const acceptance = { renderOffline, snapshot: localAudioRuntime.getSnapshot, activations, contextState, commands, history,
  fixtureCatalog: LOCAL_FIXTURE_CATALOG, openSafety: () => {} }
declare global { interface Window { e05: typeof acceptance } }
window.e05 = acceptance
createRoot(document.getElementById('root')!).render(<Harness />)