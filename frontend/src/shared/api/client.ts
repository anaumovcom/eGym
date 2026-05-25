const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  payload: unknown

  constructor(status: number, payload: unknown) {
    const message = typeof payload === 'object' && payload !== null && 'detail' in payload ? String(payload.detail) : `Request failed: ${status}`
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

function buildUrl(path: string): string {
  if (/^https?:\/\//.test(path)) {
    return path
  }

  return API_BASE_URL ? `${API_BASE_URL}${path}` : path
}

export function resolveApiAssetUrl(path?: string): string | undefined {
  if (!path) {
    return undefined
  }

  return buildUrl(path)
}

async function parseResponse<T>(response: Response): Promise<T> {
  const contentType = response.headers.get('content-type') ?? ''
  const isJson = contentType.includes('application/json')
  const payload = isJson ? await response.json() : await response.text()

  if (!response.ok) {
    throw new ApiError(response.status, payload)
  }

  return payload as T
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(buildUrl(path), {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (response.status === 204) {
    return undefined as T
  }

  return parseResponse<T>(response)
}

export async function apiGet<T>(path: string): Promise<T> {
  return apiRequest<T>(path, { method: 'GET' })
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return apiRequest<T>(path, { method: 'POST', body: JSON.stringify(body) })
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  return apiRequest<T>(path, { method: 'PUT', body: JSON.stringify(body) })
}

export async function apiDelete(path: string): Promise<void> {
  await apiRequest<void>(path, { method: 'DELETE' })
}

export function buildWebSocketUrl(path: string): string {
  const resolved = new URL(buildUrl(path), window.location.origin)
  resolved.protocol = resolved.protocol === 'https:' ? 'wss:' : 'ws:'
  return resolved.toString()
}