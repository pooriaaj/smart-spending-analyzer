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
})
