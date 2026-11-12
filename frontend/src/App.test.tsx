// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from './api/client'
import App from './App'

vi.mock('./api/client', async () => {
  let unauthHandler: (() => void) | null = null
  return {
    setOnUnauthorized: vi.fn((fn) => {
      unauthHandler = fn
    }),
    triggerUnauthorized: () => {
      if (unauthHandler) unauthHandler()
    },
    api: {
      auth: {
        me: vi.fn(),
        login: vi.fn(),
        logout: vi.fn(),
      },
      dashboard: {
        get: vi.fn().mockResolvedValue({
          month: '2026-10',
          profit: '1000.00',
          revenue: '5000.00',
          is_provisional: false,
          heats_count: 3,
          average_yield_pct: '88.50',
          planned_yield_pct: '89.00',
          yield_diff_pct: '-0.50',
          break_even_heats: '5',
          expenses_total: '500.00',
          gst_estimate: {
            collected: '300.00',
            credit: '100.00',
            net_payable_estimate: '200.00',
          },
          heats: [],
          expenses: [],
        }),
      },
    },
  }
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('App authentication integration', () => {
  it('renders login page when there is no active session', async () => {
    vi.mocked(api.auth.me).mockRejectedValueOnce(new Error('Authentication required.'))

    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /log in|sign in/i })).toBeTruthy()
    })
  })

  it('shows dashboard after login and always displays a logout button', async () => {
    vi.mocked(api.auth.me).mockRejectedValueOnce(new Error('Authentication required.'))
    vi.mocked(api.auth.login).mockResolvedValueOnce({ id: 1, email: 'owner@metalops.local' })

    render(<App />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /log in|sign in/i })).toBeTruthy()
    })

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'owner@metalops.local' },
    })
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'Secret123' },
    })
    fireEvent.click(screen.getByRole('button', { name: /log in|sign in/i }))

    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /log out/i }).length).toBeGreaterThan(0)
    })

    // Logging out calls logout endpoint and returns to login page
    vi.mocked(api.auth.logout).mockResolvedValueOnce(undefined)
    const logoutButtons = screen.getAllByRole('button', { name: /log out/i })
    expect(logoutButtons.length).toBeGreaterThan(0)
    const logoutBtn = logoutButtons[0]!
    fireEvent.click(logoutBtn)

    await waitFor(() => {
      expect(api.auth.logout).toHaveBeenCalled()
      expect(screen.getByRole('button', { name: /log in|sign in/i })).toBeTruthy()
    })
  })

  it('returns to login page when 401 occurs during use', async () => {
    vi.mocked(api.auth.me).mockResolvedValueOnce({ id: 1, email: 'owner@metalops.local' })

    render(<App />)

    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /log out/i }).length).toBeGreaterThan(0)
    })

    const clientModule = await import('./api/client')
    ;(clientModule as unknown as { triggerUnauthorized: () => void }).triggerUnauthorized()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /log in|sign in/i })).toBeTruthy()
    })
  })

  it('displays application version in both login and dashboard screens', async () => {
    vi.mocked(api.auth.me).mockRejectedValueOnce(new Error('Authentication required.'))
    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('login-app-version')).toBeTruthy()
    })
    expect(screen.getByTestId('login-app-version').textContent).toMatch(/version:/i)

    // Now log in and check dashboard version badge
    cleanup()
    vi.mocked(api.auth.me).mockResolvedValueOnce({ id: 1, email: 'owner@metalops.local' })
    render(<App />)

    await waitFor(() => {
      expect(screen.getByTestId('app-version')).toBeTruthy()
    })
    expect(screen.getByTestId('app-version').textContent).toMatch(/^v/i)
  })
})
