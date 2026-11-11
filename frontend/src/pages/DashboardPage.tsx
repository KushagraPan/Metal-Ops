import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  AlertCircle,
  Calendar,
  Flame,
  IndianRupee,
  Percent,
  Plus,
  RefreshCw,
  Trash2,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'

import { api } from '../api/client'
import type { DashboardData } from '../api/client'
import { Badge } from '../components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card'
import { Skeleton } from '../components/ui/skeleton'
import { ProfitChart, YieldChart } from '../components/DashboardCharts'
import {
  formatKg,
  formatMoney,
  formatMoneyWhole,
  formatOptionalMoney,
  formatOptionalPercent,
  formatPercent,
} from '../lib/format'

export interface DashboardPageProps {
  initialMonth?: string
  month?: string
  onMonthChange?: (month: string) => void
}

function defaultMonth(): string {
  const now = new Date()
  const year = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  return `${year}-${m}`
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.'
}

export default function DashboardPage({
  initialMonth,
  month: controlledMonth,
  onMonthChange,
}: DashboardPageProps) {
  const [internalMonth, setInternalMonth] = useState<string>(
    controlledMonth || initialMonth || defaultMonth()
  )

  const activeMonth = controlledMonth || internalMonth

  const handleMonthChange = (newMonth: string) => {
    setInternalMonth(newMonth)
    onMonthChange?.(newMonth)
  }

  const [data, setData] = useState<DashboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Expense form state
  const [expenseCategory, setExpenseCategory] = useState('')
  const [expenseAmount, setExpenseAmount] = useState('')
  const [savingExpense, setSavingExpense] = useState(false)
  const [expenseError, setExpenseError] = useState<string | null>(null)

  function loadDashboard(targetMonth: string) {
    setLoading(true)
    setError(null)
    api.dashboard
      .get(targetMonth)
      .then((res) => {
        setData(res)
      })
      .catch((err: unknown) => {
        setError(messageOf(err))
      })
      .finally(() => {
        setLoading(false)
      })
  }

  useEffect(() => {
    loadDashboard(activeMonth)
  }, [activeMonth])

  async function handleAddExpense(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setExpenseError(null)
    const category = expenseCategory.trim()
    if (!category) {
      setExpenseError('Category is required.')
      return
    }
    const amount = expenseAmount.trim()
    if (!amount || Number.isNaN(Number(amount)) || Number(amount) < 0) {
      setExpenseError('Enter a valid non-negative amount.')
      return
    }

    setSavingExpense(true)
    try {
      await api.expenses.create({
        month: activeMonth,
        category,
        amount,
      })
      setExpenseCategory('')
      setExpenseAmount('')
      loadDashboard(activeMonth)
    } catch (err: unknown) {
      setExpenseError(messageOf(err))
    } finally {
      setSavingExpense(false)
    }
  }

  async function handleDeleteExpense(id: number) {
    if (!window.confirm('Delete this expense?')) {
      return
    }
    try {
      await api.expenses.remove(id)
      loadDashboard(activeMonth)
    } catch (err: unknown) {
      setError(messageOf(err))
    }
  }

  return (
    <div className="space-y-6">
      {/* Top Header / Month Picker */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            Workshop Dashboard
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Monthly overview of profits, yields, heats, fixed expenses, and GST estimates.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <Calendar className="h-4 w-4 text-slate-500" />
            <span className="text-slate-600 dark:text-slate-400">Month</span>
            <input
              type="month"
              aria-label="Month"
              value={activeMonth}
              onChange={(e) => handleMonthChange(e.target.value)}
              className="bg-transparent font-medium text-slate-900 focus:outline-none dark:text-slate-100"
            />
          </label>
        </div>
      </div>

      {/* Error state */}
      {error !== null && (
        <div
          role="alert"
          className="flex items-center gap-3 rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/40 dark:text-rose-200"
        >
          <AlertCircle className="h-5 w-5 flex-shrink-0 text-rose-600 dark:text-rose-400" />
          <div className="flex-1">
            <p className="font-semibold">Unable to load dashboard data</p>
            <p>{error}</p>
          </div>
          <button
            type="button"
            onClick={() => loadDashboard(activeMonth)}
            className="inline-flex items-center gap-1 rounded-md bg-rose-100 px-2.5 py-1 text-xs font-semibold text-rose-900 hover:bg-rose-200 dark:bg-rose-900 dark:text-rose-100 dark:hover:bg-rose-800"
          >
            <RefreshCw className="h-3 w-3" /> Retry
          </button>
        </div>
      )}

      {/* Skeleton loading state */}
      {loading ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Card key={i} className="p-5">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="mt-4 h-8 w-36" />
                <Skeleton className="mt-2 h-3 w-20" />
              </Card>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <Card className="p-5">
              <Skeleton className="h-5 w-32" />
              <Skeleton className="mt-2 h-3 w-48" />
              <Skeleton className="mt-6 h-56 w-full" />
            </Card>
            <Card className="p-5">
              <Skeleton className="h-5 w-32" />
              <Skeleton className="mt-2 h-3 w-48" />
              <Skeleton className="mt-6 h-56 w-full" />
            </Card>
          </div>
        </div>
      ) : data !== null ? (
        <>
          {/* Row 1: Four KPI Cards */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {/* KPI 1: Profit this month */}
            <Card className="overflow-hidden border-slate-200 dark:border-slate-800">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-slate-600 dark:text-slate-400">
                  Profit this month
                </CardTitle>
                {Number(data.profit) >= 0 ? (
                  <TrendingUp className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                ) : (
                  <TrendingDown className="h-4 w-4 text-rose-600 dark:text-rose-400" />
                )}
              </CardHeader>
              <CardContent>
                <div
                  className={`text-2xl font-bold tabular-nums ${
                    Number(data.profit) > 0
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : Number(data.profit) < 0
                        ? 'text-rose-600 dark:text-rose-400'
                        : 'text-slate-900 dark:text-slate-100'
                  }`}
                >
                  {formatMoneyWhole(data.profit)}
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                  <span>Ex-GST net profit</span>
                  {data.is_provisional && (
                    <Badge variant="amber" className="text-[10px] uppercase font-bold tracking-wider">
                      provisional
                    </Badge>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* KPI 2: Revenue */}
            <Card className="overflow-hidden border-slate-200 dark:border-slate-800">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-slate-600 dark:text-slate-400">
                  Revenue
                </CardTitle>
                <IndianRupee className="h-4 w-4 text-amber-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold tabular-nums text-slate-900 dark:text-slate-100">
                  {formatMoneyWhole(data.revenue)}
                </div>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  Total alloy and scrap sales (ex-GST)
                </p>
              </CardContent>
            </Card>

            {/* KPI 3: Average yield vs plan */}
            <Card className="overflow-hidden border-slate-200 dark:border-slate-800">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-slate-600 dark:text-slate-400">
                  Average yield vs plan
                </CardTitle>
                <Percent className="h-4 w-4 text-amber-500" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold tabular-nums text-slate-900 dark:text-slate-100">
                  {formatOptionalPercent(data.average_yield_pct)}
                </div>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  <span>Plan: {formatPercent(data.planned_yield_pct)}</span>
                  {data.yield_diff_pct !== null && (
                    <span
                      className={`ml-1.5 font-medium tabular-nums ${
                        Number(data.yield_diff_pct) >= 0
                          ? 'text-emerald-600 dark:text-emerald-400'
                          : 'text-rose-600 dark:text-rose-400'
                      }`}
                    >
                      ({Number(data.yield_diff_pct) >= 0 ? '+' : ''}
                      {data.yield_diff_pct}%)
                    </span>
                  )}
                </p>
              </CardContent>
            </Card>

            {/* KPI 4: Break-even progress */}
            <Card className="overflow-hidden border-slate-200 dark:border-slate-800">
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-slate-600 dark:text-slate-400">
                  Break-even progress
                </CardTitle>
                <Flame className="h-4 w-4 text-amber-500" />
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-2xl font-bold tabular-nums text-slate-900 dark:text-slate-100">
                    {data.heats_count} {data.heats_count === 1 ? 'heat' : 'heats'}
                  </span>
                  <span className="text-sm font-medium text-slate-500 dark:text-slate-400">
                    {data.break_even_heats !== null
                      ? `(${data.heats_count} of ${Math.ceil(Number(data.break_even_heats))} heats)`
                      : '(break-even: n/a)'}
                  </span>
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                  <span>To cover {formatMoneyWhole(data.expenses_total)} fixed costs</span>
                  {data.is_provisional && (
                    <Badge variant="amber" className="text-[10px] uppercase font-bold tracking-wider">
                      provisional
                    </Badge>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Row 2: Charts (Profit per heat & Yield per heat) */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <ProfitChart heats={data.heats} />
            <YieldChart heats={data.heats} plannedYieldPct={data.planned_yield_pct} />
          </div>

          {/* Row 3: Recent heats table & GST estimate & Fixed expenses */}
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            {/* Recent heats table (span 2 cols) */}
            <Card className="lg:col-span-2">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base font-semibold">
                    Heats in {data.month}
                  </CardTitle>
                  <span className="text-xs text-slate-500 dark:text-slate-400">
                    {data.heats.length} total heats
                  </span>
                </div>
                <CardDescription>
                  Production records, yields, and profit per heat.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {data.heats.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-slate-200 p-8 text-center dark:border-slate-800">
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                      No heats recorded in this month
                    </p>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                      Heats created with dates in {data.month} will appear here automatically.
                    </p>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead>
                        <tr className="border-b border-slate-200 dark:border-slate-800 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                          <th className="py-2.5 px-3">Heat No</th>
                          <th className="py-2.5 px-3">Date</th>
                          <th className="py-2.5 px-3">Alloy</th>
                          <th className="py-2.5 px-3 text-right">Output (kg)</th>
                          <th className="py-2.5 px-3 text-right">Yield</th>
                          <th className="py-2.5 px-3 text-right">Profit</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60 font-sans">
                        {data.heats.map((heat) => (
                          <tr
                            key={heat.id}
                            className="transition-colors hover:bg-slate-50/80 dark:hover:bg-slate-800/40"
                          >
                            <td className="py-2.5 px-3 font-semibold text-slate-900 dark:text-slate-100">
                              {heat.heat_no}
                            </td>
                            <td className="py-2.5 px-3 text-slate-600 dark:text-slate-300 whitespace-nowrap">
                              {heat.heat_date}
                            </td>
                            <td className="py-2.5 px-3 text-slate-600 dark:text-slate-300">
                              {heat.alloy}
                            </td>
                            <td className="py-2.5 px-3 text-right tabular-nums text-slate-900 dark:text-slate-100">
                              {formatKg(heat.output_kg)}
                            </td>
                            <td className="py-2.5 px-3 text-right tabular-nums text-slate-900 dark:text-slate-100">
                              {formatOptionalPercent(heat.yield_pct)}
                            </td>
                            <td className="py-2.5 px-3 text-right">
                              <div className="flex flex-col items-end gap-1">
                                <span
                                  className={`tabular-nums font-medium ${
                                    heat.heat_profit !== null && Number(heat.heat_profit) < 0
                                      ? 'text-rose-600 dark:text-rose-400'
                                      : 'text-slate-900 dark:text-slate-100'
                                  }`}
                                >
                                  {formatOptionalMoney(heat.heat_profit)}
                                </span>
                                {heat.is_provisional && (
                                  <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:border-amber-900/50 dark:bg-amber-950/40 dark:text-amber-300">
                                    provisional
                                  </span>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* GST Estimate & Expenses Column */}
            <div className="space-y-6">
              {/* GST Estimate Card */}
              <Card>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base font-semibold">
                      GST Estimate
                    </CardTitle>
                    <Badge variant="amber" className="text-[10px] uppercase font-bold tracking-wider">
                      estimate
                    </Badge>
                  </div>
                  <CardDescription>
                    Indicative net liability based on WITH-GST invoices.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div>
                    <div className="text-xs text-slate-500 dark:text-slate-400">
                      Estimated Net Payable
                    </div>
                    <div className="mt-0.5 text-2xl font-bold tabular-nums text-slate-900 dark:text-slate-100">
                      {formatMoney(data.gst_estimate.net_payable_estimate)}
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 rounded-lg bg-slate-50 p-3 dark:bg-slate-800/50">
                    <div>
                      <div className="text-[11px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                        Collected (Sales)
                      </div>
                      <div className="mt-1 font-semibold tabular-nums text-slate-900 dark:text-slate-100 text-sm">
                        {formatMoney(data.gst_estimate.collected)}
                      </div>
                    </div>
                    <div>
                      <div className="text-[11px] text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                        Credit (Purchases)
                      </div>
                      <div className="mt-1 font-semibold tabular-nums text-slate-900 dark:text-slate-100 text-sm">
                        {formatMoney(data.gst_estimate.credit)}
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Monthly Fixed Expenses Card */}
              <Card>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base font-semibold">
                      Fixed Expenses
                    </CardTitle>
                    <span className="text-xs font-semibold text-slate-600 dark:text-slate-300 tabular-nums">
                      Total: {formatMoney(data.expenses_total)}
                    </span>
                  </div>
                  <CardDescription>
                    Workshop overheads for {data.month}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {data.expenses.length === 0 ? (
                    <p className="text-xs text-slate-500 dark:text-slate-400 italic">
                      No fixed expenses recorded for this month.
                    </p>
                  ) : (
                    <div className="divide-y divide-slate-100 dark:divide-slate-800">
                      {data.expenses.map((expense) => (
                        <div
                          key={expense.id}
                          className="flex items-center justify-between py-2 text-sm"
                        >
                          <span className="font-medium text-slate-800 dark:text-slate-200">
                            {expense.category}
                          </span>
                          <div className="flex items-center gap-3">
                            <span className="font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                              {formatMoney(expense.amount)}
                            </span>
                            <button
                              type="button"
                              onClick={() => handleDeleteExpense(expense.id)}
                              className="text-slate-400 hover:text-rose-600 dark:hover:text-rose-400"
                              title="Delete expense"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Add expense form */}
                  <form
                    onSubmit={handleAddExpense}
                    className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-800/40"
                  >
                    <div className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                      Add Overhead Expense
                    </div>
                    {expenseError !== null && (
                      <p className="mt-1 text-xs text-rose-600 dark:text-rose-400" role="alert">
                        {expenseError}
                      </p>
                    )}
                    <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                      <input
                        type="text"
                        placeholder="Category (e.g. Rent)"
                        value={expenseCategory}
                        onChange={(e) => setExpenseCategory(e.target.value)}
                        className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 placeholder:text-slate-400 focus:border-amber-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                      />
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        placeholder="Amount (₹)"
                        value={expenseAmount}
                        onChange={(e) => setExpenseAmount(e.target.value)}
                        className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 placeholder:text-slate-400 focus:border-amber-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                      />
                    </div>
                    <div className="mt-2 flex justify-end">
                      <button
                        type="submit"
                        disabled={savingExpense}
                        className="inline-flex items-center gap-1 rounded-md bg-amber-500 px-3 py-1 text-xs font-semibold text-slate-950 transition hover:bg-amber-400 disabled:opacity-50"
                      >
                        <Plus className="h-3 w-3" />
                        {savingExpense ? 'Adding...' : 'Add Expense'}
                      </button>
                    </div>
                  </form>
                </CardContent>
              </Card>
            </div>
          </div>
        </>
      ) : null}
    </div>
  )
}
