import { afterEach, describe, expect, it } from 'vitest'
import { resolveApiProxyTarget } from './viteProxyTarget.js'

const ORIGINAL_TARGET = process.env.VITE_API_PROXY_TARGET

afterEach(() => {
  if (ORIGINAL_TARGET === undefined) {
    delete process.env.VITE_API_PROXY_TARGET
  } else {
    process.env.VITE_API_PROXY_TARGET = ORIGINAL_TARGET
  }
})

describe('vite api proxy target', () => {
  it('uses port 8080 by default', () => {
    delete process.env.VITE_API_PROXY_TARGET

    expect(resolveApiProxyTarget()).toBe('http://127.0.0.1:8080')
  })

  it('can point the dev proxy at an alternate backend port', () => {
    process.env.VITE_API_PROXY_TARGET = 'http://127.0.0.1:18080'

    expect(resolveApiProxyTarget()).toBe('http://127.0.0.1:18080')
  })
})
