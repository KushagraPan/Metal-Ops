import { useEffect, useState } from 'react'

import { api } from '../api/client'
import type { Heat, PurchaseLot } from '../api/client'
import {
  formatKg,
  formatMoney,
  formatOptionalMoney,
  formatOptionalPercent,
} from '../lib/format'
import HeatDetail from './HeatDetail'
import HeatForm from './HeatForm'

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

  useEffect(() => {
    let active = true

    Promise.all([api.heats.list(), api.purchases.list()])
      .then(([heatRows, lotRows]) => {
        if (active) {
          setHeats(heatRows)
          setLots(lotRows)
          setError(null)
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
  }, [])

  async function refreshLots(): Promise<void> {
    try {
      const rows = await api.purchases.list()
      setLots(rows)
    } catch (loadError) {
      setError(messageOf(loadError))
    }
  }

  function handleSaved(heat: Heat): void {
    setHeats((current) => {
      const exists = current.some((item) => item.id === heat.id)
      return exists
        ? current.map((item) => (item.id === heat.id ? heat : item))
        : [heat, ...current]
    })
    setEditing(null)
    setSelected(heat)
    void refreshLots()
  }

  async function handleDelete(heat: Heat): Promise<void> {
    if (!window.confirm(`Delete heat ${heat.heat_no}?`)) {
      return
    }
    setError(null)
    try {
      await api.heats.remove(heat.id)
      setHeats((current) => current.filter((item) => item.id !== heat.id))
      if (editing?.id === heat.id) {
        setEditing(null)
      }
      if (selected?.id === heat.id) {
        setSelected(null)
      }
      void refreshLots()
    } catch (deleteError) {
      setError(messageOf(deleteError))
    }
  }

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
        <h2>Heats</h2>
        {loading ? (
          <p>Loading heats...</p>
        ) : heats.length === 0 ? (
          <p className="muted">No heats yet. Add the first heat above.</p>
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
