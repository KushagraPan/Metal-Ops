import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card'
import { formatMoneyWhole, formatPercent } from '../lib/format'
import type { DashboardHeatSummary } from '../api/client'

// Polyfill ResizeObserver for jsdom test environments if missing
if (typeof window !== 'undefined' && !('ResizeObserver' in window)) {
  ;(window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

interface ProfitChartProps {
  heats: DashboardHeatSummary[]
}

export function ProfitChart({ heats }: ProfitChartProps) {
  // Oldest heat on the left; omit heats with null profit
  const data = [...heats]
    .reverse()
    .filter((h) => h.heat_profit !== null)
    .map((h) => ({
      heat_no: h.heat_no,
      profit: Number(h.heat_profit),
      is_provisional: h.is_provisional,
    }))

  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold">Profit per Heat</CardTitle>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            Dashed outline = provisional
          </span>
        </div>
        <CardDescription>
          Net heat profit in INR (whole rupees). Green indicates profit, red indicates loss.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex-1 pb-4">
        {data.length === 0 ? (
          <div className="flex h-56 items-center justify-center text-sm text-slate-500 dark:text-slate-400">
            No profit data recorded for heats in this month.
          </div>
        ) : (
          <div
            className="h-56 w-full"
            role="img"
            aria-label="Bar chart showing profit per heat. Detailed data available in table below."
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                <XAxis
                  dataKey="heat_no"
                  tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                  tickLine={false}
                  axisLine={{ stroke: 'hsl(var(--border))' }}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                  tickLine={false}
                  axisLine={{ stroke: 'hsl(var(--border))' }}
                  tickFormatter={(val) => `₹${Math.round(val / 1000)}k`}
                />
                <ReferenceLine y={0} stroke="hsl(var(--border))" />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length && payload[0]?.payload) {
                      const item = payload[0].payload
                      const profitColor =
                        item.profit > 0
                          ? 'text-emerald-700 dark:text-emerald-400 font-medium'
                          : item.profit < 0
                            ? 'text-rose-700 dark:text-rose-400 font-medium'
                            : 'text-muted-foreground font-medium'
                      return (
                        <div className="rounded-md border border-border bg-card p-2.5 text-xs shadow-md">
                          <p className="font-semibold text-foreground">
                            {item.heat_no}
                            {item.is_provisional ? ' (Provisional)' : ''}
                          </p>
                          <p className={profitColor}>
                            Profit: {formatMoneyWhole(item.profit)}
                          </p>
                        </div>
                      )
                    }
                    return null
                  }}
                />
                <Bar dataKey="profit" radius={[3, 3, 0, 0]}>
                  {data.map((entry, index) => {
                    const fillColor =
                      entry.profit > 0
                        ? '#059669'
                        : entry.profit < 0
                          ? '#e11d48'
                          : '#64748b'
                    return (
                      <Cell
                        key={`bar-${index}`}
                        fill={fillColor}
                        stroke={entry.is_provisional ? '#d97706' : 'none'}
                        strokeWidth={entry.is_provisional ? 2 : 0}
                        strokeDasharray={entry.is_provisional ? '3 3' : undefined}
                      />
                    )
                  })}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Text alternative for screen readers and accessibility */}
        <details className="mt-3 text-xs text-muted-foreground">
          <summary className="cursor-pointer hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded px-1">
            View profit chart data as table
          </summary>
          <div className="mt-2 max-h-36 overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th className="py-1">Heat</th>
                  <th className="py-1 text-right">Profit</th>
                  <th className="py-1 text-right">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.map((h) => (
                  <tr key={h.heat_no} className="border-b border-border/50 text-foreground">
                    <td className="py-1">{h.heat_no}</td>
                    <td className="py-1 text-right tabular-nums">{formatMoneyWhole(h.profit)}</td>
                    <td className="py-1 text-right">{h.is_provisional ? 'Provisional' : 'Final'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </CardContent>
    </Card>
  )
}

interface YieldChartProps {
  heats: DashboardHeatSummary[]
  plannedYieldPct: string | number
}

export function YieldChart({ heats, plannedYieldPct }: YieldChartProps) {
  // Oldest heat on the left; omit heats with null yield
  const data = [...heats]
    .reverse()
    .filter((h) => h.yield_pct !== null)
    .map((h) => ({
      heat_no: h.heat_no,
      yield_pct: Number(h.yield_pct),
      is_provisional: h.is_provisional,
    }))

  const plannedNum = Number(plannedYieldPct)
  const yDomain: [((min: number) => number) | 'auto', ((max: number) => number) | 'auto'] =
    data.length > 0 && !isNaN(plannedNum)
      ? [
          (dataMin: number) => Math.floor(Math.min(dataMin, plannedNum) - 1),
          (dataMax: number) => Math.ceil(Math.max(dataMax, plannedNum) + 1),
        ]
      : ['auto', 'auto']

  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold">Yield per Heat</CardTitle>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            Plan: {formatPercent(plannedYieldPct)}
          </span>
        </div>
        <CardDescription>
          Metal recovery percentage per heat compared against workshop target.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex-1 pb-4">
        {data.length === 0 ? (
          <div className="flex h-56 items-center justify-center text-sm text-slate-500 dark:text-slate-400">
            No yield data recorded for heats in this month.
          </div>
        ) : (
          <div
            className="h-56 w-full"
            role="img"
            aria-label={`Line chart showing yield per heat against planned target of ${plannedYieldPct}%. Detailed data available in table below.`}
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 10, right: 10, left: -15, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                <XAxis
                  dataKey="heat_no"
                  tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                  tickLine={false}
                  axisLine={{ stroke: 'hsl(var(--border))' }}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
                  tickLine={false}
                  axisLine={{ stroke: 'hsl(var(--border))' }}
                  domain={yDomain}
                  tickFormatter={(val) => `${val}%`}
                />
                <ReferenceLine
                  y={plannedNum}
                  stroke="#d97706"
                  strokeDasharray="4 4"
                  strokeWidth={1.5}
                  label={{
                    value: `Plan ${plannedNum}%`,
                    fill: '#d97706',
                    fontSize: 10,
                    position: 'top',
                  }}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length && payload[0]?.payload) {
                      const item = payload[0].payload
                      return (
                        <div className="rounded-md border border-border bg-card p-2.5 text-xs shadow-md">
                          <p className="font-semibold text-foreground">
                            {item.heat_no}
                            {item.is_provisional ? ' (Provisional)' : ''}
                          </p>
                          <p className="text-amber-600 dark:text-amber-400 font-medium">
                            Yield: {formatPercent(item.yield_pct)}
                          </p>
                          <p className="text-muted-foreground">
                            Plan: {formatPercent(plannedYieldPct)}
                          </p>
                        </div>
                      )
                    }
                    return null
                  }}
                />
                <Line
                  type="linear"
                  dataKey="yield_pct"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  dot={(props: any): React.ReactElement => {
                    const { cx, cy, payload } = props
                    if (typeof cx !== 'number' || typeof cy !== 'number') {
                      return <g key="empty-dot" />
                    }
                    if (payload?.is_provisional) {
                      return (
                        <g key={`dot-provisional-${cx}-${cy}`}>
                          <circle cx={cx} cy={cy} r={6} fill="hsl(var(--card))" stroke="#d97706" strokeWidth={2} />
                          <circle cx={cx} cy={cy} r={2} fill="#d97706" />
                        </g>
                      )
                    }
                    return <circle key={`dot-${cx}-${cy}`} cx={cx} cy={cy} r={4} fill="#f59e0b" />
                  }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Text alternative for accessibility */}
        <details className="mt-3 text-xs text-muted-foreground">
          <summary className="cursor-pointer hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded px-1">
            View yield chart data as table
          </summary>
          <div className="mt-2 max-h-36 overflow-y-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border text-muted-foreground">
                  <th className="py-1">Heat</th>
                  <th className="py-1 text-right">Yield</th>
                  <th className="py-1 text-right">Status</th>
                </tr>
              </thead>
              <tbody>
                {data.map((h) => (
                  <tr key={h.heat_no} className="border-b border-border/50 text-foreground">
                    <td className="py-1">{h.heat_no}</td>
                    <td className="py-1 text-right tabular-nums">{formatPercent(h.yield_pct)}</td>
                    <td className="py-1 text-right">{h.is_provisional ? 'Provisional' : 'Final'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </CardContent>
    </Card>
  )
}
