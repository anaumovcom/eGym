import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { Sparkles } from 'lucide-react'
import { useStage4Store } from '@/stores/stage4-store'
import { coachErrorMessage, coachSettingsApi } from '../lib/settings-api'
import { isCurrentCoachScope, useCoachSettingsScope } from '../lib/settings-scope'
import {
  COACH_EXTRAS, COACH_HUMOR_KINDS, COACH_NICKNAME, COACH_STYLES, DEFAULT_COACH_PREFERENCES, effectiveCoachState, preferencesValid,
  type CoachExtra, type CoachHumorKind, type CoachPreferences,
} from '../model/preferences'
import { CoachOperatorPanel } from './coach-operator-panel'
import { localAudioRuntime } from '../audio/local-audio-runtime'
import { CoachLocalPreview } from './coach-mini-debug'
import { CoachVoicePackSection, COACH_VOICE_LABELS } from './coach-voice-pack'
import { COACH_VOICES, coachVoice } from '../model/contracts'
import './coach-settings.css'

const MODE_HINTS: Record<CoachPreferences['mode'], string> = {
  local: 'Готовые фразы, без интернета и расходов.',
  hybrid: 'Живые реплики голосом. Нужен интернет, тратит лимит.',
  'text-only': 'Живые реплики текстом, без звука.',
}
const STYLES: Record<CoachPreferences['style'], [string, string]> = {
  companion: ['Напарник', 'Тёплый и энергичный, с лёгкой иронией.'],
  calm: ['Спокойный наставник', 'Ровно и уверенно, без лишних эмоций.'],
  strict: ['Строгий сержант', 'Коротко и требовательно, но без унижений.'],
  showman: ['Спортивный комментатор', 'Каждый подход — как момент прямой трансляции.'],
  stoic: ['Философ-стоик', 'Сдержанно, с короткими афоризмами о дисциплине.'],
}
const HUMOR_KIND_LABELS: Record<CoachHumorKind, string> = {
  irony: 'Ирония', absurd: 'Абсурд', wordplay: 'Каламбуры', self: 'Самоирония тренера',
}
const EXTRA_LABELS: Record<CoachExtra, string> = {
  callbacks: 'Коронные шутки', 'pop-culture': 'Отсылки к кино и спорту', trivia: 'Любопытные факты', breathing: 'Подсказки по дыханию',
}
const EXTRA_HINTS: Record<CoachExtra, string> = {
  callbacks: 'Иногда возвращается к своим прошлым шуткам.',
  'pop-culture': 'Сравнения из фильмов, спорта и мультфильмов.',
  trivia: 'Интересное о мышцах и тренировках на отдыхе.',
  breathing: 'На отдыхе напоминает выдохнуть и расслабить плечи.',
}

