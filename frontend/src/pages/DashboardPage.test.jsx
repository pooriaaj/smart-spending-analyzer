import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LanguageProvider } from '../i18n/LanguageContext'
import api from '../services/api'
import DashboardPage from './DashboardPage'

const { mockNavigate } = vi.hoisted(() => ({
  mockNavigate: vi.fn(),
}))

vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}))

vi.mock('../services/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
  handleApiAuthError: vi.fn(() => false),
}))

const accounts = [
  { id: 1, name: 'Everyday', type: 'checking' },
  { id: 2, name: 'Savings', type: 'savings' },
]

const transactions = [
  {
    id: 101,
    amount: 3200,
    category: 'salary',
    description: 'Salary deposit',
    date: '2026-05-03',
    type: 'income',
    account_id: 1,
  },
  {
    id: 102,
    amount: 84.25,
    category: 'groceries',
    description: 'Grocery store',
    date: '2026-05-04',
    type: 'expense',
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

const dashboardPayload = {
  summary: {
    total_income: 3200,
    total_expenses: 875.5,
    balance: 2324.5,
  },
  category_breakdown: [
    { category: 'groceries', total: 450.25 },
    { category: 'transport', total: 52 },
  ],
}

const budgetPayload = {
  summary: {
    total_budgeted: 1000,
    total_spent: 650,
    total_remaining: 350,
    over_budget_count: 0,
    at_risk_count: 1,
    projected_total_spent: 780,
    projected_total_remaining: 220,
    projected_over_budget_count: 0,
    projected_at_risk_count: 1,
  },
  budgets: [{ id: 1, category: 'groceries' }],
}

const simulatorPayload = {
  starting_balance: 2324.5,
  monthly_net_change: 525.25,
  projected_change_amount: 1575.75,
  projected_end_balance: 3900.25,
  months: 3,
}

function mockDashboardRequests(nextTransactions = transactions) {
  api.get.mockImplementation((path) => {
    if (path === '/accounts/') {
      return Promise.resolve({ data: accounts })
    }
    if (path === '/analytics/dashboard') {
      return Promise.resolve({ data: dashboardPayload })
    }
    if (path === '/transactions/') {
      return Promise.resolve({ data: nextTransactions })
    }
    if (path === '/budgets/') {
      return Promise.resolve({ data: budgetPayload })
    }
    if (path === '/analytics/future-simulator') {
      return Promise.resolve({ data: simulatorPayload })
    }
    return Promise.reject(new Error(`Unexpected GET ${path}`))
  })
}

function renderDashboardPage() {
  return render(
    <LanguageProvider>
      <DashboardPage />
    </LanguageProvider>,
  )
}

async function waitForDashboard() {
  expect(await screen.findByText('$3200.00')).toBeInTheDocument()
  expect(screen.getByText('$875.50')).toBeInTheDocument()
  expect(screen.getAllByText('$2324.50')).toHaveLength(2)
}

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    mockDashboardRequests()
    api.post.mockResolvedValue({ data: {} })
  })

  it('loads the dashboard summary, budget health, future outlook, and recent activity', async () => {
    renderDashboardPage()

    await waitForDashboard()

    expect(screen.getByText('Grocery store')).toBeInTheDocument()
    expect(screen.getByText('Salary deposit')).toBeInTheDocument()
    expect(screen.getByText('Groceries')).toBeInTheDocument()
    expect(screen.getByText('$450.25')).toBeInTheDocument()
    expect(screen.getByText('$1000.00')).toBeInTheDocument()
    expect(screen.getByText('$3900.25')).toBeInTheDocument()
  })

  it('filters recent transactions by type and month', async () => {
    const user = userEvent.setup()
    renderDashboardPage()

    await waitForDashboard()

    const filtersPanel = screen.getByText('Recent Transaction Filters').closest('.filter-card')
    const [typeFilter, monthFilter] = within(filtersPanel).getAllByRole('combobox')

    await user.selectOptions(typeFilter, 'income')

    expect(screen.getByText('Salary deposit')).toBeInTheDocument()
    expect(screen.queryByText('Grocery store')).not.toBeInTheDocument()
    expect(screen.queryByText('Bus pass')).not.toBeInTheDocument()

    await user.selectOptions(typeFilter, '')
    await user.selectOptions(monthFilter, '2026-04')

    expect(screen.getByText('Bus pass')).toBeInTheDocument()
    expect(screen.queryByText('Salary deposit')).not.toBeInTheDocument()
  })

  it('adds a manual transaction with the selected account and refreshes dashboard data', async () => {
    const user = userEvent.setup()
    const savedTransaction = {
      id: 104,
      amount: 42.75,
      category: 'restaurant',
      description: 'Lunch meeting',
      date: '2026-05-10',
      type: 'expense',
      account_id: 2,
    }
    api.post.mockResolvedValueOnce({ data: savedTransaction })
    renderDashboardPage()

    await waitForDashboard()

    const addPanel = screen.getByRole('heading', { name: 'Add Transaction' }).closest('.dashboard-card')
    const addForm = addPanel.querySelector('form')
    const [accountSelect, typeSelect] = within(addForm).getAllByRole('combobox')

    await user.type(within(addForm).getByPlaceholderText('Amount'), '42.75')
    await user.clear(within(addForm).getByPlaceholderText('Category'))
    await user.type(within(addForm).getByPlaceholderText('Category'), 'restaurant')
    await user.type(within(addForm).getByPlaceholderText('Description'), 'Lunch meeting')
    fireEvent.change(addForm.querySelector('input[type="date"]'), {
      target: { value: '2026-05-10' },
    })
    await user.selectOptions(accountSelect, '2')
    await user.selectOptions(typeSelect, 'expense')
    await user.click(within(addForm).getByRole('button', { name: 'Add Transaction' }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/transactions/', {
        amount: 42.75,
        category: 'restaurant',
        description: 'Lunch meeting',
        date: '2026-05-10',
        type: 'expense',
        account_id: 2,
      })
    })
    expect(await screen.findByText('Transaction added successfully.')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/analytics/dashboard', {
      params: {
        account_id: undefined,
        month: expect.any(String),
      },
    })
  })
})
