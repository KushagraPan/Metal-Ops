// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '../api/client'
import { ThemeProvider } from '../context/ThemeContext'
import LoginPage from './LoginPage'

function renderLoginPage(onLoginSuccess = vi.fn()) {
  return render(
    <ThemeProvider>
      <LoginPage onLoginSuccess={onLoginSuccess} />
    </ThemeProvider>,
  )
}

vi.mock('../api/client', () => ({
  api: {
    auth: {
      login: vi.fn(),
    },
  },
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('LoginPage', () => {
  it('renders login form fields and submit button', () => {
    renderLoginPage()

    expect(screen.getByLabelText(/email/i)).toBeTruthy()
    expect(screen.getByLabelText(/password/i)).toBeTruthy()
    expect(screen.getByRole('button', { name: /log in|sign in/i })).toBeTruthy()
  })

  it('submits credentials and calls onLoginSuccess on valid response', async () => {
    const onLoginSuccess = vi.fn()
    vi.mocked(api.auth.login).mockResolvedValueOnce({ id: 1, email: 'owner@metalops.local' })

    renderLoginPage(onLoginSuccess)

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'owner@metalops.local' },
    })
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'Secret123' },
    })
    fireEvent.click(screen.getByRole('button', { name: /log in|sign in/i }))

    await waitFor(() => {
      expect(api.auth.login).toHaveBeenCalledWith({
        email: 'owner@metalops.local',
        password: 'Secret123',
      })
      expect(onLoginSuccess).toHaveBeenCalledWith({
        id: 1,
        email: 'owner@metalops.local',
      })
    })
  })

  it('displays error message when login fails', async () => {
    vi.mocked(api.auth.login).mockRejectedValueOnce(new Error('Invalid email or password.'))

    renderLoginPage()

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'wrong@metalops.local' },
    })
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'BadPass' },
    })
    fireEvent.click(screen.getByRole('button', { name: /log in|sign in/i }))

    await waitFor(() => {
      expect(screen.getByText(/invalid email or password/i)).toBeTruthy()
    })
  })
})
