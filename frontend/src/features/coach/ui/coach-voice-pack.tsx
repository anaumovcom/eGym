import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { coachPackClient, isPackSlot, type CoachPackClient, type PackSlot, type PackState } from '../audio/pack-client'
import { approveCoachClip, generateCoachPack, recordStarterClip, type RecordingPace } from '../audio/pack-generation'
import { previewPackClip } from '../audio/pack-preview'
import type { CoachVoice } from '../model/contracts'

export { isPackSlot } from '../audio/pack-client'
export const COACH_VOICE_LABELS: Readonly<Record<CoachVoice, string>> = {
  ash: 'Ash — мужской, уверенный', alloy: 'Alloy — нейтральный', ballad: 'Ballad — мужской, мягкий', cedar: 'Cedar — мужской, низкий',
  coral: 'Coral — женский, тёплый', echo: 'Echo — мужской, спокойный', marin: 'Marin — женский, естественный',
  sage: 'Sage — женский, мягкий', shimmer: 'Shimmer — женский, светлый', verse: 'Verse — мужской, выразительный',
}
const STATES: Record<PackState, string> = { not_prepared: 'Не скачан', downloading: 'Скачивание…', decoding: 'Проверка записей…', ready: 'Готово',
  partial: 'Пакет скачан не полностью', failed: 'Не удалось установить пакет', offline: 'Нет связи с сервером' }
const REASONS: Record<string, string> = { no_pack: 'пакет этого голоса ещё не создан', unavailable: 'не все файлы доступны',
  invalid_manifest: 'повреждён список фраз', checksum: 'не совпала контрольная сумма записи', decode: 'не удалось декодировать запись',
  quota: 'недостаточно места на устройстве', no_storage: 'хранилище браузера недоступно; откройте приложение на localhost или по HTTPS', no_audio: 'звук в браузере недоступен' }
const GROUPS: Record<string, string> = { guidance: 'Советы тренера', technique: 'Подсказки к технике', lifecycle: 'Начало и пауза',
  rest: 'Отдых', outcome: 'Завершение', time: 'Контрольные точки', safety: 'Безопасность', count: 'Счёт повторений', countdown: 'Обратный отсчёт', other: 'Другие записи' }
const order = new Intl.Collator('ru', { numeric: true })
type Props = { slot: string | null; userId?: string; budgetUsd?: string; volume?: number; client?: CoachPackClient }
type Operation = 'download' | 'generate' | 'replace' | 'approve' | 'preview' | 'delete'

export function CoachVoicePackSection({ slot, userId, budgetUsd = '2.00', volume = 1, client = coachPackClient }: Props) {
  if (!isPackSlot(slot)) return <p>Выберите и сохраните голос тренера, чтобы скачать пакет.</p>
  return <PackControls key={`${userId}:${slot}`} slot={slot} userId={userId} budgetUsd={budgetUsd} volume={volume} client={client} />
}

