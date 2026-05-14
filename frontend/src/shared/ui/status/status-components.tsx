import { AlertTriangle, CheckCircle2, ShieldAlert, ShieldCheck } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '@/shared/lib/cn'
import type { StatusTone } from '@/shared/ui/status/status-types'

export function MachineStatusBadge({ label, tone = 'success' }: { label: string; tone?: StatusTone }) {
  return <StatusBadge label={label} tone={tone} icon={<CheckCircle2 className="h-4 w-4" />} />
}

export function DriveStatusBadge({ label, tone = 'success' }: { label: string; tone?: StatusTone }) {
  return <StatusBadge label={label} tone={tone} icon={<CheckCircle2 className="h-4 w-4" />} />
}

export function SafetyStatusBadge({ label, tone = 'success' }: { label: string; tone?: StatusTone }) {
  return <StatusBadge label={label} tone={tone} icon={tone === 'danger' ? <ShieldAlert className="h-4 w-4" /> : <ShieldCheck className="h-4 w-4" />} />
}

export function WarningBanner({ title, description }: { title: string; description: string }) {
  return (
    <div className="glass-panel flex items-start gap-3 rounded-2xl border border-[#f0c24f]/25 p-4 text-sm text-white/80">
      <AlertTriangle className="mt-0.5 h-5 w-5 text-[#f0c24f]" />
      <div>
        <div className="font-semibold text-[#f5dc9b]">{title}</div>
        <div>{description}</div>
      </div>
    </div>
  )
}

export function BlockingAlert({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-3xl border border-[#eb5345]/30 bg-[#3b1210]/85 p-5 text-white shadow-[0_18px_40px_rgba(0,0,0,0.28)]">
      <div className="mb-2 flex items-center gap-3 text-base font-bold text-[#ff9d92]">
        <AlertTriangle className="h-5 w-5" />
        {title}
      </div>
      <div className="text-sm text-white/75">{description}</div>
    </div>
  )
}

export function ReadinessIndicator({ value, accent = 'sand' }: { value: number; accent?: 'sand' | 'green' }) {
  const clampedValue = Math.max(0, Math.min(100, value))
  const ringColor = accent === 'green' ? '#7BDB6D' : '#D7B15D'
  const radius = 58
  const circumference = 2 * Math.PI * radius
  const strokeOffset = circumference - (clampedValue / 100) * circumference

  return (
    <div className="relative flex h-40 w-40 items-center justify-center rounded-full border border-white/10 bg-[#09101a]">
      <svg className="absolute inset-3 h-[calc(100%-24px)] w-[calc(100%-24px)] -rotate-90" viewBox="0 0 140 140" aria-hidden="true">
        <circle cx="70" cy="70" r={radius} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="10" />
        <circle
          cx="70"
          cy="70"
          r={radius}
          fill="none"
          stroke={ringColor}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={strokeOffset}
        />
      </svg>
      <div className="absolute inset-6 rounded-full bg-[#09101a] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.05)]" />
      <div className="relative text-center">
        <div className="text-xs uppercase tracking-[0.2em] text-white/40">Готовность</div>
        <div className="font-display text-5xl font-bold text-[#f6e2b8]">{value}%</div>
      </div>
    </div>
  )
}

export function PrimaryActionBar({ children }: { children: React.ReactNode }) {
  return <div className="glass-panel rounded-[28px] p-4">{children}</div>
}

function StatusBadge({ label, tone, icon }: { label: string; tone: StatusTone; icon: ReactNode }) {
  return (
    <div
      className={cn(
        'inline-flex min-h-11 items-center gap-2 rounded-full border px-4 text-sm',
        tone === 'success'
          ? 'border-[#6ed36d]/20 bg-[#6ed36d]/8 text-[#b9f1b8]'
          : tone === 'warning'
            ? 'border-[#f0c24f]/20 bg-[#f0c24f]/10 text-[#f6de9f]'
            : tone === 'danger'
              ? 'border-[#eb5345]/20 bg-[#eb5345]/10 text-[#ffb1a8]'
              : 'border-white/10 bg-white/5 text-white/70',
      )}
    >
      {icon}
      {label}
    </div>
  )
}