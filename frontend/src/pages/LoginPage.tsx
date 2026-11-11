import { useState } from 'react'
import { Flame } from 'lucide-react'

import { api } from '../api/client'
import { ThemeToggle } from '../components/ThemeToggle'

interface LoginPageProps {
  onLoginSuccess: (user: { id: number; email: string }) => void
}

export default function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)

    try {
      const user = await api.auth.login({ email, password })
      onLoginSuccess(user)
    } catch (err: unknown) {
      if (
        err &&
        typeof err === 'object' &&
        'message' in err &&
        typeof (err as { message: unknown }).message === 'string'
      ) {
        setError((err as { message: string }).message)
      } else {
        setError('Login failed. Please check your credentials.')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center bg-slate-50 px-4 py-12 dark:bg-slate-950 sm:px-6 lg:px-8">
      <div className="absolute top-4 right-4">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-amber-500 text-slate-950 shadow-md">
            <Flame className="h-7 w-7" />
          </div>
          <h2 className="mt-4 text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            Sign in to MetalOps Lite
          </h2>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Aluminium Recycling Workshop Management
          </p>
        </div>

        <div className="app-card border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:rounded-xl">
          <form className="space-y-4" onSubmit={handleSubmit}>
            {error && (
              <div
                role="alert"
                className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs font-medium text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/40 dark:text-rose-300"
              >
                {error}
              </div>
            )}

            <div>
              <label htmlFor="login-email" className="app-label">
                Email Address
              </label>
              <div className="relative">
                <input
                  id="login-email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="e.g. owner@metalops.local"
                  className="app-input"
                  autoComplete="email"
                  autoFocus
                />
              </div>
            </div>

            <div>
              <label htmlFor="login-password" className="app-label">
                Password
              </label>
              <div className="relative">
                <input
                  id="login-password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="app-input"
                  autoComplete="current-password"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="app-btn-primary w-full flex items-center justify-center gap-2 mt-2"
            >
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
          </form>
        </div>

        <div className="text-center">
          <p className="text-xs text-slate-400 dark:text-slate-500 font-mono" data-testid="login-app-version">
            Version: {import.meta.env.VITE_APP_VERSION || 'dev'}
          </p>
        </div>
      </div>
    </div>
  )
}
