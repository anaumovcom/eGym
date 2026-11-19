import * as Dialog from '@radix-ui/react-dialog'
import { skipToken, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, Trophy, X } from 'lucide-react'
import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { AchievementAward } from '@/entities/achievement/model/types'
import { achievementsApi } from '@/features/achievements/lib/achievements-api'
import { achievementUnit } from '@/features/achievements/lib/achievement-units'
import { plural } from '@/shared/lib/ru-format'
import { SafetyDialogContent } from '@/shared/ui/overlays/safety-dialog'
import { AchievementAudioButton, AchievementImage, RarityBadge } from './achievement-media'
import { AwardFacts } from './award-facts'

const PREVIEW_COUNT = 4

export function WorkoutAwards({ userId, workoutId }: { userId: string | null; workoutId: number | undefined }) {
  const { data } = useQuery({
    queryKey: ['workout-awards', userId, workoutId],
    queryFn: userId && workoutId ? () => achievementsApi.workoutAwards(userId, workoutId) : skipToken,
    refetchInterval: (current) => current.state.data?.isRebuilding ? 1500 : false,
  })
  if (!userId || !data?.awards.length) {
    return data?.isRebuilding
      ? <section className="ach-workout-awards" aria-label="Достижения"><p role="status">Обновляем достижения…</p></section>
      : null
  }
  return <EarnedWorkoutAwards key={`${userId}:${workoutId}`} userId={userId} awards={data.awards} />
}

function AwardLabel({ award }: { award: AchievementAward }) {
  return <><AchievementImage tier={award.tier} decorative /><span className="ach-award-name">{award.tier.title}</span></>
}

function AwardDetails({ award, wasNew, onPlay }: { award: AchievementAward; wasNew?: boolean; onPlay: () => void }) {
  const { tier, description, unit, earnedAt, awardedAt } = award
  return (
    <article className="ach-award ach-award-detail" data-rarity={tier.rarity} aria-labelledby="selected-award-title">
      <div className="ach-award-hero">
        <AchievementImage tier={tier} decorative eager />
        <div>
          <div className="ach-award-meta">
            <RarityBadge rarity={tier.rarity} />
            {wasNew && <span className="ach-new-badge">Новая</span>}
          </div>
          <h3 id="selected-award-title">{tier.title}</h3>
          <p>Ступень {tier.tier} · {tier.tierName}</p>
          <AchievementAudioButton tier={tier} onPlaybackStart={onPlay} />
        </div>
      </div>
      {tier.phrase && <blockquote>«{tier.phrase}»</blockquote>}
      <Dialog.Description>{description}</Dialog.Description>
      {(award.movements?.length || award.valueAtAward != null) ? <div className="ach-workout-proof">
        <span>В момент открытия</span>
        {award.valueAtAward != null && <strong>{award.valueAtAward.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} {achievementUnit(unit, award.valueAtAward)}</strong>}
        {!!award.movements?.length && <p>{award.movements.join(' · ')}</p>}
      </div> : null}
      <AwardFacts tier={tier} unit={unit} earnedAt={earnedAt ?? awardedAt} />
    </article>
  )
}

