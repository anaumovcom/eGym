import * as Popover from '@radix-ui/react-popover'
import { Activity, CalendarDays, CircleAlert, CircleCheck, CircleX, Cpu, Dumbbell, House, ListChecks, OctagonAlert, RotateCcw, Settings, TrendingUp, Trophy, UserRound } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState, type PropsWithChildren, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { NavLink } from 'react-router-dom'
import { CoachMiniDebug } from '@/features/coach/ui/coach-mini-debug'
import { localAudioRuntime } from '@/features/coach/audio/local-audio-runtime'
import { startCoachLiveRuntime } from '@/features/coach/live/coach-live-runtime'
import { useAppStore } from '@/stores/app-store'
import type { MachineHealth } from '@/entities/machine/model/types'
import type { HardwareSnapshot } from '@/features/hardware/model/types'
import { navigationItems } from '@/shared/config/navigation'
import { getDriveLabel, getSafetyLabel } from '@/shared/lib/machine-status'
import { cn } from '@/shared/lib/cn'
import { useHardwareStore } from '@/stores/hardware-store'
import { useSafetyDockTarget } from '@/shared/ui/overlays/safety-dialog'

const navigationIcons = {
  '/dashboard': House,
  '/builder': ListChecks,
  '/catalog': Dumbbell,
  '/calendar': CalendarDays,
  '/progress': TrendingUp,
  '/achievements': Trophy,
  '/fatigue': Activity,
}

type MachineProblem = {
  label: string
  tone: 'warning' | 'danger'
}

function getMachineProblems(machine: MachineHealth): MachineProblem[] {
  const problems: MachineProblem[] = []

  if (machine.machineState === 'warning' || machine.machineState === 'blocked') {
    problems.push({
      label: machine.machineLabel,
      tone: machine.machineState === 'blocked' ? 'danger' : 'warning',
    })
  }

  if (machine.leftDrive === 'warning' || machine.leftDrive === 'error') {
    problems.push({
      label: getDriveLabel('left', machine.leftDrive),
      tone: machine.leftDrive === 'error' ? 'danger' : 'warning',
    })
  }

  if (machine.rightDrive === 'warning' || machine.rightDrive === 'error') {
    problems.push({
      label: getDriveLabel('right', machine.rightDrive),
      tone: machine.rightDrive === 'error' ? 'danger' : 'warning',
    })
  }

  if (machine.safety === 'disabled' || machine.safety === 'emergency_stop') {
    problems.push({
      label: getSafetyLabel(machine.safety),
      tone: machine.safety === 'emergency_stop' ? 'danger' : 'warning',
    })
  }

  return problems
}

function getMachineDetails(snapshot: HardwareSnapshot | null, machine?: MachineHealth): string[] {
  if (!snapshot) return []
  const details: string[] = []
  const control = snapshot.control
  if (control?.faultCode) details.push(`Причина блокировки: ${control.faultCode}`)
  if (machine && machine.machineState !== 'ready' && snapshot.safety.message && snapshot.safety.message !== control?.faultCode) {
    details.push(snapshot.safety.message)
  }
  for (const drive of snapshot.drives) {
    if (drive.status !== 'error' && drive.connected) continue
    const side = drive.side === 'left' ? 'Левый привод' : 'Правый привод'
    details.push(`${side}: ${drive.errorMessage || (drive.connected ? 'ошибка' : 'нет связи')}${drive.errorCode ? ` (${drive.errorCode})` : ''}`)
  }
  if (control && control.mode === 'fault') {
    if (!control.commOk) details.push('Нет связи с приводами')
    if (control.powerOk === false) details.push('Питание приводов не подтверждено')
    const failedPost = (control.postResults ?? []).filter((item) => !item.passed && item.severity === 'critical')
    for (const item of failedPost) details.push(`Самотест: ${item.label} — ${item.detail}`)
  }
  const panel = snapshot.panel
  if (panel?.enabled) {
    if (panel.faultCode) details.push(`Панель управления: ошибка ${panel.faultCode}`)
    if (panel.stopLatched) details.push('Панель управления: кнопка СТОП зафиксирована')
    if (!panel.inputHealthy) details.push('Панель управления: неисправность входов')
  }
  details.push(...snapshot.alerts)
  return [...new Set(details.filter(Boolean))]
}

