import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { AchievementLine, AchievementTier } from '@/entities/achievement/model/types'
import { AchievementImage, RarityBadge } from './achievement-media'

const date = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })

export function EarnedAwardCard({ line, tier, eager }: { line: AchievementLine; tier: AchievementTier; eager: boolean }) {
  const earnedAt = tier.earnedAt ?? tier.awardedAt
  return (
    <Link className="ach-earned-card" data-rarity={tier.rarity}
      to={`/achievements/${encodeURIComponent(line.id)}?tier=${tier.tier}`} aria-label={`Открыть награду «${tier.title}»`}>
      <AchievementImage tier={tier} decorative eager={eager} />
      <div className="ach-earned-copy">
        <div className="ach-earned-meta"><RarityBadge rarity={tier.rarity} /><span>Ступень {tier.tier}</span>
          {tier.isNew && <span className="ach-unread">Новая</span>}</div>
        <h2>{tier.title}</h2><p>{line.name}</p>
        {tier.phrase && <p className="ach-gallery-line">{tier.phrase}</p>}
        {earnedAt && <time dateTime={earnedAt}>{date.format(new Date(earnedAt))}</time>}
      </div>
      <ChevronRight className="ach-gallery-arrow" aria-hidden="true" />
    </Link>
  )
}
