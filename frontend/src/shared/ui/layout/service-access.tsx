import { TriangleAlert } from 'lucide-react'
import { createContext, useContext, useEffect, useId, useState, type PropsWithChildren } from 'react'
import { Link, Outlet } from 'react-router-dom'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { useAppStore } from '@/stores/app-store'
import { useHardwareStore } from '@/stores/hardware-store'

type ServiceAccess = { unlocked: boolean; unlock: () => void }

// No provider means locked. This acknowledgement is deliberately not persisted
// or derived from URL params, mock settings, a PIN flag, or hardware service mode.
const ServiceAccessContext = createContext<ServiceAccess | null>(null)

function SettingsAccessProvider() {
  const [unlocked, setUnlocked] = useState(false)

  return (
    <ServiceAccessContext.Provider value={{ unlocked, unlock: () => setUnlocked(true) }}>
      <Outlet />
    </ServiceAccessContext.Provider>
  )
}

/** Mount only at /settings. Route unmount and user changes discard the access state. */
export function SettingsLayout() {
  const selectedUserId = useAppStore((state) => state.selectedUserId)

  // Remount synchronously on identity changes, including a return to a previous user.
  return <SettingsAccessProvider key={selectedUserId === null ? 'no-user' : `user:${selectedUserId}`} />
}

/** embedded uses the settings screen's existing shell and emergency-stop overlay. */
export function ServiceAccessGate({ children, embedded = false }: PropsWithChildren<{ embedded?: boolean }>) {
  const access = useContext(ServiceAccessContext)

  if (access?.unlocked) {
    return children
  }

  return <ServiceAccessWarning embedded={embedded} onConfirm={access?.unlock} />
}

function ServiceAccessWarning({ embedded, onConfirm }: { embedded: boolean; onConfirm?: () => void }) {
  const [acknowledged, setAcknowledged] = useState(false)
  const titleId = useId()
  const warning = (
    <div className="flex min-h-[60vh] items-center justify-center">
      <section aria-labelledby={titleId} className="w-full max-w-2xl rounded-[32px] border border-[#d6b05f]/35 bg-[#20170b] p-8 text-white">
        <TriangleAlert className="mx-auto h-12 w-12 text-[#f2cf87]" aria-hidden="true" />
        <h1 id={titleId} className="mt-5 text-center font-display text-3xl font-bold text-[#f4dfb4]">Сервисный раздел</h1>
        <p className="mt-4 text-lg leading-8 text-white/80">
          Технические настройки и команды могут повлиять на движение и безопасность тренажёра. Раздел предназначен для обслуживания подготовленным специалистом.
        </p>
        <p className="mt-4 leading-7 text-white/65">
          Это защита интерфейса от случайного входа, а не авторизация backend или проверка PIN. Проверка сервисного PIN на backend не реализована.
          Открытие раздела не включает сервисный режим тренажёра и не отправляет команды. Аппаратные проверки безопасности сохраняются.
        </p>
        <label className="mt-6 flex min-h-16 cursor-pointer items-center gap-4 rounded-2xl border border-white/15 p-4">
          <input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} className="h-6 w-6 shrink-0 accent-[#d6b05f]" />
          <span>Понимаю риски изменения технических настроек</span>
        </label>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Button type="button" disabled={!acknowledged || !onConfirm} onClick={() => { if (acknowledged) onConfirm?.() }}>Открыть сервисный раздел</Button>
          <Button asChild variant="secondary"><Link to="/settings?tab=overview" replace>Отмена — к настройкам</Link></Button>
        </div>
      </section>
    </div>
  )

  return embedded ? warning : <LockedServiceShell>{warning}</LockedServiceShell>
}

function LockedServiceShell({ children }: PropsWithChildren) {
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const snapshot = useHardwareStore((state) => state.snapshot)
  const runCommand = useHardwareStore((state) => state.runCommand)
  const hardwareError = useHardwareStore((state) => state.errorMessage)

  useEffect(() => {
    if (snapshot?.safety.state === 'emergency_stop') {
      setEmergencyStopActive(true)
    }
  }, [setEmergencyStopActive, snapshot?.safety.state])

  return (
    <FormaShell
      userName={selectedUserId === 'elena' ? 'Елена' : selectedUserId === 'guest' ? 'Гость' : 'Алексей'}
      machine={snapshot?.machine ?? { machineState: 'blocked', machineLabel: 'Нет данных о тренажёре', safety: 'disabled', leftDrive: 'error', rightDrive: 'error', calibration: 'Нет данных' }}
      onStop={() => {
        setEmergencyStopActive(true)
        void runCommand({ action: 'trigger_emergency_stop', userId: selectedUserId }).catch(() => {})
      }}
    >
      {hardwareError ? <p role="alert" className="text-[#ffb4a7]">{hardwareError}</p> : null}
      {children}
      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}