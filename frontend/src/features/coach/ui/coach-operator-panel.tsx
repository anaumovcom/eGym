import { useEffect, useRef, useState } from 'react'
import { CoachApiError, coachErrorMessage, coachSettingsApi, type CredentialProvider, type CredentialStatus, type OperatorSession } from '../lib/settings-api'
import { isCurrentCoachScope } from '../lib/settings-scope'

const checkLabels: Readonly<Record<string, string>> = {
  not_checked: 'не выполнялась', auth_ok_models_not_verified: 'ключ принят провайдером',
  auth_failed: 'ключ отклонён провайдером', provider_unavailable: 'провайдер недоступен',
}
const PROVIDERS: readonly CredentialProvider[] = ['openai', 'fish']
const PROVIDER_LABELS: Record<CredentialProvider, { name: string; placeholder: string; hint: string }> = {
  openai: { name: 'OpenAI', placeholder: 'sk-…', hint: 'Обязателен: текст тренера и голоса OpenAI.' },
  fish: { name: 'Fish Audio', placeholder: 'ключ fish.audio', hint: 'Нужен только для голосовой модели Fish Audio Drama 3.' },
}
type ByProvider<T> = Record<CredentialProvider, T>
const NO_CREDENTIALS: ByProvider<CredentialStatus | null> = { openai: null, fish: null }
const NO_KEYS: ByProvider<string> = { openai: '', fish: '' }
/** The single next action for the operator, so the panel reads as a short checklist. */
function nextStep(credential: CredentialStatus): string {
  if (!credential.configured) return 'Шаг 1 из 3: вставьте API-ключ OpenAI (начинается с sk-) и нажмите «Сохранить ключ».'
  if (credential.lastCheckStatus === 'auth_ok_models_not_verified') return 'Готово. Шаг 3 из 3: выше включите оба согласия и «Включить AI-тренера», выберите режим «Гибридный (сеть)» и нажмите «Сохранить настройки тренера».'
  if (credential.lastCheckStatus === 'auth_failed') return 'Провайдер не принял ключ: вставьте другой ключ и сохраните его.'
  if (credential.lastCheckStatus === 'provider_unavailable') return 'Провайдер не ответил: проверьте интернет и повторите проверку.'
  return 'Шаг 2 из 3: нажмите «Проверить ключ» — это бесплатно, генерация не запускается.'
}

