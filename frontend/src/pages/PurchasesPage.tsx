import { useEffect, useState } from 'react'

import { api } from '../api/client'
import type { PurchaseLot } from '../api/client'
import { formatKg, formatMoney, formatOptionalMoney } from '../lib/format'
import PurchaseForm from './PurchaseForm'

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.'
}

export default function PurchasesPage() {
  const [lots, setLots] = useState<PurchaseLot[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<PurchaseLot | null>(null)

  useEffect(() => {
    let active = true

    api.purchases
      .list()
      .then((rows) => {
        if (active) {
          setLots(rows)
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

  function handleSaved(lot: PurchaseLot): void {
    setLots((current) => {
      const exists = current.some((item) => item.id === lot.id)
      return exists
        ? current.map((item) => (item.id === lot.id ? lot : item))
        : [lot, ...current]
    })
    setEditing(null)
  }

  async function handleDelete(lot: PurchaseLot): Promise<void> {
    if (!window.confirm(`Delete the lot from ${lot.supplier}?`)) {
      return
    }
    setError(null)
    try {
      await api.purchases.remove(lot.id)
      setLots((current) => current.filter((item) => item.id !== lot.id))
      if (editing?.id === lot.id) {
        setEditing(null)
      }
    } catch (deleteError) {
      setError(messageOf(deleteError))
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>Purchases</h1>
          <p className="muted">
            Scrap lots, landed cost and remaining stock.
          </p>
        </div>
      </header>

      <PurchaseForm
        key={editing?.id ?? 'new'}
        initial={editing}
        onSaved={handleSaved}
        onCancel={editing === null ? undefined : () => setEditing(null)}
      />

      {error !== null ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      <section className="card">
        <h2>Lots</h2>
        {loading ? (
          <p>Loading purchases...</p>
        ) : lots.length === 0 ? (
          <p className="muted">
            No purchases yet. Add the first lot above.
          </p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Supplier</th>
                  <th className="numeric">Weight kg</th>
                  <th className="numeric">Rate ₹/kg</th>
                  <th>GST</th>
                  <th className="numeric">GST amount</th>
                  <th className="numeric">Landed ₹/kg</th>
                  <th>Transport</th>
                  <th className="numeric">Remaining kg</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {lots.map((lot) => (
                  <tr key={lot.id}>
                    <td>{lot.purchase_date}</td>
                    <td>
                      <strong>{lot.supplier}</strong>
                      {lot.notes !== null ? (
                        <span className="block muted">{lot.notes}</span>
                      ) : null}
                    </td>
                    <td className="numeric">{formatKg(lot.weight_kg)}</td>
                    <td className="numeric">{formatMoney(lot.rate_per_kg)}</td>
                    <td>
                      {lot.gst_mode === 'WITH' ? 'With GST' : 'Without GST'}
                    </td>
                    <td className="numeric">
                      {formatMoney(lot.gst_amount)}
                    </td>
                    <td className="numeric">
                      {formatOptionalMoney(lot.landed_cost_per_kg)}
                    </td>
                    <td>
                      {lot.transport_mode === 'WE_PAY'
                        ? `We pay ${formatMoney(lot.transport_cost)}`
                        : 'Supplier delivers'}
                    </td>
                    <td className="numeric">
                      {formatKg(lot.remaining_kg)}
                    </td>
                    <td className="actions">
                      <button
                        type="button"
                        aria-label={`Edit ${lot.supplier}`}
                        onClick={() => setEditing(lot)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="danger"
                        aria-label={`Delete ${lot.supplier}`}
                        onClick={() => {
                          void handleDelete(lot)
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
