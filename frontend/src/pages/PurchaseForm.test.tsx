// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import type { PurchaseLot } from '../api/client'
import PurchaseForm from './PurchaseForm'

vi.mock('../api/client', () => ({
  api: {
    purchases: {
      create: vi.fn(),
      update: vi.fn(),
    },
  },
}))

const savedLot: PurchaseLot = {
  id: 7,
  purchase_date: '2026-10-01',
  supplier: 'Demo Scrap Traders',
  notes: null,
  weight_kg: '1000.00',
  rate_per_kg: '200.00',
  gst_mode: 'WITH',
  transport_mode: 'WE_PAY',
  transport_cost: '2000.00',
  gst_amount: '36000.00',
  landed_cost_per_kg: '202.00',
  consumed_kg: '0.00',
  remaining_kg: '1000.00',
}

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

describe('PurchaseForm', () => {
  it('forces transport cost to zero when the supplier delivers', async () => {
    const user = userEvent.setup()
    render(<PurchaseForm onSaved={vi.fn()} />)

    expect(screen.getByLabelText('Transport mode')).toBeDefined()
    const cost = screen.getByLabelText('Transport cost') as HTMLInputElement

    expect(cost.disabled).toBe(false)
    expect(cost.required).toBe(true)

    await user.click(screen.getByRole('button', { name: 'Transport mode' }))
    await user.click(await screen.findByRole('option', { name: 'Supplier delivers' }))

    expect(cost.disabled).toBe(true)
    expect(cost.required).toBe(false)
    expect(cost.value).toBe('0')

    await user.click(screen.getByRole('button', { name: 'Transport mode' }))
    await user.click(await screen.findByRole('option', { name: 'We pay' }))

    expect(cost.disabled).toBe(false)
    expect(cost.required).toBe(true)
    expect(cost.value).toBe('')
  })

  it('shows the server GST and landed cost after a WITH-GST lot is saved', async () => {
    vi.mocked(api.purchases.create).mockResolvedValue(savedLot)
    const onSaved = vi.fn()
    const user = userEvent.setup()
    render(<PurchaseForm onSaved={onSaved} />)

    await user.type(screen.getByLabelText('Supplier'), 'Demo Scrap Traders')
    await user.type(screen.getByLabelText('Weight (kg)'), '1000')
    await user.type(screen.getByLabelText('Rate (₹/kg)'), '200')
    await user.type(screen.getByLabelText('Transport cost'), '2000')
    await user.click(screen.getByRole('button', { name: 'Add purchase' }))

    expect(api.purchases.create).toHaveBeenCalledWith(
      expect.objectContaining({
        supplier: 'Demo Scrap Traders',
        weight_kg: '1000',
        rate_per_kg: '200',
        gst_mode: 'WITH',
        transport_mode: 'WE_PAY',
        transport_cost: '2000',
      }),
    )

    const status = await screen.findByRole('status')
    expect(status.textContent).toContain('GST ₹36,000.00')
    expect(status.textContent).toContain('landed cost ₹202.00/kg')
    expect(onSaved).toHaveBeenCalledWith(savedLot)
  })
})
