import { afterEach, describe, expect, it, vi } from 'vitest'

import { useApi } from '../useApi.js'

describe('useApi strategy6 audit endpoints', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('rejects non-2xx market snapshot and lifecycle responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: vi.fn().mockResolvedValue({ error: 'SERVER_ERROR' }),
    }))
    const api = useApi()

    await expect(api.getStrategy6MarketSnapshot('s6-task')).rejects.toThrow('strategy6 market snapshot failed')
    await expect(api.getStrategy6Lifecycle('s6-task')).rejects.toThrow('strategy6 lifecycle failed')
  })
})
