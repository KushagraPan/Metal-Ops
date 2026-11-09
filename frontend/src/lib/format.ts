const moneyFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
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
  return moneyFormatter.format(toNumber(value))
}

/** Format kilograms with two decimals. */
export function formatKg(value: string | number): string {
  return weightFormatter.format(toNumber(value))
}

/** Render a nullable money value as `n/a`, matching the spec's wording. */
export function formatOptionalMoney(value: string | null): string {
  return value === null ? 'n/a' : formatMoney(value)
}
