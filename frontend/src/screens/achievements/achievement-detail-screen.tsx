import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ChevronLeft, ChevronRight } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { MachineHealth } from '@/entities/machine/model/types'
import { achievementsApi } from '@/features/achievements/lib/achievements-api'
import { AchievementAudioButton, AchievementImage, RarityBadge } from '@/features/achievements/ui/achievement-media'
import { Button } from '@/shared/ui/button'
import { FormaShell } from '@/shared/ui/layout/forma-shell'
import { EmergencyStopOverlay } from '@/shared/ui/overlays/surface-components'
import { FormaState } from '@/shared/ui/status/forma-state'
import { useAppStore } from '@/stores/app-store'
import { formatNumber } from '@/screens/progress/progress-format'
import './achievements-screen.css'

const fallbackMachine: MachineHealth = { machineState: 'ready', machineLabel: 'Тренажёр готов', leftDrive: 'connected', rightDrive: 'connected', safety: 'enabled', calibration: '—' }

export function AchievementDetailScreen() {
  const { definitionId = '' } = useParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const userId = selectedUserId ?? 'alexey'
  const userName = userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
  const queryClient = useQueryClient()
  const { data: line, isPending, isError, refetch } = useQuery({
    queryKey: ['achievement-detail', userId, definitionId], queryFn: () => achievementsApi.detail(userId, definitionId),
  })
  const nextTier = line?.tiers.find((tier) => tier.id === line.nextTierId)
  const activeTier = line ? [...line.tiers].reverse().find((tier) => tier.earned) ?? nextTier ?? line.tiers[0] : undefined
  const viewedOpen = useRef('')
  const { mutate: recordReceipt } = useMutation({
    mutationFn: ({ surface, tier }: { surface: 'detail' | 'audio'; tier?: number }) =>
      achievementsApi.recordReceipt(userId, definitionId, surface, tier),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['achievement'] }),
        queryClient.invalidateQueries({ queryKey: ['achievements'] }),
      ])
    },
  })
  useEffect(() => {
    if (!line || !activeTier?.earned) return
    const key = `${userId}:${definitionId}`
    if (viewedOpen.current === key) return
    viewedOpen.current = key
    recordReceipt({ surface: 'detail' })
  }, [activeTier?.earned, definitionId, line, recordReceipt, userId])
  return (
    <FormaShell userName={userName} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
      <div className="ach-page">
        <Link className="ach-back" to="/achievements"><ChevronLeft aria-hidden="true" />Все достижения</Link>
        {isError ? <FormaState tone="error" title="Достижение не найдено" action={<Button onClick={() => void refetch()}>Повторить</Button>} />
          : isPending || !line || !activeTier ? <FormaState tone="loading" title="Открываем награду…" />
          : <div className="ach-detail" data-rarity={activeTier.rarity}>
            <section className="ach-detail-hero">
              <div className="ach-detail-art"><AchievementImage tier={activeTier} />{line.isNew && <span className="ach-new-badge">Новая</span>}</div>
              <div className="ach-detail-copy">
                <RarityBadge rarity={activeTier.rarity} />
                <h1 className="ach-detail-title">{activeTier.earned ? activeTier.title : 'Награда не открыта'}</h1>
                <p>{line.description}</p>
                {activeTier.earned && <p className="ach-detail-phrase">«{activeTier.phrase}»</p>}
                <AchievementAudioButton tier={activeTier} autoPlay={activeTier.earned}
                  onPlaybackStart={activeTier.earned ? () => recordReceipt({ surface: 'audio', tier: activeTier.tier }) : undefined} />
                <div className="ach-detail-meta"><span>{line.groupName}</span><span>Получено ступеней: {line.highestTier} из {line.tiers.length}</span><span>{formatNumber(line.currentValue)} {line.unit}</span></div>
                <div className="ach-progress" role="progressbar" aria-label="Прогресс достижения" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(line.progressPercent)}><span style={{ width: `${line.progressPercent}%` }} /></div>
                <p>{nextTier ? `Следующая цель: ${nextTier.threshold} ${line.unit}. Продолжайте по своему плану.` : 'Все ступени этой линии уже в вашей коллекции.'}</p>
                {nextTier?.minimumEvidenceDays != null && <p>Подтверждённая практика: {line.evidenceDays ?? 0} / {nextTier.minimumEvidenceDays} разных дней. Нужны оба условия; дни не обязательно подряд.</p>}
              </div>
            </section>
            <section><div className="ach-section-title"><h2>Все ступени линии</h2><span>{line.id}</span></div><div className="ach-detail-tiers">
              {line.tiers.map((tier) => <article className="ach-tier-detail" data-rarity={tier.rarity} data-earned={tier.earned || undefined} key={tier.id}>
                <AchievementImage tier={tier} />
                <RarityBadge rarity={tier.rarity} />
                <small>{tier.tierName} · {tier.threshold} {line.unit}</small>
                {tier.minimumEvidenceDays != null && <small>И минимум {tier.minimumEvidenceDays} разных дней подтверждённой практики</small>}
                <h3>{tier.earned ? tier.title : 'Скрытая награда'}</h3>
                {tier.earned && <p>{tier.phrase}</p>}
                <AchievementAudioButton tier={tier}
                  onPlaybackStart={tier.earned ? () => recordReceipt({ surface: 'audio', tier: tier.tier }) : undefined} />
                {tier.earned ? <small><Check aria-hidden="true" /> Получено{tier.earnedAt ? ` · ${new Date(tier.earnedAt).toLocaleDateString('ru-RU')}` : ''}</small> : <small>Ещё впереди</small>}
                {tier.earned && <Link className="ach-back" to={`/workout-summary?achievement=${encodeURIComponent(tier.id)}`}>В коллекцию<ChevronRight aria-hidden="true" /></Link>}
              </article>)}
            </div></section>
          </div>}
      </div>
      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}
