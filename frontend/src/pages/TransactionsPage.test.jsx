import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MantineProvider } from '@mantine/core'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LanguageProvider } from '../i18n/LanguageContext'
import api from '../services/api'
import TransactionsPage from './TransactionsPage'

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
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
  handleApiAuthError: vi.fn(() => false),
}))

vi.mock('../components/AccountSelector', () => ({
  default: ({ value = 'all', onChange, label = 'Account' }) => (
    <label>
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="all">All Accounts</option>
        <option value="1">Everyday Chequing</option>
        <option value="2">Savings</option>
      </select>
    </label>
  ),
}))

vi.mock('../components/TransactionForm', () => ({
  default: ({ onTransactionCreated }) => (
    <button type="button" onClick={onTransactionCreated}>
      Mock Add Transaction
    </button>
  ),
}))

const baseTransactions = [
  {
    id: 101,
    amount: 84.25,
    category: 'groceries',
    description: 'Grocery store',
    date: '2026-05-04',
    type: 'expense',
    account_id: 1,
  },
  {
    id: 102,
    amount: 3200,
    category: 'salary',
    description: 'Salary deposit',
    date: '2026-05-03',
    type: 'income',
    account_id: 1,
  },
  {
    id: 103,
    amount: 52,
    category: 'transport',
    description: 'Bus pass',
    date: '2026-04-15',
    type: 'expense',
    account_id: 2,
  },
]

let currentTransactions = []

function cloneTransactions(items) {
  return items.map((item) => ({ ...item }))
}

function filterTransactions(params = {}) {
  return currentTransactions.filter((transaction) => {
    if (params.account_id && Number(params.account_id) !== transaction.account_id) return false
    if (params.type && transaction.type !== params.type) return false
    if (params.month && !transaction.date.startsWith(params.month)) return false
    if (params.category && transaction.category !== params.category) return false
    if (
      params.description &&
      !transaction.description.toLowerCase().includes(String(params.description).toLowerCase())
    ) {
      return false
    }
    if (params.amount_min_exclusive && transaction.amount <= Number(params.amount_min)) return false
    if (!params.amount_min_exclusive && params.amount_min !== undefined && transaction.amount < Number(params.amount_min)) {
      return false
    }
    if (params.amount_max !== undefined && params.amount_max !== null && transaction.amount > Number(params.amount_max)) {
      return false
    }
    return true
  })
}

function buildPagePayload(params = {}) {
  const items = filterTransactions(params)
  const scopedTransactions = params.account_id
    ? currentTransactions.filter((item) => item.account_id === Number(params.account_id))
    : currentTransactions

  return {
    items,
    total: items.length,
    scope_total: scopedTransactions.length,
    page: Number(params.page || 1),
    page_size: Number(params.page_size || 12),
    total_pages: 1,
    available_months: ['2026-05', '2026-04'],
    available_categories: ['groceries', 'salary', 'transport', 'restaurant'],
  }
}

function mockTransactionRequests() {
  api.get.mockImplementation((path, config = {}) => {
    if (path === '/transactions/page') {
      return Promise.resolve({ data: buildPagePayload(config.params || {}) })
    }
    if (path === '/transactions/amount-repairs/preview') {
      return Promise.resolve({ data: { candidates: [] } })
    }
    if (path === '/transactions/categorize/learning-summary') {
      return Promise.resolve({
        data: {
          confidence_level: 'medium',
          confidence_score: 0.68,
          transaction_count: currentTransactions.length,
          uncategorized_count: 0,
          learning_candidate_count: 0,
          merchant_profile_count: 0,
          personal_memory_count: 0,
          learning_event_count: 0,
          community_learning_enabled: false,
          community_pattern_count: 0,
          recent_learning_events: [],
        },
      })
    }
    return Promise.reject(new Error(`Unexpected GET ${path}`))
  })

  api.put.mockImplementation((path, payload) => {
    const transactionId = Number(path.split('/').pop())
    currentTransactions = currentTransactions.map((transaction) =>
      transaction.id === transactionId ? { ...transaction, ...payload } : transaction,
    )
    return Promise.resolve({ data: currentTransactions.find((item) => item.id === transactionId) })
  })

  api.delete.mockImplementation((path) => {
    const transactionId = Number(path.split('/').pop())
    currentTransactions = currentTransactions.filter((transaction) => transaction.id !== transactionId)
    return Promise.resolve({ data: {} })
  })
}

