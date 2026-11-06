import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { AchievementLine } from '@/entities/achievement/model/types'
import { applicabilityLabels } from '@/entities/achievement/model/types'
import { formatNumber } from '@/screens/progress/progress-format'
import { AchievementImage, RarityBadge } from './achievement-media'

/** One collection line: every earned tier is shown as an icon with its title underneath; nothing else is revealed. */
export function AchievementCard({ line }: { line: AchievementLine }) {
  const earnedTiers = line.tiers.filter((tier) => tier.earned)
  const current = earnedTiers[earnedTiers.length - 1]

  if (!current) {
    return (
      <article className="ach-card ach-card-unknown" data-unknown aria-label={`Неизвестное достижение, раздел «${line.groupName}»`}>
        <AchievementImage tier={line.tiers[0]} decorative />
        <div className="ach-unknown-copy">
          <span className="ach-card-group">{line.groupName}</span>
          <h3>Неизвестное достижение</h3>
          <p>Описание и награды откроются после получения первой ступени.</p>
          <small>Ступеней в линии: {line.tiers.length}</small>
        </div>
      </article>
    )
  }

  const nextTier = line.tiers.find((tier) => tier.id === line.nextTierId)
  return (
    <article className="ach-card" data-rarity={current.rarity} data-earned data-new={line.isNew || undefined}>
      <Link className="ach-card-link" to={`/achievements/${encodeURIComponent(line.id)}`} aria-label={`Открыть достижение «${current.title}»`}>
        <div className="ach-card-topline">
          <span className="ach-card-group">{line.groupName}</span>
          {line.isNew && <span className="ach-new-badge">Новая</span>}
          <RarityBadge rarity={current.rarity} />
        </div>
        <ul className="ach-earned-tiers" aria-label={`Получено ступеней: ${line.highestTier} из ${line.tiers.length}`}>
          {earnedTiers.map((tier) => (
            <li key={tier.id} data-rarity={tier.rarity} data-current={tier.id === current.id || undefined}>
              <AchievementImage tier={tier} decorative />
              <span className="ach-earned-title">{tier.title}</span>
            </li>
          ))}
        </ul>
        <p className="ach-card-condition">{line.description}</p>
        <div className="ach-card-progress">
          <div className="ach-progress-copy">
            <span>{line.state === 'available' ? nextTier ? `Следующая: ступень ${nextTier.tier} из ${line.tiers.length}` : 'Все ступени получены' : applicabilityLabels[line.applicability]}</span>
            <b>{formatNumber(line.currentValue)} / {nextTier?.threshold ?? line.tiers[line.tiers.length - 1].threshold} <small>{line.unit}</small></b>
          </div>
          {nextTier?.minimumEvidenceDays != null && <small className="ach-evidence-days">Подтверждённая практика: {line.evidenceDays ?? 0} / {nextTier.minimumEvidenceDays} разных дней</small>}
          <div className="ach-progress" role="progressbar" aria-label={`Прогресс «${current.title}»`}
            aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(line.progressPercent)}>
            <span style={{ width: `${line.progressPercent}%` }} />
          </div>
        </div>
        <div className="ach-card-bottom"><span>{line.state === 'available' ? 'Открыть достижение' : 'Пока нет нужных данных'}</span><ChevronRight aria-hidden="true" /></div>
      </Link>
    </article>
  )
}
