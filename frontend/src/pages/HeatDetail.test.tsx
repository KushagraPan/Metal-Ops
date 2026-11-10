// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { Heat } from '../api/client'
import HeatDetail from './HeatDetail'

const emptyHeat: Heat = {
  id: 4,
  heat_no: 'H-1001',
  heat_date: '2026-10-15',
  duration_hours: null,
  notes: null,
  alloy: 'ADC12',
  output_kg: '100.00',
  dross_kg: '0.00',
  iron_scrap_kg: '0.00',
  oil_cost: '0.00',
  power_cost: '0.00',
  labour_cost: '0.00',
  other_cost: '0.00',
  inputs: [],
  sales: [],
  total_input_kg: '0.00',
  sold_alloy_kg: '0.00',
  yield_pct: null,
  scrap_cost: '0.00',
  variable_costs: '0.00',
  revenue: '0.00',
  net_outbound_transport: '0.00',
  heat_profit: null,
  is_provisional: true,
}

const soldHeat: Heat = {
  ...emptyHeat,
  id: 5,
  inputs: [
    {
      lot_id: 9,
      kg: '1000.00',
      supplier: 'Demo Scrap Traders',
      purchase_date: '2026-10-01',
      landed_cost_per_kg: '202.00',
    },
  ],
  sales: [
    {
      id: 11,
      sale_date: '2026-10-20',
      customer: 'Demo Castings',
      item_type: 'ADC12',
      heat_id: 5,
      weight_kg: '890.00',
      rate_per_kg: '240.00',
      gst_mode: 'WITH',
      transport_mode: 'WE_PAY_ABSORB',
      transport_cost: '3000.00',
      transport_billed: '0.00',
      gst_amount: '38448.00',
      revenue: '213600.00',
      net_outbound_transport: '3000.00',
    },
  ],
  total_input_kg: '1000.00',
  sold_alloy_kg: '890.00',
  yield_pct: '89.00',
  scrap_cost: '202000.00',
  variable_costs: '11000.00',
  revenue: '213600.00',
  net_outbound_transport: '3000.00',
  heat_profit: '-2400.00',
  is_provisional: false,
}

afterEach(cleanup)

describe('HeatDetail', () => {
  it('shows n/a yield and profit for a heat with no inputs', () => {
    render(<HeatDetail heat={emptyHeat} />)

    expect(screen.getByText('Yield')).toBeDefined()
    expect(screen.getByText('Profit')).toBeDefined()
    expect(screen.getAllByText('n/a')).toHaveLength(2)
    expect(screen.getByText('provisional')).toBeDefined()
    expect(screen.getByText('No lots linked to this heat.')).toBeDefined()
  })

  it('shows linked sales and removes the provisional label when fully sold', () => {
    render(<HeatDetail heat={soldHeat} />)

    expect(screen.getByText('Demo Castings')).toBeDefined()
    expect(screen.getAllByText('₹2,13,600.00').length).toBeGreaterThan(0)
    expect(screen.queryByText('provisional')).toBeNull()
  })
})
