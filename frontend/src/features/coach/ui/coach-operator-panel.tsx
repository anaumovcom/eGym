import { useEffect, useRef, useState } from 'react'
import { CoachApiError, coachErrorMessage, coachSettingsApi, type CredentialStatus, type OperatorSession } from '../lib/settings-api'
import { isCurrentCoachScope } from '../lib/settings-scope'

const checkLabels: Readonly<Record<string, string>> = {
  not_checked: 'не выполнялась', auth_ok_models_not_verified: 'ключ принят провайдером',
  auth_failed: 'ключ отклонён провайдером', provider_unavailable: 'провайдер недоступен',
}
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
  const [credential, setCredential] = useState<CredentialStatus | null>(null)
  const [password, setPassword] = useState('')
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const operation = useRef(0)
  const controller = useRef<AbortController | null>(null)
  const alive = useRef(false)
  const version = useRef<number | null>(null)

  function start() {
    controller.current?.abort()
    const abort = new AbortController()
    controller.current = abort
    const id = ++operation.current
    setBusy(true)
    setMessage('')
    return { signal: abort.signal, current: () => alive.current && isCurrentCoachScope(epoch) && operation.current === id && !abort.signal.aborted }
  }
  function acceptCredential(value: CredentialStatus) {
    version.current = value.credentialVersion
    setCredential(value)
  }
  function failed(error: unknown) {
    setMessage(coachErrorMessage(error))
    // Fail closed, including session expiry/conflict. Reauthorization refreshes version.
    setSession(null)
    setCredential(null)
    version.current = null
    setPassword('')
    setKey('')
  }
  useEffect(() => {
    alive.current = true
    const request = start()
    void (async () => {
      try {
        const next = await coachSettingsApi.session(request.signal)
        if (!request.current()) return
        setSession(next)
        if (next.authorized) {
          const nextCredential = await coachSettingsApi.credentials(request.signal)
          if (request.current()) acceptCredential(nextCredential)
        }
      } catch (error) { if (request.current()) failed(error) }
      finally { if (request.current()) setBusy(false) }
    })()
    return () => { alive.current = false; ++operation.current; controller.current?.abort() }
  }, [epoch])

  async function login() {
    const captured = password
    setPassword('')
    setKey('')
    const request = start()
    try {
      const next = await coachSettingsApi.login(captured, request.signal)
      if (!request.current()) return
      setSession(next)
      const nextCredential = await coachSettingsApi.credentials(request.signal)
      if (request.current()) acceptCredential(nextCredential)
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
    setPassword(''); setKey(''); setSession(null); setCredential(null); version.current = null
    const request = start()
    try {
      await coachSettingsApi.logout(request.signal)
      if (request.current()) setSession({ authorized: false, setupAvailable: true })
    } catch (error) { if (request.current()) failed(error) }
    finally { if (request.current()) setBusy(false) }
  }
  async function credentialAction(action: 'save' | 'delete' | 'check') {
    if (!credential || version.current !== credential.credentialVersion) return
    const captured = key
    setKey(''); setPassword('')
    const expectedVersion = credential.credentialVersion
    const request = start()
    try {
      const next = action === 'save' ? await coachSettingsApi.putCredential(captured, expectedVersion, request.signal) :
        action === 'delete' ? await coachSettingsApi.deleteCredential(expectedVersion, request.signal) : await coachSettingsApi.checkCredential(request.signal)
      if (!request.current() || version.current !== expectedVersion) return
      if ((action === 'check' && next.credentialVersion !== expectedVersion) ||
          (action !== 'check' && next.credentialVersion <= expectedVersion)) {
        failed(new Error())
        return
      }
      acceptCredential(next)
      setMessage(action === 'check' ? 'Проверка доступа завершена. Генерация не запускалась.' : action === 'save' ? 'Ключ сохранён в защищённом хранилище сервера.' : 'Ключ удалён.')
    } catch (error) { if (request.current()) failed(error) }
    finally { if (request.current()) setBusy(false) }
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
        {credential && <>
          <p className="text-sm">Ключ: {credential.configured ? 'сохранён' : 'не задан'} · Проверка: {checkLabels[credential.lastCheckStatus ?? 'not_checked'] ?? credential.lastCheckStatus} · Версия {credential.credentialVersion}</p>
          {credential.storageAvailable && <p className="rounded-xl border border-violet-400/30 bg-violet-500/10 p-3 text-sm">{nextStep(credential)}</p>}
          {!credential.storageAvailable ? <p>Настройте защищённое хранилище vault на сервере. Ввод ключа недоступен.</p> : <>
            <form className="flex flex-wrap items-end gap-3" onSubmit={event => { event.preventDefault(); void credentialAction('save') }}>
              <label className="grid gap-2 text-sm">{credential.configured ? 'Заменить ключ OpenAI' : 'API-ключ OpenAI'}<input aria-label="Ключ провайдера" className="rt-input" type="password" autoComplete="off" placeholder="sk-…" maxLength={512} value={key} disabled={busy} onChange={event => setKey(event.target.value)} /></label>
              <button className="rt-button" type="submit" disabled={busy || !key}>Сохранить ключ</button>
            </form>
            <div className="flex flex-wrap gap-3"><button className="rt-button" type="button" disabled={busy || !credential.configured} onClick={() => { void credentialAction('check') }}>Проверить ключ</button>
              <button className="rt-button" type="button" disabled={busy || !credential.configured} onClick={() => { void credentialAction('delete') }}>Удалить ключ</button></div>
          </>}
        </>}
      </div>}
  </section>
}