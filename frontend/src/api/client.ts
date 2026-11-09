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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

async function responseMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    if (isRecord(body)) {
      const detail = body['detail']
      if (typeof detail === 'string') {
        return detail
      }
      if (Array.isArray(detail)) {
        const messages = detail.map((item: unknown) => {
          if (isRecord(item) && typeof item['msg'] === 'string') {
            return item['msg']
          }
          return String(item)
        })
        if (messages.length > 0) {
          return messages.join('; ')
        }
      }
    }
  } catch {
    // Fall through to the status message.
  }
  return `Request failed with status ${response.status}`
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
    throw new ApiError(response.status, await responseMessage(response))
  }

  if (response.status === 204) {
    return undefined as T
  }

  const text = await response.text()
  return (text ? JSON.parse(text) : undefined) as T
}

export interface HealthStatus {
  status: string
}

export type GstMode = 'WITH' | 'WITHOUT'
export type PurchaseTransportMode = 'SUPPLIER_DELIVERS' | 'WE_PAY'

export interface PurchaseLotInput {
  purchase_date: string
  supplier: string
  notes: string | null
  weight_kg: string
  rate_per_kg: string
  gst_mode: GstMode
  transport_mode: PurchaseTransportMode
  transport_cost: string
}

export interface PurchaseLot extends PurchaseLotInput {
  id: number
  gst_amount: string
  landed_cost_per_kg: string | null
  consumed_kg: string
  remaining_kg: string
}

export type Alloy = 'ADC12' | 'LM6'

interface HeatFields {
  heat_no: string
  heat_date: string
  duration_hours: string | null
  notes: string | null
  alloy: Alloy
  output_kg: string
  dross_kg: string
  iron_scrap_kg: string
  oil_cost: string
  power_cost: string
  labour_cost: string
  other_cost: string
}

export interface HeatInputPayload {
  lot_id: number
  kg: string
}

export interface HeatInputRead extends HeatInputPayload {
  supplier: string
  purchase_date: string
  landed_cost_per_kg: string | null
}

export interface HeatWrite extends HeatFields {
  inputs: HeatInputPayload[]
}

export interface Heat extends HeatFields {
  id: number
  inputs: HeatInputRead[]
  total_input_kg: string
  yield_pct: string | null
  scrap_cost: string
  variable_costs: string
  heat_profit: string | null
}

export const api = {
  health: (): Promise<HealthStatus> => request<HealthStatus>('/api/health'),
  purchases: {
    list: (): Promise<PurchaseLot[]> =>
      request<PurchaseLot[]>('/api/purchases'),
    get: (id: number): Promise<PurchaseLot> =>
      request<PurchaseLot>(`/api/purchases/${id}`),
    create: (input: PurchaseLotInput): Promise<PurchaseLot> =>
      request<PurchaseLot>('/api/purchases', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      }),
    update: (id: number, input: PurchaseLotInput): Promise<PurchaseLot> =>
      request<PurchaseLot>(`/api/purchases/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      }),
    remove: (id: number): Promise<void> =>
      request<void>(`/api/purchases/${id}`, { method: 'DELETE' }),
  },
  heats: {
    list: (): Promise<Heat[]> => request<Heat[]>('/api/heats'),
    get: (id: number): Promise<Heat> => request<Heat>(`/api/heats/${id}`),
    create: (input: HeatWrite): Promise<Heat> =>
      request<Heat>('/api/heats', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      }),
    update: (id: number, input: HeatWrite): Promise<Heat> =>
      request<Heat>(`/api/heats/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      }),
    remove: (id: number): Promise<void> =>
      request<void>(`/api/heats/${id}`, { method: 'DELETE' }),
  },
}
