import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'

import { api } from '../api/client'
import type { DashboardData } from '../api/client'
import {
  formatKg,
  formatMoney,
  formatOptionalMoney,
  formatOptionalPercent,
  formatPercent,
} from '../lib/format'

interface DashboardPageProps {
  initialMonth?: string
}

function defaultMonth(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  return `${year}-${month}`
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong.'
}

export default function DashboardPage({ initialMonth }: DashboardPageProps) {
  const [month, setMonth] = useState<string>(initialMonth || defaultMonth())
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
    loadDashboard(month)
  }, [month])

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
        month,
        category,
        amount,
      })
      setExpenseCategory('')
      setExpenseAmount('')
      loadDashboard(month)
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
      loadDashboard(month)
    } catch (err: unknown) {
      setError(messageOf(err))
    }
  }

  return (
    <section className="dashboard-page">
      <header className="page-header">
        <div>
          <h2>Dashboard</h2>
          <p className="muted">Monthly overview, fixed expenses and performance</p>
        </div>
        <div className="month-picker">
          <label className="field-inline">
            <span>Month</span>
            <input
              type="month"
              aria-label="Month"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
            />
          </label>
        </div>
      </header>

      {error !== null ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="muted">Loading dashboard...</p>
      ) : data !== null ? (
        <div className="dashboard-content">
          {/* KPI cards grid */}
          <div className="detail-grid">
            <div className="kpi-card">
              <dt>Profit this month</dt>
              <dd className={Number(data.profit) >= 0 ? 'profit-pos' : 'profit-neg'}>
                {formatMoney(data.profit)}
                {data.is_provisional ? (
                  <span className="pill">provisional</span>
                ) : null}
              </dd>
            </div>

            <div className="kpi-card">
              <dt>Revenue</dt>
              <dd>{formatMoney(data.revenue)}</dd>
            </div>

            <div className="kpi-card">
              <dt>Heats</dt>
              <dd>{data.heats_count}</dd>
            </div>

            <div className="kpi-card">
              <dt>Average yield vs plan</dt>
              <dd>
                {formatOptionalPercent(data.average_yield_pct)}
                <span className="muted"> / plan {formatPercent(data.planned_yield_pct)}</span>
                {data.yield_diff_pct !== null ? (
                  <span className="muted">
                    {' '}({Number(data.yield_diff_pct) >= 0 ? '+' : ''}
                    {data.yield_diff_pct}%)
                  </span>
                ) : null}
              </dd>
            </div>

            <div className="kpi-card">
              <dt>Break-even heats</dt>
              <dd>
                {data.break_even_heats !== null ? data.break_even_heats : 'n/a'}
              </dd>
            </div>

            <div className="kpi-card">
              <dt>
                GST estimate <span className="pill">estimate</span>
              </dt>
              <dd>
                {formatMoney(data.gst_estimate.net_payable_estimate)}
                <span className="muted">
                  {' '}(Collected: {formatMoney(data.gst_estimate.collected)} · Credit:{' '}
                  {formatMoney(data.gst_estimate.credit)})
                </span>
              </dd>
            </div>
          </div>

          {/* Recent heats table */}
          <section className="card" style={{ marginTop: '1.5rem' }}>
            <h3>Heats in {data.month}</h3>
            {data.heats.length === 0 ? (
              <p className="muted">No heats recorded in this month.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Heat number</th>
                      <th>Date</th>
                      <th>Alloy</th>
                      <th className="numeric">Output kg</th>
                      <th className="numeric">Yield</th>
                      <th className="numeric">Profit</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.heats.map((heat) => (
                      <tr key={heat.id}>
                        <td>
                          <strong>{heat.heat_no}</strong>
                        </td>
                        <td>{heat.heat_date}</td>
                        <td>{heat.alloy}</td>
                        <td className="numeric">{formatKg(heat.output_kg)}</td>
                        <td className="numeric">
                          {formatOptionalPercent(heat.yield_pct)}
                        </td>
                        <td className="numeric">
                          {formatOptionalMoney(heat.heat_profit)}
                          {heat.is_provisional ? (
                            <span className="pill">provisional</span>
                          ) : null}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {/* Fixed expenses */}
          <section className="card" style={{ marginTop: '1.5rem' }}>
            <header className="detail-header">
              <div>
                <h3>Monthly fixed expenses</h3>
                <p className="muted">Total: {formatMoney(data.expenses_total)}</p>
              </div>
            </header>

            {data.expenses.length === 0 ? (
              <p className="muted">No fixed expenses recorded for this month.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Category</th>
                      <th className="numeric">Amount</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.expenses.map((expense) => (
                      <tr key={expense.id}>
                        <td>{expense.category}</td>
                        <td className="numeric">{formatMoney(expense.amount)}</td>
                        <td className="actions">
                          <button
                            type="button"
                            className="danger"
                            onClick={() => handleDeleteExpense(expense.id)}
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

            {/* Add expense form */}
            <form onSubmit={handleAddExpense} style={{ marginTop: '1rem' }}>
              <h4>Add fixed expense</h4>
              {expenseError !== null ? (
                <p className="error" role="alert">
                  {expenseError}
                </p>
              ) : null}
              <div className="form-grid">
                <label className="field">
                  <span>Category</span>
                  <input
                    type="text"
                    value={expenseCategory}
                    placeholder="e.g. Rent, Salaries"
                    onChange={(e) => setExpenseCategory(e.target.value)}
                  />
                </label>
                <label className="field">
                  <span>Amount (₹)</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={expenseAmount}
                    placeholder="0.00"
                    onChange={(e) => setExpenseAmount(e.target.value)}
                  />
                </label>
              </div>
              <div className="actions" style={{ marginTop: '0.75rem' }}>
                <button type="submit" className="primary" disabled={savingExpense}>
                  {savingExpense ? 'Adding...' : 'Add expense'}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
    </section>
  )
}

