const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

function buildUrl(path: string): string {
  if (/^https?:\/\//.test(path)) {
    return path
  }

  return API_BASE_URL ? `${API_BASE_URL}${path}` : path
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(buildUrl(path))

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }

  return response.json() as Promise<T>
}