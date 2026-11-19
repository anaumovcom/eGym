import { isPackSlot, type PackSlot } from './pack-client'

const ERRORS: Record<string, string> = {
  unauthorized: 'Войдите в «Доступ оператора Coach» внизу настроек и повторите подготовку.',
  secure_storage_unavailable: 'Не настроен доступ оператора или защищённое хранилище ключей. Для замены базовой записи нужен пароль оператора, но не ключ API.',
  credential_unavailable: 'Не найден ключ API в server vault. Сохраните ключи OpenAI и, для Fish Audio, Fish Audio в доступе оператора.',
  pack_generation_disabled: 'Генерация голоса выключена на сервере или цены не подтверждены оператором.',
  pack_generation_busy: 'Генерация уже идёт. Дождитесь её завершения и повторите загрузку.',
  pack_changed: 'На сервере уже другая версия пакета. Скачайте обновление и выберите фразу заново.',
  pack_not_prepared: 'Пакет ещё не опубликован на сервере.',
  clip_not_found: 'В этой версии пакета нет выбранной записи.',
  catalog_changed: 'Состав пакета изменился. Сначала обновите его.',
  local_voice_unavailable: 'Локальный синтезатор недоступен на сервере. Ранее скачанные записи сохранены.',
  coach_schema_outdated: 'База данных Coach требует обновления. Примените миграции или перезапустите локальный сервер для обновления схемы; генерация ещё не запускалась.',
  coach_internal_error: 'Ошибка сервера при подготовке фраз. Генерация не подтверждена; требуется проверка сервера Coach.',
  cap_exceeds_user_budget: 'Лимит подготовки превышает сохранённый лимит пользователя. Сохраните настройки и повторите.',
  generation_failed: 'Генерация остановлена: проверьте ключи API, лимиты расходов и доступность голосовой модели. Уже созданные фразы сохранены; повторная подготовка создаст только недостающие.',
  unavailable: 'Сервер Coach недоступен. Подготовка не завершена.',
}

async function request(path: string, signal: AbortSignal, body?: unknown, token?: string): Promise<Record<string, unknown>> {
  const response = await fetch(`/api/coach/${path}`, { method: body === undefined ? 'GET' : 'POST', credentials: 'include', signal: AbortSignal.any([signal, AbortSignal.timeout(15_000)]),
    headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { 'X-Coach-Run-Token': token } : {}) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) throw new Error(ERRORS.unauthorized)
    // Only an allow-listed code is displayed; never echo provider errors, secrets or request bodies.
    const raw = await response.json().catch(() => null) as { detail?: unknown } | null
    throw new Error(typeof raw?.detail === 'string' && ERRORS[raw.detail] ? ERRORS[raw.detail] : ERRORS.unavailable)
  }
  const raw: unknown = await response.json()
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error(ERRORS.unavailable)
  return raw as Record<string, unknown>
}

function wait(signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); signal.removeEventListener('abort', abort); reject(new DOMException('Aborted', 'AbortError')) }
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve() }, 1000)
    signal.addEventListener('abort', abort, { once: true })
    if (signal.aborted) abort()
  })
}

type Replacement = Readonly<{ clipId: string; expectedPackVersion: string }>
function clipAction(slot: PackSlot, target: Replacement, action: 'regenerate' | 'approve' | 'record') {
  if (!isPackSlot(slot) || !/^[a-z0-9-]{1,40}$/.test(target.clipId) || !/^[a-f0-9]{16}$/.test(target.expectedPackVersion)) throw new Error(ERRORS.unavailable)
  return `packs/${slot}/clips/${target.clipId}/${action}`
}

export async function approveCoachClip(slot: PackSlot, target: Replacement, signal: AbortSignal): Promise<void> {
  await request(clipAction(slot, target, 'approve'), signal, { expectedPackVersion: target.expectedPackVersion, listened: true })
}

/** Explicit paid operator action only. Auto-restoration and prepare/download remain GET-only. */
export async function generateCoachPack(slot: PackSlot, userId: string, capUsd: string, signal: AbortSignal,
  progress: (completed: number, total: number) => void, replacement?: Replacement): Promise<void> {
  if (!isPackSlot(slot)) throw new Error(ERRORS.unavailable)
  let run: { id: string; token: string; job: string } | null = null
  let completed = false
  try {
    if (signal.aborted) return
    // Receive the run token even if the UI cancels during startup, then cancel the server job in finally.
    const path = replacement ? clipAction(slot, replacement, 'regenerate') : `packs/${slot}/prepare`
    const result = await request(path, AbortSignal.timeout(15_000), { userId, capUsd, confirmPaid: true,
      ...(replacement ? { expectedPackVersion: replacement.expectedPackVersion } : { includeOptional: true }) })
    if (result.state === 'completed') { completed = true; return }
    if (![result.runId, result.runToken, result.jobId].every(value => typeof value === 'string' && /^[a-zA-Z0-9_-]{1,128}$/.test(value))) throw new Error(ERRORS.unavailable)
    run = { id: result.runId as string, token: result.runToken as string, job: result.jobId as string }
    const deadline = Date.now() + 20 * 60_000
    while (!signal.aborted && Date.now() < deadline) {
      const status = await request(`runs/${run.id}/jobs/${run.job}`, signal, undefined, run.token)
      if (!Number.isSafeInteger(status.completed) || !Number.isSafeInteger(status.total)) throw new Error(ERRORS.unavailable)
      progress(Number(status.completed), Number(status.total))
      if (status.state === 'completed') { completed = true; return }
      if (status.state !== 'queued') throw new Error(ERRORS.generation_failed)
      await wait(signal)
    }
    if (!signal.aborted) throw new Error(ERRORS.generation_failed)
  } catch (error) {
    if (signal.aborted) throw error
    throw error instanceof Error && Object.values(ERRORS).includes(error.message) ? error : new Error(ERRORS.unavailable)
  } finally {
    if (run && !completed) {
      // Independent bounded cancellation survives unmount/user/voice changes.
      await request(`runs/${run.id}/jobs/${run.job}/action`, AbortSignal.timeout(5000), { action: 'cancel' }, run.token).catch(() => {})
    }
  }
}

export type RecordingPace = 'normal' | 'slow' | 'brisk'
export async function recordStarterClip(target: Replacement, pace: RecordingPace, signal: AbortSignal): Promise<void> {
  await request(clipAction('ru-base', target, 'record'), signal, { expectedPackVersion: target.expectedPackVersion, pace, confirmLocal: true })
}