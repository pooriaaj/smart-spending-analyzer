import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LanguageProvider } from '../i18n/LanguageContext'
import api from '../services/api'
import ForgotPasswordPage from './ForgotPasswordPage'

vi.mock('../services/api', () => ({
  default: {
    post: vi.fn(),
  },
}))

function renderForgotPasswordPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <ForgotPasswordPage />
      </LanguageProvider>
    </MemoryRouter>,
  )
}

describe('ForgotPasswordPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.post.mockResolvedValue({
      data: {
        message: 'Check your email for reset instructions.',
        reset_url: '/reset-password?token=demo-reset-token',
      },
    })
  })

  it('requests reset instructions and shows the safe reset link when provided', async () => {
    const user = userEvent.setup()
    renderForgotPasswordPage()

    await user.type(screen.getByLabelText('Email'), 'recover@example.com')
    await user.click(screen.getByRole('button', { name: 'Send Reset Link' }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/auth/forgot-password', {
        email: 'recover@example.com',
      })
    })
    expect(screen.getByText('Check your email for reset instructions.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open password reset page' })).toHaveAttribute(
      'href',
      '/reset-password?token=demo-reset-token',
    )
  })

  it('shows a friendly error when reset instructions cannot be requested', async () => {
    api.post.mockRejectedValueOnce({
      response: {
        data: {
          detail: 'Reset service unavailable.',
        },
      },
    })

    const user = userEvent.setup()
    renderForgotPasswordPage()

    await user.type(screen.getByLabelText('Email'), 'recover@example.com')
    await user.click(screen.getByRole('button', { name: 'Send Reset Link' }))

    expect(await screen.findByText('Reset service unavailable.')).toBeInTheDocument()
  })
})
