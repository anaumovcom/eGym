import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Sparkles, ShieldCheck } from 'lucide-react'
import { useStage4Store } from '@/stores/stage4-store'
import { coachErrorMessage, coachSettingsApi } from '../lib/settings-api'
import { isCurrentCoachScope, useCoachSettingsScope } from '../lib/settings-scope'
import { DEFAULT_COACH_PREFERENCES, effectiveCoachState, preferencesValid, type CoachPreferences } from '../model/preferences'
import { CoachOperatorPanel } from './coach-operator-panel'
import { localAudioRuntime } from '../audio/local-audio-runtime'
import { CoachLocalPreview } from './coach-mini-debug'
import { CoachVoicePackSection, isPackSlot } from './coach-voice-pack'
import './coach-settings.css'

function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return <label className="flex items-start gap-3 rounded-xl border border-white/10 p-3 text-sm"><input type="checkbox" className="mt-1 accent-violet-500" checked={checked} onChange={event => onChange(event.target.checked)} /><span>{label}</span></label>
}
function Field({ label, children }: { label: string; children: ReactNode }) {
  return <label className="grid gap-2 text-sm"><span className="text-muted-foreground">{label}</span>{children}</label>
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
      setMessage('Настройки тренера сохранены отдельно от общих настроек.')
    } catch (error) { if (current()) setMessage(coachErrorMessage(error)) }
    finally { if (current()) setSaving(false) }
  }
  return <section aria-label="AI-тренер" className="coach-settings-panel overflow-hidden rounded-2xl border border-violet-400/25 bg-gradient-to-br from-violet-500/10 via-transparent to-sky-500/5">
    <header className="flex flex-wrap items-center justify-between gap-4 border-b border-white/10 p-5">
      <div className="flex items-center gap-3"><Sparkles className="h-6 w-6 text-violet-400" /><div><h2 className="text-xl font-semibold">AI-тренер</h2><p className="text-sm text-muted-foreground">Личные настройки · {userId} · {dirty ? 'Есть несохранённые изменения' : 'Отдельное сохранение'}</p></div></div>
      <span className="rounded-full border border-violet-400/25 px-3 py-1 text-xs">E05 · Локальные тестовые тоны · Без платной генерации</span>
    </header>
    <div className="space-y-5 p-5">
      <p className="text-sm text-muted-foreground">По умолчанию выключен. Общие голосовые подсказки не включают тренера. Микрофон не используется. Локальный режим не отправляет данные провайдеру.</p>
      {loading && <p role="status">Загрузка настроек тренера…</p>}
      {message && <p role="status" className="rounded-xl border border-white/10 p-3 text-sm">{message}</p>}
      <div className="grid gap-3 md:grid-cols-2">
        <Toggle label="Согласен на работу AI-тренера (версия 1)" checked={draft.consentVersion === 1} onChange={checked => { change('consentVersion', checked ? 1 : null); if (!checked) change('enabled', false) }} />
        <Toggle label="Включить AI-тренера" checked={draft.enabled} onChange={checked => change('enabled', checked)} />
        <Toggle label="Согласен на передачу данных внешнему провайдеру (версия 1)" checked={draft.networkConsentVersion === 1} onChange={checked => { change('networkConsentVersion', checked ? 1 : null); if (!checked) change('mode', 'local') }} />
        <Toggle label="Разрешить использование истории тренировок" checked={draft.historyConsent} onChange={checked => change('historyConsent', checked)} />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Режим тренера"><select className="rt-input" value={draft.mode} onChange={event => change('mode', event.target.value as CoachPreferences['mode'])}><option value="local">Локальный</option><option value="hybrid">Гибридный (сеть)</option><option value="text-only">Только текст (сеть, без звука)</option></select></Field>
        <Field label="Плотность общения"><select className="rt-input" value={draft.density} onChange={event => change('density', event.target.value as CoachPreferences['density'])}><option value="quiet">Тихий</option><option value="companion">Компаньон</option><option value="talkative">Разговорчивый</option></select></Field>
        <Field label="Подсчёт повторений"><select className="rt-input" value={draft.count} onChange={event => change('count', event.target.value as CoachPreferences['count'])}><option value="off">Выключен</option><option value="every">Каждое повторение</option><option value="last-three">Последние три</option><option value="milestones">Контрольные точки</option></select></Field>
        <Field label="Стиль тренера"><select className="rt-input" value={draft.style} onChange={event => change('style', event.target.value as CoachPreferences['style'])}><option value="companion">Живой компаньон</option><option value="calm">Спокойный</option></select></Field>
        <Field label="Юмор"><select className="rt-input" value={draft.humor} onChange={event => change('humor', event.target.value as CoachPreferences['humor'])}><option value="off">Без юмора</option><option value="light">Лёгкий</option><option value="often">Частый</option></select></Field>
        <Field label="Бюджет на тренировку, USD (не более 2)"><input className="rt-input" type="number" min="0.01" max="2" step="0.01" value={draft.budgetUsd} onChange={event => change('budgetUsd', event.target.value)} /></Field>
        <Field label="Громкость тренера"><select className="rt-input" value={draft.voiceVolume === null ? 'inherit' : String(draft.voiceVolume)} onChange={event => change('voiceVolume', event.target.value === 'inherit' ? null : Number(event.target.value))}><option value="inherit">Наследовать общую</option>{[...new Set([0, 0.25, 0.5, 0.75, 1, ...(draft.voiceVolume === null ? [] : [draft.voiceVolume])])].sort((a, b) => a - b).map(volume => <option key={volume} value={volume}>{Math.round(volume * 100)}%</option>)}</select></Field>
        <Field label="Голос подготовленных фраз"><select className="rt-input" value={isPackSlot(draft.voiceProfile) ? draft.voiceProfile : ''} onChange={event => change('voiceProfile', event.target.value || null)}><option value="">Не выбран</option><option value="female">Женский</option><option value="male">Мужской</option></select></Field>
      </div>
      <div className="grid gap-3 md:grid-cols-2"><Toggle label="Общение во время подходов" checked={draft.duringSets} onChange={checked => change('duringSets', checked)} /><Toggle label="Общение во время отдыха" checked={draft.duringRest} onChange={checked => change('duringRest', checked)} /></div>
      <p className="flex items-center gap-2 text-sm"><ShieldCheck className="h-4 w-4" />Провокационный юмор выключен. Голос фраз меняется только целиком: другой голос не подставляется вместо недостающих фраз.</p>
      <CoachVoicePackSection slot={draft.voiceProfile} />
      {!preferencesValid(draft) && <p role="alert" className="text-sm">Для включения нужно согласие на тренера; для сетевых режимов — сетевое согласие. Бюджет должен быть больше 0 и не более 2 USD.</p>}
      <p className="text-sm" data-testid="coach-effective">Сохранённый режим: {effective.textEnabled ? 'текст разрешён' : effective.audioEnabled ? 'звук разрешён' : 'выключен или заблокирован'} · Production paid readiness: false</p>
      <CoachLocalPreview />
      <div className="flex flex-wrap gap-3">
        <button className="rt-button" type="button" disabled={!saved || !dirty || saving || loading || !preferencesValid(draft)} onClick={() => { void save() }}>Сохранить настройки тренера</button>
        <button className="rt-button" type="button" disabled={!saved || saving || loading} onClick={() => { setDraft(saved!); setDirty(false); edits.current = 0 }}>Отменить изменения тренера</button>
        <button className="rt-button" type="button" disabled={saving || loading} onClick={() => { void hydrate(true) }}>Загрузить с сервера (заменить черновик)</button>
        <button className="rt-button" type="button" onClick={() => setOperatorOpen(value => !value)}>{operatorOpen ? 'Закрыть доступ оператора' : 'Доступ оператора Coach'}</button>
      </div>
      {operatorOpen && <CoachOperatorPanel epoch={epoch} />}
    </div>
  </section>
}