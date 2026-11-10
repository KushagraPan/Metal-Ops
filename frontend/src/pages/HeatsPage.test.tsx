// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import type { Heat } from '../api/client'
import HeatsPage from './HeatsPage'

vi.mock('../api/client', () => ({
  api: {
    heats: {
      list: vi.fn(),
      remove: vi.fn(),
    },
    purchases: {
      list: vi.fn(),
    },
  },
}))

const heat: Heat = {
  id: 1,
  heat_no: 'H-1001',
  heat_date: '2026-10-15',
  duration_hours: null,
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
  sold_alloy_kg: '600.00',
  yield_pct: '89.00',
  scrap_cost: '202000.00',
  variable_costs: '11000.00',
  revenue: '144000.00',
  net_outbound_transport: '3000.00',
  heat_profit: '-72000.00',
  reports: [],
  is_provisional: true,
}

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

describe('HeatsPage', () => {
  it('marks a partially sold heat profit as provisional in the list', async () => {
    vi.mocked(api.heats.list).mockResolvedValue([heat])
    vi.mocked(api.purchases.list).mockResolvedValue([])

    render(<HeatsPage />)

    expect(await screen.findByText('H-1001')).toBeDefined()
    expect(screen.getByText('provisional')).toBeDefined()
  })

  it('sends combined filters to the heats API', async () => {
    vi.mocked(api.heats.list).mockResolvedValue([heat])
    vi.mocked(api.purchases.list).mockResolvedValue([])

    render(<HeatsPage />)
    await screen.findByText('H-1001')

    const filterSection = screen
      .getByRole('heading', { name: 'Find heats' })
      .closest('section')
    if (filterSection === null) {
      throw new Error('Find heats section is missing')
    }
    const filters = within(filterSection)

    fireEvent.change(filters.getByLabelText('From date'), {
      target: { value: '2026-01-01' },
    })
    fireEvent.change(filters.getByLabelText('To date'), {
      target: { value: '2026-12-31' },
    })
    fireEvent.change(filters.getByLabelText('Alloy'), {
      target: { value: 'LM6' },
    })
    fireEvent.change(filters.getByLabelText('Report result'), {
      target: { value: 'PASS' },
    })
    fireEvent.change(filters.getByLabelText('Heat number'), {
      target: { value: 'H-1' },
    })

    await waitFor(() => {
      expect(api.heats.list).toHaveBeenLastCalledWith({
        from_date: '2026-01-01',
        to_date: '2026-12-31',
        alloy: 'LM6',
        report_result: 'PASS',
        heat_no: 'H-1',
      })
    })
  })
})
