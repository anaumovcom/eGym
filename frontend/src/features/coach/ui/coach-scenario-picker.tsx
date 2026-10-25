import * as Dialog from '@radix-ui/react-dialog'
import { Briefcase, Clapperboard, Crosshair, Flag, Medal, Rocket, Sparkles, Swords, Tv, Video, Zap, type LucideIcon } from 'lucide-react'
import { useSyncExternalStore } from 'react'
import { useSafetyDockTarget } from '@/shared/ui/overlays/safety-dialog'
import { coachNetworkClient } from '../live/coach-live-runtime'
import type { ScenarioView } from '../live/coach-network-client'
import './coach-scenario.css'

const ICONS: Readonly<Record<string, LucideIcon>> = {
  stream: Video, race: Flag, rpg: Swords, final: Medal, mission: Crosshair, movie: Clapperboard, show: Tv, space: Rocket,
  heist: Briefcase, kaiju: Zap,
}
const ERRORS: Readonly<Record<string, string>> = {
  budget: 'Не хватает бюджета тренировки на сценарий.', pipeline_busy: 'Тренер был занят. Попробуйте ещё раз.',
  provider_timeout: 'Сценарист не успел ответить.', invalid_scenarios: 'Сценарист ответил неразборчиво.',
  invalid_bible: 'Не удалось написать мир сценария.', no_more_proposals: 'Варианты на эту тренировку закончились.',
  provider_unavailable: 'Облачный тренер недоступен.',
}

function useScenario(): ScenarioView | undefined {
  const snapshot = useSyncExternalStore(coachNetworkClient.subscribe, coachNetworkClient.getSnapshot, coachNetworkClient.getSnapshot)
  return snapshot.scenario
}

/** V1: before the first set the coach offers three stories; the chosen one frames the whole workout. */
export function CoachScenarioPicker() {
  const scenario = useScenario()
  const safety = useSafetyDockTarget()
  const phase = scenario?.phase ?? 'off'
  const open = safety === null && ['proposing', 'choosing', 'building', 'failed'].includes(phase)
  if (!scenario) return null
  return <Dialog.Root open={open} onOpenChange={value => { if (!value) coachNetworkClient.skipScenario() }}>
    <Dialog.Portal>
      <Dialog.Overlay className="coach-scenario-overlay" />
      <Dialog.Content className="coach-scenario-dialog" aria-describedby="coach-scenario-hint">
        <header>
          <Sparkles aria-hidden="true" />
          <Dialog.Title>Выберите сюжет тренировки</Dialog.Title>
        </header>
        <p id="coach-scenario-hint" className="coach-scenario-hint">
          {phase === 'building' ? `Тренер пишет мир «${scenario.title ?? 'сценария'}»…`
            : phase === 'proposing' ? 'Тренер придумывает три сюжета под ваш план…'
              : phase === 'failed' ? ERRORS[scenario.error ?? ''] ?? 'Сценарий не получился.'
                : 'Тренер проведёт всю тренировку в выбранном мире. План и вес не меняются.'}
        </p>
        {phase === 'choosing' && <ul className="coach-scenario-cards">
          {scenario.cards.map((card, index) => {
            const Icon = ICONS[card.archetype] ?? Sparkles
            return <li key={card.archetype}><button type="button" className="coach-scenario-card" data-archetype={card.archetype}
              onClick={() => coachNetworkClient.selectScenario(index)}>
              <Icon aria-hidden="true" />
              <strong>{card.title}</strong>
              <span>{card.tagline}</span>
              <em>{card.tone}</em>
            </button></li>
          })}
        </ul>}
        {(phase === 'proposing' || phase === 'building') && <div className="coach-scenario-cards" aria-busy="true">
          {[0, 1, 2].map(index => <div key={index} className="coach-scenario-card is-loading" aria-hidden="true" />)}
        </div>}
        <footer>
          {(phase === 'choosing' || phase === 'failed') && scenario.proposalsLeft > 0 &&
            <button type="button" className="rt-button" onClick={() => coachNetworkClient.proposeScenarios()}>
              Другие варианты ({scenario.proposalsLeft})</button>}
          {phase === 'failed' && scenario.proposalsLeft === 0 && scenario.error !== 'no_more_proposals' &&
            <button type="button" className="rt-button" onClick={() => coachNetworkClient.proposeScenarios()}>Попробовать снова</button>}
          <Dialog.Close asChild><button type="button" className="rt-button">Без сценария</button></Dialog.Close>
        </footer>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>
}

/** The chosen story and the current act, next to the exercise counter. */
export function CoachScenarioChip({ exerciseId }: { exerciseId: string }) {
  const scenario = useScenario()
  if (!scenario || scenario.phase !== 'ready' || !scenario.title) return null
  const act = scenario.acts.find(item => item.exerciseIds.includes(exerciseId))
  const Icon = ICONS[scenario.archetype ?? ''] ?? Sparkles
  const counters = scenario.counters.filter(counter => typeof counter.value === 'number')
  return <span className="rt-chip coach-scenario-chip" title={scenario.tagline ?? undefined}>
    <Icon aria-hidden="true" />
    <span>{scenario.title}{act ? ` · Акт ${act.act}/${scenario.acts.length}: ${act.title}` : ''}</span>
    {counters.map(counter => <span key={counter.id} className="coach-scenario-counter">
      {counter.label}: {counter.id === 'boss' ? `${counter.value}%` : counter.value?.toLocaleString('ru-RU')}</span>)}
  </span>
}
