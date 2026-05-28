import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LanguageProvider } from '../i18n/LanguageContext'
import api from '../services/api'
import TransactionForm from './TransactionForm'

const { mockSelectedAccountId } = vi.hoisted(() => ({
  mockSelectedAccountId: vi.fn(() => '7'),
}))

vi.mock('../services/api', () => ({
  default: {
    post: vi.fn(),
    put: vi.fn(),
  },
}))

vi.mock('../services/accountStorage', () => ({
  getSelectedAccountId: () => mockSelectedAccountId(),
}))

vi.mock('./AccountSelector', () => ({
  default: ({ value, onChange, label }) => (
    <label>
      {label}
      <select value={value || ''} onChange={(event) => onChange(event.target.value)}>
        <option value="">Choose account</option>
        <option value="7">Everyday Chequing</option>
        <option value="9">Savings</option>
      </select>
    </label>
  ),
}))

function renderTransactionForm(props = {}) {
  return render(
    <LanguageProvider>
      <TransactionForm {...props} />
    </LanguageProvider>,
  )
}

async function fillTransactionFields(user, container) {
  await user.type(screen.getByPlaceholderText('Amount'), '42.75')
  await user.type(screen.getByPlaceholderText('Category'), 'Groceries')
  await user.type(screen.getByPlaceholderText('Description'), 'Market run')
  await user.type(container.querySelector('input[type="date"]'), '2026-05-28')
}

describe('TransactionForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockSelectedAccountId.mockReturnValue('7')
    api.post.mockResolvedValue({ data: {} })
    api.put.mockResolvedValue({ data: {} })
  })

  it('creates a transaction with the selected account and entered fields', async () => {
    const user = userEvent.setup()
    const onTransactionCreated = vi.fn()
    const { container } = renderTransactionForm({ onTransactionCreated })

    await fillTransactionFields(user, container)
    await user.click(screen.getByRole('button', { name: 'Add Transaction' }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/transactions/', {
        amount: 42.75,
        category: 'Groceries',
        description: 'Market run',
        date: '2026-05-28',
        type: 'expense',
        account_id: 7,
      })
    })
    expect(onTransactionCreated).toHaveBeenCalledTimes(1)
  })

  it('suggests a category from the current description and type', async () => {
    api.post.mockResolvedValueOnce({
      data: {
        suggested_category: 'Cafe',
        confidence: 0.91,
        reason: 'Matched coffee keyword.',
        matched_keyword: 'coffee',
      },
    })

    const user = userEvent.setup()
    renderTransactionForm()

    await user.type(screen.getByPlaceholderText('Description'), 'Starbucks coffee')
    await user.click(screen.getByRole('button', { name: 'Suggest Category' }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/transactions/categorize/suggest', {
        description: 'Starbucks coffee',
        type: 'expense',
      })
    })
    expect(screen.getByPlaceholderText('Category')).toHaveValue('Cafe')
    expect(screen.getByText('Confidence: 91%')).toBeInTheDocument()
    expect(screen.getByText('Matched coffee keyword.')).toBeInTheDocument()
  })

  it('updates an existing transaction and calls the edit callbacks', async () => {
    const user = userEvent.setup()
    const onTransactionCreated = vi.fn()
    const onCancelEdit = vi.fn()
    const { container } = renderTransactionForm({
      onTransactionCreated,
      onCancelEdit,
      editingTransaction: {
        id: 55,
        amount: 21.5,
        category: 'Transport',
        description: 'Metro pass',
        date: '2026-05-01',
        type: 'expense',
        account_id: 9,
      },
    })

    await user.clear(screen.getByPlaceholderText('Amount'))
    await user.type(screen.getByPlaceholderText('Amount'), '25.00')
    await user.clear(screen.getByPlaceholderText('Category'))
    await user.type(screen.getByPlaceholderText('Category'), 'Transit')
    await user.clear(screen.getByPlaceholderText('Description'))
    await user.type(screen.getByPlaceholderText('Description'), 'Monthly metro pass')
    await user.clear(container.querySelector('input[type="date"]'))
    await user.type(container.querySelector('input[type="date"]'), '2026-05-02')

    await user.click(screen.getByRole('button', { name: 'Update Transaction' }))

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith('/transactions/55', {
        amount: 25,
        category: 'Transit',
        description: 'Monthly metro pass',
        date: '2026-05-02',
        type: 'expense',
        account_id: 9,
      })
    })
    expect(onTransactionCreated).toHaveBeenCalledTimes(1)
    expect(onCancelEdit).toHaveBeenCalledTimes(1)
  })
})
