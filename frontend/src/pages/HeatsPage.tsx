import { useEffect, useState } from 'react'

import { api } from '../api/client'
import type {
  Alloy,
  Heat,
  HeatFilters,
  PurchaseLot,
  ReportResult,
} from '../api/client'
import {
  formatKg,
  formatMoney,
  formatOptionalMoney,
  formatOptionalPercent,
} from '../lib/format'
import HeatDetail from './HeatDetail'
import HeatForm from './HeatForm'

interface FilterState {
  from_date: string
  to_date: string
  alloy: '' | Alloy
  report_result: '' | ReportResult
  heat_no: string
}

const EMPTY_FILTERS: FilterState = {
  from_date: '',
  to_date: '',
  alloy: '',
  report_result: '',
  heat_no: '',
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.'
}

export default function HeatsPage() {
  const [heats, setHeats] = useState<Heat[]>([])
  const [lots, setLots] = useState<PurchaseLot[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Heat | null>(null)
  const [selected, setSelected] = useState<Heat | null>(null)
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS)
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let active = true

    api.purchases
      .list()
      .then((lotRows) => {
        if (active) {
          setLots(lotRows)
          setError(null)
        }
      })
      .catch((loadError: unknown) => {
        if (active) {
          setError(messageOf(loadError))
        }
      })

    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    const query: HeatFilters = {}
    if (filters.from_date !== '') {
      query.from_date = filters.from_date
    }
    if (filters.to_date !== '') {
      query.to_date = filters.to_date
    }
    if (filters.alloy !== '') {
      query.alloy = filters.alloy
    }
    if (filters.report_result !== '') {
      query.report_result = filters.report_result
    }
    if (filters.heat_no.trim() !== '') {
      query.heat_no = filters.heat_no
    }

    setLoading(true)
    setError(null)
    api.heats
      .list(query)
      .then((heatRows) => {
        if (active) {
          setHeats(heatRows)
        }
      })
      .catch((loadError: unknown) => {
        if (active) {
          setError(messageOf(loadError))
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false)
        }
      })

    return () => {
      active = false
    }
  }, [filters, refreshKey])

  async function refreshLots(): Promise<void> {
    try {
      const rows = await api.purchases.list()
      setLots(rows)
    } catch (loadError) {
      setError(messageOf(loadError))
    }
  }

  function handleSaved(heat: Heat): void {
    setEditing(null)
    setSelected(heat)
    setRefreshKey((current) => current + 1)
    void refreshLots()
  }

  async function handleDelete(heat: Heat): Promise<void> {
    if (!window.confirm(`Delete heat ${heat.heat_no}?`)) {
      return
    }
    setError(null)
    try {
      await api.heats.remove(heat.id)
      if (editing?.id === heat.id) {
        setEditing(null)
      }
      if (selected?.id === heat.id) {
        setSelected(null)
      }
      setRefreshKey((current) => current + 1)
      void refreshLots()
    } catch (deleteError) {
      setError(messageOf(deleteError))
    }
  }

  const hasFilters =
    filters.from_date !== '' ||
    filters.to_date !== '' ||
    filters.alloy !== '' ||
    filters.report_result !== '' ||
    filters.heat_no.trim() !== ''

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>Heats</h1>
          <p className="muted">
            Furnace batches, lot consumption and heat yield.
          </p>
        </div>
      </header>

      <HeatForm
        key={editing?.id ?? 'new'}
        initial={editing}
        lots={lots}
        onSaved={handleSaved}
        onCancel={editing === null ? undefined : () => setEditing(null)}
      />

      {error !== null ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      {selected !== null ? (
        <HeatDetail
          heat={selected}
          onEdit={() => setEditing(selected)}
          onDelete={() => {
            void handleDelete(selected)
          }}
        />
      ) : null}

      <section className="card">
        <h2>Find heats</h2>
        <div className="form-grid">
          <label className="field">
            <span>From date</span>
            <input
              type="date"
              value={filters.from_date}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  from_date: event.target.value,
                }))
              }
            />
          </label>

          <label className="field">
            <span>To date</span>
            <input
              type="date"
              value={filters.to_date}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  to_date: event.target.value,
                }))
              }
            />
          </label>

          <label className="field">
            <span>Alloy</span>
            <select
              value={filters.alloy}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  alloy: event.target.value as '' | Alloy,
                }))
              }
            >
              <option value="">All alloys</option>
              <option value="ADC12">ADC12</option>
              <option value="LM6">LM6</option>
            </select>
          </label>

          <label className="field">
            <span>Report result</span>
            <select
              value={filters.report_result}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  report_result: event.target.value as '' | ReportResult,
                }))
              }
            >
              <option value="">Any report result</option>
              <option value="PENDING">Pending</option>
              <option value="PASS">Pass</option>
              <option value="FAIL">Fail</option>
            </select>
          </label>

          <label className="field">
            <span>Heat number</span>
            <input
              type="search"
              placeholder="e.g. H-1001"
              value={filters.heat_no}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  heat_no: event.target.value,
                }))
              }
            />
          </label>
        </div>
        <div className="actions">
          <button
            type="button"
            onClick={() => setFilters({ ...EMPTY_FILTERS })}
          >
            Clear filters
          </button>
        </div>
      </section>

      <section className="card">
        <h2>Heats</h2>
        {loading ? (
          <p>Loading heats...</p>
        ) : heats.length === 0 ? (
          <p className="muted">
            {hasFilters
              ? 'No heats match these filters.'
              : 'No heats yet. Add the first heat above.'}
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Heat</th>
                  <th>Alloy</th>
                  <th className="numeric">Output kg</th>
                  <th className="numeric">Input kg</th>
                  <th className="numeric">Yield</th>
                  <th className="numeric">Scrap cost</th>
                  <th className="numeric">Profit</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {heats.map((heat) => (
                  <tr key={heat.id}>
                    <td>{heat.heat_date}</td>
                    <td>
                      <strong>{heat.heat_no}</strong>
                      {heat.notes !== null ? (
                        <span className="block muted">{heat.notes}</span>
                      ) : null}
                    </td>
                    <td>{heat.alloy}</td>
                    <td className="numeric">
                      {formatKg(heat.output_kg)}
                    </td>
                    <td className="numeric">
                      {formatKg(heat.total_input_kg)}
                    </td>
                    <td className="numeric">
                      {formatOptionalPercent(heat.yield_pct)}
                    </td>
                    <td className="numeric">
                      {formatMoney(heat.scrap_cost)}
                    </td>
                    <td className="numeric">
                      {formatOptionalMoney(heat.heat_profit)}
                      {heat.is_provisional ? (
                        <span className="pill">provisional</span>
                      ) : null}
                    </td>
                    <td className="actions">
                      <button
                        type="button"
                        aria-label={`View ${heat.heat_no}`}
                        onClick={() => setSelected(heat)}
                      >
                        View
                      </button>
                      <button
                        type="button"
                        aria-label={`Edit ${heat.heat_no}`}
                        onClick={() => {
                          setEditing(heat)
                          setSelected(heat)
                        }}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="danger"
                        aria-label={`Delete ${heat.heat_no}`}
                        onClick={() => {
                          void handleDelete(heat)
                        }}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </section>
  )
}
