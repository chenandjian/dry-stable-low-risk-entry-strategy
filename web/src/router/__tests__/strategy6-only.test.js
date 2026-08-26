import { describe, expect, it } from 'vitest'

import { routes } from '../index.js'

describe('strategy6-only frontend routes', () => {
  it('keeps only strategy6 business pages and redirects removed strategy URLs', () => {
    const businessPaths = routes.map(route => route.path)

    expect(businessPaths).toContain('/')
    expect(businessPaths).toContain('/strategy6/results')
    expect(businessPaths).toContain('/tasks')
    expect(businessPaths).toContain('/config')
    expect(businessPaths).toContain('/data/kline-history')
    expect(businessPaths).toContain('/strategy6/batch-evaluation')
    expect(businessPaths).not.toContain('/results')
    expect(businessPaths).not.toContain('/strategy1/backtest')
    expect(businessPaths).not.toContain('/strategy2/results')
    expect(businessPaths).not.toContain('/strategy2/backtest')
    expect(businessPaths).not.toContain('/strategy3/results')
    expect(businessPaths).not.toContain('/strategy4/results')
    expect(businessPaths).not.toContain('/strategy5/results')

    const legacyRedirect = routes.find(route => route.path === '/:pathMatch(.*)*')
    expect(legacyRedirect.redirect).toBe('/strategy6/results')
  })
})
