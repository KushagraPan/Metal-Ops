import type { Heat } from '../api/client'
import {
  formatKg,
  formatMoney,
  formatOptionalMoney,
  formatOptionalPercent,
} from '../lib/format'

interface HeatDetailProps {
  heat: Heat
  onEdit?: (() => void) | undefined
  onDelete?: (() => void) | undefined
}

export default function HeatDetail({
  heat,
  onEdit,
  onDelete,
}: HeatDetailProps) {
  const duration =
    heat.duration_hours === null
      ? 'Duration not recorded'
      : `Duration ${formatKg(heat.duration_hours)} h`

  return (
    <section className="card">
      <header className="detail-header">
        <div>
          <h2>Heat {heat.heat_no}</h2>
          <p className="muted">
            {heat.heat_date} · {heat.alloy} · {duration}
          </p>
        </div>
        <div className="actions">
          {onEdit !== undefined ? (
            <button type="button" onClick={onEdit}>
              Edit
            </button>
          ) : null}
          {onDelete !== undefined ? (
            <button type="button" className="danger" onClick={onDelete}>
              Delete
            </button>
          ) : null}
        </div>
      </header>

      <dl className="detail-grid">
        <div>
          <dt>Output</dt>
          <dd>{formatKg(heat.output_kg)} kg</dd>
        </div>
        <div>
          <dt>Total input</dt>
          <dd>{formatKg(heat.total_input_kg)} kg</dd>
        </div>
        <div>
          <dt>Yield</dt>
          <dd>{formatOptionalPercent(heat.yield_pct)}</dd>
        </div>
        <div>
          <dt>Scrap cost</dt>
          <dd>{formatMoney(heat.scrap_cost)}</dd>
        </div>
        <div>
          <dt>Variable costs</dt>
          <dd>{formatMoney(heat.variable_costs)}</dd>
        </div>
        <div>
          <dt>Profit</dt>
          <dd>{formatOptionalMoney(heat.heat_profit)}</dd>
        </div>
      </dl>

      <h3>Input lots</h3>
      {heat.inputs.length === 0 ? (
        <p className="muted">No lots linked to this heat.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Lot</th>
                <th>Supplier</th>
                <th>Purchase date</th>
                <th className="numeric">Input kg</th>
                <th className="numeric">Landed ₹/kg</th>
              </tr>
            </thead>
            <tbody>
              {heat.inputs.map((input) => (
                <tr key={input.lot_id}>
                  <td>#{input.lot_id}</td>
                  <td>{input.supplier}</td>
                  <td>{input.purchase_date}</td>
                  <td className="numeric">{formatKg(input.kg)}</td>
                  <td className="numeric">
                    {formatOptionalMoney(input.landed_cost_per_kg)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {heat.notes !== null ? (
        <p className="muted detail-notes">{heat.notes}</p>
      ) : null}
    </section>
  )
}
