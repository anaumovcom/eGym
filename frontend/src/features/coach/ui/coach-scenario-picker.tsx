import * as Dialog from '@radix-ui/react-dialog'
import { Briefcase, Check, Clapperboard, Crosshair, Flag, Headphones, LoaderCircle, Medal, Rocket, Sparkles, Swords, Tv, Video, Zap, type LucideIcon } from 'lucide-react'
import { useLayoutEffect, useState, useSyncExternalStore } from 'react'
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
  const { scenario, preparation, state } = useSyncExternalStore(coachNetworkClient.subscribe, coachNetworkClient.getSnapshot, coachNetworkClient.getSnapshot)
  const safety = useSafetyDockTarget()
  const phase = scenario?.phase ?? 'off'
  const prebuilding = preparation?.state === 'preparing'
  const loading = prebuilding || ['waiting', 'proposing', 'building'].includes(phase)
  const open = safety === null && (prebuilding || ['waiting', 'proposing', 'choosing', 'building', 'failed'].includes(phase))
  const [panelTop, setPanelTop] = useState(112)
  useLayoutEffect(() => {
    if (!open) return
    // A non-modal panel below the real header keeps STOP clickable and in the
    // accessibility tree, including when the kiosk header wraps on a narrow screen.
    const header = document.querySelector('.forma-system-dock')
    if (!header) return
    const update = () => setPanelTop(Math.max(16, header.getBoundingClientRect().bottom + 16))
    update()
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(update) : null
    observer?.observe(header)
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => { observer?.disconnect(); window.removeEventListener('resize', update); window.removeEventListener('scroll', update, true) }
  }, [open])
  if (!scenario) return null
  const stage = prebuilding ? 2 : phase === 'building' ? 1 : 0
  const hint = prebuilding ? 'Готовим голосовые реплики для упражнения, чтобы тренер мог говорить без лишних пауз.'
    : phase === 'waiting' ? state === 'retrying' ? 'Восстанавливаем связь с тренером. Подготовка продолжится после подключения.'
      : 'Подключаемся к тренеру и получаем состояние подготовки.'
      : phase === 'building' ? 'Пишем историю под ваш план: связываем упражнения и подходы в один сюжет.'
        : phase === 'proposing' ? 'Придумываем три разных сюжета под ваш план тренировки.'
          : phase === 'failed' ? ERRORS[scenario.error ?? ''] ?? 'Сценарий не получился.'
            : 'Тренер проведёт всю тренировку в выбранном мире. План и вес не меняются.'
  return <Dialog.Root open={open} modal={false}>
    <Dialog.Portal>
      <div className="coach-scenario-backdrop" style={{ top: panelTop - 8 }} aria-hidden="true" />
      <Dialog.Content className={`coach-scenario-dialog${loading ? ' is-preparing' : ''}`}
        style={{ top: panelTop, maxHeight: `calc(100dvh - ${panelTop + 16}px)` }}
        onEscapeKeyDown={event => event.preventDefault()} onInteractOutside={event => event.preventDefault()}
        onCloseAutoFocus={event => event.preventDefault()}>
        <header>
          <Sparkles aria-hidden="true" />
          <div><span className="coach-scenario-eyebrow">Ваш персональный тренер</span>
            <Dialog.Title>{loading ? 'Готовим тренировку' : 'Выберите сюжет тренировки'}</Dialog.Title></div>
        </header>
        <Dialog.Description className="coach-scenario-hint">{hint}</Dialog.Description>
        {loading && <section className="coach-preparation" aria-label="Подготовка тренера" aria-busy="true">
          {scenario.title && <p className="coach-preparation-story"><Clapperboard aria-hidden="true" /><span>Выбранный сюжет<strong>{scenario.title}</strong></span></p>}
          <ol className="coach-preparation-stages">
            {['Варианты сюжета', 'Сценарий тренировки', 'Озвучка упражнения'].map((label, index) => <li key={label}
              data-state={index < stage ? 'done' : index === stage ? 'current' : 'pending'} aria-current={index === stage ? 'step' : undefined}>
              <span className="coach-preparation-step" aria-hidden="true">{index < stage ? <Check /> : index === stage ? <LoaderCircle /> : index + 1}</span>
              <span><strong>{label}</strong><small>{index < stage ? 'Готово' : index === stage
                ? index === 2 ? 'Предзагрузка голосовых реплик' : index === 1 ? 'Создаём историю тренировки' : phase === 'waiting' ? 'Ожидаем подключения' : 'Готовим варианты для выбора'
                : 'Следующий этап'}</small></span>
            </li>)}
          </ol>
          <div className="coach-preparation-status" role="status" aria-live="polite" aria-atomic="true">
            <Headphones aria-hidden="true" />
            <div>{prebuilding && preparation ? <>
              <strong>{preparation.total > 0 ? `Обработано реплик: ${preparation.completed} из ${preparation.total}` : 'Составляем список голосовых реплик'}</strong>
              <span>Готово к воспроизведению: {preparation.ready}</span>
              {preparation.completed > preparation.ready && <span>Не все реплики удалось загрузить. Подготовка остальных продолжается.</span>}
            </> : <><strong>{phase === 'waiting' ? 'Ожидаем связь с тренером' : 'Тренер работает над вашим сюжетом'}</strong>
              <span>План упражнений и настройки нагрузки не меняются.</span></>}</div>
          </div>
          <p className="coach-preparation-note">{prebuilding ? 'Можно продолжить без ожидания. Уже звучащая речь не прервётся.'
            : 'Подготовка касается только тренера. Управление тренажёром и СТОП доступны сверху.'}</p>
        </section>}
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
        <footer>
          {(phase === 'choosing' || phase === 'failed') && scenario.proposalsLeft > 0 &&
            <button type="button" className="rt-button" onClick={() => coachNetworkClient.proposeScenarios()}>
              Другие варианты ({scenario.proposalsLeft})</button>}
          {phase === 'failed' && scenario.proposalsLeft === 0 && scenario.error !== 'no_more_proposals' &&
            <button type="button" className="rt-button" onClick={() => coachNetworkClient.proposeScenarios()}>Попробовать снова</button>}
          <button type="button" className="rt-button" onClick={() => coachNetworkClient.skipScenario()}>
            {prebuilding ? 'Продолжить без ожидания' : 'Без сценария'}</button>
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
