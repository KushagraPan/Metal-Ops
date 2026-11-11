// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App'

vi.mock('./api/client', () => ({
  setOnUnauthorized: vi.fn(),
  api: {
    auth: {
      me: vi.fn().mockRejectedValue(new Error('Unauthorized')),
    },
  },
}))

afterEach(() => {
  cleanup()
  vi.unstubAllEnvs()
})

describe('Version display', () => {
  it('renders default dev version when VITE_APP_VERSION is unset', async () => {
    render(<App />)
    const el = await screen.findByTestId('login-app-version')
    expect(el.textContent).toBe('Version: dev')
  })

  it('renders custom injected version when VITE_APP_VERSION is set', async () => {
    vi.stubEnv('VITE_APP_VERSION', '1.2.3-test')
    render(<App />)
    const el = await screen.findByTestId('login-app-version')
    expect(el.textContent).toBe('Version: 1.2.3-test')
  })
})
