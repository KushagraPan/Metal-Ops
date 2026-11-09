import { useEffect, useState, type FormEvent } from 'react'

import { api } from '../api/client'
import type {
  Alloy,
  Heat,
  HeatWrite,
  PurchaseLot,
} from '../api/client'
import {
  formatKg,
  formatMoney,
  formatOptionalMoney,
  formatOptionalPercent,
} from '../lib/format'

interface HeatFormProps {
  initial?: Heat | null
  lots: PurchaseLot[]
  onSaved: (heat: Heat) => void
  onCancel?: (() => void) | undefined
}

interface InputRow {
  lot_id: string
  kg: string
}

interface FormState {
  heat_no: string
  heat_date: string
  duration_hours: string
  notes: string
  alloy: Alloy
  output_kg: string
  dross_kg: string
  iron_scrap_kg: string
  oil_cost: string
  power_cost: string
  labour_cost: string
  other_cost: string
  inputs: InputRow[]
}

function today(): string {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

function emptyForm(): FormState {
  return {
    heat_no: '',
    heat_date: today(),
    duration_hours: '',
    notes: '',
    alloy: 'ADC12',
    output_kg: '',
    dross_kg: '0.00',
    iron_scrap_kg: '0.00',
    oil_cost: '0.00',
    power_cost: '0.00',
    labour_cost: '0.00',
    other_cost: '0.00',
    inputs: [],
  }
}

function formFromHeat(heat: Heat): FormState {
  return {
    heat_no: heat.heat_no,
    heat_date: heat.heat_date,
    duration_hours: heat.duration_hours ?? '',
    notes: heat.notes ?? '',
    alloy: heat.alloy,
    output_kg: heat.output_kg,
    dross_kg: heat.dross_kg,
    iron_scrap_kg: heat.iron_scrap_kg,
    oil_cost: heat.oil_cost,
    power_cost: heat.power_cost,
    labour_cost: heat.labour_cost,
    other_cost: heat.other_cost,
    inputs: heat.inputs.map((input) => ({
      lot_id: String(input.lot_id),
      kg: input.kg,
    })),
  }
}

function optionalDecimal(value: string): string {
  const trimmed = value.trim()
  return trimmed === '' ? '0.00' : trimmed
}

function payloadFrom(form: FormState): HeatWrite {
  const notes = form.notes.trim()
  const duration = form.duration_hours.trim()
  return {
    heat_no: form.heat_no.trim(),
    heat_date: form.heat_date,
    duration_hours: duration === '' ? null : duration,
    notes: notes === '' ? null : notes,
    alloy: form.alloy,
    output_kg: form.output_kg.trim(),
    dross_kg: optionalDecimal(form.dross_kg),
    iron_scrap_kg: optionalDecimal(form.iron_scrap_kg),
    oil_cost: optionalDecimal(form.oil_cost),
    power_cost: optionalDecimal(form.power_cost),
    labour_cost: optionalDecimal(form.labour_cost),
    other_cost: optionalDecimal(form.other_cost),
    inputs: form.inputs.map((row) => ({
      lot_id: Number(row.lot_id),
      kg: row.kg.trim(),
    })),
  }
}

function isTwoDecimals(value: string): boolean {
  return /^\d+(\.\d{1,2})?$/.test(value.trim())
}

function validate(form: FormState): string | null {
  if (form.heat_date === '') {
    return 'Heat date is required.'
  }
  if (form.heat_no.trim() === '') {
    return 'Heat number is required.'
  }
  if (!(Number(form.output_kg) > 0) || !isTwoDecimals(form.output_kg)) {
    return 'Output must be greater than 0 with at most 2 decimal places.'
  }
  if (
    form.duration_hours.trim() !== '' &&
    (!isTwoDecimals(form.duration_hours) ||
      Number(form.duration_hours) < 0)
  ) {
    return 'Duration must be zero or more with at most 2 decimal places.'
  }

  const nonNegativeFields = [
    ['Dross kg', form.dross_kg],
    ['Iron scrap kg', form.iron_scrap_kg],
    ['Oil cost', form.oil_cost],
    ['Power cost', form.power_cost],
    ['Labour cost', form.labour_cost],
    ['Other cost', form.other_cost],
  ] as const
  for (const [label, value] of nonNegativeFields) {
    if (
      value.trim() !== '' &&
      (!isTwoDecimals(value) || Number(value) < 0)
    ) {
      return `${label} must be zero or more with at most 2 decimal places.`
    }
  }

  let totalInput = 0
  for (let index = 0; index < form.inputs.length; index += 1) {
    const row = form.inputs[index]
    if (row === undefined) {
      continue
    }
    if (!(Number(row.lot_id) > 0)) {
      return `Choose a lot for input ${index + 1}.`
    }
    if (!(Number(row.kg) > 0) || !isTwoDecimals(row.kg)) {
      return `Input kg ${index + 1} must be greater than 0 with at most 2 decimal places.`
    }
    totalInput += Number(row.kg)
  }
  if (form.inputs.length > 0 && Number(form.output_kg) > totalInput) {
    return 'Output cannot exceed total input kg.'
  }
  return null
}

export default function HeatForm({
  initial = null,
  lots,
  onSaved,
  onCancel,
}: HeatFormProps) {
  const [form, setForm] = useState<FormState>(() =>
    initial === null ? emptyForm() : formFromHeat(initial),
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState<Heat | null>(null)

  useEffect(() => {
    setForm(initial === null ? emptyForm() : formFromHeat(initial))
    setError(null)
    setSaved(null)
  }, [initial])

  function setField<K extends keyof FormState>(
    field: K,
    value: FormState[K],
  ): void {
    setForm((current) => ({ ...current, [field]: value }))
  }

  function setInput(
    index: number,
    field: keyof InputRow,
    value: string,
  ): void {
    setForm((current) => ({
      ...current,
      inputs: current.inputs.map((row, rowIndex) =>
        rowIndex === index ? { ...row, [field]: value } : row,
      ),
    }))
  }

  function addInput(): void {
    if (lots.length === 0) {
      return
    }
    const used = new Set(form.inputs.map((row) => row.lot_id))
    const candidate =
      lots.find((lot) => !used.has(String(lot.id))) ?? lots[0]
    if (candidate === undefined) {
      return
    }
    setForm((current) => ({
      ...current,
      inputs: [
        ...current.inputs,
        { lot_id: String(candidate.id), kg: '' },
      ],
    }))
  }

  function removeInput(index: number): void {
    setForm((current) => ({
      ...current,
      inputs: current.inputs.filter((_, rowIndex) => rowIndex !== index),
    }))
  }

  function availableFor(lot: PurchaseLot): number {
    const own =
      initial?.inputs.find((input) => input.lot_id === lot.id) ?? null
    return Number(lot.remaining_kg) + (own === null ? 0 : Number(own.kg))
  }

  function lotLabel(lot: PurchaseLot): string {
    return `${lot.supplier} · ${lot.purchase_date} · ${formatKg(
      String(availableFor(lot)),
    )} kg left`
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
      const heat =
        initial === null
          ? await api.heats.create(payload)
          : await api.heats.update(initial.id, payload)
      setSaved(heat)
      onSaved(heat)
      setForm(emptyForm())
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : 'Could not save the heat.',
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="card">
      <h2>{initial === null ? 'New heat' : `Edit heat #${initial.id}`}</h2>
      <form className="heat-form" onSubmit={handleSubmit} noValidate>
        <div className="form-grid">
          <label className="field">
            <span>Heat number</span>
            <input
              type="text"
              value={form.heat_no}
              maxLength={50}
              onChange={(event) => setField('heat_no', event.target.value)}
              required
            />
          </label>

          <label className="field">
            <span>Heat date</span>
            <input
              type="date"
              value={form.heat_date}
              onChange={(event) =>
                setField('heat_date', event.target.value)
              }
              required
            />
          </label>

          <label className="field">
            <span>Alloy</span>
            <select
              value={form.alloy}
              onChange={(event) =>
                setField('alloy', event.target.value as Alloy)
              }
            >
              <option value="ADC12">ADC12</option>
              <option value="LM6">LM6</option>
            </select>
          </label>

          <label className="field">
            <span>Duration (hours)</span>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={form.duration_hours}
              onChange={(event) =>
                setField('duration_hours', event.target.value)
              }
            />
          </label>

          <label className="field">
            <span>Output (kg)</span>
            <input
              type="number"
              inputMode="decimal"
              min="0.01"
              step="0.01"
              value={form.output_kg}
              onChange={(event) =>
                setField('output_kg', event.target.value)
              }
              required
            />
          </label>

          <label className="field">
            <span>Dross (kg)</span>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={form.dross_kg}
              onChange={(event) =>
                setField('dross_kg', event.target.value)
              }
            />
          </label>

          <label className="field">
            <span>Iron scrap (kg)</span>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={form.iron_scrap_kg}
              onChange={(event) =>
                setField('iron_scrap_kg', event.target.value)
              }
            />
          </label>

          <label className="field">
            <span>Oil cost (₹)</span>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={form.oil_cost}
              onChange={(event) =>
                setField('oil_cost', event.target.value)
              }
            />
          </label>

          <label className="field">
            <span>Power cost (₹)</span>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={form.power_cost}
              onChange={(event) =>
                setField('power_cost', event.target.value)
              }
            />
          </label>

          <label className="field">
            <span>Labour cost (₹)</span>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={form.labour_cost}
              onChange={(event) =>
                setField('labour_cost', event.target.value)
              }
            />
          </label>

          <label className="field">
            <span>Other cost (₹)</span>
            <input
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={form.other_cost}
              onChange={(event) =>
                setField('other_cost', event.target.value)
              }
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

        <section className="input-lines">
          <div className="input-lines-header">
            <div>
              <h3>Input lots</h3>
              <p className="muted">
                Zero inputs is valid. Yield and profit then show n/a.
              </p>
            </div>
            <button
              type="button"
              onClick={addInput}
              disabled={lots.length === 0}
            >
              Add lot
            </button>
          </div>

          {lots.length === 0 ? (
            <p className="muted">
              Add a purchase lot before linking inputs. An empty heat can
              still be saved.
            </p>
          ) : null}

          {form.inputs.length === 0 ? (
            <p className="muted">No inputs yet.</p>
          ) : (
            form.inputs.map((row, index) => (
              <div className="input-line" key={index}>
                <label className="field">
                  <span>Lot {index + 1}</span>
                  <select
                    value={row.lot_id}
                    onChange={(event) =>
                      setInput(index, 'lot_id', event.target.value)
                    }
                  >
                    {lots.map((lot) => (
                      <option key={lot.id} value={String(lot.id)}>
                        {lotLabel(lot)}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="field">
                  <span>Input kg {index + 1}</span>
                  <input
                    type="number"
                    inputMode="decimal"
                    min="0.01"
                    step="0.01"
                    value={row.kg}
                    onChange={(event) =>
                      setInput(index, 'kg', event.target.value)
                    }
                    required
                  />
                </label>

                <button
                  type="button"
                  className="danger"
                  aria-label={`Remove input ${index + 1}`}
                  onClick={() => removeInput(index)}
                >
                  Remove
                </button>
              </div>
            ))
          )}
        </section>

        {error !== null ? (
          <p className="error" role="alert">
            {error}
          </p>
        ) : null}

        {saved !== null ? (
          <p className="status" role="status">
            Saved {saved.heat_no}. Yield{' '}
            {formatOptionalPercent(saved.yield_pct)} · scrap cost{' '}
            {formatMoney(saved.scrap_cost)} · profit{' '}
            {formatOptionalMoney(saved.heat_profit)}.
          </p>
        ) : null}

        <div className="actions">
          <button type="submit" className="primary" disabled={saving}>
            {saving
              ? 'Saving...'
              : initial === null
                ? 'Add heat'
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
