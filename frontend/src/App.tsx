import { useState } from 'react'

import HeatsPage from './pages/HeatsPage'
import PurchasesPage from './pages/PurchasesPage'

type Page = 'purchases' | 'heats'

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
        </nav>
      </header>
      {page === 'purchases' ? <PurchasesPage /> : <HeatsPage />}
    </main>
  )
}
