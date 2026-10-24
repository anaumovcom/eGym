import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { coachPackClient, isPackSlot, type CoachPackClient, type PackState } from '../audio/pack-client'
import { generateCoachPack } from '../audio/pack-generation'
import type { CoachVoice } from '../model/contracts'

const STATE_LABELS: Record<PackState, string> = {
  not_prepared: 'Не подготовлено', downloading: 'Загрузка…', decoding: 'Подготовка звука…', ready: 'Готово',
  partial: 'Подготовлено частично', failed: 'Ошибка подготовки', offline: 'Нет связи с сервером',
}
const REASON_LABELS: Record<string, string> = {
  no_pack: 'набор фраз для этого голоса ещё не создан', unavailable: 'сервер недоступен', invalid_manifest: 'повреждённый список фраз',
  checksum: 'файл не прошёл проверку', decode: 'файл не удалось декодировать', quota: 'не хватает места в браузере', no_audio: 'звук браузера недоступен',
}
export { isPackSlot } from '../audio/pack-client'
/** Short Russian descriptions of the provider voices (subjective; the user picks by ear). */
export const COACH_VOICE_LABELS: Readonly<Record<CoachVoice, string>> = Object.freeze({
  ash: 'Ash — мужской, уверенный (по умолчанию)', alloy: 'Alloy — нейтральный, ровный', ballad: 'Ballad — мужской, мягкий',
  cedar: 'Cedar — мужской, низкий, естественный', coral: 'Coral — женский, тёплый', echo: 'Echo — мужской, спокойный',
  marin: 'Marin — женский, естественный', sage: 'Sage — женский, мягкий', shimmer: 'Shimmer — женский, светлый',
  verse: 'Verse — мужской, выразительный',
})

/** Restores cached phrases on mount; downloading and paid generation remain explicit. */
export function CoachVoicePackSection({ slot, userId, budgetUsd = '2.00', client = coachPackClient }: {
  slot: string | null; userId?: string; budgetUsd?: string; client?: CoachPackClient
}) {
  const snapshot = useSyncExternalStore(client.subscribe, client.snapshot)
  const [busy, setBusy] = useState(false)
  const [missing, setMissing] = useState(false)
  const [message, setMessage] = useState('')
  const controller = useRef<AbortController | null>(null)
  const epoch = useRef(0)
  useEffect(() => {
    setMissing(false); setMessage(''); setBusy(false)
    return () => { ++epoch.current; controller.current?.abort(); controller.current = null }
  }, [slot, userId])
  const selected = isPackSlot(slot) ? slot : null
  useEffect(() => {
    if (selected) void client.restore(selected).catch(() => {})
  }, [client, selected])
  const own = selected !== null && snapshot.slot === selected
  const total = snapshot.required + snapshot.optional
  const megabytes = (snapshot.encodedBytes / 1024 / 1024).toFixed(1)
  async function run(action: () => Promise<unknown>) {
    const current = epoch.current
    setBusy(true)
    try { await action() }
    catch { if (current === epoch.current) setMessage('Не удалось подготовить фразы. Проверьте связь с сервером.') }
    finally { if (current === epoch.current) setBusy(false) }
  }
  async function prepare() {
    if (!selected) return
    const current = epoch.current
    setMessage('')
    const result = await client.prepare(selected)
    if (current === epoch.current) setMissing(result.reason === 'no_pack')
  }
  async function generate() {
    if (!selected || !userId) return
    const abort = new AbortController()
    controller.current = abort
    setBusy(true); setMessage('Запуск генерации… Вход оператора и ключи API проверяются на сервере.')
    try {
      await generateCoachPack(selected, userId, budgetUsd, abort.signal, (done, count) => {
        if (!abort.signal.aborted) setMessage(`Создание фраз: ${done}/${count}`)
      })
      if (abort.signal.aborted) return
      setMessage('Фразы созданы. Загрузка на устройство…')
      await client.prepare(selected)
      if (!abort.signal.aborted) { setMissing(false); setMessage('') }
    } catch (error) {
      if (!abort.signal.aborted) setMessage(error instanceof Error ? error.message : 'Не удалось создать фразы.')
    } finally {
      if (!abort.signal.aborted) setBusy(false)
      if (controller.current === abort) controller.current = null
    }
  }
  return <section aria-label="Подготовленные фразы" className="grid gap-2 py-2.5 text-sm">
    <h4>Подготовленные фразы</h4>
    {selected === null
      ? <p>Выберите голос тренера, чтобы загрузить его подготовленные фразы на это устройство.</p>
      : <p role="status" data-testid="coach-pack-status">{own ? STATE_LABELS[snapshot.state] : STATE_LABELS.not_prepared}
        {own && total > 0 && ` · Подготовлено ${snapshot.prepared}/${total} · ${megabytes} MB`}
        {own && snapshot.reason && REASON_LABELS[snapshot.reason] && ` · ${REASON_LABELS[snapshot.reason]}`}
        {own && snapshot.unapproved > 0 && ` · фраз безопасности ждут прослушивания: ${snapshot.unapproved}`}</p>}
    <p className="text-xs text-muted-foreground">Скачивает готовые фразы выбранной модели и голоса на устройство — без задержек и интернета. Недостающие фразы можно создать через API после подтверждения; другой голос не подставляется.</p>
    {missing && <p>Для выбранного голоса набора ещё нет. Создание — платный запрос, нужен вход оператора и ключи API. Лимит этой подготовки: {budgetUsd} $. Уже созданные фразы используются повторно.</p>}
    {message && <p role="status">{message}</p>}
    <div className="flex flex-wrap gap-2">
      <button className="rt-button" type="button" disabled={selected === null || busy} onClick={() => { void run(prepare) }}>Подготовить частые фразы</button>
      {missing && userId && <button className="rt-button rt-button-primary" type="button" disabled={busy} onClick={() => { void generate() }}>Создать недостающие фразы (до {budgetUsd} $)</button>}
      {busy && controller.current && <button className="rt-button" type="button" onClick={() => { controller.current?.abort(); setBusy(false); setMessage('Генерация отменена. Уже созданные фразы сохранены.') }}>Отменить генерацию</button>}
      <button className="rt-button" type="button" disabled={busy} onClick={() => { void run(() => client.deleteLocal()) }}>Удалить локальные файлы</button>
    </div>
  </section>
}
