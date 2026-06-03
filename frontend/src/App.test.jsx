import { render, screen, waitFor } from '@testing-library/react'
import { MantineProvider } from '@mantine/core'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'
import api from './services/api'

vi.mock('./services/api', () => ({
  default: {
    get: vi.fn(),
  },
}))

vi.mock('./pages/LoginPage', () => ({
  default: () => <div>Login route</div>,
}))

vi.mock('./pages/RegisterPage', () => ({
  default: () => <div>Register route</div>,
}))

vi.mock('./pages/TransactionsPage', () => ({
  default: () => <div>Transactions route</div>,
}))

vi.mock('./pages/AnalyticsPage', () => ({
  default: () => <div>Analytics route</div>,
}))

vi.mock('./pages/AssistantPage', () => ({
  default: () => <div>Assistant route</div>,
}))

vi.mock('./pages/ProfilePage', () => ({
  default: () => <div>Profile route</div>,
}))

vi.mock('./pages/ForgotPasswordPage', () => ({
  default: () => <div>Forgot password route</div>,
}))

vi.mock('./pages/ResetPasswordPage', () => ({
  default: () => <div>Reset password route</div>,
}))

vi.mock('./pages/ImportPage', () => ({
  default: () => <div>Import route</div>,
}))

vi.mock('./pages/BudgetsPage', () => ({
  default: () => <div>Budgets route</div>,
}))

function renderAt(path) {
  window.history.pushState({}, '', path)
  return render(
    <MantineProvider>
      <App />
    </MantineProvider>,
  )
}

describe('App auth routing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    window.history.pushState({}, '', '/')
  })

  it('redirects unauthenticated protected-route visitors to login', async () => {
    api.get.mockRejectedValue(new Error('Not authenticated'))

    renderAt('/analytics')

    expect(await screen.findByText('Login route')).toBeInTheDocument()
    await waitFor(() => {
      expect(window.location.pathname).toBe('/')
    })
    expect(api.get).toHaveBeenCalledWith('/users/me')
  })

  it('sends authenticated visitors from the public home route to analytics', async () => {
    api.get.mockResolvedValue({ data: { email: 'user@example.com' } })

    renderAt('/')

    expect(await screen.findByText('Analytics route')).toBeInTheDocument()
    await waitFor(() => {
      expect(window.location.pathname).toBe('/analytics')
    })
    expect(api.get).toHaveBeenCalledWith('/users/me')
  })

  it('allows authenticated visitors to open protected pages', async () => {
    api.get.mockResolvedValue({ data: { email: 'user@example.com' } })

    renderAt('/transactions')

    expect(await screen.findByText('Transactions route')).toBeInTheDocument()
    expect(window.location.pathname).toBe('/transactions')
    expect(api.get).toHaveBeenCalledWith('/users/me')
  })
})
