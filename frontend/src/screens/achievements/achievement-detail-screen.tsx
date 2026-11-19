import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, ChevronLeft } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import type { MachineHealth } from '@/entities/machine/model/types'
import { achievementUnit, distanceToAward } from '@/features/achievements/lib/achievement-units'
import { achievementsApi } from '@/features/achievements/lib/achievements-api'
import { currentTier } from '@/features/achievements/lib/collection-filters'
import { AchievementAudioButton, AchievementImage, RarityBadge } from '@/features/achievements/ui/achievement-media'
import { AwardFacts } from '@/features/achievements/ui/award-facts'
import { CollectionSymbol } from '@/features/achievements/ui/collection-symbol'
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
  const [search] = useSearchParams()
  const selectedUserId = useAppStore((state) => state.selectedUserId)
  const emergencyStopActive = useAppStore((state) => state.emergencyStopActive)
  const setEmergencyStopActive = useAppStore((state) => state.setEmergencyStopActive)
  const userId = selectedUserId ?? 'alexey'
  const userName = userId === 'elena' ? 'Елена' : userId === 'guest' ? 'Гость' : 'Алексей'
  const queryClient = useQueryClient()
  const { data: line, isPending, isError, refetch } = useQuery({
    queryKey: ['achievements', 'detail', userId, definitionId], queryFn: () => achievementsApi.detail(userId, definitionId),
  })
  const nextTier = line?.tiers.find((tier) => tier.id === line.nextTierId)
  const requestedNumber = search.get('tier')
  const requested = line?.tiers.find((tier) => (tier.earned || tier.status === 'revoked') && String(tier.tier) === requestedNumber)
  const highest = line && currentTier(line)
  const activeTier = requested ?? highest ?? nextTier ?? line?.tiers[0]
  const viewedOpen = useRef('')
  const { mutate: recordReceipt } = useMutation({
    mutationFn: ({ surface, tier }: { surface: 'detail' | 'audio'; tier?: number }) =>
      achievementsApi.recordReceipt(userId, definitionId, surface, tier),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['workout-awards', userId] }),
        queryClient.invalidateQueries({ queryKey: ['achievements'] }),
      ])
    },
  })
  useEffect(() => {
    if (!activeTier?.earned || (requestedNumber !== null && !requested)) return
    const key = `${userId}:${activeTier.id}`
    if (viewedOpen.current === key) return
    viewedOpen.current = key
    recordReceipt({ surface: 'detail', tier: activeTier.tier })
  }, [activeTier, requestedNumber, requested, recordReceipt, userId])
  return (
    <FormaShell userName={userName} machine={fallbackMachine} onStop={() => setEmergencyStopActive(true)}>
      <div className="ach-page">
        <Link className="ach-back" to="/achievements"><ChevronLeft aria-hidden="true" />Все достижения</Link>
        {isError ? <FormaState tone="error" title="Достижение не найдено" action={<Button onClick={() => void refetch()}>Повторить</Button>} />
          : isPending || !line || !activeTier ? <FormaState tone="loading" title="Открываем награду…" />
          : <div className="ach-detail" data-rarity={activeTier.rarity}>
            <section className="ach-detail-hero" aria-labelledby="ach-detail-title">
              <div className="ach-detail-art">{activeTier.earned ? <AchievementImage tier={activeTier} eager /> : <span className="ach-series-symbol"><CollectionSymbol group={line.group} /></span>}{activeTier.isNew && <span className="ach-new-badge">Новая</span>}</div>
              <div className="ach-detail-copy">
                <span className="ach-detail-group">{line.groupName}{requested ? ` · Ступень ${activeTier.tier}` : ''}</span>
                <RarityBadge rarity={activeTier.rarity} />
                <h1 className="ach-detail-title" id="ach-detail-title">{requested?.status === 'revoked' ? 'Ступень снова закрыта' : requested?.title ?? line.name}</h1>
                {requested && <Link className="ach-parent-series" to={`/achievements/${encodeURIComponent(line.id)}`}>{line.name}</Link>}
                <p>{line.description}</p>
                {requested && <AwardFacts tier={requested} unit={line.unit} />}
                {activeTier.earned && <p className="ach-detail-phrase">«{activeTier.phrase}»</p>}
                <AchievementAudioButton tier={activeTier}
                  onPlaybackStart={activeTier.earned ? () => recordReceipt({ surface: 'audio', tier: activeTier.tier }) : undefined} />
              </div>
            </section>
            {!line.archived && <section className="ach-detail-progress" aria-labelledby="ach-progress-title">
              <div className="ach-detail-progress-heading"><div><h2 id="ach-progress-title">Прогресс серии</h2><p>Открыто ступеней — {line.tiers.filter((tier) => tier.earned).length} из {line.tiers.length}</p></div><strong>{formatNumber(line.currentValue)} <small>{achievementUnit(line.unit, line.currentValue)}</small></strong></div>
              <div className="ach-progress" role="progressbar" aria-label="Прогресс достижения" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(line.progressPercent)}><span style={{ width: `${line.progressPercent}%` }} /></div>
              <p>{nextTier ? `Следующая ступень — ${formatNumber(nextTier.threshold)} ${achievementUnit(line.unit, nextTier.threshold)}` : 'Все ступени этой серии уже в вашей коллекции.'}</p>
              {nextTier && <strong className="ach-clue-distance">{distanceToAward(line.currentValue, nextTier.threshold, line.unit)}</strong>}
            </section>}
            <section className="ach-detail-levels"><div className="ach-section-title"><h2>{line.archived ? 'Сохранённые награды' : 'Ступени серии'}</h2></div><div className="ach-detail-tiers">
              {line.tiers.map((tier) => <article className="ach-tier-detail" data-rarity={tier.rarity} data-earned={tier.earned || undefined} key={tier.id}>
                <AchievementImage tier={tier} />
                <RarityBadge rarity={tier.rarity} />
                <small>{tier.tierName} · {formatNumber(tier.threshold)} {achievementUnit(line.unit, tier.threshold)}</small>
                <h3>{tier.earned ? <Link to={`?tier=${tier.tier}`} aria-current={requested?.id === tier.id ? 'page' : undefined}>{tier.title}</Link> : 'Скрытая награда'}</h3>
                {tier.earned && <p>{tier.phrase}</p>}
                <AchievementAudioButton tier={tier}
                  onPlaybackStart={tier.earned ? () => recordReceipt({ surface: 'audio', tier: tier.tier }) : undefined} />
                {tier.earned ? <small><Check aria-hidden="true" /> Получено{tier.earnedAt ? ` · ${new Date(tier.earnedAt).toLocaleDateString('ru-RU')}` : ''}</small> : <small>{tier.status === 'revoked' ? 'Условие больше не выполнено' : 'Ещё впереди'}</small>}
              </article>)}
            </div></section>
          </div>}
      </div>
      <EmergencyStopOverlay open={emergencyStopActive} onOpenChange={setEmergencyStopActive} />
    </FormaShell>
  )
}
