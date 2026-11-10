import type { Heat, Sale } from '../api/client'
import {
  formatKg,
  formatMoney,
  formatOptionalMoney,
  formatOptionalPercent,
} from '../lib/format'
import HeatReports from './HeatReports'

interface HeatDetailProps {
  heat: Heat
  onEdit?: (() => void) | undefined
  onDelete?: (() => void) | undefined
  onReportsChanged?: (() => void) | undefined
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
    return `We absorb ${net}`
  }
  return `Cost ${formatMoney(sale.transport_cost)} · billed ${formatMoney(
    sale.transport_billed,
  )}`
}

export default function HeatDetail({
  heat,
  onEdit,
  onDelete,
  onReportsChanged,
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
          <dt>Sold alloy</dt>
          <dd>{formatKg(heat.sold_alloy_kg)} kg</dd>
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
          <dt>Revenue</dt>
          <dd>{formatMoney(heat.revenue)}</dd>
        </div>
        <div>
          <dt>Net outbound transport</dt>
          <dd>{formatMoney(heat.net_outbound_transport)}</dd>
        </div>
        <div>
          <dt>Profit</dt>
          <dd>
            {formatOptionalMoney(heat.heat_profit)}
            {heat.is_provisional ? (
              <span className="pill">provisional</span>
            ) : null}
          </dd>
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

      <h3>Linked sales</h3>
      {heat.sales.length === 0 ? (
        <p className="muted">No sales linked to this heat.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Sale date</th>
                <th>Customer</th>
                <th>Item</th>
                <th className="numeric">Kg</th>
                <th className="numeric">Rate ₹/kg</th>
                <th>GST</th>
                <th className="numeric">GST amount</th>
                <th className="numeric">Revenue</th>
                <th>Transport</th>
              </tr>
            </thead>
            <tbody>
              {heat.sales.map((sale) => (
                <tr key={sale.id}>
                  <td>{sale.sale_date}</td>
                  <td>
                    <strong>{sale.customer}</strong>
                  </td>
                  <td>{itemLabel(sale.item_type)}</td>
                  <td className="numeric">{formatKg(sale.weight_kg)}</td>
                  <td className="numeric">{formatMoney(sale.rate_per_kg)}</td>
                  <td>
                    {sale.gst_mode === 'WITH' ? 'With GST' : 'Without GST'}
                  </td>
                  <td className="numeric">{formatMoney(sale.gst_amount)}</td>
                  <td className="numeric">{formatMoney(sale.revenue)}</td>
                  <td>{transportLabel(sale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <HeatReports
        heatId={heat.id}
        reports={heat.reports}
        onChanged={onReportsChanged}
      />

      {heat.notes !== null ? (
        <p className="muted detail-notes">{heat.notes}</p>
      ) : null}
    </section>
  )
}
