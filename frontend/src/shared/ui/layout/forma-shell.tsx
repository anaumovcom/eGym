import { CalendarDays, Dumbbell, HeartPulse, House, OctagonAlert, PanelTop, Settings, Sparkles, UserRound, Wrench } from 'lucide-react'
import type { PropsWithChildren } from 'react'
import { NavLink } from 'react-router-dom'
import type { MachineHealth } from '@/entities/machine/model/types'
import { getDriveLabel, getDriveTone, getMachineTone, getSafetyLabel, getSafetyTone } from '@/shared/lib/machine-status'
import { navigationItems } from '@/shared/config/navigation'
import { cn } from '@/shared/lib/cn'
import { DriveStatusBadge, MachineStatusBadge, SafetyStatusBadge } from '@/shared/ui/status/status-components'

const icons = [House, Sparkles, PanelTop, CalendarDays, Wrench, Dumbbell, Dumbbell, Sparkles, HeartPulse, UserRound, Settings]

export function LeftNavigationMenu() {
  return (
    <aside className="glass-panel hidden w-[260px] shrink-0 rounded-[28px] p-5 xl:block">
      <div className="mb-8 flex items-center gap-3 px-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-linear-to-br from-[#edcb86] to-[#9b6f22] text-2xl font-black text-[#100a00]">
          F
        </div>
        <div>
          <div className="font-display text-[32px] font-bold tracking-[-0.04em] text-[#f4dfb4]">Forma</div>
          <div className="text-xs uppercase tracking-[0.3em] text-white/35">Stage 1 shell</div>
        </div>
      </div>

      <nav className="space-y-2">
        {navigationItems.map((item, index) => {
          const Icon = icons[index]

          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                cn(
                  'flex min-h-14 items-center gap-3 rounded-2xl border px-4 text-sm font-medium transition',
                  isActive
                    ? 'border-[#d9ba71]/60 bg-[#d9ba71]/8 text-white shadow-[0_0_0_1px_rgba(217,186,113,0.1)]'
                    : 'border-transparent bg-transparent text-white/65 hover:border-white/10 hover:bg-white/4 hover:text-white',
                )
              }
            >
              <Icon className="h-5 w-5" />
              {item.label}
            </NavLink>
          )
        })}
      </nav>
    </aside>
  )
}

export function TopSystemBar({
  userName,
  machine,
  onStop,
}: {
  userName?: string
  machine: MachineHealth
  onStop: () => void
}) {
  return (
    <header className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
      <div className="flex flex-wrap items-center gap-3">
        {userName ? <div className="glass-panel inline-flex min-h-14 items-center gap-3 rounded-2xl px-4 text-sm text-white/80">{userName}</div> : null}
        <MachineStatusBadge label={machine.machineLabel} tone={getMachineTone(machine.machineState)} />
        <DriveStatusBadge label={getDriveLabel('left', machine.leftDrive)} tone={getDriveTone(machine.leftDrive)} />
        <DriveStatusBadge label={getDriveLabel('right', machine.rightDrive)} tone={getDriveTone(machine.rightDrive)} />
        <SafetyStatusBadge label={getSafetyLabel(machine.safety)} tone={getSafetyTone(machine.safety)} />
      </div>

      <EmergencyStopButton onClick={onStop} />
    </header>
  )
}

export function EmergencyStopButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="sand-glow inline-flex min-h-16 items-center justify-center gap-3 rounded-[24px] bg-linear-to-r from-[#891610] via-[#d52f22] to-[#a61612] px-8 text-lg font-extrabold tracking-[0.12em] text-white"
    >
      <OctagonAlert className="h-6 w-6" />
      СТОП
    </button>
  )
}

export function FormaShell({ children, userName, machine, onStop }: PropsWithChildren<{ userName: string; machine: MachineHealth; onStop: () => void }>) {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-[1880px] gap-6 px-4 py-4 xl:px-6">
      <LeftNavigationMenu />
      <main className="flex-1 space-y-6">
        <TopSystemBar userName={userName} machine={machine} onStop={onStop} />
        {children}
      </main>
    </div>
  )
}