import { afterEach, describe, expect, it, vi } from 'vitest'

import { api, apiUrl } from './client'

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
})
