import { describe, expect, it } from 'vitest'

import {
  formatKg,
  formatMoney,
  formatMoneyWhole,
  formatOptionalMoney,
  formatOptionalMoneyWhole,
  formatOptionalPercent,
  formatPercent,
} from './format'

describe('format utilities', () => {
  it('formats whole rupees with Indian digit grouping and negative sign before symbol', () => {
    expect(formatMoneyWhole(153093)).toBe('₹1,53,093')
    expect(formatMoneyWhole('153093')).toBe('₹1,53,093')
    expect(formatMoneyWhole(-142300)).toBe('-₹1,42,300')
    expect(formatMoneyWhole('-142300')).toBe('-₹1,42,300')
    expect(formatMoneyWhole(0)).toBe('₹0')
  })

  it('formats money with two decimals in tables', () => {
    expect(formatMoney(153093.5)).toBe('₹1,53,093.50')
    expect(formatMoney(-142300)).toBe('-₹1,42,300.00')
  })

  it('renders nullable money as n/a and never ₹0', () => {
    expect(formatOptionalMoney(null)).toBe('n/a')
    expect(formatOptionalMoneyWhole(null)).toBe('n/a')
    expect(formatOptionalMoneyWhole(153093)).toBe('₹1,53,093')
    expect(formatOptionalMoneyWhole(-142300)).toBe('-₹1,42,300')
  })

  it('formats weights and percentages', () => {
    expect(formatKg(1234.5)).toBe('1,234.50')
    expect(formatPercent(89)).toBe('89.00%')
    expect(formatOptionalPercent(null)).toBe('n/a')
    expect(formatOptionalPercent(88.41)).toBe('88.41%')
  })
})
