import { CalendarDays, Dumbbell, HeartPulse, House, OctagonAlert, PanelTop, Settings, Sparkles, UserRound, Wrench } from 'lucide-react'
import type { PropsWithChildren } from 'react'
import { NavLink } from 'react-router-dom'
import type { MachineHealth } from '@/entities/machine/model/types'
import { navigationItems } from '@/shared/config/navigation'
import { getDriveLabel, getSafetyLabel } from '@/shared/lib/machine-status'
import { cn } from '@/shared/lib/cn'
import { useHardwareStore } from '@/stores/hardware-store'

const icons = [House, Sparkles, PanelTop, CalendarDays, Wrench, Dumbbell, Dumbbell, Sparkles, HeartPulse, UserRound, Settings]

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

export function TopSystemBar({ machine, onStop }: { machine?: MachineHealth; onStop: () => void }) {
  const problems = machine ? getMachineProblems(machine) : []

  return (
    <header className="pointer-events-none fixed right-3 bottom-2 z-50 xl:right-4 xl:bottom-3">
      <div className="flex max-w-[calc(100vw-1.5rem)] items-end justify-end gap-3 xl:max-w-[calc(100vw-18rem)]">
        {problems.length > 0 ? (
          <div className="pointer-events-auto flex max-w-[min(58vw,560px)] flex-wrap justify-end gap-2">
            {problems.map((problem) => (
              <NavLink
                key={problem.label}
                to="/settings?tab=mechanics"
                className={cn(
                  'inline-flex min-h-12 items-center rounded-2xl border px-4 py-2 text-sm font-semibold leading-5 backdrop-blur transition',
                  problem.tone === 'danger'
                    ? 'border-[#ff9589]/45 bg-[#62221f]/80 text-[#ffd0ca] hover:bg-[#79302b]/85'
                    : 'border-[#f0d08c]/45 bg-[#5b4821]/80 text-[#f8df9e] hover:bg-[#6f5927]/85',
                )}
                title="Открыть Настройки, вкладка Приводы и ШВП"
              >
                {problem.label}
              </NavLink>
            ))}
          </div>
        ) : null}
        <div className="pointer-events-auto shrink-0">
          <EmergencyStopButton onClick={onStop} />
        </div>
      </div>
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
      Аварийная остановка
    </button>
  )
}

export function FormaShell({ children, machine, onStop }: PropsWithChildren<{ userName: string; machine: MachineHealth; onStop: () => void }>) {
  const liveMachine = useHardwareStore((state) => state.snapshot?.machine)

  return (
    <div className="flex min-h-screen w-full gap-6 px-4 py-4 xl:px-6">
      <LeftNavigationMenu />
      <main className="flex-1 space-y-6 pb-24 xl:pb-28">
        <TopSystemBar machine={liveMachine ?? machine} onStop={onStop} />
        {children}
      </main>
    </div>
  )
}