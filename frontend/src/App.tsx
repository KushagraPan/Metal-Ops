import PurchasesPage from './pages/PurchasesPage'

export default function App() {
  return (
    <main className="app-shell">
      <header className="app-header">
        <p className="brand">MetalOps Lite</p>
        <p className="muted">Aluminium recycling workshop</p>
      </header>
      <PurchasesPage />
    </main>
  )
}
