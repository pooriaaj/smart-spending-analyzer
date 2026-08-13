import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MantineProvider } from '@mantine/core'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LanguageProvider } from '../i18n/LanguageContext'
import api from '../services/api'
import TransactionForm from './TransactionForm'

vi.mock('../services/api', () => ({
  default: { post: vi.fn(), put: vi.fn(), get: vi.fn() },
}))

function renderForm(props = {}) {
  return render(
    <MantineProvider>
      <LanguageProvider>
        <TransactionForm {...props} />
      </LanguageProvider>
    </MantineProvider>,
  )
}

// These run against the real AccountSelector. TransactionForm.test.jsx mocks it
// out, which is what let the "all" account scope reach the payload as NaN.
describe('TransactionForm account resolution', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    api.post.mockResolvedValue({ data: {} })
  })

  it('does not post a null account_id while the account list is still loading', async () => {
    api.get.mockReturnValue(new Promise(() => {}))
    const user = userEvent.setup()
    const { container } = renderForm({ onTransactionCreated: vi.fn() })

    await user.type(screen.getByPlaceholderText('Amount'), '1200')
    await user.type(screen.getByPlaceholderText('Category'), 'salary')
    await user.type(container.querySelector('input[type="date"]'), '2026-06-15')
    await user.click(screen.getByRole('button', { name: 'Add Transaction' }))

    expect(api.post).not.toHaveBeenCalled()
    expect(
      screen.getByText('Please choose the account this transaction belongs to.'),
    ).toBeInTheDocument()
  })

  it('surfaces the real server reason instead of a generic message', async () => {
    api.get.mockResolvedValue({ data: [{ id: 7, name: 'Chequing', type: 'chequing' }] })
    api.post.mockRejectedValue({
      response: {
        status: 400,
        data: { detail: 'Category must be at least 2 letters or numbers.' },
      },
    })

    const user = userEvent.setup()
    const { container } = renderForm({ onTransactionCreated: vi.fn() })
    await waitFor(() => expect(api.get).toHaveBeenCalled())

    await user.type(screen.getByPlaceholderText('Amount'), '1200')
    await user.type(screen.getByPlaceholderText('Category'), 's')
    await user.type(container.querySelector('input[type="date"]'), '2026-06-15')
    await user.click(screen.getByRole('button', { name: 'Add Transaction' }))

    await waitFor(() =>
      expect(
        screen.getByText('Category must be at least 2 letters or numbers.'),
      ).toBeInTheDocument(),
    )
  })

  it('confirms the save and leaves the global account scope alone', async () => {
    localStorage.setItem('selectedAccountId', 'all')
    api.get.mockResolvedValue({ data: [{ id: 7, name: 'Chequing', type: 'chequing' }] })

    const user = userEvent.setup()
    const { container } = renderForm({ onTransactionCreated: vi.fn() })
    await waitFor(() => expect(api.get).toHaveBeenCalled())

    await user.type(screen.getByPlaceholderText('Amount'), '1200')
    await user.type(screen.getByPlaceholderText('Category'), 'salary')
    await user.type(container.querySelector('input[type="date"]'), '2026-06-15')
    await user.selectOptions(screen.getByLabelText('Type'), 'income')
    await user.click(screen.getByRole('button', { name: 'Add Transaction' }))

    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/transactions/', {
        amount: 1200,
        category: 'salary',
        description: '',
        date: '2026-06-15',
        type: 'income',
        account_id: 7,
      }),
    )
    expect(screen.getByText('Saved: +$1200.00 income on 2026-06-15.')).toBeInTheDocument()
    expect(localStorage.getItem('selectedAccountId')).toBe('all')
  })
})
