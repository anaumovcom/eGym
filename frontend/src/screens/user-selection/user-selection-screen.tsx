import { useMutation, useQuery } from '@tanstack/react-query'
import { ShieldAlert, ShieldCheck, UserRound } from 'lucide-react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import type { MachineHealth } from '@/entities/machine/model/types'
import { apiGet, apiPost } from '@/shared/api/client'
import { getMachineNotice, getSafetyLabel } from '@/shared/lib/machine-status'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { FormaState } from '@/shared/ui/status/forma-state'
import { BlockingAlert, WarningBanner } from '@/shared/ui/status/status-components'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { useAppStore } from '@/stores/app-store'
import type { UserSummary } from '@/entities/user/model/types'

type UsersResponse = { users: UserSummary[] }
type SelectUserResponse = { currentUser: { id: string } }

const fallbackMachine: MachineHealth = {
  machineState: 'ready',
  machineLabel: 'Проверяем тренажёр…',
  leftDrive: 'connected',
  rightDrive: 'connected',
  safety: 'enabled',
  calibration: '—',
}

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
    return (
      <FormaShell hideNavigation userName="" machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
        <FormaState tone="loading" title="Загружаем профили…" />
      </FormaShell>
    )
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
    <FormaShell hideNavigation userName="" machine={machine} onStop={onStop}>
      <div className="users-screen">
        <div className="users-brand" aria-hidden="true">
          <div>F</div>
          <strong>Forma</strong>
        </div>

        <section className="users-heading">
          <h1 className="font-display font-bold tracking-[-0.06em] text-white">Кто тренируется?</h1>
          <p>Выберите профиль, чтобы загрузить личные веса, прогресс и настройки безопасности.</p>
        </section>

        {machineNotice ? (
          <div className="users-notice">
            {machineNotice.tone === 'blocked'
              ? <BlockingAlert title={machineNotice.title} description={machineNotice.description} />
              : <WarningBanner title={machineNotice.title} description={machineNotice.description} />}
          </div>
        ) : null}

        <section className="users-grid" data-count={users.length} aria-label="Профили">
          {users.map((user) => (
            <article key={user.id} className="users-card" data-accent={user.accent} aria-label={user.name}>
              <div className="users-avatar" aria-hidden="true">{user.name.slice(0, 1)}</div>
              <h2>{user.name}</h2>
              <dl>
                <div>
                  <dt>Готовность</dt>
                  <dd><strong>{user.readinessPercent}%</strong></dd>
                </div>
                <div>
                  <dt>Последняя тренировка</dt>
                  <dd>{user.lastWorkout}</dd>
                </div>
                <div>
                  <dt>Неделя</dt>
                  <dd>{user.weekProgress}</dd>
                </div>
              </dl>
              <Button aria-label={`Выбрать профиль ${user.name}`} onClick={() => onSelectUser(user.id)}>
                Выбрать
              </Button>
            </article>
          ))}
        </section>

        <div className="users-footer">
          <Button variant="secondary" iconLeft={<UserRound aria-hidden="true" />} onClick={onGuest}>
            Гость
          </Button>
          <span className={cn('inline-flex items-center gap-2 text-sm', emergencyStopActive ? 'text-[#ff9589]' : 'text-white/60')}>
            {emergencyStopActive ? <ShieldAlert className="h-5 w-5 text-[#eb5345]" aria-hidden="true" /> : <ShieldCheck className="h-5 w-5 text-[#f0c24f]" aria-hidden="true" />}
            {emergencyStopActive ? 'Аварийная остановка: активна' : getSafetyLabel(machine.safety)}
          </span>
        </div>
      </div>

      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={onEmergencyStopChange} />
    </FormaShell>
  )
}