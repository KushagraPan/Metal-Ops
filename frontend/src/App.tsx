import { useState } from 'react'

import HeatsPage from './pages/HeatsPage'
import PurchasesPage from './pages/PurchasesPage'
import SalesPage from './pages/SalesPage'

type Page = 'purchases' | 'heats' | 'sales'

export default function App() {
  const [page, setPage] = useState<Page>('purchases')

  return (
    <main className="app-shell">
      <header className="app-header">
        <p className="brand">MetalOps Lite</p>
        <p className="muted">Aluminium recycling workshop</p>
        <nav className="nav" aria-label="Sections">
          <button
            type="button"
            className={page === 'purchases' ? 'active' : undefined}
            onClick={() => setPage('purchases')}
          >
            Purchases
          </button>
          <button
            type="button"
            className={page === 'heats' ? 'active' : undefined}
            onClick={() => setPage('heats')}
          >
            Heats
          </button>
          <button
            type="button"
            className={page === 'sales' ? 'active' : undefined}
            onClick={() => setPage('sales')}
          >
            Sales
          </button>
        </nav>
      </header>
      {page === 'purchases' ? (
        <PurchasesPage />
      ) : page === 'heats' ? (
        <HeatsPage />
      ) : (
        <SalesPage />
      )}
    </main>
  )
}
