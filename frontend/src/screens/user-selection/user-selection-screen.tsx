import { useMutation, useQuery } from '@tanstack/react-query'
import { HeartPulse, Settings, ShieldAlert, ShieldCheck, UserPlus, UserRound, Wrench } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { MachineHealth } from '@/entities/machine/model/types'
import { apiGet, apiPost } from '@/shared/api/client'
import { getDriveLabel, getDriveTone, getMachineNotice, getMachineTone, getSafetyLabel, getSafetyTone } from '@/shared/lib/machine-status'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { EmergencyStopButton } from '@/shared/ui/layout/forma-shell'
import { BlockingAlert, DriveStatusBadge, MachineStatusBadge, ReadinessIndicator, SafetyStatusBadge, WarningBanner } from '@/shared/ui/status/status-components'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { useAppStore } from '@/stores/app-store'
import type { UserSummary } from '@/entities/user/model/types'

type UsersResponse = { users: UserSummary[] }
type SelectUserResponse = { currentUser: { id: string } }

export type UserSelectionViewProps = {
  users: UserSummary[]
  machine: MachineHealth
  emergencyStopActive: boolean
  onSelectUser: (userId: string) => void
  onGuest: () => void
  onEmergencyStopChange: (open: boolean) => void
  onStop: () => void
}

export function UserSelectionScreen() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const scenario = searchParams.get('scenario') ?? 'ready'
  const setSelectedUserId = useAppStore((state) => state.setSelectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)

  const selectUserMutation = useMutation({
    mutationFn: (userId: string) => apiPost<SelectUserResponse>('/api/users/select', { userId }),
  })

  const { data: usersData } = useQuery({
    queryKey: ['users'],
    queryFn: () => apiGet<UsersResponse>('/api/users'),
  })

  const { data: machine } = useQuery({
    queryKey: ['machine-status', scenario],
    queryFn: () => apiGet<MachineHealth>(`/api/machine/status?scenario=${encodeURIComponent(scenario)}`),
  })

  if (!usersData || !machine) {
    return null
  }

  return (
    <UserSelectionView
      users={usersData.users}
      machine={machine}
      emergencyStopActive={emergencyStopActive}
      onSelectUser={(userId) => {
        void selectUserMutation.mutateAsync(userId).catch(() => undefined).finally(() => {
          setSelectedUserId(userId)
          navigate('/dashboard')
        })
      }}
      onGuest={() => {
        setSelectedUserId('guest')
        navigate('/dashboard')
      }}
      onEmergencyStopChange={setEmergencyStopActive}
      onStop={() => setEmergencyStopActive(true)}
    />
  )
}

