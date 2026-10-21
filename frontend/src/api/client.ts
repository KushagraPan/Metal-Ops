/**
 * The single place where the frontend talks to the backend.
 *
 * Every request goes through `request()` so that credentials, headers, base
 * URL and error handling stay in one place. Components must never call
 * `fetch` directly.
 */

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? ''

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** Join the configured base URL with an API path, without duplicate slashes. */
export function apiUrl(path: string): string {
  const base = API_BASE_URL.replace(/\/+$/, '')
  const suffix = path.startsWith('/') ? path : `/${path}`
  return `${base}${suffix}`
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json')
  }

  const response = await fetch(apiUrl(path), {
    ...init,
    credentials: 'include',
    headers,
  })

  if (!response.ok) {
    throw new ApiError(response.status, `Request failed with status ${response.status}`)
  }

  return (await response.json()) as T
}

export interface HealthStatus {
  status: string
}

export const api = {
  health: (): Promise<HealthStatus> => request<HealthStatus>('/api/health'),
}
