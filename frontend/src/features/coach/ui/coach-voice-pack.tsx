import { useState, useSyncExternalStore } from 'react'
import { coachPackClient, PACK_SLOTS, type CoachPackClient, type PackSlot, type PackState } from '../audio/pack-client'
import type { CoachVoice } from '../model/contracts'

const STATE_LABELS: Record<PackState, string> = {
  not_prepared: 'Не подготовлено', downloading: 'Загрузка…', decoding: 'Подготовка звука…', ready: 'Готово',
  partial: 'Подготовлено частично', failed: 'Ошибка подготовки', offline: 'Нет связи с сервером',
}
const REASON_LABELS: Record<string, string> = {
  no_pack: 'набор фраз для этого голоса ещё не создан', unavailable: 'сервер недоступен', invalid_manifest: 'повреждённый список фраз',
  checksum: 'файл не прошёл проверку', decode: 'файл не удалось декодировать', quota: 'не хватает места в браузере', no_audio: 'звук браузера недоступен',
}
export function isPackSlot(value: unknown): value is PackSlot { return PACK_SLOTS.includes(value as PackSlot) }
/** Short Russian descriptions of the provider voices (subjective; the user picks by ear). */
export const COACH_VOICE_LABELS: Readonly<Record<CoachVoice, string>> = Object.freeze({
  ash: 'Ash — мужской, уверенный (по умолчанию)', alloy: 'Alloy — нейтральный, ровный', ballad: 'Ballad — мужской, мягкий',
  cedar: 'Cedar — мужской, низкий, естественный', coral: 'Coral — женский, тёплый', echo: 'Echo — мужской, спокойный',
  marin: 'Marin — женский, естественный', sage: 'Sage — женский, мягкий', shimmer: 'Shimmer — женский, светлый',
  verse: 'Verse — мужской, выразительный',
})

/** E09: fetch/decode of a prepared pack only. Never generates or pays; never runs on mount. */
export function CoachVoicePackSection({ slot, client = coachPackClient }: { slot: string | null; client?: CoachPackClient }) {
  const snapshot = useSyncExternalStore(client.subscribe, client.snapshot)
  const [busy, setBusy] = useState(false)
  const selected = isPackSlot(slot) ? slot : null
  const own = selected !== null && snapshot.slot === selected
  const total = snapshot.required + snapshot.optional
  const megabytes = (snapshot.encodedBytes / 1024 / 1024).toFixed(1)
  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    try { await action() } finally { setBusy(false) }
  }
  return <section aria-label="Подготовленные фразы" className="grid gap-3 rounded-xl border border-white/10 p-4 text-sm">
    <h3 className="font-semibold">Подготовленные фразы</h3>
    {selected === null
      ? <p>Выберите голос тренера, чтобы загрузить его подготовленные фразы на это устройство.</p>
      : <p role="status" data-testid="coach-pack-status">{own ? STATE_LABELS[snapshot.state] : STATE_LABELS.not_prepared}
        {own && total > 0 && ` · Подготовлено ${snapshot.prepared}/${total} · ${megabytes} MB`}
        {own && snapshot.reason && REASON_LABELS[snapshot.reason] && ` · ${REASON_LABELS[snapshot.reason]}`}
        {own && snapshot.unapproved > 0 && ` · фраз безопасности ждут прослушивания: ${snapshot.unapproved}`}</p>}
    <p className="text-muted-foreground">Загружаются только уже готовые фразы. Недостающие фразы создаёт оператор отдельной платной задачей; здесь ничего не генерируется. Во время тренировки фразы берутся только из памяти устройства.</p>
    <div className="flex flex-wrap gap-3">
      <button className="rt-button" type="button" disabled={selected === null || busy} onClick={() => { if (selected) void run(() => client.prepare(selected)) }}>Подготовить частые фразы</button>
      <button className="rt-button" type="button" disabled={busy} onClick={() => { void run(() => client.deleteLocal()) }}>Удалить локальные файлы</button>
    </div>
  </section>
}
