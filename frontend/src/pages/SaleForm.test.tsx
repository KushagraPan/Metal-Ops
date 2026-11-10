// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import type { Heat, Sale } from '../api/client'
import SaleForm from './SaleForm'

vi.mock('../api/client', () => ({
  api: {
    sales: {
      create: vi.fn(),
      update: vi.fn(),
    },
  },
}))

const heat: Heat = {
  id: 1,
  heat_no: 'H-1001',
  heat_date: '2026-10-15',
  duration_hours: '5.50',
  notes: null,
  alloy: 'ADC12',
  output_kg: '890.00',
  dross_kg: '60.00',
  iron_scrap_kg: '5.00',
  oil_cost: '6000.00',
  power_cost: '3000.00',
  labour_cost: '2000.00',
  other_cost: '0.00',
  inputs: [],
  sales: [],
  total_input_kg: '1000.00',
  sold_alloy_kg: '0.00',
  yield_pct: '89.00',
  scrap_cost: '202000.00',
  variable_costs: '11000.00',
  revenue: '0.00',
  net_outbound_transport: '0.00',
  heat_profit: '-213000.00',
  is_provisional: true,
}

const sale: Sale = {
  id: 11,
  sale_date: '2026-10-20',
  customer: 'Demo Castings',
  item_type: 'ADC12',
  heat_id: 1,
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

describe('SaleForm', () => {
  it('saves an alloy sale against the selected matching heat', async () => {
    vi.mocked(api.sales.create).mockResolvedValue(sale)
    const onSaved = vi.fn()
    const user = userEvent.setup()
    render(<SaleForm heats={[heat]} onSaved={onSaved} />)

    await user.type(screen.getByLabelText('Customer'), 'Demo Castings')
    await user.type(screen.getByLabelText('Weight (kg)'), '600')
    await user.type(screen.getByLabelText('Rate (₹/kg)'), '240')
    await user.type(screen.getByLabelText('Transport cost'), '3000')
    await user.click(screen.getByRole('button', { name: 'Add sale' }))

    expect(api.sales.create).toHaveBeenCalledWith(
      expect.objectContaining({
        customer: 'Demo Castings',
        item_type: 'ADC12',
        heat_id: 1,
        weight_kg: '600',
        rate_per_kg: '240',
        transport_mode: 'WE_PAY_ABSORB',
        transport_cost: '3000',
        transport_billed: '0.00',
      }),
    )
    expect(onSaved).toHaveBeenCalledWith(sale)
  })

  it('rejects an alloy sale when no matching heat exists', async () => {
    const user = userEvent.setup()
    render(<SaleForm heats={[]} onSaved={vi.fn()} />)

    await user.type(screen.getByLabelText('Customer'), 'Demo Castings')
    await user.type(screen.getByLabelText('Weight (kg)'), '600')
    await user.type(screen.getByLabelText('Rate (₹/kg)'), '240')
    await user.click(screen.getByRole('button', { name: 'Add sale' }))

    expect(screen.getByRole('alert').textContent).toContain(
      'An alloy sale requires a linked heat.',
    )
    expect(api.sales.create).not.toHaveBeenCalled()
  })

  it('rejects alloy kg above the heat remaining output', async () => {
    const user = userEvent.setup()
    render(
      <SaleForm
        heats={[{ ...heat, sold_alloy_kg: '850.00' }]}
        onSaved={vi.fn()}
      />,
    )

    await user.type(screen.getByLabelText('Customer'), 'Demo Castings')
    await user.type(screen.getByLabelText('Weight (kg)'), '50')
    await user.type(screen.getByLabelText('Rate (₹/kg)'), '240')
    await user.click(screen.getByRole('button', { name: 'Add sale' }))

    expect(screen.getByRole('alert').textContent).toContain(
      'Weight cannot exceed the heat',
    )
    expect(api.sales.create).not.toHaveBeenCalled()
  })

  it('rejects billed transport above cost', async () => {
    const user = userEvent.setup()
    render(<SaleForm heats={[heat]} onSaved={vi.fn()} />)

    await user.type(screen.getByLabelText('Customer'), 'Demo Castings')
    await user.type(screen.getByLabelText('Weight (kg)'), '600')
    await user.type(screen.getByLabelText('Rate (₹/kg)'), '240')
    await user.selectOptions(
      screen.getByLabelText('Transport mode'),
      'WE_PAY_BILL',
    )
    await user.type(screen.getByLabelText('Transport cost'), '3000')
    await user.type(screen.getByLabelText('Transport billed'), '3001')
    await user.click(screen.getByRole('button', { name: 'Add sale' }))

    expect(screen.getByRole('alert').textContent).toContain(
      'Billed transport cannot exceed transport cost.',
    )
    expect(api.sales.create).not.toHaveBeenCalled()
  })

  it('rejects zero transport cost when the business pays', async () => {
    const user = userEvent.setup()
    render(<SaleForm heats={[heat]} onSaved={vi.fn()} />)

    await user.type(screen.getByLabelText('Customer'), 'Demo Castings')
    await user.type(screen.getByLabelText('Weight (kg)'), '600')
    await user.type(screen.getByLabelText('Rate (₹/kg)'), '240')
    await user.type(screen.getByLabelText('Transport cost'), '0')
    await user.click(screen.getByRole('button', { name: 'Add sale' }))

    expect(screen.getByRole('alert').textContent).toContain(
      'Transport cost must be greater than 0 when the business pays transport.',
    )
    expect(api.sales.create).not.toHaveBeenCalled()
  })

  it('forces both transport amounts to zero when the customer arranges', async () => {
    vi.mocked(api.sales.create).mockResolvedValue(sale)
    const user = userEvent.setup()
    render(<SaleForm heats={[heat]} onSaved={vi.fn()} />)

    await user.type(screen.getByLabelText('Customer'), 'Demo Castings')
    await user.type(screen.getByLabelText('Weight (kg)'), '600')
    await user.type(screen.getByLabelText('Rate (₹/kg)'), '240')
    await user.selectOptions(
      screen.getByLabelText('Transport mode'),
      'CUSTOMER_ARRANGES',
    )
    await user.click(screen.getByRole('button', { name: 'Add sale' }))

    expect(api.sales.create).toHaveBeenCalledWith(
      expect.objectContaining({
        transport_cost: '0.00',
        transport_billed: '0.00',
      }),
    )
  })
})
