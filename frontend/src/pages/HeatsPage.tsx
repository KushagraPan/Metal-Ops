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
import { Select } from '../components/ui/select'
import { Badge } from '../components/ui/badge'

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
  const [openUploadForHeatId, setOpenUploadForHeatId] = useState<number | null>(null)
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

  const activeFilterCount = [
    filters.from_date !== '',
    filters.to_date !== '',
    filters.alloy !== '',
    filters.report_result !== '',
    filters.heat_no.trim() !== '',
  ].filter(Boolean).length

  const hasFilters = activeFilterCount > 0

  return (
    <section className="page space-y-6">
      <header className="page-header">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Heats</h1>
          <p className="muted text-sm text-muted-foreground">
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
          initialUploadOpen={openUploadForHeatId === selected.id}
          onEdit={() => setEditing(selected)}
          onDelete={() => {
            void handleDelete(selected)
          }}
          onReportsChanged={() =>
            setRefreshKey((current) => current + 1)
          }
        />
      ) : null}

      <section className="card p-5">
        <div className="flex items-center justify-between pb-3 border-b border-border mb-4">
          <div className="flex items-center gap-2.5">
            <h2 className="!mb-0 text-base font-semibold text-foreground">Find heats</h2>
            {activeFilterCount > 0 && (
              <span className="text-xs text-muted-foreground font-medium">
                ({activeFilterCount} {activeFilterCount === 1 ? 'filter' : 'filters'} active)
              </span>
            )}
          </div>
          <button
            type="button"
            disabled={!hasFilters}
            className="text-xs font-medium px-2.5 py-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => setFilters({ ...EMPTY_FILTERS })}
          >
            Clear filters
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="filter-from-date" className="text-xs font-semibold text-muted-foreground">
              From date
            </label>
            <input
              id="filter-from-date"
              type="date"
              aria-label="From date"
              value={filters.from_date}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  from_date: event.target.value,
                }))
              }
              className="h-10 w-full rounded-input border border-border bg-card px-3 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-ring focus:ring-offset-2"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="filter-to-date" className="text-xs font-semibold text-muted-foreground">
              To date
            </label>
            <input
              id="filter-to-date"
              type="date"
              aria-label="To date"
              value={filters.to_date}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  to_date: event.target.value,
                }))
              }
              className="h-10 w-full rounded-input border border-border bg-card px-3 text-sm text-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-ring focus:ring-offset-2"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="filter-alloy" className="text-xs font-semibold text-muted-foreground">
              Alloy
            </label>
            <Select
              id="filter-alloy"
              label="Alloy"
              value={filters.alloy}
              options={[
                { value: '', label: 'All alloys' },
                { value: 'ADC12', label: 'ADC12' },
                { value: 'LM6', label: 'LM6' },
              ]}
              onChange={(value) =>
                setFilters((current) => ({
                  ...current,
                  alloy: value as '' | Alloy,
                }))
              }
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="filter-report-result" className="text-xs font-semibold text-muted-foreground">
              Report result
            </label>
            <Select
              id="filter-report-result"
              label="Report result"
              value={filters.report_result}
              options={[
                { value: '', label: 'Any report result' },
                { value: 'PENDING', label: 'Pending' },
                { value: 'PASS', label: 'Pass' },
                { value: 'FAIL', label: 'Fail' },
              ]}
              onChange={(value) =>
                setFilters((current) => ({
                  ...current,
                  report_result: value as '' | ReportResult,
                }))
              }
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="filter-heat-no" className="text-xs font-semibold text-muted-foreground">
              Heat number
            </label>
            <input
              id="filter-heat-no"
              type="search"
              aria-label="Heat number"
              placeholder="e.g. H-1001"
              value={filters.heat_no}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  heat_no: event.target.value,
                }))
              }
              className="h-10 w-full rounded-input border border-border bg-card px-3 text-sm text-foreground placeholder:text-muted-foreground outline-none transition focus:border-primary focus:ring-2 focus:ring-ring focus:ring-offset-2"
            />
          </div>
        </div>
      </section>

      <section className="card p-5">
        <h2 className="text-base font-semibold text-foreground mb-3">Heats</h2>
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading heats...</p>
        ) : heats.length === 0 ? (
          <p className="muted text-sm text-muted-foreground">
            {hasFilters
              ? 'No heats match these filters.'
              : 'No heats yet. Add the first heat above.'}
          </p>
        ) : (
          <div className="table-wrap">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="py-2.5 px-3">Date</th>
                  <th className="py-2.5 px-3">Heat</th>
                  <th className="py-2.5 px-3">Alloy</th>
                  <th className="py-2.5 px-3 numeric">Output kg</th>
                  <th className="py-2.5 px-3 numeric">Input kg</th>
                  <th className="py-2.5 px-3 numeric">Yield</th>
                  <th className="py-2.5 px-3 numeric">Scrap cost</th>
                  <th className="py-2.5 px-3 numeric w-32 min-w-[128px]">Profit</th>
                  <th className="py-2.5 px-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {heats.map((heat) => (
                  <tr key={heat.id} className="hover:bg-muted/40 transition-colors">
                    <td className="py-2.5 px-3 whitespace-nowrap text-muted-foreground">{heat.heat_date}</td>
                    <td className="py-2.5 px-3">
                      <strong className="text-foreground">{heat.heat_no}</strong>
                      {heat.notes !== null ? (
                        <span className="block text-xs text-muted-foreground">{heat.notes}</span>
                      ) : null}
                    </td>
                    <td className="py-2.5 px-3 font-medium text-foreground">{heat.alloy}</td>
                    <td className="py-2.5 px-3 numeric text-foreground">
                      {formatKg(heat.output_kg)}
                    </td>
                    <td className="py-2.5 px-3 numeric text-foreground">
                      {formatKg(heat.total_input_kg)}
                    </td>
                    <td className="py-2.5 px-3 numeric text-foreground">
                      {formatOptionalPercent(heat.yield_pct)}
                    </td>
                    <td className="py-2.5 px-3 numeric text-foreground">
                      {formatMoney(heat.scrap_cost)}
                    </td>
                    <td className="py-2.5 px-3 numeric w-32 min-w-[128px]">
                      <div className="flex flex-col items-end gap-1">
                        <span
                          className={`tabular-nums font-semibold ${
                            heat.heat_profit !== null && Number(heat.heat_profit) > 0
                              ? 'text-emerald-700 dark:text-emerald-400'
                              : heat.heat_profit !== null && Number(heat.heat_profit) < 0
                                ? 'text-rose-700 dark:text-rose-400'
                                : 'text-foreground'
                          }`}
                        >
                          {formatOptionalMoney(heat.heat_profit)}
                        </span>
                        {heat.is_provisional ? (
                          <Badge variant="amber" className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0">
                            provisional
                          </Badge>
                        ) : null}
                      </div>
                    </td>
                    <td className="py-2.5 px-3 actions whitespace-nowrap">
                      <button
                        type="button"
                        aria-label={`View ${heat.heat_no}`}
                        className="inline-flex h-8 items-center justify-center rounded-md border border-border bg-card px-2.5 text-xs font-medium text-foreground hover:bg-secondary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        onClick={() => {
                          setSelected(heat)
                          setOpenUploadForHeatId(null)
                        }}
                      >
                        View
                      </button>
                      <button
                        type="button"
                        aria-label={`Upload report for ${heat.heat_no}`}
                        className="inline-flex h-8 items-center justify-center rounded-md border border-border bg-card px-2.5 text-xs font-medium text-foreground hover:bg-secondary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        onClick={() => {
                          setSelected(heat)
                          setOpenUploadForHeatId(heat.id)
                        }}
                      >
                        Upload report
                      </button>
                      <button
                        type="button"
                        aria-label={`Edit ${heat.heat_no}`}
                        className="inline-flex h-8 items-center justify-center rounded-md border border-border bg-card px-2.5 text-xs font-medium text-foreground hover:bg-secondary transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        onClick={() => {
                          setEditing(heat)
                          setSelected(heat)
                        }}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        aria-label={`Delete ${heat.heat_no}`}
                        className="inline-flex h-8 items-center justify-center rounded-md border border-rose-200 dark:border-rose-900/40 bg-card px-2.5 text-xs font-medium text-rose-700 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-500"
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
