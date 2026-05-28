import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LanguageProvider } from '../i18n/LanguageContext'
import api from '../services/api'
import RegisterPage from './RegisterPage'

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

function renderRegisterPage() {
  return render(
    <MemoryRouter>
      <LanguageProvider>
        <RegisterPage />
      </LanguageProvider>
    </MemoryRouter>,
  )
}

async function fillRegistrationForm(user, matchingValue = 'StrongPass1') {
  await user.type(screen.getByLabelText('Email'), 'new-user@example.com')
  await user.type(screen.getByLabelText('Password'), matchingValue)
  await user.type(screen.getByLabelText('Confirm Password'), matchingValue)
}

describe('RegisterPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.post.mockResolvedValue({ data: {} })
  })

  it('creates an account and navigates to import after successful registration', async () => {
    const user = userEvent.setup()
    renderRegisterPage()

    await fillRegistrationForm(user)
    await user.click(screen.getByRole('button', { name: 'Create Account' }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledTimes(1)
    })
    const [path, requestBody] = api.post.mock.calls[0]
    expect(path).toBe('/auth/register')
    expect(requestBody.email).toBe('new-user@example.com')
    expect(requestBody.password).toBe('StrongPass1')
    expect(mockNavigate).toHaveBeenCalledWith('/import', { replace: true })
  })

  it('blocks registration when passwords do not match', async () => {
    const user = userEvent.setup()
    renderRegisterPage()

    await user.type(screen.getByLabelText('Email'), 'new-user@example.com')
    await user.type(screen.getByLabelText('Password'), 'StrongPass1')
    await user.type(screen.getByLabelText('Confirm Password'), 'DifferentPass1')
    await user.click(screen.getByRole('button', { name: 'Create Account' }))

    expect(await screen.findByText('Passwords do not match.')).toBeInTheDocument()
    expect(api.post).not.toHaveBeenCalled()
    expect(mockNavigate).not.toHaveBeenCalled()
  })

  it('shows the localized registration error and stays on the page when the API rejects', async () => {
    api.post.mockRejectedValueOnce(new Error('Email already exists'))

    const user = userEvent.setup()
    renderRegisterPage()

    await fillRegistrationForm(user)
    await user.click(screen.getByRole('button', { name: 'Create Account' }))

    expect(
      await screen.findByText('Registration failed. Email may already be in use.'),
    ).toBeInTheDocument()
    expect(mockNavigate).not.toHaveBeenCalled()
  })
})
