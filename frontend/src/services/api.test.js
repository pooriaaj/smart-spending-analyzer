import { beforeEach, describe, expect, it, vi } from 'vitest'

const axiosMocks = vi.hoisted(() => {
  const api = {
    post: vi.fn(() => Promise.resolve({ data: {} })),
  }

  return {
    api,
    create: vi.fn(() => api),
  }
})

vi.mock('axios', () => ({
  default: {
    create: axiosMocks.create,
  },
}))

describe('api service', () => {
  beforeEach(() => {
    vi.resetModules()
    vi.unstubAllEnvs()
    axiosMocks.create.mockClear()
    axiosMocks.api.post.mockReset()
    axiosMocks.api.post.mockResolvedValue({ data: {} })
  })

  it('configures axios with credentials and the Vite API base URL', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://api.example.test')

    await import('./api')

    expect(axiosMocks.create).toHaveBeenCalledWith({
      baseURL: 'https://api.example.test',
      withCredentials: true,
      timeout: 30000,
    })
  })

  it('uses the first-party API proxy on deployed HTTPS frontends backed by Render', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://smart-spending-analyzer.onrender.com')

    const { resolveApiBaseURL } = await import('./api')

    const baseURL = resolveApiBaseURL('https://smart-spending-analyzer.onrender.com', {
      protocol: 'https:',
      hostname: 'www.zero2asset.com',
      origin: 'https://www.zero2asset.com',
    })

    expect(baseURL).toBe('/api')
  })

  it('keeps explicit non-Render API URLs for deployed frontends', async () => {
    const { resolveApiBaseURL } = await import('./api')

    const baseURL = resolveApiBaseURL('https://api.zero2asset.com', {
      protocol: 'https:',
      hostname: 'www.zero2asset.com',
      origin: 'https://www.zero2asset.com',
    })

    expect(baseURL).toBe('https://api.zero2asset.com')
  })

  it('falls back to the local backend URL when no Vite API base URL is set', async () => {
    await import('./api')

    expect(axiosMocks.create).toHaveBeenCalledWith({
      baseURL: 'http://localhost:8000',
      withCredentials: true,
      timeout: 30000,
    })
  })

  it('logs out and redirects when an API call returns 401', async () => {
    const { handleApiAuthError } = await import('./api')
    const navigate = vi.fn()

    const handled = handleApiAuthError({ response: { status: 401 } }, navigate)

    expect(handled).toBe(true)
    expect(axiosMocks.api.post).toHaveBeenCalledWith('/auth/logout')
    expect(navigate).toHaveBeenCalledWith('/', { replace: true })
  })

  it('leaves non-auth errors alone', async () => {
    const { handleApiAuthError } = await import('./api')
    const navigate = vi.fn()

    const handled = handleApiAuthError({ response: { status: 500 } }, navigate)

    expect(handled).toBe(false)
    expect(axiosMocks.api.post).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })
})
