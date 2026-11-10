import { useEffect, useMemo, useState, type FormEvent } from 'react'

import { api } from '../api/client'
import type {
  GstMode,
  Heat,
  ItemType,
  Sale,
  SaleTransportMode,
  SaleWrite,
} from '../api/client'
import { formatKg, formatMoney } from '../lib/format'

interface SaleFormProps {
  initial?: Sale | null
  heats: Heat[]
  onSaved: (sale: Sale) => void
  onCancel?: (() => void) | undefined
}

interface FormState {
  sale_date: string
  customer: string
  item_type: ItemType
  heat_id: string
  weight_kg: string
  rate_per_kg: string
  gst_mode: GstMode
  transport_mode: SaleTransportMode
  transport_cost: string
  transport_billed: string
}

function today(): string {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

function emptyForm(): FormState {
  return {
    sale_date: today(),
    customer: '',
    item_type: 'ADC12',
    heat_id: '',
    weight_kg: '',
    rate_per_kg: '',
    gst_mode: 'WITH',
    transport_mode: 'WE_PAY_ABSORB',
    transport_cost: '',
    transport_billed: '0.00',
  }
}

function formFromSale(sale: Sale): FormState {
  return {
    sale_date: sale.sale_date,
    customer: sale.customer,
    item_type: sale.item_type,
    heat_id: sale.heat_id === null ? '' : String(sale.heat_id),
    weight_kg: sale.weight_kg,
    rate_per_kg: sale.rate_per_kg,
    gst_mode: sale.gst_mode,
    transport_mode: sale.transport_mode,
    transport_cost: sale.transport_cost,
    transport_billed: sale.transport_billed,
  }
}

function isAlloyType(itemType: ItemType): boolean {
  return itemType === 'ADC12' || itemType === 'LM6'
}

function optionalDecimal(value: string): string {
  const trimmed = value.trim()
  return trimmed === '' ? '0.00' : trimmed
}

function payloadFrom(form: FormState): SaleWrite {
  let transportCost = optionalDecimal(form.transport_cost)
  let transportBilled = optionalDecimal(form.transport_billed)
  if (form.transport_mode === 'CUSTOMER_ARRANGES') {
    transportCost = '0.00'
    transportBilled = '0.00'
  } else if (form.transport_mode === 'WE_PAY_ABSORB') {
    transportBilled = '0.00'
  }

  return {
    sale_date: form.sale_date,
    customer: form.customer.trim(),
    item_type: form.item_type,
    heat_id: form.heat_id === '' ? null : Number(form.heat_id),
    weight_kg: form.weight_kg.trim(),
    rate_per_kg: form.rate_per_kg.trim(),
    gst_mode: form.gst_mode,
    transport_mode: form.transport_mode,
    transport_cost: transportCost,
    transport_billed: transportBilled,
  }
}

function isTwoDecimals(value: string): boolean {
  return /^\d+(\.\d{1,2})?$/.test(value.trim())
}

function availableFor(
  heat: Heat,
  initial: Sale | null,
  itemType: ItemType,
): number {
  let available =
    Number(heat.output_kg) - Number(heat.sold_alloy_kg)
  if (
    initial !== null &&
    initial.heat_id === heat.id &&
    isAlloyType(initial.item_type) &&
    initial.item_type === itemType
  ) {
    available += Number(initial.weight_kg)
  }
  return Math.max(0, available)
}

function validate(
  form: FormState,
  heats: Heat[],
  initial: Sale | null,
): string | null {
  if (form.sale_date === '') {
    return 'Sale date is required.'
  }
  if (form.customer.trim() === '') {
    return 'Customer is required.'
  }
  if (!(Number(form.weight_kg) > 0) || !isTwoDecimals(form.weight_kg)) {
    return 'Weight must be greater than 0 with at most 2 decimal places.'
  }
  if (!(Number(form.rate_per_kg) > 0) || !isTwoDecimals(form.rate_per_kg)) {
    return 'Rate must be greater than 0 with at most 2 decimal places.'
  }

  const selectedHeat =
    heats.find((heat) => String(heat.id) === form.heat_id) ?? null
  if (isAlloyType(form.item_type)) {
    if (selectedHeat === null) {
      return 'An alloy sale requires a linked heat.'
    }
    if (selectedHeat.alloy !== form.item_type) {
      return 'Choose a heat of the same alloy as the sale.'
    }
    if (Number(form.weight_kg) > availableFor(selectedHeat, initial, form.item_type)) {
      return 'Weight cannot exceed the heat remaining alloy output.'
    }
  } else if (form.heat_id !== '' && selectedHeat === null) {
    return 'Choose a valid heat or leave the byproduct sale unlinked.'
  }

  const cost = form.transport_cost.trim() === '' ? '0' : form.transport_cost
  const billed =
    form.transport_billed.trim() === '' ? '0' : form.transport_billed
  if (
    form.transport_mode !== 'CUSTOMER_ARRANGES' &&
    (!isTwoDecimals(cost) || Number(cost) <= 0)
  ) {
    return 'Transport cost must be greater than 0 when the business pays transport.'
  }
  if (!isTwoDecimals(cost) || Number(cost) < 0) {
    return 'Transport cost must be zero or more with at most 2 decimals.'
  }
  if (!isTwoDecimals(billed) || Number(billed) < 0) {
    return 'Billed transport must be zero or more with at most 2 decimals.'
  }
  if (
    form.transport_mode === 'WE_PAY_BILL' &&
    Number(billed) > Number(cost)
  ) {
    return 'Billed transport cannot exceed transport cost.'
  }
  return null
}

export default function SaleForm({
  initial = null,
  heats,
  onSaved,
  onCancel,
}: SaleFormProps) {
  const [form, setForm] = useState<FormState>(() =>
    initial === null ? emptyForm() : formFromSale(initial),
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<Sale | null>(null)

  useEffect(() => {
    setForm(initial === null ? emptyForm() : formFromSale(initial))
    setError(null)
    setSaved(null)
  }, [initial])

  const matchingHeats = useMemo(
    () =>
      isAlloyType(form.item_type)
        ? heats.filter((heat) => heat.alloy === form.item_type)
        : heats,
    [form.item_type, heats],
  )

  useEffect(() => {
    if (
      initial === null &&
      isAlloyType(form.item_type) &&
      form.heat_id === '' &&
      matchingHeats.length > 0
    ) {
      const first = matchingHeats[0]
      if (first !== undefined) {
        setForm((current) => ({
          ...current,
          heat_id: String(first.id),
        }))
      }
    }
  }, [form.heat_id, form.item_type, initial, matchingHeats])

  function setField<K extends keyof FormState>(
    field: K,
    value: FormState[K],
  ): void {
    setForm((current) => ({ ...current, [field]: value }))
  }

  function changeItemType(itemType: ItemType): void {
    const options = isAlloyType(itemType)
      ? heats.filter((heat) => heat.alloy === itemType)
      : heats
    const keepsCurrent = options.some(
      (heat) => String(heat.id) === form.heat_id,
    )
    const nextHeat = keepsCurrent
      ? form.heat_id
      : isAlloyType(itemType) && options[0] !== undefined
        ? String(options[0].id)
        : ''
    setForm((current) => ({
      ...current,
      item_type: itemType,
      heat_id: nextHeat,
    }))
  }

  function changeTransportMode(mode: SaleTransportMode): void {
    setForm((current) => {
      let transportCost = current.transport_cost
      let transportBilled = current.transport_billed
      if (mode === 'CUSTOMER_ARRANGES') {
        transportCost = '0.00'
        transportBilled = '0.00'
      } else if (mode === 'WE_PAY_ABSORB') {
        transportBilled = '0.00'
      } else if (current.transport_mode !== 'WE_PAY_BILL') {
        transportBilled = ''
        if (current.transport_mode === 'CUSTOMER_ARRANGES') {
          transportCost = ''
        }
      }
      return {
        ...current,
        transport_mode: mode,
        transport_cost: transportCost,
        transport_billed: transportBilled,
      }
    })
  }

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()
    const problem = validate(form, heats, initial)
    if (problem !== null) {
      setError(problem)
      return
    }

    setSaving(true)
    setError(null)
    setSaved(null)
    try {
      const payload = payloadFrom(form)
      const sale =
        initial === null
          ? await api.sales.create(payload)
          : await api.sales.update(initial.id, payload)
      setSaved(sale)
      onSaved(sale)
      setForm(emptyForm())
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : 'Could not save the sale.',
      )
    } finally {
      setSaving(false)
    }
  }

  const customerArranges = form.transport_mode === 'CUSTOMER_ARRANGES'
  const billsTransport = form.transport_mode === 'WE_PAY_BILL'
  const selectedHeat =
    heats.find((heat) => String(heat.id) === form.heat_id) ?? null

  return (
    <section className="app-card">
      <div className="border-b border-slate-200 pb-3 mb-6 dark:border-slate-800">
        <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
          {initial === null ? 'New sale' : `Edit sale #${initial.id}`}
        </h2>
      </div>

      <form className="space-y-6" onSubmit={handleSubmit} noValidate>
        {/* Section 1: Sale & Material */}
        <div className="space-y-4">
          <div className="border-b border-slate-100 pb-2 dark:border-slate-800">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Sale & Material
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {/* Field 1: Sale date */}
            <div className="flex flex-col">
              <label htmlFor="sale-date" className="app-label">
                Sale date
              </label>
              <input
                id="sale-date"
                type="date"
                value={form.sale_date}
                onChange={(event) =>
                  setField('sale_date', event.target.value)
                }
                required
                className="app-input"
              />
            </div>

            {/* Field 2: Customer */}
            <div className="flex flex-col">
              <label htmlFor="sale-customer" className="app-label">
                Customer
              </label>
              <input
                id="sale-customer"
                type="text"
                value={form.customer}
                maxLength={200}
                placeholder="Customer name"
                onChange={(event) =>
                  setField('customer', event.target.value)
                }
                required
                className="app-input"
              />
            </div>

            {/* Field 3: Item type */}
            <div className="flex flex-col">
              <label htmlFor="sale-item-type" className="app-label">
                Item type
              </label>
              <select
                id="sale-item-type"
                value={form.item_type}
                onChange={(event) =>
                  changeItemType(event.target.value as ItemType)
                }
                className="app-input cursor-pointer"
              >
                <option value="ADC12">ADC12</option>
                <option value="LM6">LM6</option>
                <option value="DROSS">Dross</option>
                <option value="IRON_SCRAP">Iron scrap</option>
              </select>
            </div>

            {/* Field 4: Heat */}
            <div className="flex flex-col">
              <label htmlFor="sale-heat" className="app-label">
                Heat
              </label>
              <select
                id="sale-heat"
                value={form.heat_id}
                onChange={(event) => setField('heat_id', event.target.value)}
                className="app-input cursor-pointer"
              >
                {!isAlloyType(form.item_type) ? (
                  <option value="">Unlinked byproduct sale</option>
                ) : null}
                {matchingHeats.map((heat) => (
                  <option key={heat.id} value={String(heat.id)}>
                    {heat.heat_no} · {heat.alloy} ·{' '}
                    {formatKg(
                      String(availableFor(heat, initial, form.item_type)),
                    )}{' '}
                    kg sellable
                  </option>
                ))}
              </select>

              {/* 2. Inventory Helper Callout */}
              {selectedHeat !== null && isAlloyType(form.item_type) && (
                <div className="mt-2">
                  <span className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-2.5 py-1 inline-flex items-center gap-1.5 dark:bg-amber-950/40 dark:border-amber-900/50 dark:text-amber-300">
                    <span className="h-1.5 w-1.5 rounded-full bg-amber-500 flex-shrink-0"></span>
                    <span>
                      {formatKg(
                        String(availableFor(selectedHeat, initial, form.item_type)),
                      )}{' '}
                      kg of {selectedHeat.alloy} remain unsold on{' '}
                      {selectedHeat.heat_no}.
                    </span>
                  </span>
                </div>
              )}

              {isAlloyType(form.item_type) && matchingHeats.length === 0 && (
                <p className="mt-2 text-xs text-amber-700 dark:text-amber-400">
                  Add a {form.item_type} heat before selling this alloy.
                </p>
              )}
            </div>

            {/* Field 5: Weight (kg) */}
            <div className="flex flex-col">
              <label htmlFor="sale-weight" className="app-label">
                Weight (kg)
              </label>
              <input
                id="sale-weight"
                type="number"
                inputMode="decimal"
                min="0.01"
                step="0.01"
                placeholder="0.00"
                value={form.weight_kg}
                onChange={(event) =>
                  setField('weight_kg', event.target.value)
                }
                required
                className="app-input"
              />
            </div>

            {/* Field 6: Rate (₹/kg) */}
            <div className="flex flex-col">
              <label htmlFor="sale-rate" className="app-label">
                Rate (₹/kg)
              </label>
              <input
                id="sale-rate"
                type="number"
                inputMode="decimal"
                min="0.01"
                step="0.01"
                placeholder="0.00"
                value={form.rate_per_kg}
                onChange={(event) =>
                  setField('rate_per_kg', event.target.value)
                }
                required
                className="app-input"
              />
            </div>
          </div>
        </div>

        {/* Section 2: Logistics & Billing */}
        <div className="space-y-4">
          <div className="border-b border-slate-100 pb-2 dark:border-slate-800">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Logistics & Billing
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {/* Field 7: GST mode */}
            <div className="flex flex-col">
              <label htmlFor="sale-gst-mode" className="app-label">
                GST mode
              </label>
              <select
                id="sale-gst-mode"
                value={form.gst_mode}
                onChange={(event) =>
                  setField('gst_mode', event.target.value as GstMode)
                }
                className="app-input cursor-pointer"
              >
                <option value="WITH">With GST</option>
                <option value="WITHOUT">Without GST</option>
              </select>
            </div>

            {/* Field 8: Transport mode */}
            <div className="flex flex-col md:col-span-2">
              <label htmlFor="sale-transport-mode" className="app-label">
                Transport mode
              </label>
              <select
                id="sale-transport-mode"
                value={form.transport_mode}
                onChange={(event) =>
                  changeTransportMode(
                    event.target.value as SaleTransportMode,
                  )
                }
                className="app-input cursor-pointer"
              >
                <option value="CUSTOMER_ARRANGES">Customer arranges</option>
                <option value="WE_PAY_ABSORB">We pay and absorb</option>
                <option value="WE_PAY_BILL">We pay and bill</option>
              </select>
            </div>

            {/* Field 9: Transport cost */}
            <div className="flex flex-col">
              <label htmlFor="sale-transport-cost" className="app-label">
                Transport cost
              </label>
              <input
                id="sale-transport-cost"
                type="number"
                inputMode="decimal"
                min={customerArranges ? '0' : '0.01'}
                step="0.01"
                placeholder="0.00"
                value={customerArranges ? '0.00' : form.transport_cost}
                onChange={(event) =>
                  setField('transport_cost', event.target.value)
                }
                disabled={customerArranges}
                className="app-input"
              />
            </div>

            {/* Field 10: Transport billed */}
            <div className="flex flex-col">
              <label htmlFor="sale-transport-billed" className="app-label">
                Transport billed
              </label>
              <input
                id="sale-transport-billed"
                type="number"
                inputMode="decimal"
                min="0"
                step="0.01"
                placeholder="0.00"
                value={billsTransport ? form.transport_billed : '0.00'}
                onChange={(event) =>
                  setField('transport_billed', event.target.value)
                }
                disabled={!billsTransport}
                className="app-input"
              />
            </div>

            {customerArranges && (
              <div className="flex items-center text-xs text-slate-500 dark:text-slate-400">
                Customer arranges transport, so both transport amounts are fixed at zero.
              </div>
            )}
          </div>
        </div>

        {/* Alerts and Status */}
        {error !== null ? (
          <div
            role="alert"
            className="rounded-input border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/40 dark:text-rose-200"
          >
            {error}
          </div>
        ) : null}

        {saved !== null ? (
          <div
            role="status"
            className="rounded-input border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/40 dark:text-emerald-200"
          >
            Saved sale for {saved.customer}. Revenue{' '}
            {formatMoney(saved.revenue)} · GST {formatMoney(saved.gst_amount)}{' '}
            · net freight {formatMoney(saved.net_outbound_transport)}.
          </div>
        ) : null}

        {/* 4. Action Area: right-hand side footer bar */}
        <div className="pt-4 border-t border-slate-100 dark:border-slate-800 flex items-center justify-end gap-3">
          {initial !== null && onCancel !== undefined ? (
            <button
              type="button"
              onClick={onCancel}
              className="inline-flex h-10 items-center justify-center rounded-input border border-slate-200 bg-white px-4 text-sm font-medium text-slate-700 transition hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-brand-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              Cancel
            </button>
          ) : null}
          <button
            type="submit"
            disabled={saving}
            className="app-btn-primary"
          >
            {saving
              ? 'Saving...'
              : initial === null
                ? 'Add sale'
                : 'Save changes'}
          </button>
        </div>
      </form>
    </section>
  )
}