export function UserSelectionView({
  users,
  machine,
  emergencyStopActive,
  onSelectUser,
  onGuest,
  onEmergencyStopChange,
  onStop,
}: UserSelectionViewProps) {
  const machineNotice = getMachineNotice(machine)

  return (
    <div className="relative min-h-screen overflow-hidden px-4 py-6 xl:px-6">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.04),transparent_38%),url('https://images.unsplash.com/photo-1517836357463-d25dfeac3438?auto=format&fit=crop&w=1800&q=80')] bg-cover bg-center opacity-20" />
      <div className="relative flex w-full flex-col gap-8">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex items-center gap-4">
            <div className="flex h-15 w-15 items-center justify-center rounded-[22px] bg-linear-to-br from-[#edcb86] to-[#986c21] text-3xl font-black text-[#100a00]">
              F
            </div>
            <div>
              <div className="font-display text-5xl font-bold tracking-[-0.06em] text-[#f3ddb0]">Forma</div>
              <div className="text-sm uppercase tracking-[0.35em] text-white/35">Smith machine console</div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 text-sm">
            <MachineStatusBadge label={machine.machineLabel} tone={getMachineTone(machine.machineState)} />
            <DriveStatusBadge label={getDriveLabel('left', machine.leftDrive)} tone={getDriveTone(machine.leftDrive)} />
            <DriveStatusBadge label={getDriveLabel('right', machine.rightDrive)} tone={getDriveTone(machine.rightDrive)} />
            <EmergencyStopButton onClick={onStop} />
          </div>
        </div>

        <section className="mx-auto max-w-[980px] text-center">
          <h1 className="font-display text-6xl font-bold tracking-[-0.08em] text-white xl:text-8xl">Кто тренируется?</h1>
          <p className="mt-4 text-xl leading-8 text-white/60">
            Выберите профиль, чтобы загрузить личные веса, прогресс, рекомендации и настройки безопасности.
          </p>
        </section>

        {machineNotice ? (
          machineNotice.tone === 'blocked' ? (
            <BlockingAlert title={machineNotice.title} description={machineNotice.description} />
          ) : (
            <WarningBanner title={machineNotice.title} description={machineNotice.description} />
          )
        ) : null}

        <section className="grid gap-6 xl:grid-cols-2">
          {users.map((user) => (
            <article key={user.id} className="glass-panel sand-glow rounded-[34px] p-6 xl:p-8">
              <div className="flex flex-col gap-6 md:flex-row md:items-center">
                <div className={cn(
                  'flex h-36 w-36 items-center justify-center rounded-[32px] border text-5xl font-display font-bold',
                  user.accent === 'green'
                    ? 'border-[#8adc64]/25 bg-radial-[at_30%_30%] from-[#294819] via-[#101820] to-[#070c13] text-[#bdf090]'
                    : 'border-[#d6b05f]/20 bg-radial-[at_30%_30%] from-[#3a2b0a] via-[#0f1520] to-[#070c13] text-[#f3ddb0]',
                )}>
                  {user.name.slice(0, 1)}
                </div>
                <div className="flex-1 space-y-4">
                  <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
                    <div>
                      <div className="font-display text-4xl font-bold text-white">{user.name}</div>
                      <div className="mt-2 text-sm uppercase tracking-[0.24em] text-white/35">Готовность</div>
                    </div>
                    <ReadinessIndicator value={user.readinessPercent} accent={user.accent === 'green' ? 'green' : 'sand'} />
                  </div>
                  <div className="space-y-3 text-sm text-white/75">
                    <div>Последняя тренировка: {user.lastWorkout}</div>
                    <div>Сегодня: {user.todayFocus}</div>
                    <div>Прогресс недели: {user.weekProgress}</div>
                  </div>
                  <Button className="w-full" aria-label={`Выбрать профиль ${user.name}`} onClick={() => onSelectUser(user.id)}>
                    Выбрать
                  </Button>
                </div>
              </div>
            </article>
          ))}
        </section>

        <div className="flex flex-wrap items-center justify-center gap-4 text-base text-white/55">
          <Button variant="ghost" iconLeft={<UserRound className="h-4 w-4" />} onClick={onGuest}>
            Гость
          </Button>
          <div className="hidden h-6 w-px bg-white/10 xl:block" />
          <Button variant="ghost" iconLeft={<UserPlus className="h-4 w-4" />} disabled>
            Добавить пользователя
          </Button>
        </div>

        <footer className="grid gap-4 xl:grid-cols-[1.5fr_1fr]">
          <div className="glass-panel flex flex-wrap gap-3 rounded-[28px] p-4">
            {[
              { icon: Wrench, label: 'Сервисный режим' },
              { icon: HeartPulse, label: 'Диагностика' },
              { icon: Settings, label: 'Настройки' },
            ].map((item) => (
              <button key={item.label} type="button" className="flex min-h-14 items-center gap-3 rounded-2xl border border-white/10 bg-white/5 px-5 text-sm text-white/80">
                <item.icon className="h-5 w-5" />
                {item.label}
              </button>
            ))}
          </div>
          <div className="glass-panel flex flex-col gap-3 rounded-[28px] p-4 text-sm xl:flex-row xl:items-center xl:justify-between">
            <div className={cn('flex items-center gap-3', emergencyStopActive ? 'text-[#ff9589]' : 'text-white/60')}>
              {emergencyStopActive ? <ShieldAlert className="h-5 w-5 text-[#eb5345]" /> : <ShieldCheck className="h-5 w-5 text-[#f0c24f]" />}
              {emergencyStopActive ? 'Аварийная остановка: активна' : 'Кнопка аварийной остановки: доступна'}
            </div>
            <SafetyStatusBadge label={getSafetyLabel(machine.safety)} tone={getSafetyTone(machine.safety)} />
          </div>
        </footer>
      </div>

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={onEmergencyStopChange} />
    </div>
  )
}