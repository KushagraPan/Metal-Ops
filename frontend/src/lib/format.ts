const moneyFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const moneyWholeFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
})

const weightFormatter = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

function toNumber(value: string | number): number {
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

/** Format money in Indian digit grouping, always with two decimals. */
export function formatMoney(value: string | number): string {
  const num = toNumber(value)
  const formatted = moneyFormatter.format(Math.abs(num))
  return num < 0 ? `-${formatted}` : formatted
}

/** Format money in Indian digit grouping, rounded to whole rupees (no decimals). */
export function formatMoneyWhole(value: string | number): string {
  const num = toNumber(value)
  const formatted = moneyWholeFormatter.format(Math.abs(num))
  return num < 0 ? `-${formatted}` : formatted
}

/** Format kilograms with two decimals. */
export function formatKg(value: string | number): string {
  return weightFormatter.format(toNumber(value))
}

/** Render a nullable money value as `n/a`, matching the spec's wording. */
export function formatOptionalMoney(value: string | number | null): string {
  return value === null ? 'n/a' : formatMoney(value)
}

/** Render a nullable money value as whole rupees or `n/a`. */
export function formatOptionalMoneyWhole(value: string | number | null): string {
  return value === null ? 'n/a' : formatMoneyWhole(value)
}

/** Format a percentage with two decimals. */
export function formatPercent(value: string | number): string {
  return `${weightFormatter.format(toNumber(value))}%`
}

/** Render a nullable percentage as `n/a`, matching the spec's wording. */
export function formatOptionalPercent(value: string | number | null): string {
  return value === null ? 'n/a' : formatPercent(value)
}