export function TopNavigationMenu({ userName, systemBar }: { userName: string; systemBar?: ReactNode }) {
  const [profileMenuOpen, setProfileMenuOpen] = useState(false)

  return (
    <div className="forma-menu-band">
      <header className="forma-navigation forma-header">
        <div className="forma-header-brand flex items-center">
          <div aria-hidden="true" className="forma-brand-mark flex items-center justify-center font-black">F</div>
          <div className="forma-header-wordmark font-display font-bold tracking-[-0.04em]">Forma</div>
        </div>
        <nav aria-label="Основная навигация" className="forma-header-nav">
          {navigationItems.map((item) => {
            const Icon = navigationIcons[item.path]

            return (
              <NavLink
                key={item.path}
                to={item.path}
                title={item.label}
                className="flex items-center font-medium transition"
              >
                <Icon className="h-5 w-5" aria-hidden="true" />
                <span className="forma-nav-label">{item.label}</span>
              </NavLink>
            )
          })}
        </nav>
        <div className="forma-header-side">
          <Popover.Root open={profileMenuOpen} onOpenChange={setProfileMenuOpen}>
            <Popover.Trigger asChild>
              <button type="button" aria-label={`Меню профиля: ${userName}`} className="forma-profile-trigger flex items-center border text-white hover:bg-white/6">
                <span aria-hidden="true" className="forma-profile-avatar flex items-center justify-center rounded-full font-bold">{userName.trim().charAt(0)}</span>
              </button>
            </Popover.Trigger>
            <Popover.Portal>
              <Popover.Content aria-label="Профиль и настройки" align="end" sideOffset={12} className="forma-system-popover z-40 w-72 rounded-2xl border border-white/15 bg-[#111925] p-3 text-white shadow-2xl">
                <div className="px-4 py-3 text-lg font-semibold">{userName}</div>
                <nav aria-label="Меню пользователя" className="space-y-2">
                  {[
                    { path: '/profile', label: 'Профиль', icon: UserRound },
                    { path: '/settings', label: 'Настройки', icon: Settings },
                    { path: '/modbus', label: 'Modbus', icon: Cpu },
                  ].map((item) => (
                    <NavLink key={item.path} to={item.path} onClick={() => setProfileMenuOpen(false)} className="flex min-h-14 items-center gap-3 rounded-xl px-4 hover:bg-white/8 focus-visible:outline-2 focus-visible:outline-[#f4dfb4]">
                      <item.icon className="h-5 w-5" aria-hidden="true" />
                      {item.label}
                    </NavLink>
                  ))}
                </nav>
              </Popover.Content>
            </Popover.Portal>
          </Popover.Root>
          {systemBar}
        </div>
      </header>
    </div>
  )
}

export function MotorForceReadout() {
  const control = useHardwareStore((state) => state.snapshot?.control)
  const torque = control?.driveTorquePercent
  const force = control?.driveForceKg
  const known = typeof torque === 'number' && typeof force === 'number'

  return (
    <div className="forma-motor-force" aria-label="Усилие на двигателях" title="Суммарное усилие двигателей: момент (% номинала) и кг">
      <span>Моторы</span>
      <span>{known ? `${torque.toFixed(1)} %` : '— %'}</span>
      <span>{known ? `${force.toFixed(1)} кг` : '— кг'}</span>
    </div>
  )
}

