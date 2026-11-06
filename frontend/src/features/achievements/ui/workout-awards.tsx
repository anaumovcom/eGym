import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Sparkles, Trophy } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { achievementsApi } from '@/features/achievements/lib/achievements-api'
import { AchievementAudioButton, AchievementImage, RarityBadge } from './achievement-media'

const INITIAL_COUNT = 4

export function WorkoutAwards({ userId, workoutId }: { userId: string | null; workoutId: number | undefined }) {
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState(false)
  const { mutate: recordAudioReceipt } = useMutation({
    mutationFn: ({ definitionId, tier }: { definitionId: string; tier: number }) =>
      achievementsApi.recordReceipt(userId ?? 'alexey', definitionId, 'audio', tier),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['achievements'] }),
  })
  const query = useQuery({
    queryKey: ['workout-awards', userId, workoutId],
    queryFn: () => achievementsApi.workoutAwards(userId ?? 'alexey', workoutId!),
    enabled: Boolean(userId && workoutId),
    refetchInterval: (current) => current.state.data?.isRebuilding ? 1500 : false,
  })
  if (!query.data || query.data.awards.length === 0) {
    return query.data?.isRebuilding
      ? <section className="ach-workout-awards" aria-label="Достижения"><p className="ach-pending" role="status">Сохранили тренировку. Обновляем достижения…</p></section>
      : null
  }
  const awards = query.data.awards
  const visible = expanded ? awards : awards.slice(0, INITIAL_COUNT)
  const hiddenCount = awards.length - visible.length
  const newCount = awards.filter((award) => award.isNew).length
  return (
    <section className="ach-workout-awards" aria-labelledby="workout-awards-title">
      <header className="ach-workout-awards-head">
        <div className="ach-workout-awards-heading">
          <span className="ach-workout-awards-icon" aria-hidden="true"><Trophy /></span>
          <div className="ach-workout-awards-copy">
            <h2 id="workout-awards-title">Новые достижения</h2>
            <p>{newCount > 0 ? 'Заслужены по итогам этой тренировки' : 'Получены по итогам этой тренировки'}</p>
          </div>
        </div>
        <span className="ach-workout-awards-count" aria-label={`Всего достижений: ${awards.length}`}>
          <Sparkles aria-hidden="true" />+{awards.length}
        </span>
      </header>
      <div className="ach-award-grid">
        {visible.map((award, index) => (
          <article className="ach-award" data-rarity={award.tier.rarity} style={{ animationDelay: `${Math.min(index, 8) * 70}ms` }} key={award.grantId}>
            {award.isNew && <span className="ach-new-badge">Новая</span>}
            <AchievementImage tier={award.tier} />
            <div className="ach-award-copy">
              <div className="ach-award-meta">
                <RarityBadge rarity={award.tier.rarity} />
                <span className="ach-award-tier">Ступень {award.tier.tier} · {award.tier.tierName}</span>
              </div>
              <h3>{award.tier.title}</h3>
              <p>{award.tier.phrase}</p>
              <AchievementAudioButton tier={award.tier} compact onPlaybackStart={() => recordAudioReceipt({ definitionId: award.definitionId, tier: award.tier.tier })} />
            </div>
          </article>
        ))}
      </div>
      <footer className="ach-workout-awards-foot">
        {hiddenCount > 0 && (
          <button type="button" className="ach-foot-action" onClick={() => setExpanded(true)}>
            Показать ещё {hiddenCount}<ChevronDown aria-hidden="true" />
          </button>
        )}
        <Link className="ach-foot-action" to="/achievements">Вся коллекция<ChevronRight aria-hidden="true" /></Link>
      </footer>
    </section>
  )
}
