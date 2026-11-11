import { useEffect, useState } from 'react'
import {
  Flame,
  LayoutDashboard,
  LogOut,
  ShoppingCart,
  TrendingUp,
} from 'lucide-react'

import { ThemeProvider } from './context/ThemeContext'
import { ThemeToggle } from './components/ThemeToggle'
import { api, setOnUnauthorized } from './api/client'
import DashboardPage from './pages/DashboardPage'
import HeatsPage from './pages/HeatsPage'
import LoginPage from './pages/LoginPage'
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
  const [user, setUser] = useState<{ id: number; email: string } | null>(null)
  const [authChecked, setAuthChecked] = useState(false)
  const [page, setPage] = useState<Page>('dashboard')

  useEffect(() => {
    setOnUnauthorized(() => {
      setUser(null)
      setAuthChecked(true)
    })

    api.auth
      .me()
      .then((currentUser) => {
        setUser(currentUser)
      })
      .catch(() => {
        setUser(null)
      })
      .finally(() => {
        setAuthChecked(true)
      })
  }, [])

  const handleLogout = async () => {
    try {
      await api.auth.logout()
    } catch {
      // Continue to local logout even if network fails
    }
    setUser(null)
  }

  if (!authChecked) {
    return (
      <ThemeProvider>
        <div className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-500 dark:bg-slate-950 dark:text-slate-400">
          <div className="flex items-center gap-2">
            <Flame className="h-5 w-5 animate-pulse text-amber-500" />
            <span className="text-sm font-medium">Loading MetalOps Lite...</span>
          </div>
        </div>
      </ThemeProvider>
    )
  }

  if (!user) {
    return (
      <ThemeProvider>
        <LoginPage
          onLoginSuccess={(loggedInUser) => {
            setUser(loggedInUser)
            setPage('dashboard')
          }}
        />
      </ThemeProvider>
    )
  }

  return (
    <ThemeProvider>
      <div className="flex min-h-screen bg-background text-foreground">
        {/* Desktop Sidebar Navigation */}
        <aside className="hidden md:flex md:w-64 md:flex-col md:border-r md:border-border md:bg-card">
          <div className="flex h-16 items-center gap-2.5 border-b border-border px-6">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
              <Flame className="h-5 w-5" />
            </div>
            <div>
              <p className="font-bold tracking-tight text-foreground">
                MetalOps Lite
              </p>
              <p className="text-[11px] text-muted-foreground">
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
                  className={`flex w-full items-center gap-3 rounded-lg px-3.5 py-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${active
                      ? 'bg-primary text-primary-foreground font-semibold shadow-sm'
                      : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
                    }`}
                >
                  <Icon className="h-4 w-4 flex-shrink-0" />
                  <span>{label}</span>
                </button>
              )
            })}
          </nav>

          <div className="border-t border-border p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">Theme</span>
              <ThemeToggle />
            </div>
            <button
              type="button"
              onClick={handleLogout}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-xs font-medium text-destructive hover:bg-destructive/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-destructive"
              aria-label="Log out"
            >
              <LogOut className="h-4 w-4" />
              <span>Log out</span>
            </button>
            <div className="pt-1 text-center text-[11px] text-muted-foreground font-mono" data-testid="app-version">
              v{import.meta.env.VITE_APP_VERSION || 'dev'}
            </div>
          </div>
        </aside>

        {/* Main Content Area */}
        <div className="flex flex-1 flex-col min-w-0">
          {/* Top Bar on Mobile */}
          <header className="flex h-14 items-center justify-between border-b border-border bg-card px-4 md:hidden">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
                <Flame className="h-4 w-4" />
              </div>
              <div className="flex items-baseline gap-1.5">
                <span className="font-bold text-sm text-foreground">
                  MetalOps Lite
                </span>
                <span className="text-[10px] text-muted-foreground font-mono" data-testid="mobile-app-version">
                  v{import.meta.env.VITE_APP_VERSION || 'dev'}
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <ThemeToggle />
              <button
                type="button"
                onClick={handleLogout}
                className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-card text-destructive hover:bg-destructive/10 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-destructive"
                aria-label="Log out"
              >
                <LogOut className="h-4 w-4" />
                <span className="sr-only">Log out</span>
              </button>
            </div>
          </header>

          {/* Page Body */}
          <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto pb-24 md:pb-8 min-w-0">
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
          className="fixed bottom-0 left-0 right-0 z-50 flex h-16 items-center justify-around border-t border-border bg-card/95 px-2 backdrop-blur md:hidden"
          aria-label="Mobile Sections"
        >
          {NAV_ITEMS.map(({ id, label, icon: Icon }) => {
            const active = page === id
            return (
              <button
                key={id}
                type="button"
                onClick={() => setPage(id)}
                className={`flex flex-col items-center justify-center gap-1 rounded-md px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${active
                    ? 'text-primary font-bold'
                    : 'text-muted-foreground hover:text-foreground'
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