export function ResetBlockButton({ machine }: { machine?: MachineHealth }) {
  const runCommand = useHardwareStore((state) => state.runCommand)
  const setError = useHardwareStore((state) => state.setErrorMessage)
  const snapshot = useHardwareStore((state) => state.snapshot)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const [pending, setPending] = useState(false)
  const safetyState = snapshot?.safety.state
  const hardwareStopped = safetyState === 'emergency_stop' || snapshot?.control?.mode === 'estop'
  const observedStop = useRef(hardwareStopped)
  // The dock remounts inside dialogs. Only a confirmed stop-to-ready transition dismisses the overlay.
  useEffect(() => {
    if (hardwareStopped) {
      observedStop.current = true
    } else if (observedStop.current && safetyState === 'enabled') {
      observedStop.current = false
      setEmergencyStopActive(false)
    }
  }, [hardwareStopped, safetyState, setEmergencyStopActive])
  const blocked = machine?.machineState === 'blocked' || machine?.safety === 'emergency_stop' || machine?.leftDrive === 'error' || machine?.rightDrive === 'error'
  if (!blocked) return null

  return (
    <button
      type="button"
      className="forma-reset-block inline-flex items-center gap-2 rounded-2xl border border-amber-400/50 px-3 text-sm font-semibold text-amber-200 hover:bg-amber-400/10 disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#f4dfb4]"
      disabled={pending}
      title="Снять СТОП и сбросить ошибку приводов, блокирующую тренажёр"
      onClick={() => {
        setPending(true)
        const emergencyStop = machine?.safety === 'emergency_stop' || hardwareStopped
        // E-stop has a separate guarded clear path; reset_fault intentionally refuses an active STOP.
        void runCommand({ action: emergencyStop ? 'clear_emergency_stop' : 'reset_fault' })
          .then((response) => {
            if (emergencyStop && response.snapshot.safety.state !== 'emergency_stop' && response.snapshot.control?.mode !== 'estop') {
              setEmergencyStopActive(false)
            }
          })
          .catch((error: unknown) => setError(error instanceof Error ? error.message : 'Не удалось сбросить ошибку тренажёра.'))
          .finally(() => setPending(false))
      }}
    >
      <RotateCcw className="h-5 w-5" aria-hidden="true" />
      <span>Сбросить ошибку</span>
    </button>
  )
}

export function DisableServiceModeButton() {
  const serviceMode = useHardwareStore(state => state.snapshot?.serviceMode === true)
  const runCommand = useHardwareStore(state => state.runCommand)
  const setError = useHardwareStore(state => state.setErrorMessage)
  const selectedUserId = useAppStore(state => state.selectedUserId)
  const [pending, setPending] = useState(false)
  if (!serviceMode) return null

  return <button
    type="button"
    className="forma-reset-block inline-flex items-center gap-2 rounded-2xl border border-amber-400/50 px-3 text-sm font-semibold text-amber-200 hover:bg-amber-400/10 disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#f4dfb4]"
    disabled={pending}
    aria-busy={pending}
    title="Выйти из сервисного режима без сброса аварий и запуска движения"
    onClick={() => {
      setPending(true)
      void runCommand({ action: 'toggle_service_mode', userId: selectedUserId, serviceMode: false })
        .catch((error: unknown) => setError(error instanceof Error ? error.message : 'Не удалось отключить сервисный режим.'))
        .finally(() => setPending(false))
    }}
  >
    <Settings className="h-5 w-5" aria-hidden="true" />
    <span>Отключить сервисный режим</span>
  </button>
}

