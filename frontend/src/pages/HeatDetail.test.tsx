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
  total_input_kg: '0.00',
  yield_pct: null,
  scrap_cost: '0.00',
  variable_costs: '0.00',
  heat_profit: null,
}

afterEach(cleanup)

describe('HeatDetail', () => {
  it('shows n/a yield and profit for a heat with no inputs', () => {
    render(<HeatDetail heat={emptyHeat} />)

    expect(screen.getByText('Yield')).toBeDefined()
    expect(screen.getByText('Profit')).toBeDefined()
    expect(screen.getAllByText('n/a')).toHaveLength(2)
    expect(screen.getByText('No lots linked to this heat.')).toBeDefined()
  })
})