function renderTransactionsPage() {
  return render(
    <MemoryRouter initialEntries={['/transactions']}>
      <MantineProvider>
        <LanguageProvider>
          <TransactionsPage />
        </LanguageProvider>
      </MantineProvider>
    </MemoryRouter>,
  )
}

async function waitForLedger() {
  const table = await screen.findByRole('table')
  expect(within(table).getByText('Grocery store')).toBeInTheDocument()
  expect(within(table).getByText('Salary deposit')).toBeInTheDocument()
  expect(within(table).getByText('Bus pass')).toBeInTheDocument()
  return table
}

describe('TransactionsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    currentTransactions = cloneTransactions(baseTransactions)
    mockTransactionRequests()
  })

  it('loads the ledger and sends filter changes to the paged transaction endpoint', async () => {
    const user = userEvent.setup()
    renderTransactionsPage()

    await waitForLedger()

    const filtersPanel = screen.getByText('Transaction Filters').closest('.filter-card')
    const [typeFilter, monthFilter] = within(filtersPanel).getAllByRole('combobox')

    await user.selectOptions(typeFilter, 'income')

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/transactions/page', {
        params: expect.objectContaining({ type: 'income' }),
      })
    })
    let table = screen.getByRole('table')
    expect(within(table).getByText('Salary deposit')).toBeInTheDocument()
    expect(within(table).queryByText('Grocery store')).not.toBeInTheDocument()

    await user.selectOptions(typeFilter, '')
    await user.selectOptions(monthFilter, '2026-04')

    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/transactions/page', {
        params: expect.objectContaining({ month: '2026-04' }),
      })
    })
    table = screen.getByRole('table')
    expect(within(table).getByText('Bus pass')).toBeInTheDocument()
    expect(within(table).queryByText('Salary deposit')).not.toBeInTheDocument()
  })

  it('edits a transaction from the table and refreshes the ledger', async () => {
    const user = userEvent.setup()
    renderTransactionsPage()

    await waitForLedger()

    const table = screen.getByRole('table')
    const groceryRow = within(table).getByText('Grocery store').closest('tr')
    await user.click(within(groceryRow).getByRole('button', { name: 'Edit' }))

    const amountInput = within(groceryRow).getByDisplayValue('84.25')
    const categoryInput = within(groceryRow).getByDisplayValue('groceries')
    const descriptionInput = within(groceryRow).getByDisplayValue('Grocery store')
    const dateInput = within(groceryRow).getByDisplayValue('2026-05-04')

    await user.clear(amountInput)
    await user.type(amountInput, '42.75')
    await user.clear(categoryInput)
    await user.type(categoryInput, 'restaurant')
    await user.clear(descriptionInput)
    await user.type(descriptionInput, 'Lunch meeting')
    fireEvent.change(dateInput, {
      target: { value: '2026-05-10' },
    })
    await user.click(within(groceryRow).getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(api.put).toHaveBeenCalledWith('/transactions/101', {
        amount: 42.75,
        category: 'restaurant',
        description: 'Lunch meeting',
        date: '2026-05-10',
        type: 'expense',
        account_id: 1,
      })
    })
    await waitFor(() => {
      expect(within(screen.getByRole('table')).getByText('Lunch meeting')).toBeInTheDocument()
    })
    expect(within(screen.getByRole('table')).queryByText('Grocery store')).not.toBeInTheDocument()
  })

  it('deletes a transaction from the table and refreshes the ledger', async () => {
    const user = userEvent.setup()
    renderTransactionsPage()

    await waitForLedger()

    const table = screen.getByRole('table')
    const busRow = within(table).getByText('Bus pass').closest('tr')
    await user.click(within(busRow).getByRole('button', { name: 'Delete' }))

    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith('/transactions/103')
    })
    await waitFor(() => {
      expect(within(screen.getByRole('table')).queryByText('Bus pass')).not.toBeInTheDocument()
    })
    expect(within(screen.getByRole('table')).getByText('Grocery store')).toBeInTheDocument()
  })
})