export function TopSystemBar({ machine, onStop }: { machine?: MachineHealth; onStop: () => void }) {
  const selectedUserId = useAppStore(state => state.selectedUserId)
  useEffect(() => { void localAudioRuntime.refreshSavedPreferences() }, [selectedUserId])
  useEffect(() => { startCoachLiveRuntime() }, [])
  const problems = machine ? getMachineProblems(machine) : []
  const connectionStatus = useHardwareStore((state) => state.connectionStatus)
  const connectionLost = connectionStatus === 'error' || connectionStatus === 'disconnected'
  const snapshot = useHardwareStore((state) => state.snapshot)
  const details = problems.length ? getMachineDetails(snapshot, machine) : []
  const target = useSafetyDockTarget()
  const [detailsOpen, setDetailsOpen] = useState(false)
  const urgentProblem = machine?.safety === 'emergency_stop' ? getSafetyLabel(machine.safety) : problems.find((problem) => problem.tone === 'danger')?.label
  const status = urgentProblem ?? (connectionLost ? 'Нет связи с тренажёром' : problems[0]?.label ?? machine?.machineLabel ?? 'Статус тренажёра неизвестен')
  const StatusIcon = urgentProblem ? CircleX : connectionLost || problems.length || !machine ? CircleAlert : CircleCheck

  const dock = (
    <div role="group" className="forma-system-dock" style={{ pointerEvents: 'auto' }} aria-label="Состояние тренажёра и безопасность">
      <CoachMiniDebug />
      <MotorForceReadout />
      <DisableServiceModeButton />
      <ResetBlockButton machine={machine} />
      <div className="forma-machine-status">
        <Popover.Root open={detailsOpen} onOpenChange={setDetailsOpen}>
          <Popover.Trigger asChild>
            <button type="button" className="forma-machine-status-button" aria-label={`Состояние тренажёра: ${status}`}>
              <StatusIcon aria-hidden="true" className={cn('forma-machine-status-icon', urgentProblem ? 'text-red-500' : connectionLost || problems.length || !machine ? 'text-amber-500' : 'text-emerald-500')} />
              <span role="status" className="forma-machine-status-text">{status}</span>
            </button>
          </Popover.Trigger>
          <Popover.Portal container={target ?? undefined}>
            <Popover.Content side="bottom" align="end" sideOffset={12} className="forma-system-popover z-[110] max-h-[50vh] w-[min(90vw,32rem)] overflow-auto rounded-2xl border border-white/15 bg-[#111925] p-5 text-white shadow-2xl">
              <div className="font-semibold">Состояние тренажёра</div>
              {connectionLost ? <p className="mt-3 text-sm text-amber-500">Нет связи. Последние полученные данные могут быть неактуальны.</p> : null}
              <ul className="mt-3 space-y-3 text-sm">
                {(problems.length ? problems.map((problem) => problem.label) : [status, ...(machine ? [getSafetyLabel(machine.safety), getDriveLabel('left', machine.leftDrive), getDriveLabel('right', machine.rightDrive)] : [])]).map((label) => <li key={label}>{label}</li>)}
              </ul>
              {details.length ? (
                <>
                  <div className="mt-4 font-semibold">Подробности</div>
                  <ul className="mt-2 space-y-2 text-sm text-white/80">
                    {details.map((detail) => <li key={detail}>{detail}</li>)}
                  </ul>
                </>
              ) : null}
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>
      </div>
      <EmergencyStopButton onClick={onStop} />
    </div>
  )

  return target ? createPortal(dock, target) : dock
}

export function EmergencyStopButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      aria-label="Аварийная остановка"
      onClick={onClick}
      className="forma-stop inline-flex items-center justify-center gap-2 bg-linear-to-r from-[#891610] via-[#d52f22] to-[#a61612] font-extrabold text-white"
    >
      <OctagonAlert className="h-6 w-6" aria-hidden="true" />
      <span>Аварийная остановка</span>
    </button>
  )
}

export function FormaShell({ children, userName, machine, onStop, hideNavigation = false, legacy = false }: PropsWithChildren<{ userName: string; machine: MachineHealth; onStop: () => void; hideNavigation?: boolean; legacy?: boolean }>) {
  useLayoutEffect(() => {
    const root = document.documentElement
    const previous = root.getAttribute('data-forma-theme')
    if (legacy) root.removeAttribute('data-forma-theme')
    else root.setAttribute('data-forma-theme', 'broadcast-blue')
    return () => {
      if (previous === null) root.removeAttribute('data-forma-theme')
      else root.setAttribute('data-forma-theme', previous)
    }
  }, [legacy])
  const liveMachine = useHardwareStore((state) => state.snapshot?.machine)
  const systemBar = <TopSystemBar machine={liveMachine ?? machine} onStop={onStop} />

  return (
    <div className={cn('forma-shell', !hideNavigation && 'forma-shell-with-menu')}>
      {hideNavigation
        ? <header className="forma-navigation forma-navigation-compact">{systemBar}</header>
        : <TopNavigationMenu key={userName} userName={userName} systemBar={systemBar} />}
      <main className="forma-main">
        {children}
      </main>
    </div>
  )
}
