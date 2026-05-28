import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import PasswordField from './PasswordField'
import { LanguageProvider } from '../i18n/LanguageContext'

function renderPasswordField(props = {}) {
  return render(
    <LanguageProvider>
      <PasswordField
        label="Password"
        value="Secret123"
        onChange={vi.fn()}
        placeholder="Enter password"
        name="password"
        autoComplete="current-password"
        {...props}
      />
    </LanguageProvider>,
  )
}

describe('PasswordField', () => {
  it('toggles password visibility and announces the state', async () => {
    const user = userEvent.setup()
    renderPasswordField()

    const input = screen.getByLabelText('Password')
    const toggle = screen.getByRole('button', { name: 'Show Password' })

    expect(input).toHaveAttribute('type', 'password')
    expect(toggle).toHaveAttribute('aria-pressed', 'false')

    await user.click(toggle)

    expect(input).toHaveAttribute('type', 'text')
    expect(toggle).toHaveAccessibleName('Hide Password')
    expect(toggle).toHaveAttribute('aria-pressed', 'true')
  })

  it('passes form metadata to the underlying input', () => {
    renderPasswordField({ required: true })

    const input = screen.getByLabelText('Password')
    expect(input).toHaveAttribute('name', 'password')
    expect(input).toHaveAttribute('autocomplete', 'current-password')
    expect(input).toBeRequired()
  })
})
