import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react'
import { Volume2 } from 'lucide-react'
import { useRuntimeStore } from '@/stores/runtime-store'
import { useStage4Store } from '@/stores/stage4-store'
import { localAudioRuntime } from '../audio/local-audio-runtime'
import { coachPackSlot } from '../audio/pack-client'
import { isCoachFoundationEnabled } from '../lib/runtime-observation'
import { coachErrorMessage, coachSettingsApi } from '../lib/settings-api'
import { loadPlaybackProfile, rememberPlaybackProfile } from '../lib/playback-profile'
import { isCurrentCoachScope, useCoachSettingsScope } from '../lib/settings-scope'
import { COACH_VOICES, coachVoice } from '../model/contracts'
import { DEFAULT_COACH_PREFERENCES, effectiveCoachState, preferencesValid, type CoachPreferences } from '../model/preferences'
import { CoachLocalPreview } from './coach-mini-debug'
import { CoachOperatorPanel } from './coach-operator-panel'
import { COACH_VOICE_LABELS, CoachVoicePackSection } from './coach-voice-pack'
import './coach-settings.css'

const fishVoices = { '0a690dbeb3984a9f88cd39353880775f': 'Меллстрой', '6d23d3209d6849e0b24ddae6f734afe9': 'Екатерина' }
function Group({ title, children }: { title: string; children: ReactNode }) {
  return <section className="coach-group" aria-label={title}><header className="coach-group-title"><h3>{title}</h3></header><div className="coach-rows">{children}</div></section>
}
function Field({ label, children }: { label: string; children: ReactNode }) {
  return <div className="coach-row"><label className="coach-row-main"><span>{label}</span>{children}</label></div>
}
function Switch({ label, checked, change }: { label: string; checked: boolean; change: (v: boolean) => void }) {
  return <Field label={label}><input type="checkbox" role="switch" className="coach-switch" checked={checked} onChange={e => change(e.target.checked)} /></Field>
}
export function CoachSettingsPanel() {
  const { userId, epoch } = useCoachSettingsScope()
  if (!userId) return <section aria-label="AI-тренер" className="rt-panel p-5">Выберите пользователя для настройки голосового тренера.</section>
  return <UserCoachSettings key={epoch} userId={userId} epoch={epoch} />
}

