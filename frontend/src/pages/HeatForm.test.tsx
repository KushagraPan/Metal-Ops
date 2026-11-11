// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import type { Heat, PurchaseLot, Report } from '../api/client'
import HeatForm from './HeatForm'

vi.mock('../api/client', () => ({
  api: {
    heats: {
      create: vi.fn(),
      update: vi.fn(),
    },
    reports: {
      upload: vi.fn(),
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
    expect(api.reports.upload).not.toHaveBeenCalled()
    expect(
      screen.getByText(
        "You can also add spectro reports later from the heat's View page.",
      ),
    ).toBeDefined()
    expect(onSaved).toHaveBeenCalledWith(emptyHeat)
  })

  it('heat saves and uploads with a file', async () => {
    vi.mocked(api.heats.create).mockResolvedValue(emptyHeat)
    const uploadedReport: Report = {
      id: 10,
      heat_id: emptyHeat.id,
      sample_no: 'S-2026-001',
      original_filename: 'spectro.pdf',
      size_bytes: 100,
      uploaded_at: '2026-10-15T10:00:00Z',
      grade_tested: null,
      result: 'PENDING',
      notes: 'Lab analysis pending',
      elements: null,
    }
    vi.mocked(api.reports.upload).mockResolvedValue(uploadedReport)
    const onSaved = vi.fn()
    const user = userEvent.setup()
    render(<HeatForm lots={[]} onSaved={onSaved} />)

    await user.type(screen.getByLabelText('Heat number'), 'H-1001')
    await user.type(screen.getByLabelText('Output (kg)'), '100')

    const file = new File(['%PDF-1.4 test'], 'spectro.pdf', {
      type: 'application/pdf',
    })
    await user.upload(screen.getByLabelText('PDF file'), file)

    await user.type(screen.getByLabelText('Sample number'), 'S-2026-001')
    await user.type(screen.getByLabelText('Notes'), 'Lab analysis pending')

    await user.click(screen.getByRole('button', { name: 'Add heat' }))

    expect(api.heats.create).toHaveBeenCalledWith(
      expect.objectContaining({
        heat_no: 'H-1001',
        output_kg: '100',
      }),
    )
    expect(api.reports.upload).toHaveBeenCalledWith(
      emptyHeat.id,
      expect.objectContaining({
        file,
        sample_no: 'S-2026-001',
        result: 'PENDING',
        notes: 'Lab analysis pending',
      }),
    )
    expect(onSaved).toHaveBeenCalledWith(emptyHeat)
  })

  it('heat saves and the upload fails (fake PDF) with the message and the heat kept', async () => {
    vi.mocked(api.heats.create).mockResolvedValue(emptyHeat)
    vi.mocked(api.reports.upload).mockRejectedValue(
      new Error('File signature is not a valid PDF'),
    )
    const onSaved = vi.fn()
    const user = userEvent.setup()
    render(<HeatForm lots={[]} onSaved={onSaved} />)

    await user.type(screen.getByLabelText('Heat number'), 'H-1001')
    await user.type(screen.getByLabelText('Output (kg)'), '100')

    const fakeFile = new File(['fake content'], 'fake.pdf', {
      type: 'application/pdf',
    })
    await user.upload(screen.getByLabelText('PDF file'), fakeFile)

    await user.type(screen.getByLabelText('Sample number'), 'S-2026-002')

    await user.click(screen.getByRole('button', { name: 'Add heat' }))

    expect(api.heats.create).toHaveBeenCalled()
    expect(api.reports.upload).toHaveBeenCalled()

    // Heat is kept: onSaved was called
    expect(onSaved).toHaveBeenCalledWith(emptyHeat)

    // Warning message is displayed
    const warning = await screen.findByText(
      /Heat saved\. The report could not be uploaded: File signature is not a valid PDF\. You can upload it from the heat's page\./i,
    )
    expect(warning).toBeDefined()

    // Link to heat is offered
    const heatLink = screen.getByRole('link', { name: /View heat H-1001/i })
    expect(heatLink).toBeDefined()
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
