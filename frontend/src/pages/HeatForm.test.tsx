// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import type { Heat, PurchaseLot } from '../api/client'
import HeatForm from './HeatForm'

vi.mock('../api/client', () => ({
  api: {
    heats: {
      create: vi.fn(),
      update: vi.fn(),
    },
  },
}))

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
  reports: [],
  is_provisional: true,
}

const lot: PurchaseLot = {
  id: 9,
  purchase_date: '2026-10-01',
  supplier: 'Demo Scrap Traders',
  notes: null,
  weight_kg: '100.00',
  rate_per_kg: '200.00',
  gst_mode: 'WITH',
  transport_mode: 'WE_PAY',
  transport_cost: '2000.00',
  gst_amount: '36000.00',
  landed_cost_per_kg: '220.00',
  consumed_kg: '0.00',
  remaining_kg: '100.00',
}

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

describe('HeatForm', () => {
  it('saves an empty-input heat and shows n/a yield and profit', async () => {
    vi.mocked(api.heats.create).mockResolvedValue(emptyHeat)
    const onSaved = vi.fn()
    const user = userEvent.setup()
    render(<HeatForm lots={[]} onSaved={onSaved} />)

    await user.type(screen.getByLabelText('Heat number'), 'H-1001')
    await user.type(screen.getByLabelText('Output (kg)'), '100')
    await user.click(screen.getByRole('button', { name: 'Add heat' }))

    expect(api.heats.create).toHaveBeenCalledWith(
      expect.objectContaining({
        heat_no: 'H-1001',
        output_kg: '100',
        inputs: [],
        duration_hours: null,
        notes: null,
        oil_cost: '0.00',
        power_cost: '0.00',
        labour_cost: '0.00',
        other_cost: '0.00',
      }),
    )

    const status = await screen.findByRole('status')
    expect(status.textContent).toContain('Yield n/a')
    expect(status.textContent).toContain('scrap cost ₹0.00')
    expect(status.textContent).toContain('profit n/a')
    expect(onSaved).toHaveBeenCalledWith(emptyHeat)
  })

  it('rejects output kg above the total input kg', async () => {
    const user = userEvent.setup()
    render(<HeatForm lots={[lot]} onSaved={vi.fn()} />)

    await user.type(screen.getByLabelText('Heat number'), 'H-1002')
    await user.type(screen.getByLabelText('Output (kg)'), '101')
    await user.click(screen.getByRole('button', { name: 'Add lot' }))
    await user.type(screen.getByLabelText('Input kg 1'), '100')
    await user.click(screen.getByRole('button', { name: 'Add heat' }))

    expect(screen.getByRole('alert').textContent).toContain(
      'Output cannot exceed total input kg.',
    )
    expect(api.heats.create).not.toHaveBeenCalled()
  })
})