function PackControls({ slot, userId, budgetUsd, volume, client }: { slot: PackSlot; userId?: string; budgetUsd: string; volume: number; client: CoachPackClient }) {
  const snapshot = useSyncExternalStore(client.subscribe, client.snapshot)
  const installed = client.installed(slot)
  const [busy, setBusy] = useState<Operation | null>(null)
  const [message, setMessage] = useState('')
  const [missing, setMissing] = useState(false)
  const [choice, setChoice] = useState('')
  const [confirmation, setConfirmation] = useState<string | null>(null)
  const [heard, setHeard] = useState<string | null>(null)
  const [pace, setPace] = useState<RecordingPace>('normal')
  const active = useRef<AbortController | null>(null)
  useEffect(() => {
    const restore = new AbortController()
    void client.restore(slot, { signal: restore.signal }).catch(() => {})
    return () => { restore.abort(); active.current?.abort() }
  }, [client, slot])
  useEffect(() => { if (volume === 0 && busy === 'preview') cancel() }, [volume, busy])

  const entries = Object.entries(installed?.clips ?? {}).sort(([a], [b]) => order.compare(a, b))
  const groups = Object.entries(GROUPS).map(([key, label]) => ({ label, rows: entries.filter(([, clip]) =>
    (Object.hasOwn(GROUPS, clip.group) ? clip.group : 'other') === key) })).filter(group => group.rows.length > 0)
  const selectedId = installed && Object.hasOwn(installed.clips, choice) ? choice : groups[0]?.rows[0]?.[0]
  const clip = selectedId ? installed?.clips[selectedId] : null
  const version = installed?.packVersion
  const recording = `${version}:${selectedId}`
  const own = snapshot.slot === slot
  const cap = Number(budgetUsd) > 2 ? '2.00' : budgetUsd // The server accepts at most $2 per explicit preparation.

  function cancel() {
    active.current?.abort(); active.current = null; setBusy(null)
    setMessage(busy === 'preview' ? '' : 'Операция остановлена. Платные запросы автоматически не повторяются.')
  }
  function run(kind: Operation, action: (signal: AbortSignal) => Promise<void>) {
    if (active.current) return
    const task = new AbortController(); active.current = task
    setBusy(kind); setMessage(''); setConfirmation(null)
    void action(task.signal).catch((error: unknown) => {
      if (!task.signal.aborted) setMessage(kind === 'generate' || kind === 'replace' || kind === 'approve'
        ? (error instanceof Error ? error.message : 'Операция не выполнена.') : 'Не удалось прочитать запись или хранилище устройства.')
    }).finally(() => { if (active.current === task) { active.current = null; if (!task.signal.aborted) setBusy(null) } })
  }
  async function download(signal: AbortSignal) {
    const result = await client.prepare(slot, signal)
    if (signal.aborted) return
    setMissing(result.reason === 'no_pack')
    if (result.state === 'ready') setMessage('Пакет сохранён на этом устройстве.')
    else if (client.installed(slot)) setMessage('Остаётся доступна установленная версия. Для обновления повторите скачивание.')
  }
  function generate(replace: boolean) {
    if (!userId || (replace && (!version || !selectedId || confirmation !== recording))) return
    run(replace ? 'replace' : 'generate', async signal => {
      setMessage('Подготовка записей…')
      const target = replace ? { clipId: selectedId!, expectedPackVersion: version! } : undefined
      if (slot === 'ru-base') {
        if (!target) return
        await recordStarterClip(target, pace, signal)
      } else await generateCoachPack(slot, userId, cap, signal, (done, total) => { if (!signal.aborted) setMessage(`Создано записей: ${done}/${total}`) }, target)
      if (!signal.aborted) { setMessage('Скачивание новой версии…'); await download(signal) }
    })
  }
  return <section aria-label="Голосовой пакет" className="grid min-w-0 gap-3 py-3 text-sm">
    <p>Скачайте записи на это устройство до тренировки. Прослушивание и счёт используют только локальные файлы.</p>
    <p role="status" data-testid="coach-pack-status"><strong>{own ? STATES[snapshot.state] : STATES.not_prepared}</strong>
      {own && snapshot.required + snapshot.optional > 0 && ` · ${installed && (snapshot.state === 'ready' || snapshot.state === 'offline') ? 'Готово к воспроизведению' : 'Проверено'}: ${snapshot.prepared}/${snapshot.required + snapshot.optional} · ${(snapshot.encodedBytes / 1024 / 1024).toFixed(1)} МБ`}
      {own && snapshot.reason && REASONS[snapshot.reason] && ` · ${REASONS[snapshot.reason]}`}
      {own && snapshot.unapproved > 0 && ` · На проверке: ${snapshot.unapproved}`}</p>
    <div className="flex flex-wrap gap-2">
      <button type="button" className="rt-button rt-button-primary" disabled={!!busy} onClick={() => run('download', download)}>Скачать голосовой пакет</button>
      {installed && <button type="button" className="rt-button" disabled={!!busy} onClick={() => run('delete', async () => { await client.deleteLocal(slot) })}>Удалить с устройства</button>}
    </div>
    {(missing || !!installed?.missingClips) && userId && slot !== 'ru-base' && <div className="grid gap-2">
      <p>{missing ? 'Готового пакета на сервере пока нет.' : `В каталоге есть дополнительные записи: ${installed?.missingClips}.`} Недостающие записи можно создать заранее. Это платное действие оператора; скачивание уже созданных записей бесплатно.</p>
      <button type="button" className="rt-button" disabled={!!busy} onClick={() => generate(false)}>Создать недостающие фразы (до {cap} $)</button>
    </div>}
    {installed && clip && selectedId && version && <div className="coach-pack-library grid min-w-0 gap-2 border-t border-white/10 pt-3">
      <label className="grid gap-1">Фраза пакета <select className="rt-input w-full min-w-0" disabled={!!busy && busy !== 'preview'} value={selectedId} onChange={e => {
        if (busy === 'preview') cancel(); setChoice(e.target.value); setConfirmation(null); setMessage('')
      }}>{groups.map(group => <optgroup label={group.label} key={group.label}>{group.rows.map(([id, row]) => <option key={id} value={id}>{row.text}</option>)}</optgroup>)}</select></label>
      <p>«{clip.text}»{!clip.approved && ' · Только для проверки. На тренировке не прозвучит.'}</p>
      <div className="flex flex-wrap gap-2">
        {busy === 'preview' ? <button type="button" className="rt-button" onClick={cancel}>Остановить прослушивание</button> :
          <button type="button" className="rt-button" disabled={!!busy || volume <= 0} onClick={() => run('preview', async signal => {
            const played = await previewPackClip(client, slot, selectedId, volume, signal)
            if (!signal.aborted) { if (played) setHeard(recording); else setMessage('Не удалось воспроизвести локальную запись. Проверьте звук или скачайте пакет ещё раз.') }
          })}>Прослушать</button>}
        {userId && <button type="button" className="rt-button" disabled={!!busy} onClick={() => setConfirmation(recording)}>Перегенерировать фразу</button>}
        {userId && !clip.approved && heard === recording && <button type="button" className="rt-button" disabled={!!busy} onClick={() => run('approve', async signal => {
          await approveCoachClip(slot, { clipId: selectedId, expectedPackVersion: version }, signal)
          if (!signal.aborted) await download(signal)
        })}>Одобрить прослушанную запись</button>}
      </div>
      {volume <= 0 && <p className="coach-row-hint">Для прослушивания включите звук и увеличьте громкость.</p>}
      {confirmation === recording && <div role="group" aria-label="Подтверждение замены" className="grid gap-2 rounded-xl border border-amber-400/40 p-3">
        <p>Заменить только «{clip.text}» в пакете этого голоса? {slot === 'ru-base' ? 'Бесплатно, без облака.' : `Лимит — ${cap} $.`} Нужен вход оператора: запись общая для этого голоса. Остальные записи не изменятся.</p>
        {slot === 'ru-base' && <label>Темп новой записи <select className="rt-input" value={pace} onChange={e => setPace(e.target.value as RecordingPace)}><option value="normal">Обычный</option><option value="slow">Медленнее</option><option value="brisk">Быстрее</option></select></label>}
        <div className="flex flex-wrap gap-2"><button className="rt-button rt-button-primary" type="button" onClick={() => generate(true)}>Подтвердить замену</button>
          <button className="rt-button" type="button" onClick={() => setConfirmation(null)}>Не заменять</button></div>
      </div>}
    </div>}
    {busy && busy !== 'preview' && busy !== 'delete' && <button className="rt-button" type="button" onClick={cancel}>Отменить операцию</button>}
    {message && <p role="status">{message}</p>}
  </section>
}
