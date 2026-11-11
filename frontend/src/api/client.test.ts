import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, apiUrl, setOnUnauthorized } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api client', () => {
  it('calls the health endpoint and returns its body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.health()).resolves.toEqual({ status: 'ok' })

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0]?.[0]).toBe(apiUrl('/api/health'))
  })

  it('adds heat filters to the query string', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('[]', {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await api.heats.list({
      from_date: '2026-01-01',
      to_date: '2026-12-31',
      alloy: 'ADC12',
      report_result: 'PASS',
      heat_no: ' H-1 ',
    })

    const url = new URL(
      String(fetchMock.mock.calls[0]?.[0]),
      'http://localhost',
    )
    expect(url.pathname).toBe('/api/heats')
    expect(url.searchParams.get('from_date')).toBe('2026-01-01')
    expect(url.searchParams.get('to_date')).toBe('2026-12-31')
    expect(url.searchParams.get('alloy')).toBe('ADC12')
    expect(url.searchParams.get('report_result')).toBe('PASS')
    expect(url.searchParams.get('heat_no')).toBe('H-1')
  })

  it('triggers setOnUnauthorized callback when receiving a 401 response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: 'Authentication required.' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const onUnauthorized = vi.fn()
    setOnUnauthorized(onUnauthorized)

    await expect(api.auth.me()).rejects.toThrow('Authentication required.')
    expect(onUnauthorized).toHaveBeenCalledOnce()

    setOnUnauthorized(null)
  })
})
