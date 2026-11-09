import { useEffect, useState, type FormEvent } from 'react'

import { api } from '../api/client'
import type {
  GstMode,
  PurchaseLot,
  PurchaseLotInput,
  PurchaseTransportMode,
} from '../api/client'
import { formatKg, formatMoney, formatOptionalMoney } from '../lib/format'

interface PurchaseFormProps {
  initial?: PurchaseLot | null
  onSaved: (lot: PurchaseLot) => void
  onCancel?: (() => void) | undefined
}

interface FormState {
  purchase_date: string
  supplier: string
  notes: string
  weight_kg: string
  rate_per_kg: string
  gst_mode: GstMode
  transport_mode: PurchaseTransportMode
  transport_cost: string
}

function today(): string {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

function emptyForm(): FormState {
  return {
    purchase_date: today(),
    supplier: '',
    notes: '',
    weight_kg: '',
    rate_per_kg: '',
    gst_mode: 'WITH',
    transport_mode: 'WE_PAY',
    transport_cost: '',
  }
}

function formFromLot(lot: PurchaseLot): FormState {
  return {
    purchase_date: lot.purchase_date,
    supplier: lot.supplier,
    notes: lot.notes ?? '',
    weight_kg: lot.weight_kg,
    rate_per_kg: lot.rate_per_kg,
    gst_mode: lot.gst_mode,
    transport_mode: lot.transport_mode,
    transport_cost: lot.transport_cost,
  }
}

function payloadFrom(form: FormState): PurchaseLotInput {
  const notes = form.notes.trim()
  return {
    purchase_date: form.purchase_date,
    supplier: form.supplier.trim(),
    notes: notes === '' ? null : notes,
    weight_kg: form.weight_kg.trim(),
    rate_per_kg: form.rate_per_kg.trim(),
    gst_mode: form.gst_mode,
    transport_mode: form.transport_mode,
    transport_cost:
      form.transport_mode === 'SUPPLIER_DELIVERS'
        ? '0.00'
        : form.transport_cost.trim(),
  }
}

function validate(form: FormState): string | null {
  if (form.purchase_date === '') {
    return 'Purchase date is required.'
  }
  if (form.supplier.trim() === '') {
    return 'Supplier is required.'
  }
  if (!(Number(form.weight_kg) > 0)) {
    return 'Weight must be greater than 0.'
  }
  if (!(Number(form.rate_per_kg) > 0)) {
    return 'Rate must be greater than 0.'
  }
  if (
    form.transport_mode === 'WE_PAY' &&
    !(Number(form.transport_cost) > 0)
  ) {
    return 'Transport cost is required when we pay.'
  }
  return null
}

export default function PurchaseForm({
  initial = null,
  onSaved,
  onCancel,
}: PurchaseFormProps) {
  const [form, setForm] = useState<FormState>(() =>
    initial === null ? emptyForm() : formFromLot(initial),
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<PurchaseLot | null>(null)

  useEffect(() => {
    setForm(initial === null ? emptyForm() : formFromLot(initial))
    setError(null)
    setSaved(null)
  }, [initial])

  function setField<K extends keyof FormState>(
    field: K,
    value: FormState[K],
  ): void {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> {
    event.preventDefault()
    const problem = validate(form)
    if (problem !== null) {
      setError(problem)
      return
    }

    setSaving(true)
    setError(null)
    setSaved(null)
    try {
      const payload = payloadFrom(form)
      const lot =
        initial === null
          ? await api.purchases.create(payload)
          : await api.purchases.update(initial.id, payload)
      setSaved(lot)
      onSaved(lot)
      setForm(emptyForm())
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : 'Could not save the lot.',
      )
    } finally {
      setSaving(false)
    }
  }

  const supplierDelivers = form.transport_mode === 'SUPPLIER_DELIVERS'

  return (
    <section className="card">
      <h2>{initial === null ? 'New purchase lot' : `Edit lot #${initial.id}`}</h2>
      <form className="purchase-form" onSubmit={handleSubmit} noValidate>
        <div className="form-grid">
          <label className="field">
            <span>Purchase date</span>
            <input
              type="date"
              value={form.purchase_date}
              onChange={(event) =>
                setField('purchase_date', event.target.value)
              }
              required
            />
          </label>

          <label className="field">
            <span>Supplier</span>
            <input
              type="text"
              value={form.supplier}
              maxLength={200}
              onChange={(event) => setField('supplier', event.target.value)}
              required
            />
          </label>

          <label className="field">
            <span>Weight (kg)</span>
            <input
              type="number"
              inputMode="decimal"
              min="0.01"
              step="0.01"
              value={form.weight_kg}
              onChange={(event) => setField('weight_kg', event.target.value)}
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
              onChange={(event) => setField('rate_per_kg', event.target.value)}
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
              onChange={(event) => {
                const mode = event.target.value as PurchaseTransportMode
                setForm((current) => ({
                  ...current,
                  transport_mode: mode,
                  transport_cost:
                    mode === 'SUPPLIER_DELIVERS'
                      ? '0'
                      : current.transport_mode === 'SUPPLIER_DELIVERS'
                        ? ''
                        : current.transport_cost,
                }))
              }}
            >
              <option value="WE_PAY">We pay</option>
              <option value="SUPPLIER_DELIVERS">Supplier delivers</option>
            </select>
          </label>

          <label className="field">
            <span>Transport cost</span>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={form.transport_cost}
              onChange={(event) =>
                setField('transport_cost', event.target.value)
              }
              disabled={supplierDelivers}
              required={!supplierDelivers}
            />
          </label>
        </div>

        <label className="field">
          <span>Notes (optional)</span>
          <textarea
            value={form.notes}
            rows={2}
            onChange={(event) => setField('notes', event.target.value)}
          />
        </label>

        {supplierDelivers ? (
          <p className="muted">
            Transport cost is fixed at 0 because the supplier delivers.
          </p>
        ) : null}

        {error !== null ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}

        {saved !== null ? (
          <p className="status" role="status">
            Saved {saved.supplier}. GST {formatMoney(saved.gst_amount)} ·
            landed cost {formatOptionalMoney(saved.landed_cost_per_kg)}/kg ·
            remaining {formatKg(saved.remaining_kg)} kg.
          </p>
        ) : null}

        <div className="actions">
          <button type="submit" className="primary" disabled={saving}>
            {saving
              ? 'Saving...'
              : initial === null
                ? 'Add purchase'
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
