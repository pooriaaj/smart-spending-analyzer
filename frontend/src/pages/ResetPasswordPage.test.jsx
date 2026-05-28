import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { LanguageProvider } from '../i18n/LanguageContext'
import api from '../services/api'
import ResetPasswordPage from './ResetPasswordPage'

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

function renderResetPasswordPage(initialPath = '/reset-password?token=demo-reset-token') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <LanguageProvider>
        <ResetPasswordPage />
      </LanguageProvider>
    </MemoryRouter>,
  )
}

async function fillResetForm(user, matchingValue = 'NewStrongPass1') {
  await user.type(screen.getByLabelText('New Password'), matchingValue)
  await user.type(screen.getByLabelText('Confirm New Password'), matchingValue)
}

describe('ResetPasswordPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.post.mockResolvedValue({
      data: {
        message: 'Password reset successfully.',
      },
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('submits the token and new password before redirecting to login', async () => {
    const user = userEvent.setup()
    const replaceStateSpy = vi.spyOn(window.history, 'replaceState')
    const originalSetTimeout = window.setTimeout
    const setTimeoutSpy = vi.spyOn(window, 'setTimeout').mockImplementation((callback, delay, ...args) => {
      if (delay === 1500 && typeof callback === 'function') {
        callback()
        return 0
      }

      return originalSetTimeout(callback, delay, ...args)
    })
    renderResetPasswordPage()

    await fillResetForm(user)
    await user.click(screen.getByRole('button', { name: 'Reset Password' }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledTimes(1)
    })
    const [path, requestBody] = api.post.mock.calls[0]
    expect(path).toBe('/auth/reset-password')
    expect(requestBody.token).toBe('demo-reset-token')
    expect(requestBody.new_password).toBe('NewStrongPass1')
    expect(screen.getByText('Password reset successfully.')).toBeInTheDocument()
    expect(replaceStateSpy).toHaveBeenCalledWith(null, '', '/reset-password')
    expect(setTimeoutSpy).toHaveBeenCalledWith(expect.any(Function), 1500)
    expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
  })

  it('blocks reset when the token is missing', async () => {
    const user = userEvent.setup()
    renderResetPasswordPage('/reset-password')

    await fillResetForm(user)
    await user.click(screen.getByRole('button', { name: 'Reset Password' }))

    expect(await screen.findByText('Missing reset token.')).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('blocks reset when passwords do not match', async () => {
    const user = userEvent.setup()
    renderResetPasswordPage()

    await user.type(screen.getByLabelText('New Password'), 'NewStrongPass1')
    await user.type(screen.getByLabelText('Confirm New Password'), 'DifferentPass1')
    await user.click(screen.getByRole('button', { name: 'Reset Password' }))

    expect(await screen.findByText('Passwords do not match.')).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
    expect(mockNavigate).not.toHaveBeenCalled()
  })
})