/** Secrets exist only in these transient inputs and the lifetime of a single request. */
export function CoachOperatorPanel({ epoch }: { epoch: number }) {
  const [session, setSession] = useState<OperatorSession | null>(null)
  const [credentials, setCredentials] = useState(NO_CREDENTIALS)
  const [password, setPassword] = useState('')
  const [keys, setKeys] = useState(NO_KEYS)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const operation = useRef(0)
  const controller = useRef<AbortController | null>(null)
  const alive = useRef(false)
  const versions = useRef<ByProvider<number | null>>({ openai: null, fish: null })

  function start() {
    controller.current?.abort()
    const abort = new AbortController()
    controller.current = abort
    const id = ++operation.current
    setBusy(true)
    setMessage('')
    return { signal: abort.signal, current: () => alive.current && isCurrentCoachScope(epoch) && operation.current === id && !abort.signal.aborted }
  }
  function acceptCredential(provider: CredentialProvider, value: CredentialStatus) {
    versions.current = { ...versions.current, [provider]: value.credentialVersion }
    setCredentials(current => ({ ...current, [provider]: value }))
  }
  async function loadCredential(request: ReturnType<typeof start>, provider: CredentialProvider) {
    const next = await coachSettingsApi.credentials(request.signal, provider)
    if (request.current()) acceptCredential(provider, next)
  }
  /** Fish Audio is optional: its status is fetched only when the operator opens it. */
  async function openProvider(provider: CredentialProvider) {
    const request = start()
    try { await loadCredential(request, provider) }
    catch (error) { if (request.current()) failed(error) }
    finally { if (request.current()) setBusy(false) }
  }
  function clearSecrets() {
    setPassword('')
    setKeys(NO_KEYS)
  }
  function failed(error: unknown) {
    setMessage(coachErrorMessage(error))
    // Fail closed, including session expiry/conflict. Reauthorization refreshes versions.
    setSession(null)
    setCredentials(NO_CREDENTIALS)
    versions.current = { openai: null, fish: null }
    clearSecrets()
  }
  useEffect(() => {
    alive.current = true
    const request = start()
    void (async () => {
      try {
        const next = await coachSettingsApi.session(request.signal)
        if (!request.current()) return
        setSession(next)
        if (next.authorized) await loadCredential(request, 'openai')
      } catch (error) { if (request.current()) failed(error) }
      finally { if (request.current()) setBusy(false) }
    })()
    return () => { alive.current = false; ++operation.current; controller.current?.abort() }
  }, [epoch])

  async function login() {
    const captured = password
    clearSecrets()
    const request = start()
    try {
      const next = await coachSettingsApi.login(captured, request.signal)
      if (!request.current()) return
      setSession(next)
      await loadCredential(request, 'openai')
    } catch (error) {
      if (!request.current()) return
      const code = error instanceof CoachApiError ? error.code : null
      if (session?.setupAvailable && !session.authorized && (code === 'unauthorized' || code === 'rate_limited')) {
        // Rejected login, not an expired session: keep the form so the operator can retry.
        setMessage(code === 'unauthorized' ? 'Неверный пароль оператора. Проверьте раскладку клавиатуры и Caps Lock.' : coachErrorMessage(error))
        return
      }
      failed(error)
    }
    finally { if (request.current()) setBusy(false) }
  }
  async function logout() {
    clearSecrets(); setSession(null); setCredentials(NO_CREDENTIALS); versions.current = { openai: null, fish: null }
    const request = start()
    try {
      await coachSettingsApi.logout(request.signal)
      if (request.current()) setSession({ authorized: false, setupAvailable: true })
    } catch (error) { if (request.current()) failed(error) }
    finally { if (request.current()) setBusy(false) }
  }
  async function credentialAction(provider: CredentialProvider, action: 'save' | 'delete' | 'check') {
    const credential = credentials[provider]
    if (!credential || versions.current[provider] !== credential.credentialVersion) return
    const captured = keys[provider]
    clearSecrets()
    const expectedVersion = credential.credentialVersion
    const request = start()
    try {
      const next = action === 'save' ? await coachSettingsApi.putCredential(captured, expectedVersion, request.signal, provider) :
        action === 'delete' ? await coachSettingsApi.deleteCredential(expectedVersion, request.signal, provider) :
        await coachSettingsApi.checkCredential(request.signal, provider)
      if (!request.current() || versions.current[provider] !== expectedVersion) return
      if ((action === 'check' && next.credentialVersion !== expectedVersion) ||
          (action !== 'check' && next.credentialVersion <= expectedVersion)) {
        failed(new Error())
        return
      }
      acceptCredential(provider, next)
      setMessage(action === 'check' ? 'Проверка доступа завершена. Генерация не запускалась.' : action === 'save' ? 'Ключ сохранён в защищённом хранилище сервера.' : 'Ключ удалён.')
    } catch (error) { if (request.current()) failed(error) }
    finally { if (request.current()) setBusy(false) }
  }
  function credentialBlock(provider: CredentialProvider) {
    const credential = credentials[provider]
    const label = PROVIDER_LABELS[provider]
    if (!credential) return provider === 'openai' || !credentials.openai ? null :
      <button key={provider} className="rt-button" type="button" disabled={busy} onClick={() => { void openProvider(provider) }}>Ключ {label.name} (голос Drama 3)</button>
    return <div key={provider} className="space-y-3 rounded-xl border border-white/10 p-3">
      <p className="text-sm"><b>{label.name}</b> · Ключ: {credential.configured ? 'сохранён' : 'не задан'} · Проверка: {checkLabels[credential.lastCheckStatus ?? 'not_checked'] ?? credential.lastCheckStatus} · Версия {credential.credentialVersion}</p>
      <p className="text-sm text-muted-foreground">{label.hint}</p>
      {provider === 'openai' && credential.storageAvailable && <p className="rounded-xl border border-violet-400/30 bg-violet-500/10 p-3 text-sm">{nextStep(credential)}</p>}
      {!credential.storageAvailable ? <p>Настройте защищённое хранилище vault на сервере. Ввод ключа недоступен.</p> : <>
        <form className="flex flex-wrap items-end gap-3" onSubmit={event => { event.preventDefault(); void credentialAction(provider, 'save') }}>
          <label className="grid gap-2 text-sm">{credential.configured ? `Заменить ключ ${label.name}` : `API-ключ ${label.name}`}<input aria-label={provider === 'openai' ? 'Ключ провайдера' : `Ключ ${label.name}`} className="rt-input" type="password" autoComplete="off" placeholder={label.placeholder} maxLength={512} value={keys[provider]} disabled={busy} onChange={event => { const value = event.target.value; setKeys(current => ({ ...current, [provider]: value })) }} /></label>
          <button className="rt-button" type="submit" disabled={busy || !keys[provider]}>Сохранить ключ</button>
        </form>
        <div className="flex flex-wrap gap-3"><button className="rt-button" type="button" disabled={busy || !credential.configured} onClick={() => { void credentialAction(provider, 'check') }}>Проверить ключ</button>
          <button className="rt-button" type="button" disabled={busy || !credential.configured} onClick={() => { void credentialAction(provider, 'delete') }}>Удалить ключ</button></div>
      </>}
    </div>
  }
  return <section aria-label="Оператор Coach" className="rounded-2xl border border-white/10 bg-black/10 p-5">
    <h3 className="text-lg font-semibold">Доступ к провайдеру</h3>
    <p className="mt-2 text-sm text-muted-foreground">Только оператор сервера. Не пользовательский PIN. Серверная HttpOnly cookie-сессия: 15 минут. Ключ хранится только в server vault.</p>
    {message && <p role="status" className="mt-3 text-sm">{message}</p>}
    {!session ? <p className="mt-3">{busy ? 'Проверяем доступ…' : 'Настройте операторский доступ и защищённый vault на сервере, затем откройте панель снова. Локального хранения ключа нет.'}</p> :
      !session.setupAvailable ? <p className="mt-3">Настройте пароль оператора и защищённый vault на сервере. Plaintext fallback не поддерживается.</p> :
      !session.authorized ? <form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={event => { event.preventDefault(); void login() }}>
        <label className="grid gap-2 text-sm">Пароль оператора<input aria-label="Пароль оператора" className="rt-input" type="password" autoComplete="off" maxLength={256} value={password} disabled={busy} onChange={event => setPassword(event.target.value)} /></label>
        <button className="rt-button" type="submit" disabled={busy || !password}>Войти как оператор</button>
      </form> : <div className="mt-4 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3"><span>Оператор авторизован</span><button className="rt-button" type="button" onClick={() => { void logout() }}>Выйти из оператора</button></div>
        {PROVIDERS.map(credentialBlock)}
      </div>}
  </section>
}
