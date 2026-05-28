import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LanguageProvider } from '../i18n/LanguageContext'
import api from '../services/api'
import AnalyticsPage from './AnalyticsPage'

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

vi.mock('recharts', () => {
  const Container = ({ children }) => <div>{children}</div>
  const Empty = () => null

  return {
    ResponsiveContainer: Container,
    BarChart: Container,
    Bar: Empty,
    XAxis: Empty,
    YAxis: Empty,
    CartesianGrid: Empty,
    Tooltip: Empty,
    Legend: Empty,
    LineChart: Container,
    Line: Empty,
    PieChart: Container,
    Pie: Container,
    Cell: Empty,
  }
})

vi.mock('../services/api', () => ({
  default: {
    get: vi.fn(),
  },
  handleApiAuthError: vi.fn(() => false),
}))

vi.mock('../components/AccountSelector', () => ({
  default: ({ value = 'all', onChange, label = 'Account scope' }) => (
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

const dashboardPayload = {
  summary: {
    total_income: 5000,
    total_expenses: 1800,
    balance: 3200,
  },
  category_breakdown: [
    { category: 'groceries', total: 700 },
    { category: 'restaurant', total: 420 },
    { category: 'transport', total: 160 },
  ],
  monthly_summary: [
    { month: '2026-05', income: 5000, expenses: 1800 },
    { month: '2026-04', income: 4800, expenses: 1500 },
  ],
  spending_insights: {
    insights: ['Groceries are your largest flexible expense.'],
    recommendations: ['Review restaurant spending before the next budget reset.'],
  },
  overspending_alerts: {
    alerts: [
      {
        level: 'warning',
        title: 'Groceries jumped',
        message: 'Groceries are 20% above the previous month.',
      },
    ],
  },
  category_trends: {
    previous_month: '2026-04',
    current_month: '2026-05',
    summary: ['Groceries increased this month.'],
    top_increases: [
      {
        category: 'groceries',
        previous_amount: 500,
        current_amount: 700,
        change_amount: 200,
      },
    ],
    top_decreases: [
      {
        category: 'transport',
        previous_amount: 220,
        current_amount: 160,
        change_amount: -60,
      },
    ],
  },
  account_comparison: [
    {
      account_id: 1,
      name: 'Everyday',
      type: 'checking',
      total_income: 4200,
      total_expenses: 1450,
      balance: 2750,
      top_category: 'groceries',
      top_category_amount: 700,
    },
    {
      account_id: 2,
      name: 'Savings',
      type: 'savings',
      total_income: 800,
      total_expenses: 350,
      balance: 450,
      top_category: 'restaurant',
      top_category_amount: 220,
    },
  ],
}

const transactionsPayload = [
  {
    id: 1,
    amount: 70,
    category: 'groceries',
    description: 'Grocery store',
    date: '2026-05-26',
    type: 'expense',
  },
  {
    id: 2,
    amount: 120,
    category: 'restaurant',
    description: 'Dinner',
    date: '2026-05-21',
    type: 'expense',
  },
  {
    id: 3,
    amount: 5000,
    category: 'salary',
    description: 'Salary deposit',
    date: '2026-05-01',
    type: 'income',
  },
]

function mockAnalyticsRequests() {
  api.get.mockImplementation((path) => {
    if (path === '/analytics/dashboard') {
      return Promise.resolve({ data: dashboardPayload })
    }
    if (path === '/transactions/') {
      return Promise.resolve({ data: transactionsPayload })
    }
    return Promise.reject(new Error(`Unexpected GET ${path}`))
  })
}

function renderAnalyticsPage() {
  return render(
    <MemoryRouter initialEntries={['/analytics']}>
      <LanguageProvider>
        <AnalyticsPage />
      </LanguageProvider>
    </MemoryRouter>,
  )
}

async function waitForAnalytics() {
  expect(await screen.findByText('$5000.00')).toBeInTheDocument()
  expect(screen.getByText('$1800.00')).toBeInTheDocument()
  expect(screen.getByText('$3200.00')).toBeInTheDocument()
}

function getAnalyticsFilterControls() {
  const filtersPanel = screen.getByText('Analytics Filters').closest('.filter-card')
  return within(filtersPanel).getAllByRole('combobox')
}

describe('AnalyticsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    mockAnalyticsRequests()
  })

  it('loads analytics summary, trends, insights, alerts, and account comparison data', async () => {
    renderAnalyticsPage()

    await waitForAnalytics()

    expect(screen.getByText('Groceries ($700.00)')).toBeInTheDocument()
    expect(screen.getByText('Accounts at a Glance')).toBeInTheDocument()
    expect(screen.getByText('Everyday')).toBeInTheDocument()
    expect(screen.getAllByText('Savings').length).toBeGreaterThan(0)
    expect(screen.getByText('Groceries jumped')).toBeInTheDocument()
    expect(screen.getByText('Groceries increased this month.')).toBeInTheDocument()
    expect(screen.getByText('Groceries are your largest flexible expense.')).toBeInTheDocument()
    expect(screen.getByText('Review restaurant spending before the next budget reset.')).toBeInTheDocument()
  })

  it('sends account, month, type, category, and preset date filters to analytics', async () => {
    const user = userEvent.setup()
    renderAnalyticsPage()

    await waitForAnalytics()

    let [accountFilter, monthFilter, typeFilter, categoryFilter] = getAnalyticsFilterControls()

    await user.selectOptions(accountFilter, '2')
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/analytics/dashboard', {
        params: expect.objectContaining({ account_id: 2 }),
      })
    })

    ;[accountFilter, monthFilter, typeFilter, categoryFilter] = getAnalyticsFilterControls()
    await user.selectOptions(monthFilter, '2026-04')
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/analytics/dashboard', {
        params: expect.objectContaining({ month: '2026-04' }),
      })
    })

    ;[accountFilter, monthFilter, typeFilter, categoryFilter] = getAnalyticsFilterControls()
    await user.selectOptions(typeFilter, 'expense')
    ;[accountFilter, monthFilter, typeFilter, categoryFilter] = getAnalyticsFilterControls()
    await user.selectOptions(categoryFilter, 'Groceries')
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/analytics/dashboard', {
        params: expect.objectContaining({
          transaction_type: 'expense',
          category: 'Groceries',
        }),
      })
    })

    await user.click(screen.getByRole('button', { name: 'Last 30 Days' }))
    await waitFor(() => {
      expect(api.get).toHaveBeenCalledWith('/analytics/dashboard', {
        params: expect.objectContaining({
          start_date: expect.any(String),
          end_date: expect.any(String),
        }),
      })
    })
  })

  it('navigates to transaction drilldown when a category is selected', async () => {
    const user = userEvent.setup()
    renderAnalyticsPage()

    await waitForAnalytics()

    await user.click(screen.getAllByRole('button', { name: /Groceries/ })[0])

    expect(mockNavigate).toHaveBeenCalledWith('/transactions?category=Groceries')
  })
})
