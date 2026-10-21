import { useEffect, useState } from 'react'

import { api } from './api/client'

type Connection = 'checking' | 'connected' | 'unreachable'

export default function App() {
  const [connection, setConnection] = useState<Connection>('checking')

  useEffect(() => {
    let active = true

    api
      .health()
      .then(() => {
        if (active) setConnection('connected')
      })
      .catch(() => {
        if (active) setConnection('unreachable')
      })

    return () => {
      active = false
    }
  }, [])

  return (
    <main className="app-shell">
      <h1>MetalOps Lite</h1>
      <p>API: {connection}</p>
    </main>
  )
}
