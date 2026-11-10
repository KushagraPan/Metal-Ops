import { useEffect, useState } from 'react'

import { api } from '../api/client'
import type { Heat, Sale } from '../api/client'
import {
  formatKg,
  formatMoney,
  formatOptionalMoney,
} from '../lib/format'
import SaleForm from './SaleForm'

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.'
}

function itemLabel(itemType: Sale['item_type']): string {
  if (itemType === 'DROSS') {
    return 'Dross'
  }
  if (itemType === 'IRON_SCRAP') {
    return 'Iron scrap'
  }
  return itemType
}

function transportLabel(sale: Sale): string {
  if (sale.transport_mode === 'CUSTOMER_ARRANGES') {
    return 'Customer arranges'
  }
  const net = formatMoney(sale.net_outbound_transport)
  if (sale.transport_mode === 'WE_PAY_ABSORB') {
    return `We pay and absorb ${net}`
  }
  return `Cost ${formatMoney(sale.transport_cost)} · billed ${formatMoney(
    sale.transport_billed,
  )}`
}

export default function SalesPage() {
  const [sales, setSales] = useState<Sale[]>([])
  const [heats, setHeats] = useState<Heat[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<Sale | null>(null)

  useEffect(() => {
    let active = true

    Promise.all([api.sales.list(), api.heats.list()])
      .then(([saleRows, heatRows]) => {
        if (active) {
          setSales(saleRows)
          setHeats(heatRows)
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

  async function refreshBoth(): Promise<void> {
    try {
      const [saleRows, heatRows] = await Promise.all([
        api.sales.list(),
        api.heats.list(),
      ])
      setSales(saleRows)
      setHeats(heatRows)
      setError(null)
    } catch (loadError) {
      setError(messageOf(loadError))
    }
  }

  function handleSaved(): void {
    setEditing(null)
    void refreshBoth()
  }

  async function handleDelete(sale: Sale): Promise<void> {
    if (!window.confirm(`Delete the sale to ${sale.customer}?`)) {
      return
    }
    setError(null)
    try {
      await api.sales.remove(sale.id)
      setSales((current) => current.filter((item) => item.id !== sale.id))
      if (editing?.id === sale.id) {
        setEditing(null)
      }
      void refreshHeats()
    } catch (deleteError) {
      setError(messageOf(deleteError))
    }
  }

  async function refreshHeats(): Promise<void> {
    try {
      const heatRows = await api.heats.list()
      setHeats(heatRows)
    } catch (loadError) {
      setError(messageOf(loadError))
    }
  }

  function heatLabel(heatId: number | null): string {
    if (heatId === null) {
      return 'Unlinked'
    }
    const heat = heats.find((row) => row.id === heatId)
    return heat === undefined ? `#${heatId}` : heat.heat_no
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>Sales</h1>
          <p className="muted">
            Alloy sales by heat, plus dross and iron scrap linked or unlinked.
          </p>
        </div>
      </header>

      <SaleForm
        key={editing?.id ?? 'new'}
        initial={editing}
        heats={heats}
        onSaved={handleSaved}
        onCancel={editing === null ? undefined : () => setEditing(null)}
      />

      {error !== null ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      <section className="card">
        <h2>Sales</h2>
        {loading ? (
          <p>Loading sales...</p>
        ) : sales.length === 0 ? (
          <p className="muted">No sales yet. Add the first sale above.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Customer</th>
                  <th>Item</th>
                  <th>Heat</th>
                  <th className="numeric">Kg</th>
                  <th className="numeric">Rate ₹/kg</th>
                  <th>GST</th>
                  <th className="numeric">GST amount</th>
                  <th className="numeric">Revenue</th>
                  <th>Transport</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {sales.map((sale) => (
                  <tr key={sale.id}>
                    <td>{sale.sale_date}</td>
                    <td>
                      <strong>{sale.customer}</strong>
                    </td>
                    <td>{itemLabel(sale.item_type)}</td>
                    <td>{heatLabel(sale.heat_id)}</td>
                    <td className="numeric">{formatKg(sale.weight_kg)}</td>
                    <td className="numeric">
                      {formatMoney(sale.rate_per_kg)}
                    </td>
                    <td>
                      {sale.gst_mode === 'WITH' ? 'With GST' : 'Without GST'}
                    </td>
                    <td className="numeric">
                      {formatMoney(sale.gst_amount)}
                    </td>
                    <td className="numeric">
                      {formatOptionalMoney(sale.revenue)}
                    </td>
                    <td>{transportLabel(sale)}</td>
                    <td className="actions">
                      <button
                        type="button"
                        aria-label={`Edit sale to ${sale.customer}`}
                        onClick={() => setEditing(sale)}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="danger"
                        aria-label={`Delete sale to ${sale.customer}`}
                        onClick={() => {
                          void handleDelete(sale)
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
