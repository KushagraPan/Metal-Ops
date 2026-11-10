import { useEffect, useState, type FormEvent } from 'react'

import { api } from '../api/client'
import type {
  GstMode,
  PurchaseLot,
  PurchaseLotInput,
  PurchaseTransportMode,
} from '../api/client'
import { formatKg, formatMoney, formatOptionalMoney } from '../lib/format'
import { CustomSelect } from '../components/ui/CustomSelect'

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
    <section className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="border-b border-gray-200 pb-3 mb-5 dark:border-slate-800">
        <h2 className="text-base font-semibold text-gray-900 dark:text-slate-100">
          {initial === null ? 'New purchase lot' : `Edit lot #${initial.id}`}
        </h2>
      </div>

      <form className="space-y-4" onSubmit={handleSubmit} noValidate>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="purchase-date"
              className="text-xs font-semibold text-gray-700 dark:text-slate-300"
            >
              Purchase date
            </label>
            <input
              id="purchase-date"
              type="date"
              value={form.purchase_date}
              onChange={(event) =>
                setField('purchase_date', event.target.value)
              }
              required
              className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm text-slate-900 transition-colors focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
          </div>

          <div className="flex flex-col gap-1.5 sm:col-span-2 lg:col-span-3">
            <label
              htmlFor="purchase-supplier"
              className="text-xs font-semibold text-gray-700 dark:text-slate-300"
            >
              Supplier
            </label>
            <input
              id="purchase-supplier"
              type="text"
              value={form.supplier}
              maxLength={200}
              placeholder="Supplier name"
              onChange={(event) => setField('supplier', event.target.value)}
              required
              className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm text-slate-900 transition-colors focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="purchase-weight"
              className="text-xs font-semibold text-gray-700 dark:text-slate-300"
            >
              Weight (kg)
            </label>
            <input
              id="purchase-weight"
              type="number"
              inputMode="decimal"
              min="0.01"
              step="0.01"
              placeholder="0.00"
              value={form.weight_kg}
              onChange={(event) => setField('weight_kg', event.target.value)}
              required
              className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm text-slate-900 transition-colors focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="purchase-rate"
              className="text-xs font-semibold text-gray-700 dark:text-slate-300"
            >
              Rate (₹/kg)
            </label>
            <input
              id="purchase-rate"
              type="number"
              inputMode="decimal"
              min="0.01"
              step="0.01"
              placeholder="0.00"
              value={form.rate_per_kg}
              onChange={(event) => setField('rate_per_kg', event.target.value)}
              required
              className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm text-slate-900 transition-colors focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold text-gray-700 dark:text-slate-300">
              GST mode
            </span>
            <CustomSelect
              id="purchase-gst-mode"
              label="GST mode"
              value={form.gst_mode}
              options={[
                { value: 'WITH', label: 'With GST' },
                { value: 'WITHOUT', label: 'Without GST' },
              ]}
              onChange={(value) =>
                setField('gst_mode', value as GstMode)
              }
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold text-gray-700 dark:text-slate-300">
              Transport mode
            </span>
            <CustomSelect
              id="purchase-transport-mode"
              label="Transport mode"
              value={form.transport_mode}
              options={[
                { value: 'WE_PAY', label: 'We pay' },
                { value: 'SUPPLIER_DELIVERS', label: 'Supplier delivers' },
              ]}
              onChange={(value) => {
                const mode = value as PurchaseTransportMode
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
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="purchase-transport-cost"
              className="text-xs font-semibold text-gray-700 dark:text-slate-300"
            >
              Transport cost
            </label>
            <input
              id="purchase-transport-cost"
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              placeholder={supplierDelivers ? '0.00' : '0.00'}
              value={form.transport_cost}
              onChange={(event) =>
                setField('transport_cost', event.target.value)
              }
              disabled={supplierDelivers}
              required={!supplierDelivers}
              className="h-10 w-full rounded-lg border border-gray-200 bg-white px-3 text-sm text-slate-900 transition-colors focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:disabled:bg-slate-800/50"
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="purchase-notes"
            className="text-xs font-semibold text-gray-700 dark:text-slate-300"
          >
            Notes (optional)
          </label>
          <textarea
            id="purchase-notes"
            value={form.notes}
            rows={2}
            placeholder="Optional purchase lot notes..."
            onChange={(event) => setField('notes', event.target.value)}
            className="w-full rounded-lg border border-gray-200 bg-white p-3 text-sm text-slate-900 transition-colors focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          />
        </div>

        {supplierDelivers ? (
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Transport cost is fixed at 0 because the supplier delivers.
          </p>
        ) : null}

        {error !== null ? (
          <div
            role="alert"
            className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/40 dark:text-rose-200"
          >
            {error}
          </div>
        ) : null}

        {saved !== null ? (
          <div
            role="status"
            className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/40 dark:text-emerald-200"
          >
            Saved {saved.supplier}. GST {formatMoney(saved.gst_amount)} ·
            landed cost {formatOptionalMoney(saved.landed_cost_per_kg)}/kg ·
            remaining {formatKg(saved.remaining_kg)} kg.
          </div>
        ) : null}

        <div className="flex items-center gap-3 pt-2">
          <button
            type="submit"
            disabled={saving}
            className="inline-flex h-10 items-center justify-center rounded-lg bg-amber-500 px-5 text-sm font-semibold text-slate-950 transition hover:bg-amber-400 focus:outline-none focus:ring-2 focus:ring-amber-500/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving
              ? 'Saving...'
              : initial === null
                ? 'Add purchase'
                : 'Save changes'}
          </button>
          {initial !== null && onCancel !== undefined ? (
            <button
              type="button"
              onClick={onCancel}
              className="inline-flex h-10 items-center justify-center rounded-lg border border-gray-200 bg-white px-4 text-sm font-medium text-slate-700 transition hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-amber-500/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
            >
              Cancel
            </button>
          ) : null}
        </div>
      </form>
    </section>
  )
}
