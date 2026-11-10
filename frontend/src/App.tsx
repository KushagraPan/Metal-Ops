import { useState } from 'react'
import {
  Flame,
  LayoutDashboard,
  ShoppingCart,
  TrendingUp,
} from 'lucide-react'

import { ThemeProvider } from './context/ThemeContext'
import { ThemeToggle } from './components/ThemeToggle'
import DashboardPage from './pages/DashboardPage'
import HeatsPage from './pages/HeatsPage'
import PurchasesPage from './pages/PurchasesPage'
import SalesPage from './pages/SalesPage'

type Page = 'dashboard' | 'purchases' | 'heats' | 'sales'

interface NavItem {
  id: Page
  label: string
  icon: typeof LayoutDashboard
}

const NAV_ITEMS: NavItem[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'purchases', label: 'Purchases', icon: ShoppingCart },
  { id: 'heats', label: 'Heats', icon: Flame },
  { id: 'sales', label: 'Sales', icon: TrendingUp },
]

export default function App() {
  const [page, setPage] = useState<Page>('dashboard')

  return (
    <ThemeProvider>
      <div className="flex min-h-screen bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
        {/* Desktop Sidebar Navigation */}
        <aside className="hidden md:flex md:w-64 md:flex-col md:border-r md:border-slate-200 md:bg-white dark:md:border-slate-800 dark:md:bg-slate-900">
          <div className="flex h-16 items-center gap-2.5 border-b border-slate-200 px-6 dark:border-slate-800">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-amber-500 text-slate-950 shadow-sm">
              <Flame className="h-5 w-5" />
            </div>
            <div>
              <p className="font-bold tracking-tight text-slate-900 dark:text-slate-100">
                MetalOps Lite
              </p>
              <p className="text-[11px] text-slate-500 dark:text-slate-400">
                Aluminium Recycling
              </p>
            </div>
          </div>

          <nav className="flex-1 space-y-1.5 p-4" aria-label="Sections">
            {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
              const active = page === id
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setPage(id)}
                  className={`flex w-full items-center gap-3 rounded-lg px-3.5 py-2.5 text-sm font-medium transition-colors ${
                    active
                      ? 'bg-amber-500 text-slate-950 font-semibold shadow-sm'
                      : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100'
                  }`}
                >
                  <Icon className="h-4 w-4 flex-shrink-0" />
                  <span>{label}</span>
                </button>
              )
            })}
          </nav>

          <div className="border-t border-slate-200 p-4 dark:border-slate-800 flex items-center justify-between">
            <span className="text-xs text-slate-400">Theme</span>
            <ThemeToggle />
          </div>
        </aside>

        {/* Main Content Area */}
        <div className="flex flex-1 flex-col min-w-0">
          {/* Top Bar on Mobile */}
          <header className="flex h-14 items-center justify-between border-b border-slate-200 bg-white px-4 md:hidden dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-amber-500 text-slate-950">
                <Flame className="h-4 w-4" />
              </div>
              <span className="font-bold text-sm text-slate-900 dark:text-slate-100">
                MetalOps Lite
              </span>
            </div>
            <div className="flex items-center gap-2">
              <ThemeToggle />
            </div>
          </header>

          {/* Page Body */}
          <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto pb-24 md:pb-8">
            {page === 'dashboard' ? (
              <DashboardPage />
            ) : page === 'purchases' ? (
              <PurchasesPage />
            ) : page === 'heats' ? (
              <HeatsPage />
            ) : (
              <SalesPage />
            )}
          </main>
        </div>

        {/* Mobile Bottom Tab Navigation */}
        <nav
          className="fixed bottom-0 left-0 right-0 z-50 flex h-16 items-center justify-around border-t border-slate-200 bg-white/95 px-2 backdrop-blur md:hidden dark:border-slate-800 dark:bg-slate-900/95"
          aria-label="Mobile Sections"
        >
          {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
            const active = page === id
            return (
              <button
                key={id}
                type="button"
                onClick={() => setPage(id)}
                className={`flex flex-col items-center justify-center gap-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                  active
                    ? 'text-amber-600 dark:text-amber-400 font-bold'
                    : 'text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100'
                }`}
              >
                <Icon className="h-5 w-5" />
                <span>{label}</span>
              </button>
            )
          })}
        </nav>
      </div>
    </ThemeProvider>
  )
}
