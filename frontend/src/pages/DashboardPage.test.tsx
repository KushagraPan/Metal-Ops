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
import type { DashboardData } from '../api/client'
import DashboardPage from './DashboardPage'

vi.mock('../api/client', () => ({
  api: {
    dashboard: {
      get: vi.fn(),
    },
    expenses: {
      create: vi.fn(),
      remove: vi.fn(),
    },
  },
}))

const octDashboard: DashboardData = {
  month: '2026-10',
  revenue: '831370.00',
  profit: '-639830.00',
  is_provisional: true,
  heats_count: 3,
  average_yield_pct: '88.41',
  planned_yield_pct: '89.00',
  yield_diff_pct: '-0.59',
  break_even_heats: null,
  expenses_total: '173000.00',
  gst_estimate: {
    collected: '111195.00',
    credit: '90720.00',
    net_payable_estimate: '20475.00',
  },
  heats: [
    {
      id: 1,
      heat_no: 'H-2026-001',
      heat_date: '2026-10-14',
      alloy: 'ADC12',
      output_kg: '3100.00',
      yield_pct: '88.57',
      heat_profit: '3750.00',
      is_provisional: true,
    },
  ],
  expenses: [
    {
      id: 1,
      month: '2026-10',
      category: 'Rent',
      amount: '35000.00',
    },
  ],
}

const novDashboard: DashboardData = {
  month: '2026-11',
  revenue: '222500.00',
  profit: '25000.00',
  is_provisional: false,
  heats_count: 1,
  average_yield_pct: '89.00',
  planned_yield_pct: '89.00',
  yield_diff_pct: '0.00',
  break_even_heats: '2.00',
  expenses_total: '45000.00',
  gst_estimate: {
    collected: '10000.00',
    credit: '5000.00',
    net_payable_estimate: '5000.00',
  },
  heats: [
    {
      id: 2,
      heat_no: 'H-2026-002',
      heat_date: '2026-11-02',
      alloy: 'ADC12',
      output_kg: '890.00',
      yield_pct: '89.00',
      heat_profit: '25000.00',
      is_provisional: false,
    },
  ],
  expenses: [
    {
      id: 2,
      month: '2026-11',
      category: 'Salaries',
      amount: '45000.00',
    },
  ],
}

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

describe('DashboardPage', () => {
  it('renders monthly figures with provisional label, n/a break-even, and estimate badge', async () => {
    vi.mocked(api.dashboard.get).mockResolvedValue(octDashboard)

    render(<DashboardPage initialMonth="2026-10" />)

    // Revenue card shows whole rupees
    expect(await screen.findByText('₹8,31,370')).toBeDefined()
    // Profit card shows whole rupees with leading minus
    expect(screen.getByText('-₹6,39,830')).toBeDefined()
    const profitCard = screen.getByText('Profit this month').closest('div')
    expect(profitCard).not.toBeNull()
    expect(within(profitCard!).getByText('provisional')).toBeDefined()

    // Break-even card shows "3 heats (break-even: n/a)" and provisional note
    const breakEvenCard = screen.getByText('Break-even progress').closest('div')
    expect(breakEvenCard).not.toBeNull()
    expect(within(breakEvenCard!).getByText(/3 heats \(break-even: n\/a\)/i)).toBeDefined()
    expect(within(breakEvenCard!).getByText('provisional')).toBeDefined()

    // GST estimate card
    expect(screen.getAllByText(/estimate/i).length).toBeGreaterThan(0)

    // Recent heats table shows 2 decimals for profit
    expect(screen.getAllByText('H-2026-001').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('₹3,750.00')).toBeDefined()
  })

  it('changes all figures when the month selector is changed', async () => {
    vi.mocked(api.dashboard.get)
      .mockResolvedValueOnce(octDashboard)
      .mockResolvedValueOnce(novDashboard)

    render(<DashboardPage initialMonth="2026-10" />)

    await screen.findByText('₹8,31,370')
    const profitCard = screen.getByText('Profit this month').closest('div')
    expect(profitCard).not.toBeNull()
    expect(within(profitCard!).getByText('provisional')).toBeDefined()

    const monthInput = screen.getByLabelText('Month')
    fireEvent.change(monthInput, { target: { value: '2026-11' } })

    await waitFor(() => {
      expect(api.dashboard.get).toHaveBeenCalledWith('2026-11')
    })

    expect(await screen.findByText('₹2,22,500')).toBeDefined()
    const updatedCard = screen.getByText('Profit this month').closest('div')
    expect(within(updatedCard!).getByText('₹25,000')).toBeDefined()
    expect(within(updatedCard!).queryByText('provisional')).toBeNull()

    // Nov break-even progress: "1 of 2 heats"
    const breakEvenCard = screen.getByText('Break-even progress').closest('div')
    expect(within(breakEvenCard!).getByText(/1 of 2 heats/i)).toBeDefined()
    expect(screen.getAllByText('H-2026-002').length).toBeGreaterThanOrEqual(1)
  })

  it('shows empty state when no heats are recorded', async () => {
    vi.mocked(api.dashboard.get).mockResolvedValueOnce({
      ...novDashboard,
      heats: [],
      heats_count: 0,
      break_even_heats: null,
    })

    render(<DashboardPage initialMonth="2026-11" />)
    expect(await screen.findByText(/No heats recorded in this month/i)).toBeDefined()
  })

  it('shows error banner when loading fails', async () => {
    vi.mocked(api.dashboard.get).mockRejectedValueOnce(new Error('Failed to load dashboard data.'))

    render(<DashboardPage initialMonth="2026-11" />)
    expect(await screen.findByRole('alert')).toBeDefined()
    expect(screen.getByText('Failed to load dashboard data.')).toBeDefined()
  })
})


