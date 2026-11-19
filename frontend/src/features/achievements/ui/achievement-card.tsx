import { Check, ChevronRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { AchievementLine } from '@/entities/achievement/model/types'
import { applicabilityLabels } from '@/entities/achievement/model/types'
import { achievementUnit } from '@/features/achievements/lib/achievement-units'
import { currentTier } from '@/features/achievements/lib/collection-filters'
import { formatNumber } from '@/screens/progress/progress-format'
import { AchievementImage, RarityBadge } from './achievement-media'
import { CollectionSymbol } from './collection-symbol'

export function AchievementCard({ line }: { line: AchievementLine }) {
  const earned = line.tiers.filter((tier) => tier.earned)
  const current = currentTier(line)
  const next = line.tiers.find((tier) => tier.id === line.nextTierId)
  const rarity = (current ?? line.tiers[0]).rarity
  return (
    <article className="ach-card" data-rarity={rarity} data-group={line.group} data-earned={Boolean(current) || undefined}>
      <Link className="ach-card-link" to={`/achievements/${encodeURIComponent(line.id)}`} aria-label={`Открыть достижение «${line.name}»`}>
        <div className="ach-card-topline">
          <span className="ach-card-group">{line.groupName}</span>
          {line.isNew && <span className="ach-new-badge">Новая</span>}
          <RarityBadge rarity={rarity} />
        </div>
        <div className="ach-series-heading">
          <span className="ach-series-symbol"><CollectionSymbol group={line.group} /></span>
          <h2>{line.name}</h2>
        </div>
        {!line.archived && <p className="ach-card-condition">{line.description}</p>}
        {current && <ul className="ach-earned-tiers" aria-label={`Получено ступеней: ${earned.length} из ${line.tiers.length}`}>
          {earned.map((tier) => <li key={tier.id} data-rarity={tier.rarity} data-current={tier.id === current.id || undefined}>
            <AchievementImage tier={tier} decorative />
            <span className="ach-earned-title">{tier.title}</span>
          </li>)}
        </ul>}
        <div className="ach-card-progress">
          <div className="ach-progress-copy">
            {next ? <><span>{line.state === 'insufficient_data' ? applicabilityLabels[line.applicability] : `Ступень ${next.tier} из ${line.tiers.length}`}</span>
              <b>{formatNumber(line.currentValue)} / {formatNumber(next.threshold)} <small>{achievementUnit(line.unit, next.threshold)}</small></b></>
              : <span><Check aria-hidden="true" />{line.archived ? 'В архиве коллекции' : 'Все ступени получены'}</span>}
          </div>
          {next && <div className="ach-progress" role="progressbar" aria-label={`Прогресс «${line.name}»`}
            aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(line.progressPercent)}>
            <span style={{ width: `${line.progressPercent}%` }} />
          </div>}
        </div>
        <div className="ach-card-bottom"><span>{line.archived ? 'Посмотреть награды' : 'Все ступени'}</span><ChevronRight aria-hidden="true" /></div>
      </Link>
    </article>
  )
}