function Toggle({ label, hint, checked, onChange }: { label: string; hint?: string; checked: boolean; onChange: (checked: boolean) => void }) {
  const id = useId()
  return <div className="coach-row">
    <label className="coach-row-main"><span>{label}</span><input type="checkbox" role="switch" className="coach-switch" aria-describedby={hint ? id : undefined} checked={checked} onChange={event => onChange(event.target.checked)} /></label>
    {hint && <p id={id} className="coach-row-hint">{hint}</p>}
  </div>
}
function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return <div className="coach-row"><label className="coach-row-main"><span>{label}</span>{children}</label>{hint && <p className="coach-row-hint">{hint}</p>}</div>
}
function Chips<T extends string>({ label, options, labels, titles, value, onChange }: {
  label: string; options: readonly T[]; labels: Record<T, string>; titles?: Record<T, string>; value: readonly T[]; onChange: (next: T[]) => void
}) {
  return <div className="coach-row"><span className="coach-row-label">{label}</span>
    <div role="group" aria-label={label} className="coach-chips">
      {options.map(option => <label key={option} className="coach-chip" title={titles?.[option]}>
        <input type="checkbox" checked={value.includes(option)} onChange={event => onChange(toggled(value, option, event.target.checked))} /><span>{labels[option]}</span>
      </label>)}
    </div>
  </div>
}
function Group({ title, note, children }: { title: string; note?: string; children: ReactNode }) {
  return <section aria-label={title} className="coach-group">
    <header className="coach-group-title"><h3>{title}</h3>{note && <span className="coach-note">{note}</span>}</header>
    <div className="coach-rows">{children}</div>
  </section>
}
function toggled<T>(list: readonly T[], value: T, on: boolean): T[] {
  return on ? [...list.filter(item => item !== value), value] : list.filter(item => item !== value)
}
function problems(p: CoachPreferences): string[] {
  const list: string[] = []
  if (p.enabled && p.consentVersion !== 1) list.push('Чтобы включить тренера, отметьте согласие на его работу.')
  if (p.mode !== 'local' && p.networkConsentVersion !== 1) list.push('Для облачного режима нужно согласие на отправку данных.')
  if (!/^\d{1,3}(\.\d{1,4})?$/.test(p.budgetUsd) || !(Number(p.budgetUsd) > 0 && Number(p.budgetUsd) <= 2)) list.push('Лимит — от 0.01 до 2 $.')
  if (p.nickname.length > 24 || !COACH_NICKNAME.test(p.nickname)) list.push('Имя: только буквы, пробел или дефис, до 24 символов.')
  return list
}
export function CoachSettingsPanel() {
  const { userId, epoch } = useCoachSettingsScope()
  if (!userId) return <section aria-label="AI-тренер" className="rt-panel p-5">Выберите пользователя для настройки AI-тренера.</section>
  // Key changes synchronously with the external-store epoch, even for batched A→B→A.
  return <UserCoachSettings key={epoch} userId={userId} epoch={epoch} />
}
function UserCoachSettings({ userId, epoch }: { userId: string; epoch: number }) {
  const [saved, setSaved] = useState<CoachPreferences | null>(null)
  const [draft, setDraft] = useState<CoachPreferences>(DEFAULT_COACH_PREFERENCES)
  const [dirty, setDirty] = useState(false)
  const edits = useRef(0)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const [operatorOpen, setOperatorOpen] = useState(false)
  const alive = useRef(false)
  const sequence = useRef(0)
  const controller = useRef<AbortController | null>(null)
  const general = useStage4Store(state => state.settingsSaved)
  const effective = effectiveCoachState(saved, { soundEnabled: general.soundEnabled === true, voiceHintsEnabled: general.voiceHintsEnabled === true,
    volume: Number(String(general.signalVolume).replace('%', '')) / 100 }, import.meta.env.VITE_COACH_ENABLED === 'true')

  function change<K extends keyof CoachPreferences>(name: K, value: CoachPreferences[K]) {
    edits.current++
    setDraft(current => ({ ...current, [name]: value }))
    setDirty(true)
  }
  async function hydrate(discard = false) {
    controller.current?.abort()
    const abort = new AbortController()
    controller.current = abort
    const id = ++sequence.current
    const initialEdits = edits.current
    const current = () => alive.current && isCurrentCoachScope(epoch) && sequence.current === id && !abort.signal.aborted
    setLoading(true); setMessage('')
    try {
      const next = await coachSettingsApi.get(userId, abort.signal)
      if (!current()) return
      localAudioRuntime.setSavedCoachPreferences(userId, next)
      setSaved(next)
      if (edits.current === initialEdits && (discard || edits.current === 0)) { setDraft(next); setDirty(false); edits.current = 0 }
    } catch (error) { if (current()) setMessage(coachErrorMessage(error)) }
    finally { if (current()) setLoading(false) }
  }
  useEffect(() => {
    alive.current = true
    void hydrate()
    return () => { alive.current = false; ++sequence.current; controller.current?.abort() }
  }, [userId, epoch])

  async function save() {
    if (!saved || saving || loading || !preferencesValid(draft)) return
    controller.current?.abort()
    const abort = new AbortController()
    controller.current = abort
    const id = ++sequence.current
    const initialEdits = edits.current
    const current = () => alive.current && isCurrentCoachScope(epoch) && sequence.current === id && !abort.signal.aborted
    setSaving(true); setMessage('')
    try {
      const next = await coachSettingsApi.save(userId, { ...draft, revision: saved.revision }, saved.revision, abort.signal)
      if (!current()) return
      localAudioRuntime.setSavedCoachPreferences(userId, next)
      setSaved(next)
      if (edits.current === initialEdits) { setDraft(next); setDirty(false); edits.current = 0 }
      setMessage('Настройки тренера сохранены.')
    } catch (error) { if (current()) setMessage(coachErrorMessage(error)) }
    finally { if (current()) setSaving(false) }
  }
  const cloud = draft.mode !== 'local'
  const issues = problems(draft)
  const status = effective.textEnabled ? 'пишет текстом' : effective.audioEnabled ? 'говорит голосом' : 'молчит'
  return <section aria-label="AI-тренер" className="coach-settings-panel overflow-clip rounded-2xl border border-violet-400/25 bg-gradient-to-br from-violet-500/10 via-transparent to-sky-500/5">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
      <div className="flex items-center gap-2"><Sparkles className="h-5 w-5 text-violet-400" /><h2 className="text-lg font-semibold">AI-тренер</h2></div>
      <span className="coach-status" data-state={status === 'молчит' ? 'off' : 'on'} data-testid="coach-effective" title={status === 'молчит' ? 'Тренер выключен или в общих настройках нет звука.' : undefined}>Сейчас тренер {status}</span>
    </header>
    <div className="grid items-start gap-3 p-3 lg:grid-cols-2">
      {loading && <p role="status" className="text-sm text-muted-foreground lg:col-span-2">Загрузка настроек тренера…</p>}
      <div className="grid gap-3">
        <Group title="Основное">
          <Toggle label="Включить AI-тренера" checked={draft.enabled} onChange={checked => change('enabled', checked)} />
          <Toggle label="Согласие на работу AI-тренера" checked={draft.consentVersion === 1} onChange={checked => { change('consentVersion', checked ? 1 : null); if (!checked) change('enabled', false) }} />
          <Field label="Режим тренера" hint={MODE_HINTS[draft.mode]}><select className="rt-input" value={draft.mode} onChange={event => change('mode', event.target.value as CoachPreferences['mode'])}><option value="local">Без интернета</option><option value="hybrid">Облачный ИИ, голос</option><option value="text-only">Облачный ИИ, только текст</option></select></Field>
          {cloud && <Toggle label="Согласие на отправку данных тренировки в облачный ИИ" hint="Уходят факты тренировки и настройки характера, включая имя." checked={draft.networkConsentVersion === 1} onChange={checked => { change('networkConsentVersion', checked ? 1 : null); if (!checked) change('mode', 'local') }} />}
          {cloud && <Field label="Лимит на тренировку, $ (до 2)"><input className="rt-input" type="number" min="0.01" max="2" step="0.01" value={draft.budgetUsd} onChange={event => change('budgetUsd', event.target.value)} /></Field>}
          <Toggle label="Учитывать историю тренировок" checked={draft.historyConsent} onChange={checked => change('historyConsent', checked)} />
        </Group>
        <Group title="Когда говорить">
          <Field label="Плотность общения"><select className="rt-input" value={draft.density} onChange={event => change('density', event.target.value as CoachPreferences['density'])}><option value="quiet">Только главное</option><option value="companion">Обычно</option><option value="talkative">Разговорчиво</option></select></Field>
          <Field label="Подсчёт повторений"><select className="rt-input" value={draft.count} onChange={event => change('count', event.target.value as CoachPreferences['count'])}><option value="off">Не считать</option><option value="every">Каждое</option><option value="last-three">Последние три</option><option value="milestones">Контрольные точки</option></select></Field>
          <Toggle label="Говорить во время подходов" checked={draft.duringSets} onChange={checked => change('duringSets', checked)} />
          <Toggle label="Говорить во время отдыха" checked={draft.duringRest} onChange={checked => change('duringRest', checked)} />
        </Group>
        <Group title="Голос">
          <Field label="Голос тренера"><select className="rt-input" value={coachVoice(draft.voiceProfile)} onChange={event => change('voiceProfile', coachVoice(event.target.value))}>{COACH_VOICES.map(voice => <option key={voice} value={voice}>{COACH_VOICE_LABELS[voice]}</option>)}</select></Field>
          <Field label="Громкость тренера"><select className="rt-input" value={draft.voiceVolume === null ? 'inherit' : String(draft.voiceVolume)} onChange={event => change('voiceVolume', event.target.value === 'inherit' ? null : Number(event.target.value))}><option value="inherit">Как общая</option>{[...new Set([0, 0.25, 0.5, 0.75, 1, ...(draft.voiceVolume === null ? [] : [draft.voiceVolume])])].sort((a, b) => a - b).map(volume => <option key={volume} value={volume}>{Math.round(volume * 100)}%</option>)}</select></Field>
          <CoachVoicePackSection slot={draft.voiceProfile} />
        </Group>
      </div>
      <Group title="Характер и юмор" note={cloud ? undefined : 'Только с облачным ИИ'}>
        <Field label="Стиль тренера" hint={STYLES[draft.style][1]}><select className="rt-input" value={draft.style} onChange={event => change('style', event.target.value as CoachPreferences['style'])}>{COACH_STYLES.map(style => <option key={style} value={style}>{STYLES[style][0]}</option>)}</select></Field>
        <Field label="Обращение"><select className="rt-input" value={draft.address} onChange={event => change('address', event.target.value as CoachPreferences['address'])}><option value="ty">На «ты»</option><option value="vy">На «вы»</option></select></Field>
        <Field label="Как вас называть"><input className="rt-input" type="text" maxLength={24} autoComplete="off" placeholder="Без имени" value={draft.nickname} onChange={event => change('nickname', event.target.value)} /></Field>
        <Field label="Юмор"><select className="rt-input" value={draft.humor} onChange={event => change('humor', event.target.value as CoachPreferences['humor'])}><option value="off">Без шуток</option><option value="light">Иногда</option><option value="often">Часто</option></select></Field>
        {draft.humor !== 'off' && <>
          <Chips label="Виды юмора" options={COACH_HUMOR_KINDS} labels={HUMOR_KIND_LABELS} value={draft.humorKinds} onChange={next => change('humorKinds', next)} />
          <Toggle label="Чёрный юмор (18+)" hint="Мрачные шутки о тяготах тренировки. Без шуток о боли, травмах, теле и людях." checked={draft.edgyOptIn} onChange={checked => change('edgyOptIn', checked)} />
        </>}
        <Chips label="Фишки" options={COACH_EXTRAS} labels={EXTRA_LABELS} titles={EXTRA_HINTS} value={draft.extras} onChange={next => change('extras', next)} />
        {draft.extras.length > 0 && <p className="coach-row-hint">{draft.extras.map(extra => EXTRA_HINTS[extra]).join(' ')}</p>}
      </Group>
    </div>
    <footer className="coach-footer">
      {issues.length > 0 && <ul role="alert" className="coach-issues">{issues.map(issue => <li key={issue}>{issue}</li>)}</ul>}
      <p role="status" className="mr-auto text-sm text-muted-foreground">{message || (dirty ? 'Есть несохранённые изменения' : 'Все изменения сохранены')}</p>
      <button className="rt-button" type="button" disabled={!saved || !dirty || saving || loading} onClick={() => { setDraft(saved!); setDirty(false); edits.current = 0 }}>Отменить изменения тренера</button>
      <button className="rt-button rt-button-primary" type="button" disabled={!saved || !dirty || saving || loading || !preferencesValid(draft)} onClick={() => { void save() }}>Сохранить настройки тренера</button>
    </footer>
    <div className="px-3 pb-3">
      <details className="rounded-xl border border-white/10 px-3 py-2 text-sm">
        <summary className="cursor-pointer text-muted-foreground">Диагностика и доступ оператора</summary>
        <div className="mt-3 grid gap-3">
          <CoachLocalPreview />
          <div className="flex flex-wrap gap-3">
            <button className="rt-button" type="button" disabled={saving || loading} onClick={() => { void hydrate(true) }}>Загрузить с сервера (заменить черновик)</button>
            <button className="rt-button" type="button" onClick={() => setOperatorOpen(value => !value)}>{operatorOpen ? 'Закрыть доступ оператора' : 'Доступ оператора Coach'}</button>
          </div>
          {operatorOpen && <CoachOperatorPanel epoch={epoch} />}
        </div>
      </details>
    </div>
  </section>
}