function EarnedWorkoutAwards({ userId, awards }: { userId: string; awards: AchievementAward[] }) {
  const [openedAward, setOpenedAward] = useState<AchievementAward | null>(null)
  const opener = useRef<HTMLButtonElement>(null)
  const queryClient = useQueryClient()
  const { mutate: recordReceipt } = useMutation({
    mutationFn: ({ award, surface }: { award: AchievementAward; surface: 'detail' | 'audio' }) =>
      achievementsApi.recordReceipt(userId, award.definitionId, surface, award.tier.tier),
    onSuccess: () => Promise.all([
      queryClient.invalidateQueries({ queryKey: ['workout-awards', userId] }),
      queryClient.invalidateQueries({ queryKey: ['achievements'] }),
    ]),
  })
  const position = awards.findIndex(award => award.grantId === openedAward?.grantId)
  const selected = awards[position]

  function selectAward(award: AchievementAward, trigger?: HTMLButtonElement) {
    if (trigger) opener.current = trigger
    if (award.grantId === openedAward?.grantId) return
    setOpenedAward(award)
    if (award.isNew) recordReceipt({ award, surface: 'detail' })
  }

  return (
    <Dialog.Root open={Boolean(selected)} onOpenChange={open => { if (!open) setOpenedAward(null) }}>
      <section className="ach-workout-awards" aria-labelledby="workout-awards-title">
        <div><h2 id="workout-awards-title"><Trophy aria-hidden="true" />{awards.some(award => award.isNew) ? 'Новые достижения' : 'Достижения тренировки'}</h2>
          <small className="ach-workout-count">{awards.length} {plural(awards.length, 'награда', 'награды', 'наград')} за занятие</small></div>
        <div className="ach-award-preview">
          {awards.slice(0, PREVIEW_COUNT).map(award => (
            <button type="button" className="ach-award" data-rarity={award.tier.rarity} aria-haspopup="dialog"
              key={award.grantId} onClick={event => selectAward(award, event.currentTarget)}>
              <AwardLabel award={award} />
            </button>
          ))}
        </div>
        {awards.length > PREVIEW_COUNT && (
          <button type="button" className="ach-foot-action" aria-haspopup="dialog" aria-label={`Все достижения тренировки, ${awards.length}`}
            onClick={event => selectAward(awards[0], event.currentTarget)}>
            Все {awards.length}<ChevronRight aria-hidden="true" />
          </button>
        )}
      </section>

      {selected && (
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-[#05080f]/80 backdrop-blur-sm" />
          <SafetyDialogContent className="ach-awards-dialog" onCloseAutoFocus={event => {
            event.preventDefault()
            opener.current?.focus({ preventScroll: true })
          }}>
            <header className="ach-awards-dialog-head">
              <Dialog.Title>Достижения тренировки</Dialog.Title>
              <div>
                <Link className="ach-foot-action" to="/achievements">Вся коллекция<ChevronRight aria-hidden="true" /></Link>
                <Dialog.Close className="ach-foot-action"><X aria-hidden="true" />Закрыть</Dialog.Close>
              </div>
            </header>
            <div className="ach-awards-dialog-body">
              <div className="ach-award-stage">
                <AwardDetails key={selected.grantId} award={selected} wasNew={openedAward?.isNew}
                  onPlay={() => recordReceipt({ award: selected, surface: 'audio' })} />
                <footer className="ach-award-detail-actions">
                  <Link className="ach-foot-action" to={`/achievements/${encodeURIComponent(selected.definitionId)}?tier=${selected.tier.tier}`}>В коллекцию наград<ChevronRight aria-hidden="true" /></Link>
                  {awards.length > 1 && <nav className="ach-scene-controls" aria-label="Просмотр наград тренировки">
                    <button type="button" className="ach-foot-action" disabled={position === 0} aria-label="Предыдущая награда"
                      onClick={() => selectAward(awards[position - 1])}><ChevronLeft aria-hidden="true" /></button>
                    <span aria-live="polite">Награда {position + 1} из {awards.length}</span>
                    <button type="button" className="ach-foot-action" disabled={position === awards.length - 1} aria-label="Следующая награда"
                      onClick={() => selectAward(awards[position + 1])}><ChevronRight aria-hidden="true" /></button>
                  </nav>}
                </footer>
              </div>
              {awards.length > 1 && (
                <section className="ach-award-picker" aria-labelledby="workout-award-list-title">
                  <h3 id="workout-award-list-title">Все награды <span>{awards.length}</span></h3>
                  <div className="ach-award-list">
                    {awards.map(award => (
                      <button type="button" className="ach-award" data-rarity={award.tier.rarity} key={award.grantId}
                        aria-pressed={award.grantId === selected.grantId} onClick={() => selectAward(award)}>
                        <AwardLabel award={award} />
                      </button>
                    ))}
                  </div>
                </section>
              )}
            </div>
          </SafetyDialogContent>
        </Dialog.Portal>
      )}
    </Dialog.Root>
  )
}