function UserCoachSettings({ userId, epoch }: { userId: string; epoch: number }) {
  const [saved, setSaved] = useState<CoachPreferences | null>(null)
  const [draft, setDraft] = useState<CoachPreferences>(DEFAULT_COACH_PREFERENCES)
  const [loading, setLoading] = useState(true), [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(''), [operator, setOperator] = useState(false)
  const [offline, setOffline] = useState(false)
  const edits = useRef(0), controller = useRef<AbortController | null>(null)
  const changes = useRef<Partial<CoachPreferences>>({})
  const dirty = edits.current > 0
  const general = useStage4Store(s => s.settingsSaved)
  const view = useRuntimeStore(s => s.session?.view)
  const audio = useSyncExternalStore(localAudioRuntime.subscribe, localAudioRuntime.getSnapshot)
  const locked = view === 'exercise-session' || view === 'rest' || audio.reason === 'hardware_active' || audio.reason === 'safety'
  const volume = Number(String(general.signalVolume).replace('%', '')) / 100
  const effective = effectiveCoachState(saved, { soundEnabled: general.soundEnabled === true, voiceHintsEnabled: general.voiceHintsEnabled === true, volume }, isCoachFoundationEnabled())
  const slot = coachPackSlot(saved)
  function change(patch: Partial<CoachPreferences>) { edits.current++; changes.current = { ...changes.current, ...patch }; setDraft(p => ({ ...p, ...patch })); setMessage('') }
  function begin() { controller.current?.abort(); const next = new AbortController(); controller.current = next; return next.signal }
  function current(signal: AbortSignal) { return !signal.aborted && isCurrentCoachScope(epoch) }
  function accept(next: CoachPreferences, revision: number) {
    localAudioRuntime.setSavedCoachPreferences(userId, next); setSaved(next)
    if (edits.current === revision) { setDraft(next); edits.current = 0; changes.current = {} }
    else setDraft({ ...next, ...changes.current })
  }
  async function load() {
    const signal = begin(), revision = edits.current
    setLoading(true); setMessage('')
    try {
      const result = await loadPlaybackProfile(userId, signal)
      if (current(signal)) { accept(result.value, revision); setOffline(result.offline) }
    }
    catch (error) { if (current(signal)) setMessage(coachErrorMessage(error)) }
    finally { if (current(signal)) setLoading(false) }
  }
  useEffect(() => { void load(); return () => controller.current?.abort() }, [userId, epoch])
  async function save() {
    if (offline || !saved || saving || !preferencesValid(draft)) return
    const signal = begin(), revision = edits.current
    setSaving(true); setMessage('')
    try {
      const next = await coachSettingsApi.save(userId, { ...draft, mode: 'local', networkConsentVersion: null, revision: saved.revision }, saved.revision, signal)
      if (current(signal)) { rememberPlaybackProfile(userId, next); accept(next, revision); if (edits.current === 0) setMessage('Настройки тренера сохранены.') }
    } catch (error) { if (current(signal)) setMessage(coachErrorMessage(error)) }
    finally { if (current(signal)) setSaving(false) }
  }
  async function forgetMemory() {
    const signal = begin(); setSaving(true)
    try { await coachSettingsApi.forgetMemory(userId, signal); if (current(signal)) setMessage('Память всех разговоров очищена. История результатов не изменена.') }
    catch (error) { if (current(signal)) setMessage(coachErrorMessage(error)) }
    finally { if (current(signal)) setSaving(false) }
  }
  const fish = draft.voiceModel === 'fish-drama-3'
  return <section aria-label="AI-тренер" className="coach-settings-panel overflow-clip rounded-2xl border border-white/15">
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3"><div className="flex items-center gap-2"><Volume2 aria-hidden="true" /><h2 className="text-lg font-semibold">Голосовой тренер</h2></div>
      <span className="coach-status" data-state={effective.audioEnabled ? 'on' : 'off'} data-testid="coach-effective">{effective.audioEnabled ? 'Голос включён' : 'Голос выключен'}</span></header>
    <p className="px-4 pt-3 text-sm">Во время тренировки звучат только скачанные записи: счёт, советы и ключевые события. Данные упражнения не отправляются на озвучивание.</p>
    {loading && <p role="status" className="px-4 pt-2">Загрузка настроек тренера…</p>}
    {offline && <p role="status" className="px-4 pt-2">Сервер недоступен. Скачанные записи можно слушать; для изменений восстановите связь и загрузите настройки с сервера.</p>}
    <div className="grid items-start gap-3 p-3 lg:grid-cols-2"><fieldset disabled={offline} className="grid min-w-0 gap-3">
      <Group title="Сопровождение">
        <Switch label="Включить AI-тренера" checked={draft.enabled} change={enabled => change({ enabled })} />
        <Switch label="Согласие на работу AI-тренера" checked={draft.consentVersion === 1} change={on => change(on ? { consentVersion: 1 } : { consentVersion: null, enabled: false })} />
        <Field label="Подсчёт повторений"><select className="rt-input" value={draft.count} onChange={e => change({ count: e.target.value as CoachPreferences['count'] })}>
          <option value="every">Каждое повторение</option><option value="last-three">Последние три</option><option value="milestones">Контрольные точки</option><option value="off">Не считать</option></select></Field>
        <Switch label="Советы во время подхода" checked={draft.duringSets} change={duringSets => change({ duringSets })} />
        <Switch label="Советы в паузах отдыха" checked={draft.duringRest} change={duringRest => change({ duringRest })} />
        <Field label="Громкость тренера"><select className="rt-input" value={draft.voiceVolume ?? 'inherit'} onChange={e => change({ voiceVolume: e.target.value === 'inherit' ? null : Number(e.target.value) })}>
          <option value="inherit">Как общая</option>{[...new Set([0, 0.25, 0.5, 0.75, 1, ...(draft.voiceVolume === null ? [] : [draft.voiceVolume])])].sort((a,b) => a-b).map(v => <option key={v} value={v}>{Math.round(v*100)}%</option>)}</select></Field>
      </Group>
      <Group title="Выбор голоса">
        <Field label="Голосовая модель"><select className="rt-input" value={draft.standardPack ? 'ru-base' : draft.voiceModel} onChange={e => change(e.target.value === 'ru-base' ? { standardPack: true } : { standardPack: false, voiceModel: e.target.value as CoachPreferences['voiceModel'] })}>
          <option value="ru-base">Базовый русский (бесплатно)</option>
          <option value="fish-drama-3">Fish Audio</option><option value="openai-tts">OpenAI TTS</option><option value="openai-realtime">OpenAI Realtime (записи)</option></select></Field>
        {draft.standardPack ? <p className="py-2">Готовый русский голос. Для скачивания не нужны ни ключ, ни вход оператора.</p> : fish ? <Field label="Голос Fish Audio"><select className="rt-input" value={draft.fishVoiceId || draft.persona} onChange={e => change(e.target.value === 'streamer' || e.target.value === 'classic' ? { fishVoiceId: '', persona: e.target.value } : { fishVoiceId: e.target.value })}>
          <option value="streamer">Голос стримера</option><option value="classic">Голос напарника</option>{Object.entries(fishVoices).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          {draft.fishVoiceId && !Object.hasOwn(fishVoices, draft.fishVoiceId) && <option value={draft.fishVoiceId}>Сохранённый голос</option>}</select></Field>
        : <Field label="Голос тренера"><select className="rt-input" value={draft.voiceProfile} onChange={e => change({ voiceProfile: coachVoice(e.target.value) })}>{COACH_VOICES.map(v => <option key={v} value={v}>{COACH_VOICE_LABELS[v]}</option>)}</select></Field>}
        <p className="coach-row-hint py-2">Модель используется только для записи пакета в настройках. Во время упражнения другой голос не подставляется.</p>
      </Group>
    </fieldset><Group title="Пакет на этом устройстве">
      {locked ? <p className="py-3">Управление записями доступно до или после тренировки, когда тренажёр остановлен.</p> : saved && slot === coachPackSlot(draft)
        ? <CoachVoicePackSection slot={slot} userId={offline ? undefined : userId} budgetUsd={saved.budgetUsd} volume={general.soundEnabled && volume > 0 ? (saved.voiceVolume ?? volume) : 0} />
        : <p className="py-3">{saved ? 'Сохраните выбранный голос, чтобы скачать его пакет.' : 'Для выбора пакета нужны настройки профиля.'}</p>}
    </Group></div>
    <footer className="coach-footer">
      {draft.enabled && draft.consentVersion !== 1 && <p role="alert">Чтобы включить голосового тренера, отметьте согласие на его работу.</p>}
      <p role="status" className="mr-auto text-sm">{message || (dirty ? 'Есть несохранённые изменения' : '')}</p>
      <button className="rt-button" type="button" disabled={!saved || !dirty || saving || loading} onClick={() => { setDraft(saved!); edits.current = 0; changes.current = {}; setMessage('') }}>Отменить изменения тренера</button>
      <button className="rt-button rt-button-primary" type="button" disabled={offline || !saved || !dirty || saving || loading || !preferencesValid(draft)} onClick={() => void save()}>Сохранить настройки тренера</button>
    </footer>
    <details className="m-3 rounded-xl border border-white/10 px-3 py-2 text-sm"><summary>Диагностика и доступ оператора</summary><div className="mt-3 grid gap-3">
      <CoachLocalPreview /><div className="flex flex-wrap gap-2">
        <button className="rt-button" type="button" disabled={saving || loading} onClick={() => void load()}>Загрузить с сервера (заменить черновик)</button>
        <button className="rt-button" type="button" disabled={saving || loading} onClick={() => void forgetMemory()}>Удалить память тренера</button>
        <button className="rt-button" type="button" onClick={() => setOperator(v => !v)}>{operator ? 'Закрыть доступ оператора' : 'Доступ оператора Coach'}</button></div>
      {operator && <CoachOperatorPanel epoch={epoch} />}</div></details>
  </section>
}
