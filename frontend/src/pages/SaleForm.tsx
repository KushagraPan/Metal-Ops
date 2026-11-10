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
    <section className="card">
      <h2>{initial === null ? 'New sale' : `Edit sale #${initial.id}`}</h2>
      <form className="sale-form" onSubmit={handleSubmit} noValidate>
        <div className="form-grid">
          <label className="field">
            <span>Sale date</span>
            <input
              type="date"
              value={form.sale_date}
              onChange={(event) =>
                setField('sale_date', event.target.value)
              }
              required
            />
          </label>

          <label className="field">
            <span>Customer</span>
            <input
              type="text"
              value={form.customer}
              maxLength={200}
              onChange={(event) =>
                setField('customer', event.target.value)
              }
              required
            />
          </label>

          <label className="field">
            <span>Item type</span>
            <select
              value={form.item_type}
              onChange={(event) =>
                changeItemType(event.target.value as ItemType)
              }
            >
              <option value="ADC12">ADC12</option>
              <option value="LM6">LM6</option>
              <option value="DROSS">Dross</option>
              <option value="IRON_SCRAP">Iron scrap</option>
            </select>
          </label>

          <label className="field">
            <span>Heat</span>
            <select
              value={form.heat_id}
              onChange={(event) => setField('heat_id', event.target.value)}
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
          </label>

          <label className="field">
            <span>Weight (kg)</span>
            <input
              type="number"
              inputMode="decimal"
              min="0.01"
              step="0.01"
              value={form.weight_kg}
              onChange={(event) =>
                setField('weight_kg', event.target.value)
              }
              required
            />
          </label>

          <label className="field">
            <span>Rate (₹/kg)</span>
            <input
              type="number"
              inputMode="decimal"
              min="0.01"
              step="0.01"
              value={form.rate_per_kg}
              onChange={(event) =>
                setField('rate_per_kg', event.target.value)
              }
              required
            />
          </label>

          <label className="field">
            <span>GST mode</span>
            <select
              value={form.gst_mode}
              onChange={(event) =>
                setField('gst_mode', event.target.value as GstMode)
              }
            >
              <option value="WITH">With GST</option>
              <option value="WITHOUT">Without GST</option>
            </select>
          </label>

          <label className="field">
            <span>Transport mode</span>
            <select
              value={form.transport_mode}
              onChange={(event) =>
                changeTransportMode(
                  event.target.value as SaleTransportMode,
                )
              }
            >
              <option value="CUSTOMER_ARRANGES">Customer arranges</option>
              <option value="WE_PAY_ABSORB">We pay and absorb</option>
              <option value="WE_PAY_BILL">We pay and bill</option>
            </select>
          </label>

          <label className="field">
            <span>Transport cost</span>
            <input
              type="number"
              inputMode="decimal"
              min={customerArranges ? '0' : '0.01'}
              step="0.01"
              value={customerArranges ? '0.00' : form.transport_cost}
              onChange={(event) =>
                setField('transport_cost', event.target.value)
              }
              disabled={customerArranges}
            />
          </label>

          <label className="field">
            <span>Transport billed</span>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={billsTransport ? form.transport_billed : '0.00'}
              onChange={(event) =>
                setField('transport_billed', event.target.value)
              }
              disabled={!billsTransport}
            />
          </label>
        </div>

        {isAlloyType(form.item_type) && matchingHeats.length === 0 ? (
          <p className="muted">
            Add a {form.item_type} heat before selling this alloy.
          </p>
        ) : null}

        {selectedHeat !== null && isAlloyType(form.item_type) ? (
          <p className="muted">
            {formatKg(
              String(availableFor(selectedHeat, initial, form.item_type)),
            )}{' '}
            kg of {selectedHeat.alloy} remain unsold on{' '}
            {selectedHeat.heat_no}.
          </p>
        ) : null}

        {customerArranges ? (
          <p className="muted">
            Customer arranges transport, so both transport amounts are fixed
            at zero.
          </p>
        ) : null}

        {error !== null ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}

        {saved !== null ? (
          <p className="status" role="status">
            Saved sale for {saved.customer}. Revenue{' '}
            {formatMoney(saved.revenue)} · GST {formatMoney(saved.gst_amount)}{' '}
            · net freight {formatMoney(saved.net_outbound_transport)}.
          </p>
        ) : null}

        <div className="actions">
          <button type="submit" className="primary" disabled={saving}>
            {saving
              ? 'Saving...'
              : initial === null
                ? 'Add sale'
                : 'Save changes'}
          </button>
          {initial !== null && onCancel !== undefined ? (
            <button type="button" onClick={onCancel}>
              Cancel
            </button>
          ) : null}
        </div>
      </form>
    </section>
  )
}
