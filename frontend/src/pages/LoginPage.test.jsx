import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LanguageProvider } from '../i18n/LanguageContext'
import api from '../services/api'
import LoginPage from './LoginPage'

const { mockNavigate } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')

  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

vi.mock('../services/api', () => ({
  default: {
    post: vi.fn(),
  },
}))

function renderLoginPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <LoginPage />
      </LanguageProvider>
    </MemoryRouter>,
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.post.mockResolvedValue({ data: {} })
  })

  it('submits URL-encoded credentials and navigates to analytics on success', async () => {
    const user = userEvent.setup()
    renderLoginPage()

    await user.type(screen.getByLabelText('Email'), 'demo@example.com')
    await user.type(screen.getByLabelText('Password'), 'StrongPass1')
    await user.click(screen.getByRole('button', { name: 'Login' }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledTimes(1)
    })

    const [path, formData, config] = api.post.mock.calls[0]
    expect(path).toBe('/auth/login')
    expect(formData).toBeInstanceOf(URLSearchParams)
    expect(formData.get('username')).toBe('demo@example.com')
    expect(formData.get('password')).toBe('StrongPass1')
    expect(config).toEqual({
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    })
    expect(mockNavigate).toHaveBeenCalledWith('/analytics', { replace: true })
  })

  it('shows the localized login error and stays on the page when login fails', async () => {
    api.post.mockRejectedValueOnce(new Error('Invalid credentials'))

    const user = userEvent.setup()
    renderLoginPage()

    await user.type(screen.getByLabelText('Email'), 'wrong@example.com')
    await user.type(screen.getByLabelText('Password'), 'WrongPass1')
    await user.click(screen.getByRole('button', { name: 'Login' }))

    expect(
      await screen.findByText('Login failed. Please check your email and password.'),
    ).toBeInTheDocument()
    expect(mockNavigate).not.toHaveBeenCalled()
  })
})
