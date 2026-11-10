// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import type { Heat, Sale } from '../api/client'
import SalesPage from './SalesPage'

vi.mock('../api/client', () => ({
  api: {
    sales: {
      list: vi.fn(),
    },
    heats: {
      list: vi.fn(),
    },
  },
}))

const heat: Heat = {
  id: 2,
  heat_no: 'H-1001',
  heat_date: '2026-10-15',
  duration_hours: null,
  notes: null,
  alloy: 'ADC12',
  output_kg: '890.00',
  dross_kg: '60.00',
  iron_scrap_kg: '5.00',
  oil_cost: '0.00',
  power_cost: '0.00',
  labour_cost: '0.00',
  other_cost: '0.00',
  inputs: [],
  sales: [],
  total_input_kg: '1000.00',
  sold_alloy_kg: '600.00',
  yield_pct: '89.00',
  scrap_cost: '202000.00',
  variable_costs: '11000.00',
  revenue: '144000.00',
  net_outbound_transport: '3000.00',
  heat_profit: '-72000.00',
  is_provisional: true,
}

const sale: Sale = {
  id: 11,
  sale_date: '2026-10-20',
  customer: 'Demo Castings',
  item_type: 'ADC12',
  heat_id: 2,
  weight_kg: '600.00',
  rate_per_kg: '240.00',
  gst_mode: 'WITH',
  transport_mode: 'WE_PAY_ABSORB',
  transport_cost: '3000.00',
  transport_billed: '0.00',
  gst_amount: '25920.00',
  revenue: '144000.00',
  net_outbound_transport: '3000.00',
}

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

describe('SalesPage', () => {
  it('lists sales with their heat and revenue', async () => {
    vi.mocked(api.sales.list).mockResolvedValue([sale])
    vi.mocked(api.heats.list).mockResolvedValue([heat])

    render(<SalesPage />)

    expect(await screen.findByText('Demo Castings')).toBeDefined()
    expect(screen.getByText('H-1001')).toBeDefined()
    expect(screen.getByText('₹1,44,000.00')).toBeDefined()
  })
})
