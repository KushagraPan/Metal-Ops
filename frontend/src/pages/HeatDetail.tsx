import type { Heat, Sale } from '../api/client'
import {
  formatKg,
  formatMoney,
  formatOptionalMoney,
  formatOptionalPercent,
} from '../lib/format'
import HeatReports from './HeatReports'
import { Badge } from '../components/ui/badge'

interface HeatDetailProps {
  heat: Heat
  initialUploadOpen?: boolean
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
  initialUploadOpen = false,
  onEdit,
  onDelete,
  onReportsChanged,
}: HeatDetailProps) {
  const duration =
    heat.duration_hours === null
      ? 'Duration not recorded'
      : `Duration ${formatKg(heat.duration_hours)} h`

  return (
    <section className="card p-5 space-y-6">
      <header className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 pb-4 border-b border-border">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-foreground">Heat {heat.heat_no}</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {heat.heat_date} · {heat.alloy} · {duration}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {onEdit !== undefined ? (
            <button
              type="button"
              onClick={onEdit}
              className="inline-flex h-8 items-center justify-center rounded-md border border-border bg-card px-3 text-xs font-medium text-foreground hover:bg-secondary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Edit
            </button>
          ) : null}
          {onDelete !== undefined ? (
            <button
              type="button"
              onClick={onDelete}
              className="inline-flex h-8 items-center justify-center rounded-md border border-rose-200 dark:border-rose-900/40 bg-card px-3 text-xs font-medium text-rose-700 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
            >
              Delete
            </button>
          ) : null}
        </div>
      </header>

      {/* KPI Stats Grid */}
      <dl className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <div className="rounded-xl border border-border bg-card p-3 shadow-xs">
          <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Output</dt>
          <dd className="mt-1 text-base font-bold tabular-nums text-foreground">{formatKg(heat.output_kg)} kg</dd>
        </div>
        <div className="rounded-xl border border-border bg-card p-3 shadow-xs">
          <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Total input</dt>
          <dd className="mt-1 text-base font-bold tabular-nums text-foreground">{formatKg(heat.total_input_kg)} kg</dd>
        </div>
        <div className="rounded-xl border border-border bg-card p-3 shadow-xs">
          <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Yield</dt>
          <dd className="mt-1 text-base font-bold tabular-nums text-foreground">{formatOptionalPercent(heat.yield_pct)}</dd>
        </div>
        <div className="rounded-xl border border-border bg-card p-3 shadow-xs">
          <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Sold alloy</dt>
          <dd className="mt-1 text-base font-bold tabular-nums text-foreground">{formatKg(heat.sold_alloy_kg)} kg</dd>
        </div>
        <div className="rounded-xl border border-border bg-card p-3 shadow-xs">
          <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Scrap cost</dt>
          <dd className="mt-1 text-base font-bold tabular-nums text-foreground">{formatMoney(heat.scrap_cost)}</dd>
        </div>
        <div className="rounded-xl border border-border bg-card p-3 shadow-xs">
          <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Variable costs</dt>
          <dd className="mt-1 text-base font-bold tabular-nums text-foreground">{formatMoney(heat.variable_costs)}</dd>
        </div>
        <div className="rounded-xl border border-border bg-card p-3 shadow-xs">
          <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Revenue</dt>
          <dd className="mt-1 text-base font-bold tabular-nums text-foreground">{formatMoney(heat.revenue)}</dd>
        </div>
        <div className="rounded-xl border border-border bg-card p-3 shadow-xs">
          <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Net outbound transport</dt>
          <dd className="mt-1 text-base font-bold tabular-nums text-foreground">{formatMoney(heat.net_outbound_transport)}</dd>
        </div>
        <div className="col-span-2 rounded-xl border border-border bg-card p-3 shadow-xs">
          <dt className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Profit</dt>
          <dd className="mt-1 text-base font-bold tabular-nums text-foreground flex items-center gap-2">
            <span
              className={
                heat.heat_profit !== null && Number(heat.heat_profit) > 0
                  ? 'text-emerald-700 dark:text-emerald-400'
                  : heat.heat_profit !== null && Number(heat.heat_profit) < 0
                    ? 'text-rose-700 dark:text-rose-400'
                    : 'text-foreground'
              }
            >
              {formatOptionalMoney(heat.heat_profit)}
            </span>
            {heat.is_provisional ? (
              <Badge variant="amber" className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0">
                provisional
              </Badge>
            ) : null}
          </dd>
        </div>
      </dl>

      {/* Input lots subsection */}
      <div className="space-y-3 pt-2">
        <h3 className="text-sm font-semibold text-foreground">Input lots</h3>
        {heat.inputs.length === 0 ? (
          <p className="text-xs text-muted-foreground italic">No lots linked to this heat.</p>
        ) : (
          <div className="table-wrap rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground bg-muted/20">
                  <th className="py-2.5 px-3">Lot</th>
                  <th className="py-2.5 px-3">Supplier</th>
                  <th className="py-2.5 px-3">Purchase date</th>
                  <th className="py-2.5 px-3 numeric">Input kg</th>
                  <th className="py-2.5 px-3 numeric">Landed ₹/kg</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {heat.inputs.map((input) => (
                  <tr key={input.lot_id} className="hover:bg-muted/40 transition-colors">
                    <td className="py-2.5 px-3 font-semibold text-foreground">#{input.lot_id}</td>
                    <td className="py-2.5 px-3 text-foreground">{input.supplier}</td>
                    <td className="py-2.5 px-3 whitespace-nowrap text-muted-foreground">{input.purchase_date}</td>
                    <td className="py-2.5 px-3 numeric font-medium text-foreground">{formatKg(input.kg)}</td>
                    <td className="py-2.5 px-3 numeric font-medium text-foreground">
                      {formatOptionalMoney(input.landed_cost_per_kg)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Linked sales subsection */}
      <div className="space-y-3 pt-2">
        <h3 className="text-sm font-semibold text-foreground">Linked sales</h3>
        {heat.sales.length === 0 ? (
          <p className="text-xs text-muted-foreground italic">No sales linked to this heat.</p>
        ) : (
          <div className="table-wrap rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground bg-muted/20">
                  <th className="py-2.5 px-3">Sale date</th>
                  <th className="py-2.5 px-3">Customer</th>
                  <th className="py-2.5 px-3">Item</th>
                  <th className="py-2.5 px-3 numeric">Kg</th>
                  <th className="py-2.5 px-3 numeric">Rate ₹/kg</th>
                  <th className="py-2.5 px-3">GST</th>
                  <th className="py-2.5 px-3 numeric">GST amount</th>
                  <th className="py-2.5 px-3 numeric">Revenue</th>
                  <th className="py-2.5 px-3">Transport</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {heat.sales.map((sale) => (
                  <tr key={sale.id} className="hover:bg-muted/40 transition-colors">
                    <td className="py-2.5 px-3 whitespace-nowrap text-muted-foreground">{sale.sale_date}</td>
                    <td className="py-2.5 px-3">
                      <strong className="text-foreground">{sale.customer}</strong>
                    </td>
                    <td className="py-2.5 px-3 text-muted-foreground">{itemLabel(sale.item_type)}</td>
                    <td className="py-2.5 px-3 numeric text-foreground">{formatKg(sale.weight_kg)}</td>
                    <td className="py-2.5 px-3 numeric text-foreground">{formatMoney(sale.rate_per_kg)}</td>
                    <td className="py-2.5 px-3 text-muted-foreground">
                      {sale.gst_mode === 'WITH' ? 'With GST' : 'Without GST'}
                    </td>
                    <td className="py-2.5 px-3 numeric text-foreground">{formatMoney(sale.gst_amount)}</td>
                    <td className="py-2.5 px-3 numeric font-semibold text-foreground">{formatMoney(sale.revenue)}</td>
                    <td className="py-2.5 px-3 text-xs text-muted-foreground">{transportLabel(sale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="pt-2">
        <HeatReports
          heatId={heat.id}
          reports={heat.reports}
          initialUploadOpen={initialUploadOpen}
          onChanged={onReportsChanged}
        />
      </div>

      {heat.notes !== null ? (
        <p className="text-xs text-muted-foreground p-3 rounded-lg bg-muted/30 border border-border">
          {heat.notes}
        </p>
      ) : null}
    </section>
  )
}
