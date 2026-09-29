import * as Popover from '@radix-ui/react-popover'
import { Activity, CalendarDays, CircleAlert, CircleCheck, CircleX, Cpu, Dumbbell, House, ListChecks, OctagonAlert, Settings, TrendingUp, UserRound, Wrench } from 'lucide-react'
import { useState, type PropsWithChildren, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { NavLink } from 'react-router-dom'
import type { MachineHealth } from '@/entities/machine/model/types'
import { navigationItems } from '@/shared/config/navigation'
import { getDriveLabel, getSafetyLabel } from '@/shared/lib/machine-status'
import { cn } from '@/shared/lib/cn'
import { useHardwareStore } from '@/stores/hardware-store'
import { useSafetyDockTarget } from '@/shared/ui/overlays/safety-dialog'
import { stopRaisePosition } from '@/features/modbus/api/modbus-api'
import { useModbusStore } from '@/features/modbus/lib/use-modbus-store'

const navigationIcons = {
  '/dashboard': House,
  '/builder': ListChecks,
  '/catalog': Dumbbell,
  '/calendar': CalendarDays,
  '/progress': TrendingUp,
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

export function TopNavigationMenu({ userName, systemBar }: { userName: string; systemBar?: ReactNode }) {
  const [profileMenuOpen, setProfileMenuOpen] = useState(false)

  return (
    <header className="forma-navigation forma-header glass-panel rounded-[28px] p-3">
      <div className="forma-header-brand flex items-center gap-3">
        <div aria-hidden="true" className="flex h-12 w-12 items-center justify-center rounded-2xl bg-linear-to-br from-[#edcb86] to-[#9b6f22] text-2xl font-black text-[#100a00]">
          F
        </div>
        <div className="forma-header-wordmark font-display text-[32px] font-bold tracking-[-0.04em] text-[#f4dfb4]">Forma</div>
      </div>

      <nav aria-label="Основная навигация" className="forma-header-nav flex flex-wrap justify-center gap-2">
        {navigationItems.map((item) => {
          const Icon = navigationIcons[item.path]

          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                cn(
                  'flex min-h-14 items-center gap-3 rounded-2xl border px-4 text-base font-medium transition focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#f4dfb4]',
                  isActive
                    ? 'border-[#d9ba71]/60 bg-[#d9ba71]/8 text-white shadow-[0_0_0_1px_rgba(217,186,113,0.1)]'
                    : 'border-transparent bg-transparent text-white/65 hover:border-white/10 hover:bg-white/4 hover:text-white',
                )
              }
            >
              <Icon className="h-5 w-5" aria-hidden="true" />
              {item.label}
            </NavLink>
          )
        })}
      </nav>
      <div className="forma-header-side">
        <Popover.Root open={profileMenuOpen} onOpenChange={setProfileMenuOpen}>
          <Popover.Trigger asChild>
            <button type="button" aria-label={`Меню профиля: ${userName}`} className="flex min-h-14 items-center gap-3 rounded-2xl border border-white/15 px-3 text-white hover:bg-white/6 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[#f4dfb4]">
              <span aria-hidden="true" className="flex h-10 w-10 items-center justify-center rounded-full bg-[#d6b05f]/20 text-xl font-bold text-[#f4dfb4]">{userName.trim().charAt(0)}</span>
            </button>
          </Popover.Trigger>
          <Popover.Portal>
            <Popover.Content aria-label="Профиль и настройки" align="end" sideOffset={12} className="z-40 w-72 rounded-2xl border border-white/15 bg-[#111925] p-3 text-white shadow-2xl">
              <div className="px-4 py-3 text-lg font-semibold">{userName}</div>
              <nav aria-label="Меню пользователя" className="space-y-2">
                {[
                  { path: '/profile', label: 'Профиль', icon: UserRound },
                  { path: '/settings', label: 'Настройки', icon: Settings },
                  { path: '/modbus', label: 'Modbus', icon: Cpu },
                  { path: '/settings/mechanics', label: 'Механика', icon: Wrench },
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
  )
}

export function TopSystemBar({ machine, onStop, stopLabel }: { machine?: MachineHealth; onStop: () => void; stopLabel?: string }) {
  const problems = machine ? getMachineProblems(machine) : []
  const connectionStatus = useHardwareStore((state) => state.connectionStatus)
  const modbusConnected = useModbusStore((state) => state.connectionStatus?.connected ?? false)
  const modbusMotion = useHardwareStore((state) => state.snapshot?.control?.adapter === 'modbus-rtu') || modbusConnected
  const connectionLost = connectionStatus === 'error' || connectionStatus === 'disconnected'
  const target = useSafetyDockTarget()
  const [detailsOpen, setDetailsOpen] = useState(false)
  const urgentProblem = machine?.safety === 'emergency_stop' ? getSafetyLabel(machine.safety) : problems.find((problem) => problem.tone === 'danger')?.label
  const status = urgentProblem ?? (connectionLost ? 'Нет связи с тренажёром' : problems[0]?.label ?? machine?.machineLabel ?? 'Статус тренажёра неизвестен')
  const StatusIcon = urgentProblem ? CircleX : connectionLost || problems.length || !machine ? CircleAlert : CircleCheck

  const dock = (
    <div role="group" className="forma-system-dock" style={{ pointerEvents: 'auto' }} aria-label="Состояние тренажёра и безопасность">
      <div className="forma-machine-status">
        <Popover.Root open={detailsOpen} onOpenChange={setDetailsOpen}>
          <Popover.Trigger asChild>
            <button type="button" className="forma-machine-status-button" aria-label={`Состояние тренажёра: ${status}`}>
              <StatusIcon aria-hidden="true" className={cn('forma-machine-status-icon', urgentProblem ? 'text-red-500' : connectionLost || problems.length || !machine ? 'text-amber-500' : 'text-emerald-500')} />
              <span role="status" className="forma-machine-status-text">{status}</span>
            </button>
          </Popover.Trigger>
          <Popover.Portal container={target ?? undefined}>
            <Popover.Content side="bottom" align="end" sideOffset={12} className="z-[110] max-h-[50vh] w-[min(90vw,32rem)] overflow-auto rounded-2xl border border-white/15 bg-[#111925] p-5 text-white shadow-2xl">
              <div className="font-semibold">Состояние тренажёра</div>
              {connectionLost ? <p className="mt-3 text-sm text-amber-500">Нет связи. Последние полученные данные могут быть неактуальны.</p> : null}
              <ul className="mt-3 space-y-3 text-sm">
                {(problems.length ? problems.map((problem) => problem.label) : [status, ...(machine ? [getSafetyLabel(machine.safety), getDriveLabel('left', machine.leftDrive), getDriveLabel('right', machine.rightDrive)] : [])]).map((label) => <li key={label}>{label}</li>)}
              </ul>
            </Popover.Content>
          </Popover.Portal>
        </Popover.Root>
      </div>
      <EmergencyStopButton onClick={modbusMotion ? () => { void stopRaisePosition().catch((error: unknown) => window.alert(`STOP не выполнен: ${error instanceof Error ? error.message : String(error)}. Используйте аппаратный E-STOP.`)) } : onStop} label={stopLabel ?? (modbusMotion ? 'STOP · подъём (не E-STOP)' : undefined)} />
    </div>
  )

  return target ? createPortal(dock, target) : dock
}

export function EmergencyStopButton({ onClick, label = 'Аварийная остановка' }: { onClick: () => void; label?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="forma-stop inline-flex items-center justify-center gap-2 bg-linear-to-r from-[#891610] via-[#d52f22] to-[#a61612] font-extrabold text-white"
    >
      <OctagonAlert className="h-6 w-6" aria-hidden="true" />
      <span>{label}</span>
    </button>
  )
}

export function FormaShell({ children, userName, machine, onStop, stopLabel, hideNavigation = false }: PropsWithChildren<{ userName: string; machine: MachineHealth; onStop: () => void; stopLabel?: string; hideNavigation?: boolean }>) {
  const liveMachine = useHardwareStore((state) => state.snapshot?.machine)
  const systemBar = <TopSystemBar machine={liveMachine ?? machine} onStop={onStop} stopLabel={stopLabel} />

  return (
    <div className="forma-shell">
      {hideNavigation
        ? <header className="forma-navigation forma-navigation-compact">{systemBar}</header>
        : <TopNavigationMenu key={userName} userName={userName} systemBar={systemBar} />}
      <main className="forma-main">
        {children}
      </main>
    </div>
  )
}