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
export type ItemType = 'ADC12' | 'LM6' | 'DROSS' | 'IRON_SCRAP'
export type ReportResult = 'PENDING' | 'PASS' | 'FAIL'

export interface Report {
  id: number
  heat_id: number
  sample_no: string
  original_filename: string
  size_bytes: number
  uploaded_at: string
  grade_tested: string | null
  result: ReportResult
  notes: string | null
  elements: Record<string, string> | null
}

export interface ReportUploadInput {
  file: File
  sample_no: string
  result: ReportResult
  notes: string | null
  grade_tested?: string | null
}

export interface ReportUpdateInput {
  result?: ReportResult
  notes?: string | null
  grade_tested?: string | null
}

export type SaleTransportMode =
  | 'CUSTOMER_ARRANGES'
  | 'WE_PAY_ABSORB'
  | 'WE_PAY_BILL'

export interface HeatFilters {
  from_date?: string | undefined
  to_date?: string | undefined
  alloy?: Alloy | undefined
  report_result?: ReportResult | undefined
  heat_no?: string | undefined
}

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

export interface SaleWrite {
  sale_date: string
  customer: string
  item_type: ItemType
  heat_id: number | null
  weight_kg: string
  rate_per_kg: string
  gst_mode: GstMode
  transport_mode: SaleTransportMode
  transport_cost: string
  transport_billed: string
}

export interface Sale extends SaleWrite {
  id: number
  gst_amount: string
  revenue: string
  net_outbound_transport: string
}

export interface Heat extends HeatFields {
  id: number
  inputs: HeatInputRead[]
  sales: Sale[]
  reports: Report[]
  total_input_kg: string
  sold_alloy_kg: string
  yield_pct: string | null
  scrap_cost: string
  variable_costs: string
  revenue: string
  net_outbound_transport: string
  heat_profit: string | null
  is_provisional: boolean
}

function heatQuery(filters: HeatFilters): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters)) {
    if (typeof value === 'string' && value.trim() !== '') {
      params.set(key, value.trim())
    }
  }
  const query = params.toString()
  return query === '' ? '' : `?${query}`
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
    list: (filters: HeatFilters = {}): Promise<Heat[]> =>
      request<Heat[]>(`/api/heats${heatQuery(filters)}`),
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
  reports: {
    list: (heatId: number): Promise<Report[]> =>
      request<Report[]>(`/api/heats/${heatId}/reports`),
    upload: (
      heatId: number,
      input: ReportUploadInput,
    ): Promise<Report> => {
      const body = new FormData()
      body.append('file', input.file)
      body.append('sample_no', input.sample_no)
      body.append('result', input.result)
      if (input.notes !== null) {
        body.append('notes', input.notes)
      }
      if (input.grade_tested !== undefined && input.grade_tested !== null) {
        body.append('grade_tested', input.grade_tested)
      }
      return request<Report>(`/api/heats/${heatId}/reports`, {
        method: 'POST',
        body,
      })
    },
    update: (
      id: number,
      input: ReportUpdateInput,
    ): Promise<Report> =>
      request<Report>(`/api/reports/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      }),
    remove: (id: number): Promise<void> =>
      request<void>(`/api/reports/${id}`, { method: 'DELETE' }),
    downloadUrl: (id: number): string =>
      apiUrl(`/api/reports/${id}/download`),
  },
  sales: {
    list: (): Promise<Sale[]> => request<Sale[]>('/api/sales'),
    get: (id: number): Promise<Sale> => request<Sale>(`/api/sales/${id}`),
    create: (input: SaleWrite): Promise<Sale> =>
      request<Sale>('/api/sales', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      }),
    update: (id: number, input: SaleWrite): Promise<Sale> =>
      request<Sale>(`/api/sales/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(input),
      }),
    remove: (id: number): Promise<void> =>
      request<void>(`/api/sales/${id}`, { method: 'DELETE' }),
  },
}
