import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LanguageProvider } from '../i18n/LanguageContext'
import api from '../services/api'
import BudgetsPage from './BudgetsPage'

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
    delete: vi.fn(),
  },
  handleApiAuthError: vi.fn(() => false),
}))

vi.mock('../components/AccountSelector', () => ({
  default: ({ value = 'all', onChange, label = 'Budget scope' }) => (
    <label>
      {label}
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="all">All Accounts</option>
        <option value="7">Everyday Chequing</option>
        <option value="9">Savings</option>
      </select>
    </label>
  ),
}))

const baseBudgets = [
  {
    id: 1,
    category: 'groceries',
    amount: 500,
    spent_amount: 450,
    remaining_amount: 50,
    usage_percent: 90,
    status: 'at_risk',
    days_elapsed: 20,
    days_remaining: 10,
    days_total: 30,
    daily_allowance: 5,
    daily_pace: 22.5,
    projected_spent_amount: 675,
    projected_remaining_amount: -175,
    projected_usage_percent: 135,
    projected_status: 'over_budget',
  },
]

let currentBudgets = []

function cloneBudgets() {
  return baseBudgets.map((budget) => ({ ...budget }))
}

function buildBudgetPayload() {
  const totalBudgeted = currentBudgets.reduce((total, budget) => total + Number(budget.amount || 0), 0)
  const totalSpent = currentBudgets.reduce((total, budget) => total + Number(budget.spent_amount || 0), 0)

  return {
    summary: {
      total_budgeted: totalBudgeted,
      total_spent: totalSpent,
      total_remaining: totalBudgeted - totalSpent,
      over_budget_count: currentBudgets.filter((budget) => budget.status === 'over_budget').length,
      at_risk_count: currentBudgets.filter((budget) => budget.status === 'at_risk').length,
      on_track_count: currentBudgets.filter((budget) => budget.status === 'on_track').length,
      projected_total_spent: totalSpent + 225,
      projected_total_remaining: totalBudgeted - totalSpent - 225,
      projected_over_budget_count: 1,
      projected_at_risk_count: 0,
    },
    budgets: currentBudgets,
    suggestions: [
      {
        category: 'transport',
        suggested_amount: 120,
        average_spent: 100,
        latest_month_spent: 140,
      },
    ],
    insights: [
      {
        category: 'restaurant',
        severity: 'action',
        recommended_amount: 200,
      },
    ],
    available_categories: ['groceries', 'transport', 'restaurant', 'utilities'],
  }
}

function mockBudgetRequests() {
  api.get.mockImplementation((path) => {
    if (path === '/budgets/') {
      return Promise.resolve({ data: buildBudgetPayload() })
    }
    return Promise.reject(new Error(`Unexpected GET ${path}`))
  })

  api.post.mockImplementation((path, payload) => {
    if (path === '/budgets/') {
      currentBudgets = [
        ...currentBudgets,
        {
          id: currentBudgets.length + 2,
          category: payload.category,
          amount: payload.amount,
          spent_amount: 0,
          remaining_amount: payload.amount,
          usage_percent: 0,
          status: 'on_track',
          days_elapsed: 0,
          days_remaining: 30,
          days_total: 30,
          daily_allowance: payload.amount / 30,
          daily_pace: 0,
          projected_spent_amount: 0,
          projected_remaining_amount: payload.amount,
          projected_usage_percent: 0,
          projected_status: 'on_track',
        },
      ]
      return Promise.resolve({ data: {} })
    }
    return Promise.reject(new Error(`Unexpected POST ${path}`))
  })

  api.delete.mockImplementation((path) => {
    const budgetId = Number(path.split('/').pop())
    currentBudgets = currentBudgets.filter((budget) => budget.id !== budgetId)
    return Promise.resolve({ data: {} })
  })
}

function renderBudgetsPage() {
  return render(
    <MemoryRouter initialEntries={['/budgets?month=2026-05']}>
      <LanguageProvider>
        <BudgetsPage />
      </LanguageProvider>
    </MemoryRouter>,
  )
}

async function waitForBudgets() {
  expect(await screen.findByText('Suggested Budgets')).toBeInTheDocument()
  expect(screen.getByText('Budget Tracking')).toBeInTheDocument()
}

describe('BudgetsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    Object.defineProperty(window, 'scrollTo', {
      configurable: true,
      value: vi.fn(),
    })
    currentBudgets = cloneBudgets()
    mockBudgetRequests()
  })

  it('loads budget summary, suggestions, moves, and existing budget cards', async () => {
    renderBudgetsPage()

    await waitForBudgets()

    expect(screen.getByText('$500.00')).toBeInTheDocument()
    expect(screen.getByText('$450.00')).toBeInTheDocument()
    expect(screen.getByText('$50.00')).toBeInTheDocument()
    expect(screen.getByText('Transport')).toBeInTheDocument()
    expect(screen.getByText('Restaurant')).toBeInTheDocument()
    expect(screen.getByText('Groceries')).toBeInTheDocument()
    expect(api.get).toHaveBeenCalledWith('/budgets/', {
      params: {
        month: '2026-05',
        account_id: undefined,
      },
    })
  })

  it('loads a suggested budget into the form and saves it', async () => {
    const user = userEvent.setup()
    renderBudgetsPage()

    await waitForBudgets()
    await user.click(screen.getByRole('button', { name: 'Load Form' }))

    expect(screen.getByLabelText('Category')).toHaveValue('Transport')
    expect(screen.getByLabelText('Budget amount')).toHaveValue(120)

    await user.click(screen.getAllByRole('button', { name: 'Save Budget' }).at(-1))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/budgets/', {
        month: '2026-05',
        category: 'Transport',
        amount: 120,
        account_id: undefined,
      })
    })
    expect(screen.getByText('Budget saved.')).toBeInTheDocument()
  })

  it('deletes a budget and refreshes the list', async () => {
    const user = userEvent.setup()
    renderBudgetsPage()

    await waitForBudgets()
    await user.click(screen.getByRole('button', { name: 'Delete' }))

    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith('/budgets/1')
    })
    expect(screen.getByText('Budget deleted.')).toBeInTheDocument()
    expect(screen.queryByText('Groceries')).not.toBeInTheDocument()
  })
})
