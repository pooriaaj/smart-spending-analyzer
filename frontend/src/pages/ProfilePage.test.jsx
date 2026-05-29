import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LanguageProvider } from '../i18n/LanguageContext'
import api from '../services/api'
import ProfilePage from './ProfilePage'

const { mockNavigate } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
}))

vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}))

vi.mock('../services/api', () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
  handleApiAuthError: vi.fn(() => false),
}))

function renderProfilePage() {
  return render(
    <LanguageProvider>
      <ProfilePage />
    </LanguageProvider>,
  )
}

describe('ProfilePage', () => {
  let createObjectUrlMock
  let revokeObjectUrlMock
  let clickSpy

  beforeEach(() => {
    vi.clearAllMocks()
    api.get.mockResolvedValue({
      data: {
        email: 'profile@example.com',
        community_learning_enabled: true,
      },
    })
    api.put.mockImplementation((path, payload) => {
      if (path === '/users/me') {
        return Promise.resolve({ data: { email: payload.email } })
      }
      if (path === '/users/me/learning') {
        return Promise.resolve({
          data: {
            community_learning_enabled: payload.community_learning_enabled,
          },
        })
      }
      if (path === '/users/me/password') {
        return Promise.resolve({
          data: { message: 'Password changed successfully.' },
        })
      }
      return Promise.reject(new Error(`Unexpected PUT ${path}`))
    })
    api.delete.mockResolvedValue({ data: {} })
    createObjectUrlMock = vi.fn(() => 'blob:smart-spending-export')
    revokeObjectUrlMock = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: createObjectUrlMock,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: revokeObjectUrlMock,
    })
    clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {})
  })

  it('downloads the authenticated user data export after password confirmation', async () => {
    const exportPayload = {
      schema_version: 1,
      user: { email: 'profile@example.com' },
      transactions: [{ description: 'Current user bus pass' }],
      excluded: ['Password hashes are not exported.'],
    }
    api.post.mockResolvedValueOnce({ data: exportPayload })

    const user = userEvent.setup()
    renderProfilePage()

    await screen.findByDisplayValue('profile@example.com')
    await user.type(screen.getByLabelText('Password for export'), 'StrongPass1')
    await user.click(screen.getByRole('button', { name: 'Download Data' }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/users/me/export', {
        password: 'StrongPass1',
      })
    })

    expect(createObjectUrlMock).toHaveBeenCalledTimes(1)
    const blob = createObjectUrlMock.mock.calls[0][0]
    expect(blob.type).toBe('application/json')
    await expect(blob.text()).resolves.toContain('"schema_version": 1')
    expect(clickSpy).toHaveBeenCalledTimes(1)
    expect(revokeObjectUrlMock).toHaveBeenCalledWith('blob:smart-spending-export')
    expect(screen.getByText('Your data export downloaded.')).toBeInTheDocument()
    expect(screen.getByLabelText('Password for export')).toHaveValue('')
  })

  it('updates the profile email address', async () => {
    const user = userEvent.setup()
    renderProfilePage()

    const emailInput = await screen.findByDisplayValue('profile@example.com')
    await user.clear(emailInput)
    await user.type(emailInput, 'updated@example.com')
    await user.click(screen.getByRole('button', { name: 'Save Profile' }))

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith('/users/me', {
        email: 'updated@example.com',
      })
    })
    expect(screen.getByText('Profile updated successfully.')).toBeInTheDocument()
    expect(emailInput).toHaveValue('updated@example.com')
  })

  it('toggles anonymous community learning preference', async () => {
    const user = userEvent.setup()
    renderProfilePage()

    await screen.findByDisplayValue('profile@example.com')
    expect(screen.getByText('Enabled')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Turn Off Anonymous Learning' }))

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith('/users/me/learning', {
        community_learning_enabled: false,
      })
    })
    expect(screen.getByText('Learning preference updated.')).toBeInTheDocument()
    expect(screen.getByText('Disabled')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Turn On Anonymous Learning' })).toBeInTheDocument()
  })

  it('changes password and clears the password fields', async () => {
    const user = userEvent.setup()
    renderProfilePage()

    await screen.findByDisplayValue('profile@example.com')
    await user.type(screen.getByLabelText('Current Password'), 'OldPass1')
    await user.type(screen.getByLabelText('New Password'), 'NewPass2')
    await user.click(screen.getByRole('button', { name: 'Change Password' }))

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith('/users/me/password', {
        current_password: 'OldPass1',
        new_password: 'NewPass2',
      })
    })
    expect(screen.getByText('Password changed successfully.')).toBeInTheDocument()
    expect(screen.getByLabelText('Current Password')).toHaveValue('')
    expect(screen.getByLabelText('New Password')).toHaveValue('')
  })

  it('requires delete confirmation text before deleting the account', async () => {
    const user = userEvent.setup()
    renderProfilePage()

    await screen.findByDisplayValue('profile@example.com')
    await user.type(screen.getByLabelText('Confirm Password'), 'StrongPass1')
    await user.type(screen.getByLabelText('Type DELETE to confirm'), 'NOPE')
    await user.click(screen.getByRole('button', { name: 'Delete Account' }))

    expect(screen.getByText('Please type DELETE to confirm account deletion.')).toBeInTheDocument()
    expect(api.delete).not.toHaveBeenCalled()

    await user.clear(screen.getByLabelText('Type DELETE to confirm'))
    await user.type(screen.getByLabelText('Type DELETE to confirm'), 'DELETE')
    await user.click(screen.getByRole('button', { name: 'Delete Account' }))

    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith('/users/me', {
        data: {
          password: 'StrongPass1',
        },
      })
    })
    expect(mockNavigate).toHaveBeenCalledWith('/', { replace: true })
  })
})
